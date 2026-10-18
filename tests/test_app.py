"""Real HTTP/SQLite integration tests; external inference uses an explicit HTTP fixture."""
import concurrent.futures
import datetime as dt
import http.cookiejar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit
from app.domain import (Store, PLACES, DEFAULT_DEMO_PASSWORD, location, overlaps, Problem,
    check_password, distance_miles, shared_meeting_point)
from app.places import Places
from app.rag import Ollama, RAG
from app.server import App, Server

class Client:
    def __init__(self,base):
        self.base,self.csrf=base,''
        self.jar=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
    def call(self,path,data=None,method=None,csrf=True):
        req=urllib.request.Request(self.base+path,method=method or ('POST' if data is not None else 'GET'),data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json',**({'X-CSRF-Token':self.csrf} if csrf and self.csrf else {})})
        try:
            with self.opener.open(req,timeout=15) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as exc:return exc.code,json.load(exc)
    def login(self,email):
        code,r=self.call('/api/auth/login',{'email':email+'@usc.edu','password':DEFAULT_DEMO_PASSWORD})
        assert code==200,r
        self.csrf=r['csrf']
        return r['user']

class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'campusloop.sqlite3')
        self.app=App(self.store,demo_mode=True);self.server=Server(('127.0.0.1',0),self.app)
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.01},daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port);self.clients={}
        for name in ['jamie','mina','sofia','daniel','leo','ethan']:
            c=Client(self.base);c.login(name);self.clients[name]=c
        self.date=self.clients['jamie'].call('/api/config')[1]['default_date']
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2);self.temp.cleanup()
    def search(self,who='jamie',**criteria):
        code,r=self.clients[who].call('/api/rides/search',{'date':self.date,**criteria});self.assertEqual(code,200,r);return r['rides']
    def create(self,owner='mina',role='driver',seats=1,kind='one',**overrides):
        def loc(n,mode='exact',radius=0):return {**{k:v for k,v in PLACES[n].items() if k!='id'},'mode':mode,'radius_miles':radius}
        data=dict(role=role,origin=loc(0,'area',1),destination=loc(4,'area',.5),departure_hour=8,arrive_by=9,kind=kind,weekdays=[0,2,4],start_date=self.date,end_date=str(dt.date.fromisoformat(self.date)+dt.timedelta(days=7)),seats=seats,price_cents=400,detour_minutes=10,note='A real integration test.',return_hour=17)
        data.update(overrides)
        code,r=self.clients[owner].call('/api/trips',data);self.assertEqual(code,201,r)
        return next(x for x in self.search(date=r['first_date']) if x['trip_id']==r['trip_id'])
    def apply(self,who,ride,auto=True,party=1):
        pickup={**ride['origin'],'mode':'exact','radius_miles':0};dropoff={**ride['destination'],'mode':'exact','radius_miles':0}
        code,r=self.clients[who].call(f"/api/occurrences/{ride['id']}/request",dict(auto_confirm=auto,party_size=party,meeting_origin=pickup,meeting_destination=dropoff));self.assertEqual(code,201,r);return r['application_id']
    def status(self,who,aid):
        _,r=self.clients[who].call('/api/applications');return next(a for a in r['applications'] if a['id']==aid)['status']
    def test_auth_csrf_permissions_and_static(self):
        self.assertEqual(Client(self.base).call('/api/rides/search',{})[0],401)
        self.assertEqual(self.clients['jamie'].call('/api/rides/search',{'date':self.date},csrf=False)[0],403)
        ride=self.create();aid=self.apply('jamie',ride)
        self.assertEqual(self.clients['leo'].call(f'/api/applications/{aid}/accept',{})[0],403)
        self.assertEqual(self.status('jamie',aid),'pending')
        with urllib.request.urlopen(self.base) as r:
            html=r.read();self.assertIn(b'/static/api.js',html);self.assertIn(b'/static/events.js',html);self.assertIn('frame-ancestors',r.headers['Content-Security-Policy'])
        self.clients['jamie'].call('/api/auth/logout',{})
        self.assertEqual(self.clients['jamie'].call('/api/me')[0],401)
    def test_rider_offer_accept_and_cancel(self):
        rides=self.search(role='rider');self.assertEqual(len(rides),1);ride=rides[0]
        aid=self.apply('jamie',ride);other=self.apply('mina',ride)
        self.assertEqual(self.clients['daniel'].call(f'/api/applications/{aid}/accept',{})[1]['status'],'confirmed')
        self.assertEqual(self.status('mina',other),'declined')
        _,mine=self.clients['jamie'].call('/api/my-rides')
        self.assertEqual(next(r for r in mine['rides'] if r['id']==ride['id'])['my_role'],'driver')
        self.clients['jamie'].call(f'/api/applications/{aid}/cancel',{})
        self.assertIsNone(next(r for r in self.search(role='rider') if r['id']==ride['id'])['driver_id'])
    def test_concurrent_accepts_capacity_and_promotion(self):
        ride=self.create();first=self.apply('jamie',ride);second=self.apply('leo',ride);owner=self.clients['mina']
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda aid:owner.call(f'/api/applications/{aid}/accept',{}),[first,second]))
        self.assertTrue(all(r[0]==200 for r in results),results)
        statuses={first:self.status('jamie',first),second:self.status('leo',second)}
        self.assertCountEqual(statuses.values(),['confirmed','waitlisted'])
        booked=next(a for a,s in statuses.items() if s=='confirmed');waiting=next(a for a,s in statuses.items() if s=='waitlisted')
        person='jamie' if booked==first else 'leo';other='leo' if person=='jamie' else 'jamie'
        code,result=self.clients[person].call(f'/api/applications/{booked}/cancel',{})
        self.assertEqual(code,200,result);self.assertEqual(result['promoted_application_ids'],[waiting]);self.assertEqual(self.status(other,waiting),'confirmed')
        self.assertEqual(next(r for r in self.search() if r['id']==ride['id'])['confirmed_seats'],1)
    def test_manual_waitlist_whole_party(self):
        ride=self.create(seats=2);first=self.apply('jamie',ride,party=2);waiting=self.apply('leo',ride,auto=False,party=2)
        for aid in [first,waiting]:self.assertEqual(self.clients['mina'].call(f'/api/applications/{aid}/accept',{})[0],200)
        self.assertEqual(self.clients['leo'].call(f'/api/applications/{waiting}/claim',{})[0],409)
        self.clients['jamie'].call(f'/api/applications/{first}/cancel',{})
        self.assertEqual(self.status('leo',waiting),'waitlisted');self.assertEqual(self.clients['leo'].call(f'/api/applications/{waiting}/claim',{})[0],200)
        self.assertEqual(next(r for r in self.search() if r['id']==ride['id'])['confirmed_seats'],2)
    def test_recurring_dates_are_independent(self):
        _,body=self.clients['jamie'].call('/api/applications');booked=[a for a in body['applications'] if a['owner_name']=='Sofia Lee' and a['status']=='confirmed']
        self.assertGreater(len(booked),1);first=min(booked,key=lambda a:a['trip_date']);later=max(booked,key=lambda a:a['trip_date'])
        self.clients['jamie'].call(f"/api/applications/{first['id']}/cancel",{})
        self.assertEqual(self.status('jamie',later['id']),'confirmed');self.assertEqual(self.status('jamie',first['id']),'canceled')
        _,queue=self.clients['leo'].call('/api/applications');self.assertEqual(next(a for a in queue['applications'] if a['occurrence_id']==first['occurrence_id'])['status'],'confirmed')
    def test_coordinates_and_invalid_filters(self):
        ride=self.create();bad={**ride['origin'],'lat':35.5,'mode':'exact','radius_miles':0}
        code,_=self.clients['jamie'].call(f"/api/occurrences/{ride['id']}/request",dict(auto_confirm=True,party_size=1,meeting_origin=bad,meeting_destination={**ride['destination'],'mode':'exact'}));self.assertEqual(code,422)
        self.assertEqual(self.clients['jamie'].call('/api/rides/search',{'date':self.date,'departure_hour':'invalid'})[0],422)
        exact=location({**PLACES[0],'mode':'exact','radius_miles':3});self.assertEqual(exact['radius_miles'],0)
        near={**exact,'lon':exact['lon']+.005};self.assertFalse(overlaps(exact,near));self.assertTrue(overlaps({**exact,'mode':'area','radius_miles':1},near))
        with self.assertRaises(Problem):location({**exact,'lat':float('nan')})
    def test_chat_private_and_persistent(self):
        ride=self.create();aid=self.apply('jamie',ride);path=f"/api/occurrences/{ride['id']}/messages"
        self.assertEqual(self.clients['jamie'].call(path)[0],403);self.clients['mina'].call(f'/api/applications/{aid}/accept',{})
        body='<script>alert(1)</script> See you at the entrance.'
        self.assertEqual(self.clients['jamie'].call(path,{'body':body})[0],200);self.assertEqual(self.clients['mina'].call(path)[1]['messages'][0]['body'],body)
        self.assertEqual(self.clients['leo'].call(path)[0],403)
        with Store(self.store.path).read() as db:self.assertEqual(db.execute('SELECT count(*) FROM messages').fetchone()[0],1)
    def test_register_verify_and_profile(self):
        c=Client(self.base);code,result=c.call('/api/auth/register',{'name':'Test Student','email':'test@usc.edu','password':'long-enough-password'});self.assertEqual(code,201,result)
        self.assertEqual(c.call('/api/auth/verify',{'email':'test@usc.edu','code':'badbad'})[0],400)
        with self.store.read() as db:self.assertEqual(db.execute("SELECT verification_attempts FROM users WHERE email='test@usc.edu'").fetchone()[0],1)
        code,verified=c.call('/api/auth/verify',{'email':'test@usc.edu','code':result['development_code']});self.assertEqual(code,200,verified);c.csrf=verified['csrf']
        self.assertTrue(verified['user']['verified']);self.assertEqual(c.call('/api/me',{'name':'Test Student','vehicle':'Honda Civic'},method='PUT')[0],200)
    def test_owner_cancel_and_round_trip(self):
        ride=self.create(kind='round');self.assertEqual(ride['return_hour'],17)
        first=self.apply('jamie',ride);second=self.apply('leo',ride)
        for aid in [first,second]:self.clients['mina'].call(f'/api/applications/{aid}/accept',{})
        self.assertEqual(self.clients['mina'].call(f"/api/occurrences/{ride['id']}/cancel",{})[0],200)
        self.assertEqual(self.status('jamie',first),'canceled');self.assertEqual(self.status('leo',second),'canceled')

    def test_concurrent_manual_claims_have_one_winner(self):
        ride=self.create();first=self.apply('jamie',ride);one=self.apply('leo',ride,auto=False);two=self.apply('ethan',ride,auto=False)
        for aid in [first,one,two]:self.clients['mina'].call(f'/api/applications/{aid}/accept',{})
        self.clients['jamie'].call(f'/api/applications/{first}/cancel',{})
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda item:self.clients[item[0]].call(f'/api/applications/{item[1]}/claim',{}),[('leo',one),('ethan',two)]))
        self.assertCountEqual([r[0] for r in results],[200,409])
        self.assertEqual(next(r for r in self.search() if r['id']==ride['id'])['confirmed_seats'],1)
    def test_rag_endpoint_uses_real_http_model_contract(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),ModelFixture);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
        try:
            self.app.rag=RAG(self.store,Ollama(f'http://127.0.0.1:{server.server_port}'))
            code,result=self.clients['jamie'].call('/api/rag/ask',{'question':'How do cancellation and waitlist work?','filters':{'date':self.date}})
            self.assertEqual(code,200,result);self.assertEqual(result['mode'],'rag');self.assertTrue(result['sources'])
            self.assertNotIn('password_hash',json.dumps(result));self.assertNotIn(DEFAULT_DEMO_PASSWORD,json.dumps(result))
        finally:server.shutdown();server.server_close();thread.join(2)

    def test_recurring_creation_returns_first_actual_date(self):
        start=dt.date.fromisoformat(self.date)
        loc=lambda n:{**{k:v for k,v in PLACES[n].items() if k!='id'},'mode':'exact','radius_miles':0}
        payload=dict(role='driver',kind='regular',origin=loc(0),destination=loc(4),departure_hour=8,arrive_by=9,seats=1,price_cents=400,detour_minutes=10,note='',start_date=self.date,end_date=str(start+dt.timedelta(days=7)),weekdays=[2])
        code,result=self.clients['mina'].call('/api/trips',payload)
        self.assertEqual(code,201,result)
        first=dt.date.fromisoformat(result['first_date']);self.assertEqual(first.weekday(),2)
        self.assertTrue(any(r['trip_id']==result['trip_id'] for r in self.search(date=result['first_date'])))

    def test_all_dates_roles_and_combined_time_date_filters(self):
        first=self.create()
        later=str(dt.date.fromisoformat(self.date)+dt.timedelta(days=1))
        second=self.create(role='rider',start_date=later,end_date=later,departure_hour=15,arrive_by=16)
        code,result=self.clients['jamie'].call('/api/rides/search',{})
        self.assertEqual(code,200,result)
        self.assertTrue({first['id'],second['id']} <= {r['id'] for r in result['rides']})
        self.assertEqual({r['role'] for r in result['rides']},{'driver','rider'})
        exact=self.search(date=later,departure_from=15,departure_to=15)
        self.assertIn(second['id'],[r['id'] for r in exact]);self.assertNotIn(first['id'],[r['id'] for r in exact])
        code,result=self.clients['jamie'].call('/api/rides/search',dict(date_from=self.date,date_to=later,departure_from=8,departure_to=15))
        self.assertEqual(code,200,result)
        self.assertTrue(all(self.date<=r['trip_date']<=later and 8<=r['departure_hour']<=15 for r in result['rides']))
        self.assertTrue({first['id'],second['id']} <= {r['id'] for r in result['rides']})
        self.assertEqual(self.clients['jamie'].call('/api/rides/search',{'departure_from':None,'departure_to':None})[0],200)
        self.assertEqual(self.clients['jamie'].call('/api/rides/search',{'departure_from':17,'departure_to':8})[0],422)
        self.assertEqual(self.clients['jamie'].call('/api/rides/search',{'date_from':later,'date_to':self.date})[0],422)

    def test_both_location_areas_and_distance_order(self):
        close=self.create()
        farther=self.create(origin={**close['origin'],'label':'Nearby pickup','lon':close['origin']['lon']+.008})
        wrong_end=self.create(destination={**close['destination'],'label':'Unrelated destination','lon':close['destination']['lon']+.2})
        requested_origin={**close['origin'],'label':'My requested pickup','radius_miles':.5}
        requested_dest={**close['destination'],'label':'My requested destination','radius_miles':.5}
        rides=self.search(origin=requested_origin,destination=requested_dest)
        ids=[r['id'] for r in rides]
        self.assertIn(close['id'],ids);self.assertIn(farther['id'],ids);self.assertNotIn(wrong_end['id'],ids)
        self.assertLess(ids.index(close['id']),ids.index(farther['id']))
        matched=next(r for r in rides if r['id']==farther['id'])
        self.assertEqual(matched['match_type'],'both_locations');self.assertEqual(matched['search_origin'],'My requested pickup')
        self.assertGreater(matched['pickup_distance_miles'],0)
        for target,posted,point in [(requested_origin,matched['origin'],matched['suggested_meeting_origin']),(requested_dest,matched['destination'],matched['suggested_meeting_destination'])]:
            self.assertTrue(overlaps(target,point));self.assertTrue(overlaps(posted,point));self.assertEqual(point['mode'],'exact')
        self.assertIn(wrong_end['id'],[r['id'] for r in self.search(origin=requested_origin)])
        # Overlapping edges without either center inside the other circle.
        a=location({**close['origin'],'radius_miles':1})
        b={**a,'lon':a['lon']+.026}
        self.assertGreater(distance_miles(a,b),1);self.assertTrue(overlaps(a,b))
        point=shared_meeting_point(a,b)
        self.assertTrue(overlaps(a,point));self.assertTrue(overlaps(b,point))

    def test_names_private_until_confirmation_for_this_date(self):
        ride=self.create(note='Mina Park can meet you. Email mina@usc.edu.')
        self.assertFalse(ride['identity_revealed']);alias=ride['owner_name'];self.assertTrue(alias.startswith('Loop Member '))
        self.assertNotIn('Mina Park',json.dumps(ride));self.assertNotIn('mina@usc.edu',json.dumps(ride))
        aid=self.apply('jamie',ride);waiting=self.apply('leo',ride)
        outgoing=next(a for a in self.clients['jamie'].call('/api/applications')[1]['applications'] if a['id']==aid)
        incoming=next(a for a in self.clients['mina'].call('/api/applications')[1]['applications'] if a['id']==aid)
        self.assertEqual(outgoing['owner_name'],alias);self.assertFalse(outgoing['identity_revealed'])
        self.assertTrue(incoming['requester_name'].startswith('Loop Member '));self.assertFalse(incoming['identity_revealed'])
        path=f"/api/occurrences/{ride['id']}/activity"
        self.assertNotIn('Jamie Lee',json.dumps(self.clients['mina'].call(path)[1]))
        with self.store.read() as db:user=dict(db.execute("SELECT * FROM users WHERE email='jamie@usc.edu'").fetchone())
        sources=self.app.rag.documents(user,{'date':self.date})
        source=next(s for s in sources if s.get('occurrence_id')==ride['id'])
        self.assertNotIn('Mina Park',json.dumps(source));self.assertIn(alias,json.dumps(source))
        self.clients['mina'].call(f'/api/applications/{aid}/accept',{})
        self.clients['mina'].call(f'/api/applications/{waiting}/accept',{})
        matched=next(r for r in self.search() if r['id']==ride['id'])
        self.assertEqual(matched['owner_name'],'Mina Park');self.assertTrue(matched['identity_revealed'])
        incoming=next(a for a in self.clients['mina'].call('/api/applications')[1]['applications'] if a['id']==aid)
        self.assertEqual(incoming['requester_name'],'Jamie Lee');self.assertTrue(incoming['identity_revealed'])
        third_party=next(r for r in self.search('ethan') if r['id']==ride['id'])
        self.assertEqual(third_party['owner_name'],alias);self.assertFalse(third_party['identity_revealed'])
        waiting_view=next(a for a in self.clients['leo'].call('/api/applications')[1]['applications'] if a['id']==waiting)
        self.assertEqual(waiting_view['status'],'waitlisted');self.assertEqual(waiting_view['owner_name'],alias)
        activity=self.clients['jamie'].call(path)[1]
        self.assertNotIn('Leo Kim',json.dumps(activity));self.assertIn('Loop Member ',json.dumps(activity))
        self.clients['jamie'].call(f'/api/applications/{aid}/cancel',{})
        canceled=next(r for r in self.search() if r['id']==ride['id'])
        self.assertEqual(canceled['owner_name'],alias);self.assertFalse(canceled['identity_revealed'])
        promoted=next(r for r in self.search('leo') if r['id']==ride['id'])
        self.assertEqual(promoted['owner_name'],'Mina Park');self.assertTrue(promoted['identity_revealed'])

    def test_old_database_upgrade_and_session_cookie(self):
        ride=self.create()
        with self.store.tx() as db:
            counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['users','trips','occurrences','applications','sessions']}
            # These two tables were absent in the previous release.
            db.execute('DROP TABLE app_settings');db.execute('DROP TABLE place_cache')
        upgraded=Store(self.store.path)
        with upgraded.read() as db:
            for table,count in counts.items():self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],count)
            self.assertTrue(check_password(DEFAULT_DEMO_PASSWORD,db.execute("SELECT password_hash FROM users WHERE email='jamie@usc.edu'").fetchone()[0]))
            salt=db.execute("SELECT value FROM app_settings WHERE key='identity_salt'").fetchone()[0]
        with Store(self.store.path).read() as db:self.assertEqual(db.execute("SELECT value FROM app_settings WHERE key='identity_salt'").fetchone()[0],salt)
        for cookie in self.clients['jamie'].jar:
            self.assertEqual(cookie.name,'campusloop_session')
        self.assertEqual(self.clients['jamie'].call('/api/me')[0],200)
        self.assertEqual(self.clients['jamie'].call('/api/auth/logout',{})[0],200)
        self.assertEqual(self.clients['jamie'].call('/api/me')[0],401)

    def test_place_search_endpoint_and_bad_bias(self):
        code,result=self.clients['jamie'].call('/api/places/search',{'query':'USC'})
        self.assertEqual(code,200,result);self.assertTrue(result['places']);self.assertEqual(result['source'],'catalog')
        self.assertEqual(self.clients['jamie'].call('/api/places/search',{'query':'USC','bias':'invalid'})[0],422)


class PlaceFixture(BaseHTTPRequestHandler):
    calls=[]
    def log_message(self,*args):pass
    def do_GET(self):
        type(self).calls.append(parse_qs(urlsplit(self.path).query))
        result={'features':[
            {'geometry':{'type':'Point','coordinates':[-118.3,34.04]},'properties':{'name':'Fixture Station','city':'Los Angeles','state':'California','osm_type':'N','osm_id':42}},
            {'geometry':{'type':'Point','coordinates':[0,999]},'properties':{'name':'Invalid point'}},
            {'geometry':{'type':'Point','coordinates':None}},None]}
        body=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)


class PlaceTests(unittest.TestCase):
    def test_http_geocoder_bias_cache_validation_and_rate_limit(self):
        with tempfile.TemporaryDirectory() as path:
            store=Store(Path(path)/'db.sqlite')
            server=ThreadingHTTPServer(('127.0.0.1',0),PlaceFixture);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start();PlaceFixture.calls=[]
            try:
                places=Places(store,f'http://127.0.0.1:{server.server_port}/api/')
                result=places.search('Fixture Station',{'lat':34.041239,'lon':-118.301239})
                self.assertEqual(len(result['places']),1);self.assertEqual(result['places'][0]['label'],'Fixture Station, Los Angeles, California')
                self.assertEqual(PlaceFixture.calls[0]['lat'],['34.0412']);self.assertEqual(PlaceFixture.calls[0]['lang'],['en'])
                cached=places.search('Fixture Station',{'lat':34.041239,'lon':-118.301239})
                self.assertTrue(cached['cached']);self.assertEqual(len(PlaceFixture.calls),1)
                with self.assertRaises(Problem) as exc:places.search('Another Station')
                self.assertEqual(exc.exception.status,429)
                self.assertEqual(places.search('USC')['source'],'catalog')
                with self.assertRaises(Problem):places.search('USC',{'lat':100,'lon':0})
            finally:server.shutdown();server.server_close();thread.join(2)

    def test_unavailable_geocoder_returns_error_instead_of_a_fake_place(self):
        with tempfile.TemporaryDirectory() as path:
            places=Places(Store(Path(path)/'db.sqlite'),'http://127.0.0.1:1/api/')
            with self.assertRaises(Problem) as exc:places.search('Unknown Station')
            self.assertEqual(exc.exception.status,503)
            # A query without Latin letters must not match every bundled place.
            disabled=Places(places.store,'')
            with self.assertRaises(Problem) as exc:disabled.search('\u6771\u4eac')
            self.assertEqual(exc.exception.status,503)

class ModelFixture(BaseHTTPRequestHandler):
    calls=[]
    def log_message(self,*args):pass
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])));type(self).calls.append((self.path,data))
        if self.path=='/api/embed':result={'embeddings':[[float(t.lower().count('cancel')),float(t.lower().count('waitlist')),1.0] for t in data['input']]}
        else:result={'response':'Approved waitlisted parties can be confirmed when seats open. [S1] [S999]'}
        payload=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)

class RAGTests(unittest.TestCase):
    def test_http_embedding_generation_cache_and_citations(self):
        with tempfile.TemporaryDirectory() as path:
            store=Store(Path(path)/'db.sqlite');App(store,demo_mode=True)
            server=ThreadingHTTPServer(('127.0.0.1',0),ModelFixture);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start();ModelFixture.calls=[]
            try:
                rag=RAG(store,Ollama(f'http://127.0.0.1:{server.server_port}'))
                with store.read() as db:user=dict(db.execute('SELECT * FROM users WHERE id=1').fetchone());date=db.execute('SELECT min(trip_date) FROM occurrences').fetchone()[0]
                answer=rag.ask(user,'cancellation cancel waitlist promotion',{'date':date});self.assertEqual(answer['mode'],'rag');self.assertEqual(answer['retrieval'],'hybrid_bm25_vector');self.assertIn('[S1]',answer['answer']);self.assertNotIn('[S999]',answer['answer'])
                embeds=sum(p=='/api/embed' for p,_ in ModelFixture.calls);rag.ask(user,'cancellation cancel waitlist promotion',{'date':date});self.assertEqual(embeds,sum(p=='/api/embed' for p,_ in ModelFixture.calls))
                request=next(data for p,data in ModelFixture.calls if p=='/api/generate');self.assertIn('<retrieved_sources>',request['prompt']);self.assertIn('no action tools',request['system'])
                with store.read() as db:self.assertGreater(db.execute('SELECT count(*) FROM embeddings').fetchone()[0],0)
            finally:server.shutdown();server.server_close();thread.join(2)
    def test_model_unavailable_has_no_fake_answer(self):
        with tempfile.TemporaryDirectory() as path:
            store=Store(Path(path)/'db.sqlite');App(store,demo_mode=True)
            with store.read() as db:user=dict(db.execute('SELECT * FROM users WHERE id=1').fetchone());date=db.execute('SELECT min(trip_date) FROM occurrences').fetchone()[0]
            answer=RAG(store,Ollama('http://127.0.0.1:1')).ask(user,'How does cancellation and waitlist work?',{'date':date})
            self.assertEqual(answer['mode'],'retrieval_only');self.assertIsNone(answer['answer']);self.assertTrue(answer['sources'])

if __name__=='__main__':unittest.main()
