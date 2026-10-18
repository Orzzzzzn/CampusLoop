"""OSRM road geometry with a clearly labelled offline approximation and cached quotes."""
from __future__ import annotations
import hashlib
import json
import math
import os
import threading
import time
from urllib.request import Request, urlopen
from .domain import location, distance_miles, require


class Routes:
    def __init__(self,store,url=None):
        self.store=store
        self.url=(os.getenv('ROUTER_URL','https://router.project-osrm.org/route/v1/driving') if url is None else url).rstrip('/')
        self.lock=threading.Lock();self.last_request=0

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

    def quote(self,origin,destination,kind):
        require(kind in ('regular','one','round'),'Invalid trip type.')
        route=self.route(origin,destination)
        base=100; mileage=round(route['distance_miles']*35)
        one_way=min(3000,max(200,int(math.floor((base+mileage+12.5)/25)*25)))
        multiplier=2 if kind=='round' else 1
        return dict(price_cents=one_way*multiplier,mode='automatic',currency='USD',per='passenger per booked date; both legs included for round trips',distance_miles=route['distance_miles'],is_road_route=route['is_road_route'],base_cents=base,cents_per_mile=35,minimum_cents=200,maximum_one_way_cents=3000,rounding_cents=25,legs=multiplier,formula='$1 + $0.35 per route mile; nearest $0.25; $2–$30 per leg. Round trips double the one-way amount.',notice=route['notice'])
