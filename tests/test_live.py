"""Live app flows against SQLite and an explicit Google HTTP fixture."""
import concurrent.futures
import datetime as dt
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from app.domain import Store, list_trips
from app.demo import seed_walkthrough,seed_scenarios
from app.live import KEY, GooglePrices, prepare
from app.routes import Routes
from app.server import App,Server
from test_app import Client

class LiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.calls=[];self.error=False;self.durations={}
        owner=self
        class Google(BaseHTTPRequestHandler):
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.calls.append(dict(body=body,headers=dict(self.headers)))
                data=json.dumps({'error':'provider-secret'} if owner.error else dict(routes=[dict(distanceMeters=16093.44,duration=owner.durations.get(body['departureTime'],'1200s'))])).encode()
                self.send_response(403 if owner.error else 200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            def log_message(self,*args):pass
        self.google=ThreadingHTTPServer(('127.0.0.1',0),Google);self.gt=threading.Thread(target=self.google.serve_forever,kwargs={'poll_interval':.01},daemon=True);self.gt.start()
        self.store=Store(self.root/'db.sqlite');self.app=App(self.store,demo_mode=True,routes=self.router(self.store))
        self.app.google_prices.thread.join(5);self.assertFalse(self.app.google_prices.running)
        self.http=Server(('127.0.0.1',0),self.app);self.thread=threading.Thread(target=self.http.serve_forever,kwargs={'poll_interval':.01},daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.http.server_port);self.clients={}
        config=Client(self.base).call('/api/config')[1]
        for name,email in config['accounts'].items():
            c=Client(self.base);code,result=c.call('/api/auth/login',dict(email=email,password='heky-local-2026'));self.assertEqual(code,200,result);c.csrf=result['csrf'];self.clients[name]=c
        with self.store.read() as db:self.catalog=json.loads(db.execute('SELECT value FROM app_settings WHERE key=?',(KEY,)).fetchone()[0])
    def router(self,store,key=True):
        r=Routes(store,'');r.google_key='local-fixture-key' if key else '';r.google_url=f'http://127.0.0.1:{self.google.server_port}/computeRoutes';return r
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join(2)
        self.google.shutdown();self.google.server_close();self.gt.join(2);self.temp.cleanup()
    def class_rides(self):
        code,result=self.clients['yelyn'].call('/api/rides/search',dict(trip_id=self.catalog['routes']['class']))
        self.assertEqual(code,200,result);return sorted(result['rides'],key=lambda r:r['trip_date'])
    def request(self,who,ride):
        data=dict(scope='date',party_size=1,auto_confirm=True,meeting_origin={**ride['origin'],'mode':'exact','radius_miles':0},meeting_destination={**ride['destination'],'mode':'exact','radius_miles':0})
        code,result=self.clients[who].call(f"/api/occurrences/{ride['id']}/request",data);self.assertEqual(code,201,result);return result['application_id']
    def accept(self,aid):
        code,q=self.clients['kate'].call(f'/api/applications/{aid}/price',{});self.assertEqual(code,200,q)
        code,result=self.clients['kate'].call(f'/api/applications/{aid}/accept',dict(expected_rider_count=q['pricing']['rider_count']));self.assertEqual(code,200,result);return result
    def test_prepared_offers_are_google_priced_and_start_without_bookings(self):
        with self.store.read() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM applications').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM trips').fetchone()[0],10)
        rides=self.class_rides();self.assertEqual(len(rides),4)
        for ride in rides:
            self.assertEqual(ride['price_meta']['model'],'google_shared_v1');self.assertEqual(ride['price_cents'],1200)
            self.assertEqual(ride['pricing']['source'],'Google Maps');self.assertEqual(ride['pricing']['duration_minutes'],20)
            self.assertEqual(ride['pricing']['price_min_cents'],990);self.assertEqual(ride['pricing']['price_max_cents'],1200)
            self.assertEqual(ride['confirmed_seats'],0);self.assertFalse(ride['identity_revealed'])
            self.assertNotIn('Walkthrough',ride['note'])
        payload=json.dumps(Client(self.base).call('/api/config')[1]);self.assertNotIn('local-fixture-key',payload)
        self.assertTrue(all(c['body']['routingPreference']=='TRAFFIC_AWARE' for c in self.calls))
    def test_real_requests_change_prices_and_week_cancellation_promotes_one_booking(self):
        first,second,*_=self.class_rides();ids={}
        for ride in [first,second]:
            for who in ['yelyn','hannah','emily']:
                aid=self.request(who,ride);ids[(ride['id'],who)]=aid;result=self.accept(aid)
                self.assertEqual(result['status'],'waitlisted' if who=='emily' else 'confirmed')
                self.assertEqual(result['pricing']['rider_price_cents'],1200 if who=='yelyn' else 990)
        code,result=self.clients['yelyn'].call(f"/api/occurrences/{first['id']}/skip-week",{});self.assertEqual(code,200,result)
        apps=self.clients['emily'].call('/api/applications')[1]['applications']
        self.assertEqual(next(a for a in apps if a['id']==ids[(first['id'],'emily')])['status'],'confirmed')
        self.assertEqual(next(a for a in apps if a['id']==ids[(second['id'],'emily')])['status'],'waitlisted')
        ride=next(r for r in self.clients['emily'].call('/api/my-rides/search',dict(date=first['trip_date']))[1]['rides'] if r['id']==first['id'])
        self.assertEqual(ride['driver']['name'],'Kate');self.assertEqual(ride['agreed_price_cents'],990)
        self.assertEqual(ride['pricing']['driver_earnings_cents'],1980)
    def test_missing_key_blocks_booking_without_fixed_or_zero_price_fallback(self):
        store=Store(self.root/'missing.sqlite');app=App(store,demo_mode=True,routes=self.router(store,key=False))
        with store.read() as db:
            user=dict(db.execute("SELECT * FROM users WHERE email='yelyn@usc.edu'").fetchone());ride=list_trips(db,user['id'])[0]
        body,headers=app.new_session(user);auth={'Cookie':headers['Set-Cookie'].split(';')[0],'X-CSRF-Token':body['csrf']}
        self.assertFalse(ride['pricing_status']['ready']);self.assertIsNone(ride['pricing'])
        data=dict(auto_confirm=True,party_size=1,meeting_origin={**ride['origin'],'mode':'exact','radius_miles':0},meeting_destination={**ride['destination'],'mode':'exact','radius_miles':0})
        from app.domain import Problem
        with self.assertRaises(Problem) as exc:app.dispatch('POST',f"/api/occurrences/{ride['id']}/request",data,auth)
        self.assertEqual(exc.exception.status,503)
        with store.read() as db:self.assertEqual(db.execute('SELECT count(*) FROM applications').fetchone()[0],0)
    def test_google_failure_can_be_retried_without_duplicate_posts(self):
        self.error=True;store=Store(self.root/'failed.sqlite');app=App(store,demo_mode=True,routes=self.router(store));app.google_prices.thread.join(5)
        self.assertEqual(app.google_prices.status()['failed'],19)
        self.error=False;app.google_prices.start();app.google_prices.thread.join(5)
        self.assertEqual(app.google_prices.status()['pending'],0)
        with store.read() as db:self.assertEqual(db.execute('SELECT count(*) FROM trips').fetchone()[0],10)
    def test_upgrade_preserves_prior_agreements_and_user_posts(self):
        store=Store(self.root/'old.sqlite');main=seed_walkthrough(store);seed_scenarios(store)
        with store.tx() as db:
            users=[tuple(r) for r in db.execute('SELECT * FROM users ORDER BY id')]
            apps=[tuple(r) for r in db.execute('SELECT * FROM applications ORDER BY id')]
            old_prices=[tuple(r) for r in db.execute('SELECT id,price_cents FROM trips ORDER BY id')]
            db.execute("UPDATE trips SET note='Keep my actual post' WHERE id=?",(main['trip_id'],))
        prepare(store)
        with store.read() as db:
            self.assertEqual(users,[tuple(r) for r in db.execute('SELECT * FROM users ORDER BY id')])
            self.assertEqual(apps,[tuple(r) for r in db.execute('SELECT * FROM applications ORDER BY id')])
            for tid,cents in old_prices:self.assertEqual(db.execute('SELECT price_cents FROM trips WHERE id=?',(tid,)).fetchone()[0],cents)
            visible=list_trips(db,main['yelyn_id']);self.assertTrue(all(not r['price_meta'].get('retired_setup') for r in visible))
            self.assertEqual(len({r['trip_id'] for r in visible}),10)
            from app.domain import joined_occurrence,ensure_open,Problem
            oid=db.execute('SELECT id FROM occurrences WHERE trip_id=? LIMIT 1',(main['trip_id'],)).fetchone()[0]
            with self.assertRaises(Problem):ensure_open(joined_occurrence(db,oid))
        prepare(store)
        with store.read() as db:self.assertEqual(db.execute('SELECT count(*) FROM trips').fetchone()[0],20)
    def test_all_existing_posts_and_date_exceptions_use_separate_google_quotes(self):
        from app.domain import trip_create,joined_occurrence,ZONE
        day=dt.date.fromisoformat(self.class_rides()[0]['trip_date'])+dt.timedelta(days=49)
        with self.store.tx() as db:
            owner=dict(db.execute("SELECT * FROM users WHERE email='noah@usc.edu'").fetchone())
            ride=self.class_rides()[0]
            tid=trip_create(db,owner,dict(role='driver',kind='regular',origin=ride['origin'],destination=ride['destination'],
                departure_hour=13,arrive_by=14,start_date=str(day),end_date=str(day+dt.timedelta(days=14)),weekdays=[1],
                seats=2,price_cents=777,detour_minutes=10,note='Untracked existing user post'))
            ids=[r[0] for r in db.execute('SELECT id FROM occurrences WHERE trip_id=? ORDER BY trip_date',(tid,))]
            # Retain the first historical agreement, while pricing both future dates.
            db.execute('UPDATE occurrences SET trip_date=? WHERE id=?',(str(day-dt.timedelta(days=70)),ids[0]))
            db.execute('UPDATE occurrences SET overrides=? WHERE id=?',(json.dumps(dict(departure_hour=15,arrive_by=16,price_cents=555,note='This week only')),ids[2]))
        self.app.google_prices.prepare()
        with self.store.read() as db:
            self.assertEqual(joined_occurrence(db,ids[0])['price_cents'],777)
            self.assertEqual(joined_occurrence(db,ids[1])['price_cents'],0)
            self.assertEqual(json.loads(joined_occurrence(db,ids[2])['price_meta'])['status'],'pending')
        stamp=dt.datetime.combine(day+dt.timedelta(days=14),dt.time(15),ZONE).astimezone(dt.timezone.utc).isoformat().replace('+00:00','Z')
        self.durations[stamp]='2100s'
        self.app.google_prices.start();self.app.google_prices.thread.join(5)
        code,result=self.clients['yelyn'].call('/api/rides/search',dict(trip_id=tid));self.assertEqual(code,200,result)
        rides=sorted(result['rides'],key=lambda r:r['trip_date']);self.assertEqual(len(rides),2)
        self.assertEqual([r['price_cents'] for r in rides],[1200,1650])
        self.assertEqual([r['pricing']['duration_minutes'] for r in rides],[20,35])
        self.assertNotEqual(rides[0]['pricing']['departure_time'],rides[1]['pricing']['departure_time'])
        self.assertTrue(rides[1]['has_exception']);self.assertFalse(rides[0]['has_exception'])
        self.assertEqual(self.app.google_prices.status()['pending'],0)
        with self.store.read() as db:
            self.assertEqual(db.execute('SELECT price_cents FROM trips WHERE id=?',(tid,)).fetchone()[0],777)
            self.assertEqual(joined_occurrence(db,ids[0])['price_cents'],777)
        self.assertEqual(json.loads(rides[1]['overrides'])['note'],'This week only')

    def test_existing_manual_confirmed_booking_shows_google_price_in_all_views(self):
        from app.domain import trip_create,request_ride,decide,joined_occurrence
        r=self.class_rides()[0]
        with self.store.tx() as db:
            users={name:dict(db.execute('SELECT * FROM users WHERE email=?',(name+'@usc.edu',)).fetchone()) for name in ('noah','yelyn','hannah')}
            tid=trip_create(db,users['noah'],dict(role='driver',kind='one',origin=r['origin'],destination=r['destination'],
                start_date=r['trip_date'],departure_hour=13,arrive_by=14,seats=2,detour_minutes=10,price_cents=400,note='Existing manual agreement'))
            oid=db.execute('SELECT id FROM occurrences WHERE trip_id=?',(tid,)).fetchone()[0]
            ids=[]
            for name in ('yelyn','hannah'):
                aid=request_ride(db,users[name],oid,dict(party_size=1,auto_confirm=True,meeting_origin={**r['origin'],'mode':'exact','radius_miles':0},meeting_destination={**r['destination'],'mode':'exact','radius_miles':0}))
                decide(db,users['noah'],aid,True);ids.append(aid)
        self.app.google_prices.start();self.app.google_prices.thread.join(5)
        for who in ('noah','yelyn','hannah'):
            board=self.clients[who].call('/api/rides/search',dict(trip_id=tid))[1]['rides'][0]
            self.assertEqual(board['pricing']['rider_price_cents'],990)
            my=next(r for r in self.clients[who].call('/api/my-rides/search',{})[1]['rides'] if r['id']==oid)
            self.assertEqual(my['agreed_price_cents'],990)
            for a in self.clients[who].call('/api/applications')[1]['applications']:
                if a['id'] in ids:self.assertEqual(a['agreed_price_cents'],990)
        with self.store.read() as db:
            self.assertEqual([r[0] for r in db.execute('SELECT agreed_price_cents FROM applications WHERE occurrence_id=?',(oid,))],[400,400])

    def test_new_posts_reject_manual_prices_and_ignore_client_supplied_amounts(self):
        r=self.class_rides()[0]
        data=dict(role='driver',kind='one',origin=r['origin'],destination=r['destination'],start_date=r['trip_date'],
            departure_hour=13,arrive_by=14,seats=2,detour_minutes=10,note='New quote policy',price_mode='manual',price_cents=1)
        code,result=self.clients['kate'].call('/api/trips',data);self.assertEqual(code,422,result)
        data.pop('price_mode');data['_price_meta']=dict(model='forged',price_cents=1)
        code,result=self.clients['kate'].call('/api/trips',data);self.assertEqual(code,201,result)
        rides=self.clients['kate'].call('/api/rides/search',dict(trip_id=result['trip_id']))[1]['rides']
        self.assertEqual(rides[0]['price_cents'],1200);self.assertEqual(rides[0]['price_meta']['source'],'Google Maps')

    def test_changed_departure_requotes_only_that_date(self):
        first,second,*_=self.class_rides();before=second['price_meta']
        code,result=self.clients['kate'].call(f"/api/occurrences/{first['id']}/edit-date",dict(departure_hour=15,arrive_by=16,note='Later this week'))
        self.assertEqual(code,200,result);self.app.google_prices.thread.join(5)
        dates=self.class_rides();self.assertEqual(dates[0]['departure_hour'],15)
        self.assertEqual(dt.datetime.fromisoformat(dates[0]['pricing']['departure_time'].replace('Z','+00:00')).astimezone(__import__('app.domain',fromlist=['ZONE']).ZONE).hour,15)
        self.assertEqual(dates[1]['price_meta'],before)
        self.assertEqual(dates[0]['note'],'Later this week')

    def test_driver_cancel_and_republish_calculates_new_meeting_point_price(self):
        first=self.class_rides()[0];aid=self.request('yelyn',first);self.accept(aid)
        code,result=self.clients['kate'].call(f"/api/occurrences/{first['id']}/cancel",{});self.assertEqual(code,200,result)
        code,result=self.clients['yelyn'].call(f'/api/applications/{aid}/republish',{});self.assertEqual(code,200,result)
        self.app.google_prices.thread.join(5)
        rides=self.clients['kate'].call('/api/rides/search',dict(trip_id=result['trip_id']))[1]['rides']
        self.assertEqual(len(rides),1);self.assertEqual(rides[0]['price_cents'],1200)
        self.assertEqual(rides[0]['price_meta']['model'],'google_shared_v1')
        self.assertEqual(rides[0]['role'],'rider');self.assertEqual(rides[0]['confirmed_seats'],0)

    def test_initial_command_does_not_request_confirm_or_cancel(self):
        root=Path(__file__).resolve().parents[1]
        for _ in range(2):
            result=subprocess.run(['python3',str(root/'run_flow.py'),'--base',self.base],text=True,capture_output=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIn('Applications on this post: 0',result.stdout)
        with self.store.read() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM applications').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM trips').fetchone()[0],10)
            self.assertEqual(db.execute("SELECT count(*) FROM occurrences WHERE status!='active'").fetchone()[0],0)

    def test_update_archives_previous_flow_and_starts_at_clean_kate_offer_once(self):
        from app.domain import trip_create,application_views,joined_occurrence,list_notifications
        from app.live import PREVIOUS_KEY
        first=self.class_rides()[0];aid=self.request('yelyn',first);self.accept(aid)
        with self.store.tx() as db:
            kate=dict(db.execute("SELECT * FROM users WHERE email='kate@usc.edu'").fetchone())
            users=[tuple(r) for r in db.execute('SELECT * FROM users ORDER BY id')]
            old_apps=[tuple(r) for r in db.execute('SELECT * FROM applications ORDER BY id')]
            # Reproduce the exact v2.4.0 runner post signature, with no server marker.
            runner=trip_create(db,kate,dict(role='driver',kind='regular',origin=first['origin'],destination=first['destination'],
                departure_hour=13,arrive_by=14,start_date=first['trip_date'],end_date=first['trip_date'],weekdays=[1],seats=2,
                price_cents=1200,detour_minutes=10,note='Tuesday class commute. Meet at the station entrance; two passenger seats.'))
            db.execute('UPDATE app_settings SET key=? WHERE key=?',(PREVIOUS_KEY,KEY))
        fresh=prepare(self.store);self.app.google_prices.start();self.app.google_prices.thread.join(5)
        self.assertNotEqual(fresh['routes']['class'],self.catalog['routes']['class'])
        with self.store.read() as db:
            self.assertEqual(users,[tuple(r) for r in db.execute('SELECT * FROM users ORDER BY id')])
            self.assertEqual(old_apps,[tuple(r) for r in db.execute('SELECT * FROM applications ORDER BY id')])
            self.assertEqual(application_views(db,kate),[]);self.assertEqual(list_notifications(db,kate),[])
            visible=list_trips(db,kate['id'],dict(_include_retired=True))
            self.assertEqual(len({r['trip_id'] for r in visible}),10)
            self.assertTrue(all(r['confirmed_seats']==0 and r['pricing']['source']=='Google Maps' for r in visible))
            self.assertTrue(json.loads(db.execute('SELECT price_meta FROM trips WHERE id=?',(runner,)).fetchone()[0])['retired_setup'])
        self.assertEqual(prepare(self.store),fresh)
        with self.store.read() as db:self.assertEqual(db.execute('SELECT count(*) FROM trips').fetchone()[0],21)

    def test_preset_fixture_endpoints_and_cli_are_disabled(self):
        self.assertEqual(self.clients['kate'].call('/api/demo/scenarios',{})[0],404)
        result=subprocess.run(['python3','-m','app.demo','--reset','--scenario','B'],text=True,capture_output=True)
        self.assertNotEqual(result.returncode,0);self.assertIn('disabled',result.stderr)
        with self.store.read() as db:self.assertEqual(db.execute('SELECT count(*) FROM applications').fetchone()[0],0)

    def test_command_performs_actual_http_flow_and_second_run_does_not_duplicate(self):
        root=Path(__file__).resolve().parents[1];state=self.root/'flow-state.json'
        command=['python3',str(root/'run_flow.py'),'--base',self.base,'--state-file',str(state),'--perform-sequence']
        first=subprocess.run(command,text=True,capture_output=True,timeout=30)
        self.assertEqual(first.returncode,0,first.stdout+'\n'+first.stderr)
        result=json.loads(state.read_text());self.assertTrue(result['completed'])
        with self.store.read() as db:
            trips=db.execute('SELECT count(*) FROM trips').fetchone()[0];apps=db.execute('SELECT count(*) FROM applications').fetchone()[0]
            self.assertEqual(trips,11);self.assertEqual(apps,12)
            statuses=[r[0] for r in db.execute('SELECT status FROM applications ORDER BY id')]
            self.assertCountEqual(statuses,['canceled']+['confirmed']*8+['waitlisted']*3)
        again=subprocess.run(command,text=True,capture_output=True,timeout=30)
        self.assertEqual(again.returncode,0,again.stdout+'\n'+again.stderr)
        with self.store.read() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM trips').fetchone()[0],trips)
            self.assertEqual(db.execute('SELECT count(*) FROM applications').fetchone()[0],apps)
        self.assertNotIn('heky-local-2026',state.read_text());self.assertNotIn('local-fixture-key',first.stdout)

    def test_repeated_startup_does_not_reopen_or_duplicate_rides(self):
        before=self.catalog
        prepare(self.store)
        with self.store.read() as db:
            self.assertEqual(json.loads(db.execute('SELECT value FROM app_settings WHERE key=?',(KEY,)).fetchone()[0]),before)
            self.assertEqual(db.execute('SELECT count(*) FROM trips').fetchone()[0],10)
            self.assertEqual(db.execute('SELECT count(*) FROM applications').fetchone()[0],0)
    @unittest.skipUnless(shutil.which('node'),'Node is optional for UI handler checks')
    def test_live_frontend_post_accept_waitlist_cancel_and_landing(self):
        sessions={}
        for name,c in self.clients.items():
            me=c.call('/api/me')[1]
            sessions[name]=dict(cookie='; '.join(k.name+'='+k.value for k in c.jar),csrf=c.csrf,user=me['user'])
        day=dt.date.fromisoformat(self.class_rides()[0]['trip_date'])+dt.timedelta(days=28)
        root=Path(__file__).resolve().parents[1]
        payload=dict(base=self.base,sessions=sessions,js=str(root/'static/app.js'),date=str(day),places=Client(self.base).call('/api/config')[1]['places'])
        result=subprocess.run(['node',str(root/'tests/live_frontend.cjs')],input=json.dumps(payload),text=True,capture_output=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr);self.assertIn('PASS:',result.stdout)

if __name__=='__main__':unittest.main()
