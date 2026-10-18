"""Ordinary unbooked ride offers, with real asynchronous Google quote loading."""
import datetime as dt
import json
import os
import threading
from .domain import (Store, PLACES, ZONE, hash_password, now, today, trip_create,
                     Problem)

KEY='live-rides:v2'
PREVIOUS_KEY='live-rides:v1'
# Labels describe travel plans, not precomputed booking scenarios.
ROUTES=[
 ('class',0,4,'regular',13,2,'Weekly class commute. Meet at the station entrance.'),
 ('campus',5,4,'regular',13,2,'Weekly campus commute. Two passenger seats available.'),
 ('library',1,6,'one',9,2,'Heading to the library. Meet by the station entrance.'),
 ('village',0,5,'one',11,2,'Sharing a trip to USC Village.'),
 ('pasadena',2,5,'one',14,1,'Traveling from Pasadena to campus. One passenger seat.'),
 ('westside',3,6,'one',10,2,'Traveling from Santa Monica to campus. Parties stay together.'),
 ('weekly',2,4,'regular',13,2,'Weekly trip from Pasadena to campus.'),
 ('round',5,3,'round',8,2,'Santa Monica day trip. Return departure at 17:00.'),
 ('station',1,5,'one',16,1,'Afternoon trip from the station to campus.'),
 ('rider',6,0,'one',15,2,'Looking for a driver for two passengers.'),
]


def future_tuesday(hour):
    day=today()+dt.timedelta(days=(1-today().weekday())%7)
    if dt.datetime.combine(day,dt.time(hour),ZONE)<=now():day+=dt.timedelta(days=7)
    return day


def accounts_config(db):
    row=db.execute('SELECT value FROM app_settings WHERE key=?',(KEY,)).fetchone()
    if row:return {key:value['email'] for key,value in json.loads(row['value'])['accounts'].items()}
    # Read-only compatibility for explicitly seeded regression fixtures.
    old=db.execute("SELECT value FROM app_settings WHERE key='walkthrough:waitlists:v1'").fetchone()
    if old:return {key:value['email'] for key,value in json.loads(old['value'])['accounts'].items()}
    return {}


def prepare(store):
    """Add real offers once, with no applications, confirmations, or fixed prices."""
    with store.tx() as db:
        saved=db.execute('SELECT value FROM app_settings WHERE key=?',(KEY,)).fetchone()
        if saved:return json.loads(saved['value'])
        accounts={};old_ids=[];known={}
        previous=db.execute('SELECT value FROM app_settings WHERE key=?',(PREVIOUS_KEY,)).fetchone()
        if previous:
            previous=json.loads(previous['value'])
            known.update({key:value['id'] for key,value in previous['accounts'].items()})
            old_ids.extend(previous['routes'].values())
        # The earlier HTTP runner did not save a server marker. Retire only its
        # exact generated post signature owned by the recorded testing account.
        if known.get('kate'):
            for trip in db.execute("SELECT * FROM trips WHERE owner_id=? AND kind='regular' AND departure_hour=13 AND seats=2 AND note=?",
                (known['kate'],'Tuesday class commute. Meet at the station entrance; two passenger seats.')):
                a,b=json.loads(trip['origin']),json.loads(trip['destination'])
                if (a['lat'],a['lon'],b['lat'],b['lon'])==(PLACES[0]['lat'],PLACES[0]['lon'],PLACES[4]['lat'],PLACES[4]['lon']):old_ids.append(trip['id'])
        row=db.execute("SELECT value FROM app_settings WHERE key='walkthrough:tuesday-class:v1'").fetchone()
        if row:
            old=json.loads(row['value']);old_ids.append(old['trip_id'])
            known.update({key:old[key+'_id'] for key in ('kate','yelyn')})
        row=db.execute("SELECT value FROM app_settings WHERE key='walkthrough:waitlists:v1'").fetchone()
        if row:
            old=json.loads(row['value']);known.update({key:value['id'] for key,value in old['accounts'].items()})
            old_ids.extend(case['trip_id'] for case in old['scenarios'])
        password=hash_password(os.getenv('DEMO_PASSWORD','heky-local-2026'))
        for name,vehicle in [('Kate','Honda Civic · Blue'),('Yelyn',''),('Hannah',''),('Emily',''),('Noah','Toyota Prius · Silver')]:
            key=name.lower();existing=db.execute('SELECT id,email FROM users WHERE id=?',(known.get(key,-1),)).fetchone()
            if existing:accounts[key]=dict(existing);continue
            email=key+'@usc.edu';number=1
            while db.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone():
                email=key+'.demo'+(str(number) if number>1 else '')+'@usc.edu';number+=1
            uid=db.execute('INSERT INTO users(name,email,password_hash,verified,vehicle) VALUES(?,?,?,1,?)',(name,email,password,vehicle)).lastrowid
            accounts[key]=dict(id=uid,email=email)
        # Keep every legacy application, agreed amount and password. Retire only the
        # generated setup offers from default views; never touch manually posted trips.
        for tid in old_ids:
            trip=db.execute('SELECT owner_id,price_meta FROM trips WHERE id=?',(tid,)).fetchone()
            if trip and trip['owner_id'] in {a['id'] for a in accounts.values()}:
                meta=json.loads(trip['price_meta'] or '{}');meta['retired_setup']=True
                db.execute('UPDATE trips SET price_meta=? WHERE id=?',(json.dumps(meta),tid))
        routes={}
        for key,a,b,kind,hour,seats,note in ROUTES:
            start=future_tuesday(hour)
            origin={**{k:v for k,v in PLACES[a].items() if k!='id'},'mode':'area','radius_miles':.5}
            dest={**{k:v for k,v in PLACES[b].items() if k!='id'},'mode':'exact','radius_miles':0}
            owner=dict(db.execute('SELECT * FROM users WHERE id=?',(accounts['yelyn' if key=='rider' else 'kate']['id'],)).fetchone())
            # A changed existing driver profile must not be overwritten on upgrade.
            if kind and owner['vehicle'].strip()=='' and key!='rider':continue
            tid=trip_create(db,owner,dict(role='rider' if key=='rider' else 'driver',kind=kind,
                origin=origin,destination=dest,start_date=str(start),end_date=str(start+dt.timedelta(days=21)),
                weekdays=[1],departure_hour=hour,arrive_by=hour+1,seats=seats,price_cents=0,
                detour_minutes=10,return_hour=17,note=note,
                _price_meta={'mode':'automatic','status':'pending','demo_generated':True,'notice':'Waiting for a Google Maps route quote.'}))
            routes[key]=tid
        result=dict(accounts=accounts,routes=routes,retired_trip_ids=old_ids)
        db.execute('INSERT INTO app_settings(key,value) VALUES(?,?)',(KEY,json.dumps(result)))
        return result


class GooglePrices:
    """Price every upcoming occurrence, including existing user posts and exceptions."""
    def __init__(self,store,routes):
        self.store=store;self.routes=routes;self.lock=threading.Lock();self.running=False;self.thread=None;self.rescan=False

    def upcoming(self,db):
        from .domain import joined_occurrence
        result=[]
        for row in db.execute("SELECT id FROM occurrences WHERE status='active' AND trip_date>=? ORDER BY trip_date,id",(str(today()),)).fetchall():
            ride=joined_occurrence(db,row['id'])
            if json.loads(ride['price_meta']).get('retired_setup'):continue
            if dt.datetime.combine(dt.date.fromisoformat(ride['trip_date']),dt.time(ride['departure_hour']),ZONE)>now():result.append(ride)
        return result

    def prepare(self):
        # Only future occurrence overrides change. Historical dates and the
        # original trip/application amounts are retained in the database.
        with self.store.tx() as db:
            for ride in self.upcoming(db):
                meta=json.loads(ride['price_meta'])
                departure=dt.datetime.combine(dt.date.fromisoformat(ride['trip_date']),dt.time(ride['departure_hour']),ZONE)
                stamp=departure.astimezone(dt.timezone.utc).isoformat().replace('+00:00','Z')
                if meta.get('model')=='google_shared_v1' and meta.get('departure_time')==stamp:continue
                if meta.get('mode')=='automatic' and meta.get('model')!='google_shared_v1':continue
                override=json.loads(ride['overrides'])
                override['price_meta']=dict(mode='automatic',status='pending',notice='Waiting for a Google Maps route quote.')
                override['price_cents']=0
                db.execute('UPDATE occurrences SET overrides=? WHERE id=?',(json.dumps(override),ride['id']))

    def pending(self):
        with self.store.read() as db:
            return [r for r in self.upcoming(db) if json.loads(r['price_meta']).get('model')!='google_shared_v1']

    def status(self):
        with self.store.read() as db:rides=self.upcoming(db)
        pending=[r for r in rides if json.loads(r['price_meta']).get('model')!='google_shared_v1']
        return dict(configured=bool(self.routes.google_key),running=self.running,pending=len(pending),
                    total=len(rides),ready=len(rides)-len(pending),
                    failed=sum(json.loads(t['price_meta']).get('status')=='error' for t in pending))

    def start(self):
        self.prepare()
        if not self.routes.google_key or not self.pending():return False
        with self.lock:
            if self.running:
                self.rescan=True;return False
            self.running=True;self.rescan=False
            self.thread=threading.Thread(target=self.run,daemon=True,name='google-route-prices');self.thread.start()
        return True

    def run(self):
        try:
            for ride in self.pending():
                try:
                    quote=self.routes.quote(json.loads(ride['origin']),json.loads(ride['destination']),ride['kind'],
                        seats=ride['capacity'],start_date=ride['trip_date'],departure_hour=ride['departure_hour'],
                        return_hour=ride['return_hour'],weekdays=[dt.date.fromisoformat(ride['trip_date']).weekday()])
                except Exception:
                    quote=dict(mode='automatic',status='error',
                        notice='Google Maps price unavailable. Check the server key, Routes API access and billing, then retry.')
                with self.store.tx() as db:
                    from .domain import joined_occurrence
                    current=joined_occurrence(db,ride['id'])
                    # A cancellation or schedule edit during HTTP must not receive a stale quote.
                    if current['status']!='active' or any(current[k]!=ride[k] for k in ('departure_hour','origin','destination','return_hour')):continue
                    if json.loads(current['price_meta']).get('model')=='google_shared_v1':continue
                    if json.loads(current['price_meta']).get('retired_setup'):continue
                    override=json.loads(current['overrides']);override['price_meta']=quote
                    override['price_cents']=quote.get('price_cents',0)
                    db.execute('UPDATE occurrences SET overrides=? WHERE id=?',(json.dumps(override),ride['id']))
                    if quote.get('model')=='google_shared_v1':
                        from .domain import promote
                        promote(db,joined_occurrence(db,ride['id']))
        finally:
            with self.lock:
                self.running=False;again=self.rescan;self.rescan=False
            if again:self.start()
