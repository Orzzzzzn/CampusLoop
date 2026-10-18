"""Release 2.2 behavior checks over real HTTP and SQLite, without external services."""
import datetime as dt
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import test_app as base
from app.domain import Store, PLACES, now, today
from app.routes import Routes
from app.features import recommend

class FeatureTests(unittest.TestCase):
    setUp=base.AppTests.setUp
    tearDown=base.AppTests.tearDown
    search=base.AppTests.search
    create=base.AppTests.create
    apply=base.AppTests.apply
    status=base.AppTests.status

    def mine(self,who='jamie',**criteria):
        code,data=self.clients[who].call('/api/my-rides/search',criteria)
        self.assertEqual(code,200,data);return data['rides']

    def test_legacy_columns_migrate_without_resetting_bookings(self):
        with self.store.tx() as db:
            before=[tuple(r) for r in db.execute('SELECT id,status,party_size,occurrence_id FROM applications ORDER BY id')]
            passwords=[tuple(r) for r in db.execute('SELECT id,password_hash FROM users ORDER BY id')]
            for table,column in [('users','is_demo_fixture'),('trips','price_meta'),('occurrences','overrides'),('applications','agreed_price_cents')]:
                db.execute('ALTER TABLE '+table+' DROP COLUMN '+column)
        Store(self.store.path)
        with self.store.read() as db:
            self.assertEqual(before,[tuple(r) for r in db.execute('SELECT id,status,party_size,occurrence_id FROM applications ORDER BY id')])
            self.assertEqual(passwords,[tuple(r) for r in db.execute('SELECT id,password_hash FROM users ORDER BY id')])
            self.assertEqual(db.execute('SELECT count(*) FROM applications WHERE agreed_price_cents IS NULL').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT agreed_price_cents FROM applications LIMIT 1').fetchone()[0],400)

    def test_my_rides_date_time_roles_and_actual_driver(self):
        ride=self.create();aid=self.apply('jamie',ride)
        self.assertFalse(any(r['id']==ride['id'] for r in self.mine()))
        self.clients['mina'].call(f'/api/applications/{aid}/accept',{})
        match=next(r for r in self.mine(date=self.date,departure_from=8,departure_to=8) if r['id']==ride['id'])
        self.assertEqual(match['my_role'],'rider');self.assertEqual(match['driver']['name'],'Mina Park')
        self.assertEqual(match['driver']['vehicle'],'Toyota Prius · Silver');self.assertTrue(match['driver']['identity_revealed'])
        self.assertFalse(any(r['id']==ride['id'] for r in self.mine(departure_from=10)))
        self.assertEqual(self.mine(date='2000-01-01'),[])
        self.assertEqual(next(r for r in self.mine('mina',date=self.date) if r['id']==ride['id'])['my_role'],'driver')
        # Open rider posts appear under Still pending until a driver is accepted.
        wanted=self.create(owner='daniel',role='rider')
        pending=next(r for r in self.mine('daniel',date=self.date) if r['id']==wanted['id'])
        self.assertEqual(pending['my_role'],'pending');self.assertEqual(pending['pending_offers'],0)
        offer=self.apply('mina',wanted)
        pending=next(r for r in self.mine('daniel',date=self.date) if r['id']==wanted['id'])
        self.assertEqual(pending['my_role'],'pending');self.assertEqual(pending['pending_offers'],1)
        self.clients['daniel'].call(f'/api/applications/{offer}/accept',{})
        r=next(r for r in self.mine('daniel',date=self.date) if r['id']==wanted['id'])
        self.assertEqual(r['my_role'],'rider');self.assertEqual(r['driver']['name'],'Mina Park')
        self.assertEqual(next(r for r in self.mine('mina') if r['id']==wanted['id'])['my_role'],'driver')

    def test_per_date_exception_filters_and_booking_terms(self):
        r=self.create(kind='regular');owner=self.clients['mina']
        before=[x for x in self.mine('mina') if x['trip_id']==r['trip_id']]
        code,data=owner.call(f"/api/occurrences/{r['id']}/edit-date",dict(departure_hour=10,arrive_by=11,note='Late start this date only'))
        self.assertEqual(code,200,data)
        changed=next(x for x in self.search(departure_from=10) if x['id']==r['id'])
        self.assertTrue(changed['has_exception']);self.assertEqual(changed['note'],'Late start this date only')
        self.assertFalse(any(x['id']==r['id'] for x in self.search(departure_to=8)))
        others=[x for x in self.mine('mina') if x['trip_id']==r['trip_id'] and x['id']!=r['id']]
        self.assertTrue(others);self.assertTrue(all(x['departure_hour']==8 for x in others))
        aid=self.apply('jamie',changed)
        self.assertEqual(owner.call(f"/api/occurrences/{r['id']}/edit-date",dict(departure_hour=12,arrive_by=13))[0],409)
        self.assertEqual(self.clients['leo'].call(f"/api/occurrences/{r['id']}/edit-date",dict(departure_hour=12,arrive_by=13))[0],403)
        self.assertEqual(next(a for a in self.clients['jamie'].call('/api/applications')[1]['applications'] if a['id']==aid)['departure_hour'],10)

    def test_skip_week_only_affects_selected_owner_week(self):
        r=self.create(kind='regular',end_date=str(dt.date.fromisoformat(self.date)+dt.timedelta(days=20)))
        dates=[x for x in self.mine('mina') if x['trip_id']==r['trip_id']]
        day=dt.date.fromisoformat(r['trip_date']);end=day+dt.timedelta(days=6-day.weekday())
        code,result=self.clients['mina'].call(f"/api/occurrences/{r['id']}/skip-week",{})
        self.assertEqual(code,200,result)
        remaining=[x for x in self.mine('mina') if x['trip_id']==r['trip_id']]
        self.assertTrue(remaining);self.assertTrue(all(x['trip_date']>str(end) for x in remaining))
        self.assertEqual(len(dates)-len(remaining),len(result['skipped_occurrence_ids']))

    def test_passenger_skip_week_promotes_only_their_bookings(self):
        rides=self.search();booked=next(x for x in rides if x['owner_name']=='Sofia Lee')
        code,result=self.clients['jamie'].call(f"/api/occurrences/{booked['id']}/skip-week",{})
        self.assertEqual(code,200,result);self.assertTrue(result['skipped_occurrence_ids'])
        with self.store.read() as db:
            for oid in result['skipped_occurrence_ids']:
                status=db.execute("SELECT a.status,u.email FROM applications a JOIN users u ON u.id=a.requester_id WHERE a.occurrence_id=?",(oid,)).fetchall()
                self.assertEqual(next(r['status'] for r in status if r['email']=='jamie@usc.edu'),'canceled')
                self.assertEqual(next(r['status'] for r in status if r['email']=='leo@usc.edu'),'confirmed')
                self.assertEqual(next(r['status'] for r in status if r['email']=='ethan@usc.edu'),'confirmed')
            self.assertTrue(db.execute("SELECT 1 FROM applications a JOIN users u ON u.id=a.requester_id WHERE u.email='jamie@usc.edu' AND a.status='confirmed'").fetchone())

    def test_price_snapshot_survives_post_changes(self):
        r=self.create(price_cents=625);aid=self.apply('jamie',r,party=1)
        with self.store.tx() as db: db.execute('UPDATE trips SET price_cents=999 WHERE id=?',(r['trip_id'],))
        self.clients['mina'].call(f'/api/applications/{aid}/accept',{})
        application=next(a for a in self.clients['jamie'].call('/api/applications')[1]['applications'] if a['id']==aid)
        self.assertEqual(application['agreed_price_cents'],625);self.assertEqual(application['total_price_cents'],625)
        self.assertEqual(next(r for r in self.mine() if r['id']==application['occurrence_id'])['agreed_price_cents'],625)

    def test_demo_lab_four_waitlists_and_repeatable_existing_database(self):
        c=self.clients['jamie'];original={r['id'] for r in self.search()}
        code,result=c.call('/api/demo/scenarios',{});self.assertEqual(code,201,result)
        cases={r['title'][0]:r for r in result['scenarios']};self.assertEqual(len(cases),6)
        def mine(case):return next(m for m in case['members'] if m['is_you'])
        def getcase(key):return next(s for s in c.call('/api/demo/scenarios')[1]['scenarios'] if s['id']==cases[key]['id'])
        c.call(f"/api/applications/{mine(cases['1'])['id']}/cancel",{})
        self.assertTrue(any(m['status']=='confirmed' and not m['is_you'] for m in getcase('1')['members']))
        def release(key,size):
            case=getcase(key);m=next(m for m in case['members'] if m['can_release'] and m['party_size']==size)
            status,data=c.call(f"/api/demo/scenarios/{case['id']}/release",dict(application_id=m['id']));self.assertEqual(status,200,data)
        release('2',1);self.assertEqual(mine(getcase('2'))['status'],'waitlisted')
        c.call(f"/api/applications/{mine(cases['2'])['id']}/claim",{});self.assertEqual(mine(getcase('2'))['status'],'confirmed')
        release('3',1);self.assertEqual(mine(getcase('3'))['status'],'waitlisted')
        self.assertTrue(any(m['status']=='confirmed' and m['party_size']==1 and m['name']!='You' for m in getcase('3')['members']))
        release('3',2);self.assertEqual(mine(getcase('3'))['status'],'confirmed')
        release('4',1);self.assertEqual(mine(getcase('4'))['status'],'pending')
        self.assertTrue(any(m['status']=='confirmed' and not m['is_you'] for m in getcase('4')['members']))
        code,new=c.call('/api/demo/scenarios',{});self.assertEqual(code,201,new);self.assertEqual(len(new['scenarios']),12)
        self.assertTrue(original.issubset({r['id'] for r in self.search()}))
        # Existing credentials and source trips still work; another student cannot release these fixtures.
        self.assertEqual(self.clients['leo'].call(f"/api/demo/scenarios/{cases['2']['id']}/release",dict(application_id=mine(cases['2'])['id']))[0],403)
        self.app.demo_mode=False;self.assertEqual(c.call('/api/demo/scenarios',{})[0],404)

    def test_ratings_require_completed_partners_and_update_without_extra_vote(self):
        r=self.create();aid=self.apply('jamie',r);self.clients['mina'].call(f'/api/applications/{aid}/accept',{})
        driver=self.clients['mina'].call('/api/me')[1]['user']['id']
        self.assertEqual(self.clients['jamie'].call(f"/api/occurrences/{r['id']}/rating",dict(subject_id=driver,stars=5))[0],403)
        with self.store.tx() as db:db.execute('UPDATE occurrences SET trip_date=? WHERE id=?',(str(today()-dt.timedelta(days=1)),r['id']))
        target=next(x for x in self.mine(scope='past') if x['id']==r['id'])
        self.assertEqual(target['rating_targets'][0]['name'],'Mina Park')
        for stars in (5,3):
            code,result=self.clients['jamie'].call(f"/api/occurrences/{r['id']}/rating",dict(subject_id=driver,stars=stars))
            self.assertEqual(code,200,result);self.assertEqual(result['rating']['count'],1);self.assertEqual(result['rating']['average'],stars)
        self.assertEqual(self.clients['leo'].call(f"/api/occurrences/{r['id']}/rating",dict(subject_id=driver,stars=5))[0],403)
        self.assertEqual(self.clients['jamie'].call(f"/api/occurrences/{r['id']}/rating",dict(subject_id=driver,stars=6))[0],422)
        public=next(x for x in self.search('leo',date=str(today()-dt.timedelta(days=1))) if x['id']==r['id'])
        self.assertFalse(public['identity_revealed']);self.assertEqual(public['owner_rating'],dict(count=1,average=3,role='driver'))
        self.assertFalse(any(x['id']==r['id'] for x in self.mine(scope='upcoming')))

    def test_recommendations_explain_and_rank_cost_and_route(self):
        expensive=self.create(price_cents=1500);cheap=self.create(price_cents=200)
        results=self.search(sort='recommended')
        ids=[r['id'] for r in results];self.assertLess(ids.index(cheap['id']),ids.index(expensive['id']))
        self.assertIn('Route 40',results[0]['recommendation']['explanation'])
        self.assertTrue(results[0]['recommendation']['reasons'])
        self.assertTrue(all(0<=r['recommendation']['score']<=100 for r in results))
        self.assertEqual(self.clients['jamie'].call('/api/rides/search',dict(sort='bogus'))[0],422)

class RouteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'db.sqlite3');self.calls=[]
        calls=self.calls
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                payload=json.dumps(dict(routes=[dict(distanceMeters=16093.44,duration='1200s')])).encode()
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200);self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
            def do_GET(self):
                calls.append((self.path,self.headers.get('User-Agent')))
                payload=json.dumps(dict(code='Ok',routes=[dict(distance=16093.44,duration=1200,geometry=dict(coordinates=[[-118.2904,34.0621],[-118.30,34.04],[-118.2915,34.0203]]))])).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
            def log_message(self,*args):pass
        self.http=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.thread=threading.Thread(target=self.http.serve_forever,kwargs=dict(poll_interval=.01),daemon=True);self.thread.start()
        self.router=Routes(self.store,'http://127.0.0.1:'+str(self.http.server_port)+'/route/v1/driving')
        self.router.google_key='test-only';self.router.google_url='http://127.0.0.1:'+str(self.http.server_port)+'/google'
        self.a={**PLACES[0], 'mode':'exact','radius_miles':0};self.b={**PLACES[4], 'mode':'exact','radius_miles':0}
    def tearDown(self):self.http.shutdown();self.http.server_close();self.thread.join(2);self.temp.cleanup()
    def test_road_geometry_http_cache_and_round_trip_price(self):
        options=dict(seats=2,start_date=str(today()+dt.timedelta(days=2)),departure_hour=8,return_hour=17)
        q=self.router.quote(self.a,self.b,'one',**options);self.assertEqual(q['price_cents'],1200);self.assertTrue(q['is_road_route'])
        self.assertEqual(self.router.quote(self.a,self.b,'round',**options)['price_cents'],2400)
        result=self.router.route(self.a,self.b);self.assertEqual(len(result['coordinates']),3)
        self.assertEqual(result['distance_miles'],10);self.assertEqual(result['duration_minutes'],20)
        self.assertEqual(len(self.calls),1);self.assertIn('geometries=geojson',self.calls[0][0]);self.assertIn('CampusLoop',self.calls[0][1])
    def test_distinct_visible_routes_are_queued_instead_of_discarded(self):
        self.assertTrue(self.router.route(self.a,self.b)['is_road_route'])
        other={**self.a,'lon':self.a['lon']+.01}
        self.assertTrue(self.router.route(other,self.b)['is_road_route'])
        self.assertEqual(len(self.calls),2)
    def test_offline_map_fallback_does_not_generate_a_price(self):
        router=Routes(self.store,'');router.google_key=''
        result=router.route(self.a,self.b)
        self.assertFalse(result['is_road_route']);self.assertIsNone(result['duration_minutes'])
        self.assertIn('straight-line',result['notice'])
        with self.assertRaisesRegex(Exception,'GOOGLE_MAPS_API_KEY'):
            router.quote(self.a,self.b,'one',seats=1,start_date=str(today()+dt.timedelta(days=2)),departure_hour=8)
    def test_automatic_pricing_is_computed_by_server(self):
        from app.domain import seed
        seed(self.store)  # Explicit legacy regression fixtures; not production startup data.
        app=base.App(self.store,demo_mode=True,seed_data=False);app.routes=self.router
        with self.store.read() as db:user=dict(db.execute("SELECT * FROM users WHERE email='mina@usc.edu'").fetchone())
        body,headers=app.new_session(user);auth={'Cookie':headers['Set-Cookie'].split(';')[0],'X-CSRF-Token':body['csrf']}
        data=dict(role='driver',kind='one',origin=self.a,destination=self.b,departure_hour=8,arrive_by=9,start_date=str(today()+dt.timedelta(days=2)),seats=2,price_cents=1,price_mode='automatic',detour_minutes=10,note='Computed by server')
        result,status,_=app.dispatch('POST','/api/trips',data,auth);self.assertEqual(status,201)
        with self.store.read() as db:
            trip=db.execute('SELECT * FROM trips WHERE id=?',(result['trip_id'],)).fetchone()
            self.assertEqual(trip['price_cents'],1200);self.assertEqual(json.loads(trip['price_meta'])['mode'],'automatic')
