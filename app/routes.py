"""Google traffic-aware pricing and independent OSRM map previews."""
from __future__ import annotations
import hashlib
import json
import math
import os
import threading
import time
import datetime as dt
from decimal import Decimal
import re
from urllib.request import Request, urlopen
from .domain import location, distance_miles, require, Problem, ZONE, date_value, integer, now
from .pricing import MODEL, cents, summary


class Routes:
    def __init__(self,store,url=None):
        self.store=store
        self.url=(os.getenv('ROUTER_URL','https://router.project-osrm.org/route/v1/driving') if url is None else url).rstrip('/')
        self.lock=threading.Lock();self.last_request=0
        self.google_key=os.getenv('GOOGLE_MAPS_API_KEY','').strip()
        self.google_url='https://routes.googleapis.com/directions/v2:computeRoutes'
        self.google_cache={}
        self.google_lock=threading.Lock()

    def route(self,origin,destination):
        origin,destination=location(origin),location(destination)
        coordinates=[[origin['lon'],origin['lat']],[destination['lon'],destination['lat']]]
        key=hashlib.sha256(json.dumps([self.url,coordinates],sort_keys=True).encode()).hexdigest()
        with self.store.read() as db:
            row=db.execute('SELECT result FROM route_cache WHERE cache_key=? AND expires>?',(key,time.time())).fetchone()
        if row: return json.loads(row[0])
        result=dict(coordinates=coordinates,distance_miles=round(distance_miles(origin,destination)*1.25,2),duration_minutes=None,is_road_route=False,source='approximation',notice='Approximate connection between area centers. Road routing is unavailable; distance uses straight-line distance × 1.25.')
        # Cache failures briefly; serialize provider calls and never hold a SQLite write transaction over HTTP.
        with self.lock:
            with self.store.read() as db:
                row=db.execute('SELECT result FROM route_cache WHERE cache_key=? AND expires>?',(key,time.time())).fetchone()
            if row: return json.loads(row[0])
            if self.url:
                delay=max(0,1-(time.monotonic()-self.last_request))
                if delay: time.sleep(delay)
                self.last_request=time.monotonic()
                try:
                    path='/'+(';'.join(f'{lon:.6f},{lat:.6f}' for lon,lat in coordinates))+'?overview=simplified&geometries=geojson&steps=false'
                    with urlopen(Request(self.url+path,headers={'User-Agent':'CampusLoop/2.2.0 route-preview','Accept':'application/json'}),timeout=5) as response:
                        raw=json.loads(response.read(2_000_000))
                    r=raw['routes'][0];points=r['geometry']['coordinates']
                    require(raw.get('code')=='Ok' and 2<=len(points)<=20000,'Route unavailable.')
                    require(all(isinstance(p,list) and len(p)>=2 and all(type(x) in (int,float) and math.isfinite(x) for x in p[:2]) and -180<=p[0]<=180 and -90<=p[1]<=90 for p in points),'Invalid route geometry.')
                    require(type(r['distance']) in (int,float) and math.isfinite(r['distance']) and 0<=r['distance']<=10_000_000,'Invalid route distance.')
                    require(type(r['duration']) in (int,float) and math.isfinite(r['duration']) and r['duration']>=0,'Invalid route duration.')
                    result=dict(coordinates=[p[:2] for p in points],distance_miles=round(r['distance']/1609.344,2),duration_minutes=round(r['duration']/60),is_road_route=True,source='OSRM',notice='Road route between posted area centers. Estimated travel time excludes live traffic; exact meeting points can differ.')
                except Exception:
                    # External provider failure must never prevent posting or booking a ride.
                    pass
            with self.store.tx() as db:
                db.execute('INSERT OR REPLACE INTO route_cache(cache_key,result,expires) VALUES(?,?,?)',(key,json.dumps(result),time.time()+(86400 if result['is_road_route'] else 60)))
        return result

    def google_metrics(self, origin, destination, departure):
        require(bool(self.google_key),'Automatic pricing is unavailable. Configure GOOGLE_MAPS_API_KEY on the server or choose a manual price.',503)
        origin,destination=location(origin),location(destination)
        def waypoint(point):
            return {'location':{'latLng':{'latitude':point['lat'],'longitude':point['lon']}}}
        payload=dict(origin=waypoint(origin),destination=waypoint(destination),travelMode='DRIVE',
                     routingPreference='TRAFFIC_AWARE',departureTime=departure,
                     computeAlternativeRoutes=False)
        key=json.dumps(payload,sort_keys=True)
        # Brief memory-only reuse for form edits; do not reuse the 24h map cache for traffic.
        with self.google_lock:
            cached=self.google_cache.get(key)
            if cached and cached[0]>time.time(): return cached[1]
            try:
                request=Request(self.google_url,data=json.dumps(payload).encode(),method='POST',headers={
                    'Content-Type':'application/json','X-Goog-Api-Key':self.google_key,
                    'X-Goog-FieldMask':'routes.distanceMeters,routes.duration'})
                with urlopen(request,timeout=8) as response:
                    route=json.loads(response.read(1_000_000))['routes'][0]
                distance=route['distanceMeters'];duration=route['duration']
                require(type(distance) in (int,float) and math.isfinite(distance) and distance>=0,'Invalid Google distance.')
                require(isinstance(duration,str) and re.fullmatch(r'\d+(?:\.\d{1,9})?s',duration) is not None,'Invalid Google duration.')
                result=dict(distance_meters=str(distance),duration_seconds=duration[:-1])
            except Exception:
                # Never return provider bodies or credentials to the browser.
                raise Problem(503,'Google Maps route data is unavailable. Retry or choose a manual price.') from None
            self.google_cache={k:v for k,v in self.google_cache.items() if v[0]>time.time()}
            self.google_cache[key]=(time.time()+60,result)
            return result

    def quote(self,origin,destination,kind,*,seats=1,start_date=None,departure_hour=None,return_hour=None,weekdays=None):
        require(kind in ('regular','one','round'),'Invalid trip type.')
        integer({'seats':seats},'seats',1,4)
        day=date_value(start_date)
        hour=integer({'hour':departure_hour},'hour',0,22)
        if kind=='regular':
            require(isinstance(weekdays,list) and weekdays and all(type(d) is int and 0<=d<=6 for d in weekdays),'Choose recurring weekdays.')
            day+=dt.timedelta(days=next(i for i in range(7) if (day+dt.timedelta(days=i)).weekday() in weekdays))
        departure=dt.datetime.combine(day,dt.time(hour),ZONE)
        require(departure>now(),'Departure must be in the future.')
        def stamp(value): return value.astimezone(dt.timezone.utc).isoformat().replace('+00:00','Z')
        legs=[self.google_metrics(origin,destination,stamp(departure))]
        if kind=='round':
            back=integer({'hour':return_hour},'hour',hour+1,23)
            legs.append(self.google_metrics(destination,origin,stamp(dt.datetime.combine(day,dt.time(back),ZONE))))
        miles=sum(Decimal(r['distance_meters']) for r in legs)/Decimal('1609.344')
        minutes=sum(Decimal(r['duration_seconds']) for r in legs)/60
        base=miles*60+minutes*30
        result=dict(model=MODEL,mode='automatic',currency='USD',price_cents=cents(base),
                    base_amount_cents=str(base),distance_miles=round(float(miles),2),duration_minutes=round(float(minutes),2),
                    source='Google Maps',traffic_aware=True,is_road_route=True,legs=len(legs),route_legs=legs,
                    quoted_at=now().isoformat(),departure_time=stamp(departure),cents_per_mile=60,cents_per_minute=30,
                    rider_multiplier=0.65,service_fee_cents=0,
                    formula='$0.60 × miles + $0.30 × minutes; earnings = base × [1 + 0.65 × (riders − 1)]; price = earnings ÷ riders.',
                    notice='Google Maps traffic-aware estimate at posting time. Current prices change with confirmed rider count. No service fee or payment collection.')
        result['pricing']=summary(result,seats)
        return result
