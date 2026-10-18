"""Whole-period enrollment through production HTTP endpoints and SQLite."""
import concurrent.futures
import datetime as dt
import json
from pathlib import Path
import shutil
import subprocess
import unittest
import test_live as base
from app.domain import Store
from test_app import Client


class RecurringTests(unittest.TestCase):
    setUp=base.LiveTests.setUp
    tearDown=base.LiveTests.tearDown
    router=base.LiveTests.router
    class_rides=base.LiveTests.class_rides
    date_request=base.LiveTests.request
    date_accept=base.LiveTests.accept

    def join(self,who='yelyn',ride=None,**changes):
        ride=ride or self.class_rides()[0]
        data=dict(party_size=1,auto_confirm=True,meeting_origin={**ride['origin'],'mode':'exact','radius_miles':0},meeting_destination={**ride['destination'],'mode':'exact','radius_miles':0})
        data.update(changes)
        code,result=self.clients[who].call(f"/api/occurrences/{ride['id']}/request",data)
        self.assertIn(code,(200,201),result);return result

    def accept(self,aid,owner='kate'):
        code,quote=self.clients[owner].call(f'/api/applications/{aid}/price',{});self.assertEqual(code,200,quote)
        self.assertIn('series',quote)
        code,result=self.clients[owner].call(f'/api/applications/{aid}/accept',dict(expected_series_token=quote['series']['review_token']))
        self.assertEqual(code,200,result);return result

    def records(self,who='yelyn',sid=None):
        rows=self.clients[who].call('/api/applications')[1]['applications']
        return sorted([r for r in rows if sid is None or r['recurring_id']==sid],key=lambda r:r['trip_date'])

    def test_one_request_and_one_approval_books_entire_declared_period(self):
        rides=self.class_rides();schedule=rides[0]['recurring_schedule']
        self.assertEqual(schedule['start_date'],rides[0]['start_date']);self.assertEqual(schedule['end_date'],rides[0]['end_date'])
        self.assertEqual(schedule['date_count'],4)
        joined=self.join(ride=rides[-1]);sid=joined['recurring_id'];self.assertIsNotNone(sid)
        rows=self.records(sid=sid);self.assertEqual(len(rows),4);self.assertTrue(all(r['status']=='pending' for r in rows))
        self.assertTrue(all(not r['identity_revealed'] for r in rows))
        approved=self.accept(joined['application_id']);self.assertEqual(approved['series']['counts']['confirmed'],4)
        rows=self.records(sid=sid);self.assertTrue(all(r['status']=='confirmed' and r['owner_name']=='Kate' for r in rows))
        my=self.clients['yelyn'].call('/api/my-rides/search',{})[1]['rides']
        self.assertEqual(len([r for r in my if r['trip_id']==rides[0]['trip_id']]),4)
        for ride in my:
            if ride['trip_id']==rides[0]['trip_id']:self.assertEqual(ride['driver']['name'],'Kate');self.assertEqual(ride['agreed_price_cents'],1200)

    def test_duplicate_parallel_join_and_approval_are_idempotent(self):
        ride=self.class_rides()[0];client=self.clients['yelyn']
        data=dict(party_size=1,auto_confirm=True,meeting_origin={**ride['origin'],'mode':'exact','radius_miles':0},meeting_destination={**ride['destination'],'mode':'exact','radius_miles':0})
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:client.call(f"/api/occurrences/{ride['id']}/request",data),range(4)))
        self.assertEqual(sum(code==201 for code,_ in results),1)
        self.assertEqual(len({r['recurring_id'] for _,r in results}),1)
        aid=results[0][1]['application_id'];self.accept(aid)
        with self.store.read() as db:
            before=[tuple(r) for r in db.execute('SELECT * FROM applications ORDER BY id')]
            events=db.execute('SELECT count(*) FROM events').fetchone()[0]
        self.accept(aid);self.join()
        with self.store.read() as db:
            self.assertEqual(before,[tuple(r) for r in db.execute('SELECT * FROM applications ORDER BY id')])
            self.assertEqual(events,db.execute('SELECT count(*) FROM events').fetchone()[0])
            self.assertEqual(db.execute('SELECT count(*) FROM recurring_requests').fetchone()[0],1)

    def test_week_cancel_promotes_emily_only_that_week_and_keeps_later_bookings(self):
        joins={}
        for who in ('yelyn','hannah','emily'):
            joins[who]=self.join(who);self.accept(joins[who]['application_id'])
        self.assertEqual([r['status'] for r in self.records('emily')],['waitlisted']*4)
        rides=self.class_rides();code,result=self.clients['yelyn'].call(f"/api/occurrences/{rides[0]['id']}/skip-week",{});self.assertEqual(code,200,result)
        self.assertEqual([r['status'] for r in self.records()],['canceled']+['confirmed']*3)
        self.assertEqual([r['status'] for r in self.records('emily')],['confirmed']+['waitlisted']*3)
        self.join();self.assertEqual(self.records()[0]['status'],'canceled')
        code,result=self.clients['kate'].call(f"/api/occurrences/{rides[1]['id']}/skip-week",{});self.assertEqual(code,200,result)
        for who in ('yelyn','hannah','emily'):
            rows=self.records(who);self.assertEqual(rows[1]['status'],'canceled')
            self.assertEqual(rows[2]['status'],'waitlisted' if who=='emily' else 'confirmed')

    def test_full_date_waitlists_only_that_date_and_preserves_other_confirmations(self):
        first=self.class_rides()[0]
        for who in ('hannah','emily'):self.date_accept(self.date_request(who,first))
        joined=self.join();result=self.accept(joined['application_id'])
        self.assertEqual(result['series']['counts']['confirmed'],3);self.assertEqual(result['series']['counts']['waitlisted'],1)
        self.assertEqual([r['status'] for r in self.records()],['waitlisted']+['confirmed']*3)
        emily=self.records('emily')[0]
        code,result=self.clients['emily'].call(f"/api/applications/{emily['id']}/cancel",{});self.assertEqual(code,200,result)
        self.assertEqual([r['status'] for r in self.records()],['confirmed']*4)
        self.assertEqual([r['agreed_price_cents'] for r in self.records()],[990,1200,1200,1200])

    def test_change_on_another_date_invalidates_review_without_partial_approval(self):
        rides=self.class_rides();joined=self.join();aid=joined['application_id']
        code,quote=self.clients['kate'].call(f'/api/applications/{aid}/price',{});self.assertEqual(code,200,quote)
        self.date_accept(self.date_request('hannah',rides[-1]))
        code,result=self.clients['kate'].call(f'/api/applications/{aid}/accept',dict(expected_series_token=quote['series']['review_token']))
        self.assertEqual(code,409,result);self.assertTrue(all(r['status']=='pending' for r in self.records()))
        self.accept(aid);self.assertEqual([r['agreed_price_cents'] for r in self.records()],[1200,1200,1200,990])

    def test_any_unpriced_date_blocks_all_requests_atomically(self):
        last=self.class_rides()[-1]
        with self.store.tx() as db:
            override=json.loads(db.execute('SELECT overrides FROM occurrences WHERE id=?',(last['id'],)).fetchone()[0])
            override.update(price_cents=0,price_meta=dict(mode='automatic',status='error',notice='Google unavailable'))
            db.execute('UPDATE occurrences SET overrides=? WHERE id=?',(json.dumps(override),last['id']))
        first=self.class_rides()[0]
        code,result=self.clients['yelyn'].call(f"/api/occurrences/{first['id']}/request",dict(party_size=1,auto_confirm=True,meeting_origin={**first['origin'],'mode':'exact','radius_miles':0},meeting_destination={**first['destination'],'mode':'exact','radius_miles':0}))
        self.assertEqual(code,503,result)
        with self.store.read() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM applications').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM recurring_requests').fetchone()[0],0)

    def test_unavailable_quote_during_approval_keeps_entire_period_pending(self):
        joined=self.join();last=self.class_rides()[-1]
        with self.store.tx() as db:
            override=json.loads(last['overrides']);override.update(price_cents=0,price_meta=dict(mode='automatic',status='error',notice='Google unavailable'))
            db.execute('UPDATE occurrences SET overrides=? WHERE id=?',(json.dumps(override),last['id']))
        code,result=self.clients['kate'].call(f"/api/applications/{joined['application_id']}/accept",dict(expected_series_token='stale'))
        self.assertEqual(code,503,result);self.assertTrue(all(r['status']=='pending' for r in self.records()))

    def test_decline_reapply_and_withdraw_affect_remaining_period_once(self):
        joined=self.join();aid=joined['application_id'];sid=joined['recurring_id']
        code,result=self.clients['kate'].call(f'/api/applications/{aid}/decline',{});self.assertEqual(code,200,result)
        self.assertTrue(all(r['status']=='declined' for r in self.records()))
        ids=[r['id'] for r in self.records()];again=self.join();self.assertEqual(again['recurring_id'],sid)
        self.assertEqual(ids,[r['id'] for r in self.records()]);self.accept(aid)
        for who in ('hannah','emily'):j=self.join(who);self.accept(j['application_id'])
        code,result=self.clients['yelyn'].call(f'/api/recurring/{sid}/withdraw',{});self.assertEqual(code,200,result)
        self.assertEqual(len(result['canceled_application_ids']),4)
        self.assertTrue(all(r['status']=='confirmed' for r in self.records('emily')))
        code,result=self.clients['yelyn'].call(f'/api/recurring/{sid}/withdraw',{});self.assertEqual(code,200,result);self.assertEqual(result['canceled_application_ids'],[])

    def test_existing_single_date_booking_can_join_period_without_resetting_it(self):
        first=self.class_rides()[0];aid=self.date_request('yelyn',first);self.date_accept(aid)
        joined=self.join();self.assertEqual(joined['application_id'],aid)
        self.assertEqual([r['status'] for r in self.records()],['confirmed']+['pending']*3)
        self.accept(aid);self.assertTrue(all(r['status']=='confirmed' for r in self.records()))
        with self.store.read() as db:self.assertEqual(db.execute('SELECT count(*) FROM applications').fetchone()[0],4)
        Store(self.store.path)
        self.assertTrue(all(r['status']=='confirmed' for r in self.records()))

    def test_requester_cannot_approve_and_other_rider_cannot_withdraw(self):
        joined=self.join();aid=joined['application_id'];sid=joined['recurring_id']
        code,result=self.clients['yelyn'].call(f'/api/applications/{aid}/accept',dict(expected_series_token='wrong'));self.assertEqual(code,403,result)
        code,result=self.clients['hannah'].call(f'/api/recurring/{sid}/withdraw',{});self.assertEqual(code,403,result)
        self.assertTrue(all(r['status']=='pending' for r in self.records()))

    def test_canceled_and_past_dates_are_excluded_and_date_filters_still_work(self):
        rides=self.class_rides()
        with self.store.tx() as db:db.execute('UPDATE occurrences SET trip_date=? WHERE id=?',(str(dt.date.fromisoformat(rides[0]['trip_date'])-dt.timedelta(days=14)),rides[0]['id']))
        code,result=self.clients['kate'].call(f"/api/occurrences/{rides[1]['id']}/cancel",{});self.assertEqual(code,200,result)
        joined=self.join(ride=rides[-1]);self.accept(joined['application_id']);self.assertEqual(len(self.records()),2)
        code,result=self.clients['yelyn'].call('/api/my-rides/search',dict(date=rides[-1]['trip_date']))
        self.assertEqual(code,200,result);self.assertEqual(len(result['rides']),1)
        self.assertEqual(result['rides'][0]['id'],rides[-1]['id'])

    def test_competing_series_approvals_never_overbook_a_date(self):
        for who in ('yelyn','hannah','emily'):self.join(who)
        rows={who:self.records(who)[0] for who in ('yelyn','hannah','emily')}
        self.accept(rows['yelyn']['id'])
        quotes={who:self.clients['kate'].call(f"/api/applications/{rows[who]['id']}/price",{})[1] for who in ('hannah','emily')}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda who:self.clients['kate'].call(f"/api/applications/{rows[who]['id']}/accept",dict(expected_series_token=quotes[who]['series']['review_token'])),('hannah','emily')))
        self.assertCountEqual([c for c,_ in results],[200,409])
        loser='hannah' if results[0][0]==409 else 'emily';self.accept(rows[loser]['id'])
        self.assertTrue(all(r['status']=='waitlisted' for r in self.records(loser)))
        self.assertTrue(all(r['confirmed_seats']==2 for r in self.class_rides()))

    def test_upgrading_existing_confirmed_request_extends_period_and_preserves_week_exception(self):
        from app.recurring import MIGRATION_KEY
        from app.server import App
        rides=self.class_rides();aid=self.date_request('yelyn',rides[0]);self.date_accept(aid)
        skipped=self.date_request('yelyn',rides[1]);self.date_accept(skipped)
        code,result=self.clients['yelyn'].call(f"/api/occurrences/{rides[1]['id']}/skip-week",{});self.assertEqual(code,200,result)
        with self.store.tx() as db:
            db.execute('DELETE FROM app_settings WHERE key=?',(MIGRATION_KEY,))
            before=db.execute('SELECT agreed_price_cents,created_at FROM applications WHERE id=?',(aid,)).fetchone()
        updated=App(self.store,demo_mode=True,routes=self.router(self.store))
        if updated.google_prices.thread:updated.google_prices.thread.join(5)
        rows=self.records();self.assertEqual([r['status'] for r in rows],['confirmed','canceled','confirmed','confirmed'])
        self.assertTrue(rows[0]['recurring_id']);self.assertEqual(rows[0]['id'],aid)
        with self.store.read() as db:
            self.assertEqual(tuple(before),tuple(db.execute('SELECT agreed_price_cents,created_at FROM applications WHERE id=?',(aid,)).fetchone()))
            count=db.execute('SELECT count(*) FROM applications').fetchone()[0]
        updated=App(self.store,demo_mode=True,routes=self.router(self.store))
        with self.store.read() as db:self.assertEqual(db.execute('SELECT count(*) FROM applications').fetchone()[0],count)

    def test_upgrading_pending_request_requests_all_dates_without_confirming_them(self):
        from app.recurring import MIGRATION_KEY
        from app.server import App
        aid=self.date_request('yelyn',self.class_rides()[0])
        with self.store.tx() as db:db.execute('DELETE FROM app_settings WHERE key=?',(MIGRATION_KEY,))
        updated=App(self.store,demo_mode=True,routes=self.router(self.store))
        if updated.google_prices.thread:updated.google_prices.thread.join(5)
        rows=self.records();self.assertEqual(len(rows),4);self.assertTrue(all(r['status']=='pending' for r in rows))
        self.assertEqual(rows[0]['id'],aid);self.accept(aid)
        self.assertTrue(all(r['status']=='confirmed' for r in self.records()))

    def test_legacy_extension_waits_for_google_prices_and_completes_after_retry(self):
        from app.recurring import MIGRATION_KEY
        from app.server import App
        first=self.class_rides()[0];aid=self.date_request('yelyn',first);self.date_accept(aid)
        with self.store.tx() as db:
            db.execute('DELETE FROM app_settings WHERE key=?',(MIGRATION_KEY,))
            for ride in self.class_rides():
                override=json.loads(ride['overrides']);override.update(price_cents=0,price_meta=dict(mode='automatic',status='pending'))
                db.execute('UPDATE occurrences SET overrides=? WHERE id=?',(json.dumps(override),ride['id']))
        self.error=True;updated=App(self.store,demo_mode=True,routes=self.router(self.store));updated.google_prices.thread.join(5)
        self.assertEqual(len(self.records()),1);self.assertIsNone(self.records()[0]['recurring_id'])
        self.error=False;updated.google_prices.start();updated.google_prices.thread.join(5)
        self.assertEqual(len(self.records()),4);self.assertTrue(all(r['status']=='confirmed' for r in self.records()))

    def test_nonrecurring_requests_still_apply_to_one_date(self):
        for key in ('library','round'):
            rides=self.clients['yelyn'].call('/api/rides/search',dict(trip_id=self.catalog['routes'][key]))[1]['rides']
            joined=self.join(ride=rides[0]);self.assertIsNone(joined['recurring_id'])
        with self.store.read() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM recurring_requests').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM applications').fetchone()[0],2)

    def test_party_is_never_split_across_undersized_dates(self):
        self.join('hannah');self.accept(self.records('hannah')[0]['id'])
        joined=self.join(party_size=2);result=self.accept(joined['application_id'])
        self.assertEqual(result['series']['counts']['waitlisted'],4)
        self.assertTrue(all(r['confirmed_seats']==1 for r in self.class_rides()))
        hannah=self.records('hannah')[0]
        code,result=self.clients['hannah'].call(f"/api/occurrences/{hannah['occurrence_id']}/skip-week",{});self.assertEqual(code,200,result)
        self.assertEqual([r['status'] for r in self.records()],['confirmed']+['waitlisted']*3)
        self.assertEqual(self.class_rides()[0]['confirmed_seats'],2)

    def test_recurring_driver_offer_is_accepted_for_the_whole_rider_post(self):
        from app.domain import trip_create
        first=self.class_rides()[0]
        with self.store.tx() as db:
            owner=dict(db.execute("SELECT * FROM users WHERE email='yelyn@usc.edu'").fetchone())
            tid=trip_create(db,owner,dict(role='rider',kind='regular',origin=first['origin'],destination=first['destination'],
                start_date=first['start_date'],end_date=first['end_date'],departure_hour=13,arrive_by=14,seats=2,weekdays=[1],
                price_cents=0,detour_minutes=10,note='Recurring rider request',_price_meta=dict(mode='automatic',status='pending')))
        self.app.google_prices.start();self.app.google_prices.thread.join(5)
        ride=self.clients['kate'].call('/api/rides/search',dict(trip_id=tid))[1]['rides'][0]
        kate=self.join('kate',ride);noah=self.join('noah',ride)
        approved=self.accept(kate['application_id'],owner='yelyn');self.assertEqual(approved['series']['counts']['confirmed'],4)
        with self.store.read() as db:
            drivers=[r[0] for r in db.execute('SELECT driver_id FROM occurrences WHERE trip_id=?',(tid,))]
            self.assertEqual(len(set(drivers)),1)
            self.assertTrue(all(r[0]=='declined' for r in db.execute('SELECT status FROM applications WHERE recurring_id=?',(noah['recurring_id'],))))
        self.assertTrue(all(r['my_role']=='driver' for r in self.clients['kate'].call('/api/my-rides/search',dict(trip_id=tid))[1]['rides']))

    @unittest.skipUnless(shutil.which('node'),'Node is optional for handler checks')
    def test_recurring_frontend_requests_and_approves_once_for_all_dates(self):
        sessions={}
        for name,c in self.clients.items():
            me=c.call('/api/me')[1];sessions[name]=dict(cookie='; '.join(k.name+'='+k.value for k in c.jar),csrf=c.csrf,user=me['user'])
        root=Path(__file__).resolve().parents[1]
        payload=dict(base=self.base,sessions=sessions,js=str(root/'static/app.js'))
        result=subprocess.run(['node',str(root/'tests/recurring_frontend.cjs')],input=json.dumps(payload),text=True,capture_output=True,timeout=40)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr);self.assertIn('PASS:',result.stdout)

if __name__=='__main__':unittest.main()
