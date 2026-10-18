"""Recurring enrollment with per-date seats, quotes and cancellation exceptions."""
import hashlib
import json
from .domain import (Problem, joined_occurrence, ensure_open, now, today, request_ride,
                     decide, cancel_application, require, integer, fixed_point, boolean)
from .pricing import occurrence_pricing, require_price, price_status, summary as price_summary


def future_dates(db,trip_id):
    output=[]
    for row in db.execute("SELECT id FROM occurrences WHERE trip_id=? AND trip_date>=? AND status='active' ORDER BY trip_date,id",(trip_id,str(today()))).fetchall():
        ride=joined_occurrence(db,row['id'])
        try:ensure_open(ride)
        except Problem:continue
        output.append(ride)
    return output


def schedule(db,trip_id):
    trip=db.execute('SELECT start_date,end_date,weekdays FROM trips WHERE id=?',(trip_id,)).fetchone()
    dates=[]
    for ride in future_dates(db,trip_id):
        meta=json.loads(ride['price_meta']);state=price_status(meta)
        dates.append(dict(occurrence_id=ride['id'],trip_date=ride['trip_date'],departure_hour=ride['departure_hour'],
            pricing_status=state,pricing=price_summary(meta,ride['capacity']) if meta.get('model')=='google_shared_v1' else None,
            price_cents=ride['price_cents'] if state['ready'] else None))
    return dict(start_date=trip['start_date'],end_date=trip['end_date'],weekdays=json.loads(trip['weekdays']),
        dates=dates,date_count=len(dates),ready=bool(dates) and all(d['pricing_status']['ready'] for d in dates))


def enroll(db,user,oid,data):
    require(user['verified'],'Verify your student email first.',403)
    selected=joined_occurrence(db,oid);ensure_open(selected)
    require(selected['role']!='rider' or bool(user['vehicle'].strip()),'Add your vehicle before offering to drive.')
    require(selected['kind']=='regular','This post is not a recurring ride.')
    require(selected['owner_id']!=user['id'],'You cannot request your own post.',409)
    party=integer(data,'party_size',1,4,1) if selected['role']=='driver' else selected['seats']
    auto=boolean(data,'auto_confirm') if selected['role']=='driver' else False
    origin=fixed_point(data.get('meeting_origin'),json.loads(selected['origin']))
    destination=fixed_point(data.get('meeting_destination'),json.loads(selected['destination']))
    existing=db.execute('SELECT * FROM recurring_requests WHERE trip_id=? AND requester_id=?',(selected['trip_id'],user['id'])).fetchone()
    if existing and existing['status'] in ('pending','approved'):
        same=existing['party_size']==party and bool(existing['auto_confirm'])==auto and json.loads(existing['meeting_origin'])==origin and json.loads(existing['meeting_destination'])==destination
        require(same,'Withdraw the recurring request before changing its party or meeting points.',409)
        # A retry must never re-open a deliberately canceled week or move a queue.
        application=db.execute('SELECT id FROM applications WHERE recurring_id=? ORDER BY (occurrence_id=?) DESC,id LIMIT 1',(existing['id'],oid)).fetchone()
        require(application is not None,'Recurring request has no dates.',409)
        return application['id'],existing['id'],True
    dates=future_dates(db,selected['trip_id'])
    require(dates,'This recurring ride has no future dates.',409)
    for ride in dates:require_price(ride)
    values=(party,int(auto),json.dumps(origin),json.dumps(destination),now().timestamp())
    if existing:
        sid=existing['id']
        db.execute("UPDATE recurring_requests SET status='pending',party_size=?,auto_confirm=?,meeting_origin=?,meeting_destination=?,created_at=? WHERE id=?",(*values,sid))
    else:
        sid=db.execute("INSERT INTO recurring_requests(trip_id,requester_id,status,party_size,auto_confirm,meeting_origin,meeting_destination,created_at) VALUES(?,?,'pending',?,?,?,?,?)",(selected['trip_id'],user['id'],*values)).lastrowid
    ids={}
    for ride in dates:
        prior=db.execute('SELECT * FROM applications WHERE occurrence_id=? AND requester_id=?',(ride['id'],user['id'])).fetchone()
        # When joining a period around existing bookings, preserve explicit weekly exceptions.
        if prior and prior['status']=='canceled' and not (existing and existing['status']=='canceled'):
            continue
        aid=request_ride(db,user,ride['id'],dict(data,party_size=party,auto_confirm=auto,
            meeting_origin=origin,meeting_destination=destination))
        db.execute('UPDATE applications SET recurring_id=? WHERE id=?',(sid,aid));ids[ride['id']]=aid
    require(ids,'No future dates remain to request. Post a new ride request instead.',409)
    return ids.get(oid,next(iter(ids.values()))),sid,False


def series_info(db,sid,*,review=False):
    parent=db.execute('SELECT r.*,t.owner_id,t.start_date,t.end_date,t.weekdays FROM recurring_requests r JOIN trips t ON t.id=r.trip_id WHERE r.id=?',(sid,)).fetchone()
    require(parent is not None,'Recurring request not found.',404)
    dates=[];fingerprint=[]
    for a in db.execute('SELECT a.*,o.trip_date FROM applications a JOIN occurrences o ON o.id=a.occurrence_id WHERE recurring_id=? ORDER BY o.trip_date,a.id',(sid,)).fetchall():
        ride=joined_occurrence(db,a['occurrence_id'])
        try:ensure_open(ride);upcoming=True
        except Problem:upcoming=False
        pricing=occurrence_pricing(db,ride,a['party_size'] if a['status'] in ('pending','waitlisted') else 0)
        if review and upcoming and a['status']=='pending':require_price(ride)
        state=price_status(ride['price_meta'])
        dates.append(dict(application_id=a['id'],occurrence_id=ride['id'],trip_date=ride['trip_date'],departure_hour=ride['departure_hour'],
            status=a['status'],upcoming=upcoming,pricing=pricing,pricing_status=state,
            price_cents=pricing['rider_price_cents'] if pricing else a['agreed_price_cents'] if state['ready'] else None))
        fingerprint.append([upcoming,a['id'],a['created_at'],a['meeting_origin'],a['meeting_destination'],a['status'],a['party_size'],a['auto_confirm'],ride['status'],ride['capacity'],ride['driver_id'],
            ride['trip_date'],ride['departure_hour'],ride['origin'],ride['destination'],ride['price_meta'],pricing])
    counts={status:sum(d['status']==status and d['upcoming'] for d in dates) for status in ('pending','confirmed','waitlisted','canceled','declined')}
    token=hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest()
    return dict(id=sid,status=parent['status'],start_date=parent['start_date'],end_date=parent['end_date'],
        weekdays=json.loads(parent['weekdays']),date_count=len(dates),dates=dates,counts=counts,review_token=token)


def approve(db,user,sid,accept,token=None):
    parent=db.execute('SELECT r.*,t.owner_id FROM recurring_requests r JOIN trips t ON t.id=r.trip_id WHERE r.id=?',(sid,)).fetchone()
    require(parent is not None,'Recurring request not found.',404)
    require(parent['owner_id']==user['id'],'Only the post owner can approve this recurring request.',403)
    info=series_info(db,sid,review=accept)
    targets=[d for d in info['dates'] if d['upcoming'] and d['status']=='pending']
    if not targets:
        require(parent['status']==('approved' if accept else 'declined'),'No undecided dates remain in this recurring request.',409)
        return info
    if accept:require(token==info['review_token'],'A date, price or rider count changed. Review all recurring dates and confirm again.',409)
    for item in targets:
        # decide() rechecks capacity and competing driver offers under the same write transaction.
        decide(db,user,item['application_id'],accept)
    db.execute('UPDATE recurring_requests SET status=? WHERE id=?',('approved' if accept else 'declined',sid))
    return series_info(db,sid)


def withdraw(db,user,sid):
    parent=db.execute('SELECT * FROM recurring_requests WHERE id=?',(sid,)).fetchone()
    require(parent is not None,'Recurring request not found.',404)
    require(parent['requester_id']==user['id'],'Only the requester can withdraw this recurring ride.',403)
    canceled=[];promoted=[]
    for item in series_info(db,sid)['dates']:
        if item['upcoming'] and item['status'] in ('pending','confirmed','waitlisted'):
            promoted.extend(cancel_application(db,user,item['application_id']));canceled.append(item['application_id'])
    db.execute("UPDATE recurring_requests SET status='canceled' WHERE id=?",(sid,))
    return dict(canceled_application_ids=canceled,promoted_application_ids=promoted)


MIGRATION_KEY='recurring:period-upgrade:v1'


def prepare_upgrade(store):
    """Capture only pre-upgrade active requests; never reinterpret later date-only requests."""
    with store.tx() as db:
        if db.execute('SELECT 1 FROM app_settings WHERE key=?',(MIGRATION_KEY,)).fetchone():return
        groups={}
        for row in db.execute("SELECT a.id,a.occurrence_id,a.requester_id,o.trip_id,a.status FROM applications a JOIN occurrences o ON o.id=a.occurrence_id JOIN trips t ON t.id=o.trip_id WHERE t.kind='regular' AND a.recurring_id IS NULL AND a.status IN ('pending','confirmed','waitlisted') ORDER BY a.id").fetchall():
            ride=joined_occurrence(db,row['occurrence_id'])
            try:ensure_open(ride)
            except Problem:continue
            key=(row['trip_id'],row['requester_id'])
            candidate=groups.setdefault(key,dict(application_id=row['id'],approved=False))
            candidate['approved']=candidate['approved'] or row['status'] in ('confirmed','waitlisted')
        db.execute('INSERT INTO app_settings(key,value) VALUES(?,?)',(MIGRATION_KEY,json.dumps(dict(candidates=list(groups.values()),done=[]))))


def upgrade_existing(store):
    """Extend legacy recurring requests once after every future date has a valid quote."""
    with store.read() as db:
        saved=db.execute('SELECT value FROM app_settings WHERE key=?',(MIGRATION_KEY,)).fetchone()
        state=json.loads(saved[0]) if saved else dict(candidates=[],done=[])
    for candidate in state['candidates']:
        aid=candidate['application_id']
        if aid in state['done']:continue
        try:
            with store.tx() as db:
                # Another startup may already have completed this candidate.
                current=json.loads(db.execute('SELECT value FROM app_settings WHERE key=?',(MIGRATION_KEY,)).fetchone()[0])
                if aid in current['done']:continue
                application=db.execute('SELECT * FROM applications WHERE id=?',(aid,)).fetchone()
                ride=joined_occurrence(db,application['occurrence_id'])
                # The original anchor may be canceled while quotes load. Use another
                # still-active date in that request, never reopen the canceled one.
                active={r['id'] for r in future_dates(db,ride['trip_id'])}
                eligible=[r for r in db.execute("SELECT a.* FROM applications a JOIN occurrences o ON o.id=a.occurrence_id WHERE o.trip_id=? AND a.requester_id=? AND a.status IN ('pending','confirmed','waitlisted') ORDER BY a.id",(ride['trip_id'],application['requester_id'])).fetchall() if r['occurrence_id'] in active]
                if not eligible:
                    current['done'].append(aid)
                else:
                    application=next((r for r in eligible if r['id']==aid),eligible[0])
                    ride=joined_occurrence(db,application['occurrence_id'])
                    user=dict(db.execute('SELECT * FROM users WHERE id=?',(application['requester_id'],)).fetchone())
                    _,sid,_=enroll(db,user,ride['id'],dict(party_size=application['party_size'],auto_confirm=bool(application['auto_confirm']),
                        meeting_origin=json.loads(application['meeting_origin']),meeting_destination=json.loads(application['meeting_destination'])))
                    info=series_info(db,sid,review=True)
                    if info['counts']['confirmed'] or info['counts']['waitlisted']:
                        owner=dict(db.execute('SELECT * FROM users WHERE id=?',(ride['owner_id'],)).fetchone())
                        approve(db,owner,sid,True,info['review_token'])
                    current['done'].append(aid)
                db.execute('UPDATE app_settings SET value=? WHERE key=?',(json.dumps(current),MIGRATION_KEY))
        except Problem:
            # Quotes or conflicting legacy terms may still need review. Retain the
            # original agreement intact and try again after the quote job completes.
            continue
