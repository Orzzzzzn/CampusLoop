"""Ordinary Kate/Yelyn HTTP flows and additive seed persistence."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from app.demo import KEY, next_tuesday, seed_walkthrough, seed_scenarios
from app.domain import Store, check_password, hash_password
from app.server import App, Server
from test_app import Client

class WalkthroughTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'db.sqlite')
        seed_walkthrough(self.store);seed_scenarios(self.store)
        self.app=App(self.store,demo_mode=True,seed_data=False);self.http=Server(('127.0.0.1',0),self.app)
        self.thread=threading.Thread(target=self.http.serve_forever,kwargs={'poll_interval':.01},daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.http.server_port)
        self.kate=Client(self.base);self.kate.login('kate')
        self.yelyn=Client(self.base);self.yelyn.login('yelyn')
        self.config=self.kate.call('/api/config')[1]['walkthrough']
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join(2);self.temp.cleanup()
    def rides(self,client=None):
        code,data=(client or self.yelyn).call('/api/rides/search',{'trip_id':self.config['trip_id']})
        self.assertEqual(code,200,data);return sorted(data['rides'],key=lambda r:r['trip_date'])
    def book(self,ride):
        data=dict(party_size=1,auto_confirm=True,meeting_origin={**ride['origin'],'mode':'exact','radius_miles':0},meeting_destination={**ride['destination'],'mode':'exact','radius_miles':0})
        code,body=self.yelyn.call(f"/api/occurrences/{ride['id']}/request",data)
        self.assertEqual(code,201,body);aid=body['application_id']
        code,body=self.kate.call(f'/api/applications/{aid}/accept',{})
        self.assertEqual(code,200,body);return aid
    def snapshot(self):
        with self.store.read() as db:
            return {t:[tuple(r) for r in db.execute('SELECT * FROM '+t+' ORDER BY id')] for t in ['users','trips','occurrences','applications']}
    def test_fresh_four_tuesdays_no_preconfirmed_booking(self):
        rides=self.rides();self.assertEqual(len(rides),4)
        for r in rides:
            self.assertEqual(dt.date.fromisoformat(r['trip_date']).weekday(),1)
            self.assertEqual(r['departure_hour'],13);self.assertEqual(r['kind'],'regular')
            self.assertEqual(r['price_cents'],400);self.assertEqual(r['confirmed_seats'],0)
            self.assertFalse(r['identity_revealed']);self.assertTrue(r['owner_name'].startswith('Loop Member '))
        with self.store.read() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],5)
            self.assertEqual(db.execute('SELECT count(*) FROM applications a JOIN occurrences o ON o.id=a.occurrence_id WHERE o.trip_id=?',(self.config['trip_id'],)).fetchone()[0],0)
            price=json.loads(db.execute('SELECT price_meta FROM trips').fetchone()[0] or '{}')
            self.assertNotEqual(price.get('mode'),'automatic')
    def test_two_confirmed_dates_passenger_skips_only_one_week(self):
        first,second,*_=self.rides();a=self.book(first);b=self.book(second)
        code,data=self.yelyn.call('/api/my-rides/search',dict(date=first['trip_date'],trip_id=self.config['trip_id']))
        self.assertEqual(code,200,data);r=data['rides'][0]
        self.assertEqual(r['my_role'],'rider');self.assertEqual(r['driver']['name'],'Kate')
        self.assertEqual(r['driver']['vehicle'],'Honda Civic · Blue');self.assertEqual(r['agreed_price_cents'],400)
        code,data=self.yelyn.call(f"/api/occurrences/{first['id']}/skip-week",{})
        self.assertEqual(code,200,data)
        with self.store.read() as db:
            status=dict(db.execute('SELECT id,status FROM applications'))
            self.assertEqual(status[a],'canceled');self.assertEqual(status[b],'confirmed')
            self.assertEqual(db.execute('SELECT status FROM occurrences WHERE id=?',(first['id'],)).fetchone()[0],'active')
        self.assertEqual(len(self.rides(self.kate)),4)
        self.assertEqual(len(self.yelyn.call('/api/my-rides/search',dict(date=second['trip_date'],trip_id=self.config['trip_id']))[1]['rides']),1)
    def test_driver_skip_notifies_and_leaves_later_confirmed_date(self):
        first,second,*_=self.rides();a=self.book(first);b=self.book(second)
        code,data=self.kate.call(f"/api/occurrences/{first['id']}/skip-week",{})
        self.assertEqual(code,200,data)
        with self.store.read() as db:
            status=dict(db.execute('SELECT id,status FROM applications'))
            self.assertEqual(status[a],'canceled');self.assertEqual(status[b],'confirmed')
            self.assertEqual(db.execute('SELECT status FROM occurrences WHERE id=?',(first['id'],)).fetchone()[0],'canceled')
            self.assertTrue(db.execute('SELECT 1 FROM notifications WHERE user_id=(SELECT id FROM users WHERE email=?)',('yelyn@usc.edu',)).fetchone())
        self.assertEqual(len(self.rides()),3)
    def test_restart_never_reopens_canceled_dates_or_changes_passwords(self):
        first=self.rides()[0];self.book(first)
        self.kate.call(f"/api/occurrences/{first['id']}/skip-week",{})
        before=self.snapshot();seed_walkthrough(self.store)
        self.assertEqual(self.snapshot(),before)
        App(self.store,demo_mode=True,seed_data=False)
        self.assertEqual(self.snapshot(),before)
    def test_reset_preserves_accounts_passwords_and_unrelated_rides(self):
        # Post an unrelated offer through the ordinary endpoint.
        first=self.rides()[0]
        code,data=self.kate.call('/api/trips',dict(role='driver',kind='one',origin=first['origin'],destination=first['destination'],start_date=first['trip_date'],departure_hour=15,arrive_by=16,seats=1,price_cents=550,detour_minutes=10,note='Keep this unrelated ride'))
        self.assertEqual(code,201,data);unrelated=data['trip_id']
        with self.store.read() as db:users=[tuple(r) for r in db.execute('SELECT * FROM users ORDER BY id')]
        fresh=seed_walkthrough(self.store,reset=True)
        self.assertNotEqual(fresh['trip_id'],self.config['trip_id'])
        with self.store.read() as db:
            self.assertEqual(users,[tuple(r) for r in db.execute('SELECT * FROM users ORDER BY id')])
            self.assertEqual(db.execute('SELECT status FROM occurrences WHERE trip_id=?',(unrelated,)).fetchone()[0],'active')
            self.assertEqual(db.execute("SELECT count(*) FROM occurrences WHERE trip_id=? AND status='active'",(self.config['trip_id'],)).fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM occurrences WHERE trip_id=? AND status='active'",(fresh['trip_id'],)).fetchone()[0],4)
    def test_existing_email_is_preserved_and_demo_uses_alias(self):
        with tempfile.TemporaryDirectory() as path:
            store=Store(Path(path)/'other.sqlite');password=hash_password('my-existing-password')
            with store.tx() as db:
                db.execute('INSERT INTO users(name,email,password_hash,verified,vehicle) VALUES(?,?,?,1,?)',('Original Yelyn','yelyn@usc.edu',password,'My vehicle'))
            result=seed_walkthrough(store)
            self.assertEqual(result['yelyn_email'],'yelyn.demo@usc.edu')
            with store.read() as db:
                old=db.execute("SELECT * FROM users WHERE email='yelyn@usc.edu'").fetchone()
                self.assertEqual(old['name'],'Original Yelyn');self.assertEqual(old['vehicle'],'My vehicle')
                self.assertEqual(old['password_hash'],password);self.assertTrue(check_password('my-existing-password',old['password_hash']))
    def test_disabled_mode_and_tuesday_boundary(self):
        with tempfile.TemporaryDirectory() as path:
            store=Store(Path(path)/'other.sqlite');App(store,demo_mode=False)
            with store.read() as db:self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],0)
        from app.domain import ZONE
        tuesday=dt.date(2026,10,20)
        with patch('app.demo.today',return_value=tuesday),patch('app.demo.now',return_value=dt.datetime(2026,10,20,12,59,tzinfo=ZONE)):
            self.assertEqual(next_tuesday(),tuesday)
        with patch('app.demo.today',return_value=tuesday),patch('app.demo.now',return_value=dt.datetime(2026,10,20,13,tzinfo=ZONE)):
            self.assertEqual(next_tuesday(),tuesday+dt.timedelta(days=7))

if __name__=='__main__':unittest.main()
