"""Repeatable real HTTP examples, duplicate retries and queue/seat invariants."""
import concurrent.futures
import datetime as dt
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from app.demo import seed_walkthrough, seed_scenarios, walkthrough_config
from app.domain import Store, hash_password, ZONE
from app.server import App, Server
from test_app import Client

class WaitlistWalkthroughTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'db.sqlite')
        seed_walkthrough(self.store);seed_scenarios(self.store)
        self.app=App(self.store,demo_mode=True,seed_data=False);self.http=Server(('127.0.0.1',0),self.app)
        self.thread=threading.Thread(target=self.http.serve_forever,kwargs={'poll_interval':.01},daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.http.server_port);self.clients={}
        config=Client(self.base).call('/api/config')[1]['walkthrough']
        self.cases={c['code']:c for c in config['scenarios']}
        for name,email in config['accounts'].items():
            client=Client(self.base);code,result=client.call('/api/auth/login',dict(email=email,password='heky-local-2026'))
            self.assertEqual(code,200,result);client.csrf=result['csrf'];self.clients[name]=client
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join(2);self.temp.cleanup()
    def rides(self,case,who='kate'):
        code,result=self.clients[who].call('/api/rides/search',dict(trip_id=self.cases[case]['trip_id']))
        self.assertEqual(code,200,result);return sorted(result['rides'],key=lambda r:r['trip_date'])
    def applications(self,who='kate'):
        return self.clients[who].call('/api/applications')[1]['applications']
    def member(self,case,who,date=None):
        return min((a for a in self.applications(who) if a['trip_id']==self.cases[case]['trip_id'] and (date is None or a['trip_date']==date)),key=lambda a:(a['trip_date'],a['id']))
    def status(self,case,who,date=None):return self.member(case,who,date)['status']
    def cancel(self,case,who,week=False):
        a=self.member(case,who)
        path=f"/api/occurrences/{a['occurrence_id']}/skip-week" if week else f"/api/applications/{a['id']}/cancel"
        code,result=self.clients[who].call(path,{})
        self.assertEqual(code,200,result);return result
    def request_data(self,ride,party=1,auto=True):
        return dict(party_size=party,auto_confirm=auto,meeting_origin={**ride['origin'],'mode':'exact','radius_miles':0},meeting_destination={**ride['destination'],'mode':'exact','radius_miles':0})
    def accept(self,case,who):
        a=self.member(case,who);code,result=self.clients['kate'].call(f"/api/applications/{a['id']}/accept",{})
        self.assertEqual(code,200,result);return result
    def check_capacity(self):
        with self.store.read() as db:
            self.assertFalse(db.execute("SELECT o.id FROM occurrences o JOIN applications a ON a.occurrence_id=o.id WHERE a.status='confirmed' GROUP BY o.id HAVING sum(a.party_size)>o.capacity").fetchall())
            self.assertFalse(db.execute('SELECT occurrence_id,requester_id FROM applications GROUP BY occurrence_id,requester_id HAVING count(*)>1').fetchall())
    def test_ten_routes_accounts_and_initial_states(self):
        self.assertEqual(set(self.cases),set('ABCDEFGHIJ'))
        self.assertEqual(len({(c['origin'],c['destination']) for c in self.cases.values()}),10)
        self.assertEqual(len(self.rides('A')),4);self.assertEqual(len(self.rides('B')),4);self.assertEqual(len(self.rides('G')),4)
        self.assertFalse(any(a['trip_id']==self.cases['A']['trip_id'] for a in self.applications('yelyn')))
        for code in ['B','C','D','F','G','H']:
            self.assertEqual(self.status(code,'yelyn'),'confirmed');self.assertEqual(self.status(code,'hannah'),'confirmed')
        self.assertEqual(self.status('B','emily'),'waitlisted');self.assertEqual(self.status('D','emily'),'pending')
        self.assertFalse(self.member('C','emily')['auto_confirm']);self.assertEqual(self.member('F','emily')['party_size'],2)
        self.check_capacity()
    def test_hannah_takes_second_seat_then_emily_waits_in_live_class_flow(self):
        r=self.rides('A')[0]
        for who in ['yelyn','hannah','emily']:
            code,result=self.clients[who].call(f"/api/occurrences/{r['id']}/request",self.request_data(r))
            self.assertEqual(code,201,result);self.accept('A',who)
        self.assertEqual(self.status('A','yelyn'),'confirmed');self.assertEqual(self.status('A','hannah'),'confirmed')
        self.assertEqual(self.status('A','emily'),'waitlisted')
        self.cancel('A','yelyn',week=True);self.assertEqual(self.status('A','emily'),'confirmed')
        self.assertEqual(self.status('A','hannah'),'confirmed');self.check_capacity()
    def test_yelyn_week_cancel_promotes_emily_once_and_preserves_next_week(self):
        dates=self.rides('B');first=dates[0]['trip_date'];later=dates[1]['trip_date']
        aid=self.member('B','emily',first)['id'];self.cancel('B','yelyn',week=True)
        self.assertEqual(self.status('B','emily',first),'confirmed');self.assertEqual(self.status('B','hannah',first),'confirmed')
        self.assertEqual(self.status('B','yelyn',later),'confirmed');self.assertEqual(self.status('B','emily',later),'waitlisted')
        with self.store.read() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM notifications WHERE kind='waitlist_promoted' AND application_id=?",(aid,)).fetchone()[0],1)
        self.assertEqual(len(self.rides('B')),4);self.check_capacity()
    def test_hannah_cancel_also_promotes_emily(self):
        self.cancel('B','hannah',week=True)
        self.assertEqual(self.status('B','emily'),'confirmed');self.assertEqual(self.status('B','yelyn'),'confirmed');self.check_capacity()
    def test_driver_cancel_cancels_waitlist_and_keeps_later_weeks(self):
        first,second,*_=self.rides('G')
        code,result=self.clients['kate'].call(f"/api/occurrences/{first['id']}/skip-week",{})
        self.assertEqual(code,200,result)
        for who in ['yelyn','hannah','emily']:
            self.assertEqual(self.status('G',who,first['trip_date']),'canceled')
        self.assertEqual(self.status('G','emily',second['trip_date']),'waitlisted')
        self.assertEqual(self.status('G','yelyn',second['trip_date']),'confirmed');self.assertEqual(len(self.rides('G')),3)
        self.check_capacity()
    def test_manual_claim_waits_for_explicit_confirmation(self):
        emily=self.member('C','emily')
        self.assertEqual(self.clients['emily'].call(f"/api/applications/{emily['id']}/claim",{})[0],409)
        self.cancel('C','yelyn');self.assertEqual(self.status('C','emily'),'waitlisted')
        code,result=self.clients['emily'].call(f"/api/applications/{emily['id']}/claim",{})
        self.assertEqual(code,200,result);self.assertEqual(self.status('C','emily'),'confirmed');self.check_capacity()
    def test_pending_does_not_promote_until_approved(self):
        self.cancel('D','yelyn');self.assertEqual(self.status('D','emily'),'pending')
        self.accept('D','emily');self.assertEqual(self.status('D','emily'),'confirmed');self.check_capacity()
    def test_decline_and_reapply_reuses_single_request(self):
        a=self.member('D','emily');r=self.rides('D')[0]
        self.assertEqual(self.clients['kate'].call(f"/api/applications/{a['id']}/decline",{})[0],200)
        code,result=self.clients['emily'].call(f"/api/occurrences/{r['id']}/request",self.request_data(r))
        self.assertEqual(code,201,result);self.assertEqual(result['application_id'],a['id']);self.assertEqual(self.status('D','emily'),'pending')
        self.check_capacity()
    def test_queue_order_and_sequential_promotions(self):
        self.cancel('E','yelyn');self.assertEqual(self.status('E','hannah'),'confirmed');self.assertEqual(self.status('E','emily'),'waitlisted')
        self.cancel('E','hannah');self.assertEqual(self.status('E','emily'),'confirmed');self.check_capacity()
    def test_whole_party_is_never_split_and_smaller_party_can_fit(self):
        self.cancel('F','yelyn');self.assertEqual(self.status('F','emily'),'waitlisted');self.assertEqual(self.status('F','noah'),'confirmed')
        self.cancel('F','hannah');self.assertEqual(self.status('F','emily'),'waitlisted')
        self.cancel('F','noah');self.assertEqual(self.status('F','emily'),'confirmed')
        self.assertEqual(self.rides('F')[0]['confirmed_seats'],2);self.check_capacity()
    def test_round_trip_has_one_booking_for_both_legs(self):
        self.assertEqual(self.rides('H')[0]['kind'],'round')
        a=self.member('H','emily');self.cancel('H','yelyn')
        matched=self.member('H','emily');self.assertEqual(matched['id'],a['id']);self.assertEqual(matched['status'],'confirmed')
        self.assertEqual(matched['total_price_cents'],400);self.check_capacity()
    def test_withdraw_then_rejoin_goes_to_back_without_duplicate(self):
        a=self.member('I','emily');self.cancel('I','emily');r=self.rides('I')[0]
        code,result=self.clients['emily'].call(f"/api/occurrences/{r['id']}/request",self.request_data(r))
        self.assertEqual(code,201,result);self.assertEqual(result['application_id'],a['id']);self.accept('I','emily')
        self.assertEqual(self.member('I','hannah')['waitlist_position'],1);self.assertEqual(self.member('I','emily')['waitlist_position'],2)
        self.cancel('I','yelyn');self.assertEqual(self.status('I','hannah'),'confirmed');self.assertEqual(self.status('I','emily'),'waitlisted');self.check_capacity()
    def test_rider_post_accepts_one_driver_and_restores_other_offer_after_cancel(self):
        r=self.rides('J')[0];offers={}
        for who in ['kate','noah']:
            code,result=self.clients[who].call(f"/api/occurrences/{r['id']}/request",self.request_data(r,auto=False))
            self.assertEqual(code,201,result);offers[who]=result['application_id']
        self.assertEqual(self.clients['yelyn'].call(f"/api/applications/{offers['kate']}/accept",{})[0],200)
        self.assertEqual(self.status('J','noah'),'declined')
        self.assertEqual(self.clients['kate'].call(f"/api/applications/{offers['kate']}/cancel",{})[0],200)
        self.assertEqual(self.status('J','noah'),'pending');self.check_capacity()
    def test_accepted_driver_offer_retry_reuses_existing_booking(self):
        r=self.rides('J')[0];path=f"/api/occurrences/{r['id']}/request";data=self.request_data(r,auto=False)
        code,result=self.clients['kate'].call(path,data);self.assertEqual(code,201,result)
        aid=result['application_id'];self.assertEqual(self.clients['yelyn'].call(f'/api/applications/{aid}/accept',{})[0],200)
        code,result=self.clients['kate'].call(path,data)
        self.assertEqual(code,200,result);self.assertEqual(result['application_id'],aid);self.assertEqual(result['status'],'confirmed')
        self.assertEqual(self.clients['noah'].call(path,data)[0],409);self.check_capacity()

    def test_parallel_identical_requests_create_one_row_and_one_event(self):
        r=self.rides('A')[0];data=self.request_data(r);path=f"/api/occurrences/{r['id']}/request"
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.clients['emily'].call(path,data),range(8)))
        self.assertEqual(sum(code==201 for code,_ in results),1)
        self.assertEqual(sum(code==200 for code,_ in results),7)
        self.assertEqual(len({body['application_id'] for _,body in results}),1)
        with self.store.read() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM applications WHERE occurrence_id=?',(r['id'],)).fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM events WHERE occurrence_id=? AND message LIKE '%sent a seat request%'",(r['id'],)).fetchone()[0],1)
        self.check_capacity()
    def test_retry_waitlisted_request_preserves_queue_price_and_events(self):
        a=self.member('I','emily');r=self.rides('I')[0]
        with self.store.read() as db:before=dict(db.execute('SELECT * FROM applications WHERE id=?',(a['id'],)).fetchone());events=db.execute('SELECT count(*) FROM events').fetchone()[0]
        code,result=self.clients['emily'].call(f"/api/occurrences/{r['id']}/request",self.request_data(r))
        self.assertEqual(code,200,result);self.assertEqual(result['application_id'],a['id']);self.assertEqual(result['status'],'waitlisted')
        with self.store.read() as db:
            self.assertEqual(dict(db.execute('SELECT * FROM applications WHERE id=?',(a['id'],)).fetchone()),before)
            self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],events)
        bad=self.request_data(r);bad['auto_confirm']=False
        self.assertEqual(self.clients['emily'].call(f"/api/occurrences/{r['id']}/request",bad)[0],409)
    def test_restart_and_selective_reset_preserve_other_examples_and_passwords(self):
        self.cancel('B','yelyn',week=True)
        with self.store.read() as db:
            users=[tuple(r) for r in db.execute('SELECT * FROM users ORDER BY id')]
            apps=[tuple(r) for r in db.execute('SELECT * FROM applications ORDER BY id')]
        seed_scenarios(self.store)
        with self.store.read() as db:self.assertEqual(apps,[tuple(r) for r in db.execute('SELECT * FROM applications ORDER BY id')])
        old=self.cases['B']['trip_id'];seed_scenarios(self.store,reset=True,only='B')
        with self.store.read() as db:
            new=walkthrough_config(db);self.assertEqual(users,[tuple(r) for r in db.execute('SELECT * FROM users ORDER BY id')])
            self.assertNotEqual(next(c['trip_id'] for c in new['scenarios'] if c['code']=='B'),old)
            self.assertEqual(next(c['trip_id'] for c in new['scenarios'] if c['code']=='C'),self.cases['C']['trip_id'])
            self.assertEqual(db.execute("SELECT count(*) FROM occurrences WHERE trip_id=? AND status='active'",(old,)).fetchone()[0],0)
        self.check_capacity()
    def test_existing_231_walkthrough_and_colliding_account_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'older.sqlite');main=seed_walkthrough(store);password=hash_password('keep-this-password')
            with store.tx() as db:db.execute('INSERT INTO users(name,email,password_hash,verified) VALUES(?,?,?,1)',('My Hannah','hannah@usc.edu',password))
            added=seed_scenarios(store)
            self.assertEqual(added['accounts']['hannah']['email'],'hannah.demo@usc.edu')
            with store.read() as db:
                self.assertEqual(db.execute("SELECT password_hash FROM users WHERE email='hannah@usc.edu'").fetchone()[0],password)
                self.assertEqual(walkthrough_config(db)['trip_id'],main['trip_id'])
    def test_mid_tuesday_start_keeps_every_example_future(self):
        moment=dt.datetime(2026,10,20,10,tzinfo=ZONE)
        with tempfile.TemporaryDirectory() as folder,patch('app.demo.now',return_value=moment),patch('app.demo.today',return_value=moment.date()),patch('app.domain.now',return_value=moment):
            store=Store(Path(folder)/'midday.sqlite');seed_walkthrough(store);result=seed_scenarios(store)
            cases={c['code']:c for c in result['scenarios']}
            self.assertEqual(cases['C']['first_date'],'2026-10-27')
            self.assertEqual(cases['I']['first_date'],'2026-10-20')
            with store.read() as db:
                for row in db.execute('SELECT o.trip_date,t.departure_hour FROM occurrences o JOIN trips t ON t.id=o.trip_id'):
                    self.assertGreater(dt.datetime.combine(dt.date.fromisoformat(row['trip_date']),dt.time(row['departure_hour']),ZONE),moment)

    def test_trip_filter_is_exact_and_validated(self):
        for case in self.cases.values():
            code,result=self.clients['kate'].call('/api/rides/search',dict(trip_id=case['trip_id']))
            self.assertEqual(code,200,result);self.assertTrue(all(r['trip_id']==case['trip_id'] for r in result['rides']))
        for value in [-1,'bogus']:
            self.assertEqual(self.clients['kate'].call('/api/rides/search',dict(trip_id=value))[0],422)
        self.assertTrue(all(r['trip_id']==self.cases['B']['trip_id'] for r in self.clients['yelyn'].call('/api/my-rides/search',dict(trip_id=self.cases['B']['trip_id']))[1]['rides']))

if __name__=='__main__':unittest.main()
