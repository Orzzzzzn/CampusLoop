"""Ride views, transparent scoring, occurrence exceptions, ratings and isolated demo scenarios."""
from __future__ import annotations
import datetime as dt
import json
import math
from .domain import (ZONE, PLACES, Problem, require, integer, date_value, location,
    distance_miles, today, now, joined_occurrence, ensure_open, list_trips,
    identity_name, private_text, occupied, event, trip_create, request_ride,
    decide, cancel_application, cancel_occurrence)


def rating_summary(db, subject, role):
    row=db.execute('SELECT count(*) AS count,avg(stars) AS average FROM ratings WHERE subject_id=? AND subject_role=?',(subject,role)).fetchone()
    return dict(count=row['count'],average=round(row['average'],2) if row['count'] else None,role=role)


def recommend(ride, criteria):
    """Explainable relevance score, not a prediction of acceptance or safety."""
    distances=[ride[k] for k in ('pickup_distance_miles','dropoff_distance_miles') if ride[k] is not None]
    route=40/(1+sum(distances)) if distances else 20
    target=criteria.get('departure_hour',criteria.get('departure_from'))
    timing=25/(1+abs(ride['departure_hour']-target)/2) if target is not None else 12.5
    price=15/(1+ride['price_cents']/500) if ride['role']=='driver' else 15*ride['price_cents']/(500+ride['price_cents'])
    rating=ride['owner_rating']; reputation=2*rating['average'] if rating['count'] else 5
    available=10 if ride['available_seats'] else 0
    reasons=[]
    if distances: reasons.append('Pickup and drop-off proximity' if len(distances)==2 else 'Selected location proximity')
    if target is not None: reasons.append('Departure close to your selected time')
    reasons.extend(['Lower listed cost share' if ride['role']=='driver' else 'Higher offered rider budget', 'Seats available' if available else 'Full; approved waitlist required'])
    if rating['count']: reasons.append(f"{rating['average']:.1f}/5 from {rating['count']} {rating['role']} ratings")
    return dict(score=round(route+timing+price+reputation+available),reasons=reasons,
        explanation='Route 40, time 25, price 15, role rating 10, availability 10. Unselected route/time and unrated members receive neutral scores.')


def participants(db,o):
    confirmed=[dict(a) for a in db.execute("SELECT * FROM applications WHERE occurrence_id=? AND status='confirmed' ORDER BY id",(o['id'],))]
    driver=o['driver_id']
    riders=[a['requester_id'] for a in confirmed] if o['role']=='driver' else ([o['owner_id']] if driver else [])
    return driver,riders,confirmed


def completed(o):
    end=o['return_hour']+1 if o['return_hour'] is not None else o['arrive_by']
    return dt.datetime.combine(date_value(o['trip_date']),dt.time.min,ZONE)+dt.timedelta(hours=end)<=now()


def rating_targets(db,viewer,o):
    if o['status']!='active' or not completed(o): return []
    driver,riders,_=participants(db,o)
    subjects=[(uid,'rider') for uid in riders] if viewer==driver else [(driver,'driver')] if viewer in riders and driver else []
    output=[]
    for subject,role in subjects:
        if subject==viewer: continue
        name,revealed=identity_name(db,viewer,subject,o['id'])
        stars=db.execute('SELECT stars FROM ratings WHERE occurrence_id=? AND rater_id=? AND subject_id=?',(o['id'],viewer,subject)).fetchone()
        output.append(dict(id=subject,name=name,role=role,stars=stars[0] if stars else None))
    return output


def rate_person(db,user,oid,data):
    o=joined_occurrence(db,oid);subject=integer(data,'subject_id',1,2**53);stars=integer(data,'stars',1,5)
    target=next((x for x in rating_targets(db,user['id'],o) if x['id']==subject),None)
    require(target is not None,'Only confirmed ride partners can be rated, after the ride ends.',403)
    db.execute('''INSERT INTO ratings(occurrence_id,rater_id,subject_id,subject_role,stars,created_at) VALUES(?,?,?,?,?,?)
        ON CONFLICT(occurrence_id,rater_id,subject_id) DO UPDATE SET stars=excluded.stars''',(oid,user['id'],subject,target['role'],stars,now().timestamp()))
    return rating_summary(db,subject,target['role'])


def my_rides(db,user,criteria=None):
    criteria=criteria or {}; scope=criteria.get('scope','upcoming')
    require(scope in ('upcoming','past','all'),'Choose upcoming, past, or all rides.')
    filters={k:v for k,v in criteria.items() if k in ('date','date_from','date_to','departure_from','departure_to') and v not in ('',None)}
    if scope in ('past','all') and not filters.get('date'):
        filters.setdefault('date_from','2000-01-01');filters['_include_past']=True
    if scope=='past' and not filters.get('date'): filters.setdefault('date_to',str(today()))
    rides=[]
    for r in list_trips(db,user['id'],filters):
        o=joined_occurrence(db,r['id']);driver,riders,confirmed=participants(db,o)
        # Open rider posts (looking for a driver) belong in Still pending, not Confirmed passenger.
        if user['id']==driver:
            r['my_role']='driver'
        elif user['id'] in riders:
            r['my_role']='rider'
        elif r['is_owner'] and r['role']=='rider' and not driver:
            r['my_role']='pending'
        else:
            continue
        if scope=='upcoming' and r['departed']: continue
        if scope=='past' and not r['departed']: continue
        r['completed']=completed(o)
        r['driver']=None
        if driver:
            name,revealed=identity_name(db,user['id'],driver,r['id'])
            vehicle=db.execute('SELECT vehicle FROM users WHERE id=?',(driver,)).fetchone()[0]
            r['driver']=dict(name=name,identity_revealed=revealed,vehicle=private_text(db,vehicle,user['id'],r['id']),rating=rating_summary(db,driver,'driver'))
        r['passengers']=[]
        for uid in riders:
            name,revealed=identity_name(db,user['id'],uid,r['id'])
            a=next((a for a in confirmed if a['requester_id']==uid),None)
            r['passengers'].append(dict(name=name,identity_revealed=revealed,party_size=a['party_size'] if a else r['capacity'],rating=rating_summary(db,uid,'rider')))
        own=r['application']
        agreed=own['agreed_price_cents'] if own else (confirmed[0]['agreed_price_cents'] if r['role']=='rider' and confirmed else r['price_cents'])
        r['agreed_price_cents']=agreed if agreed is not None else r['price_cents']
        booking=next((a for a in confirmed if a['requester_id']==user['id']),None)
        if booking is None and r['role']=='rider' and confirmed: booking=confirmed[0]
        r['meeting_origin']=json.loads(booking['meeting_origin']) if booking else None
        r['meeting_destination']=json.loads(booking['meeting_destination']) if booking else None
        r['party_size']=own['party_size'] if own else r['capacity'] if r['role']=='rider' else None
        r['total_price_cents']=r['agreed_price_cents']*(r['party_size'] or 1)
        r['rating_targets']=rating_targets(db,user['id'],o) if r['my_role']!='pending' else []
        r['pending_offers']=db.execute(
            "SELECT count(*) FROM applications WHERE occurrence_id=? AND status='pending'",
            (r['id'],),
        ).fetchone()[0] if r['my_role']=='pending' else 0
        r['can_edit_date']=r['is_owner'] and r['kind']=='regular' and not r['departed'] and not db.execute("SELECT 1 FROM applications WHERE occurrence_id=? AND status IN ('pending','waitlisted','confirmed')",(r['id'],)).fetchone()
        rides.append(r)
    return rides


def cancel_date(db,user,oid):
    o=joined_occurrence(db,oid);ensure_open(o)
    if o['owner_id']==user['id']:
        cancel_occurrence(db,user,oid)
    else:
        a=db.execute("SELECT id FROM applications WHERE occurrence_id=? AND requester_id=? AND status IN ('pending','waitlisted','confirmed')",(oid,user['id'])).fetchone()
        require(a is not None,'You do not have an active booking on this date.',403)
        cancel_application(db,user,a['id'])


def skip_week(db,user,oid):
    o=joined_occurrence(db,oid);ensure_open(o)
    require(o['kind']=='regular','Weekly exceptions apply only to regular rides.')
    day=date_value(o['trip_date']);start=day-dt.timedelta(days=day.weekday());end=start+dt.timedelta(days=6)
    ids=[]
    for row in db.execute("SELECT id FROM occurrences WHERE trip_id=? AND trip_date BETWEEN ? AND ? AND status='active'",(o['trip_id'],str(start),str(end))).fetchall():
        current=joined_occurrence(db,row['id'])
        try: ensure_open(current)
        except Problem: continue
        if current['owner_id']!=user['id'] and not db.execute("SELECT 1 FROM applications WHERE occurrence_id=? AND requester_id=? AND status IN ('pending','waitlisted','confirmed')",(current['id'],user['id'])).fetchone(): continue
        cancel_date(db,user,current['id']);ids.append(current['id'])
    require(ids,'No future bookings in this week belong to you.',403)
    return ids


def edit_date(db,user,oid,data):
    o=joined_occurrence(db,oid);ensure_open(o)
    require(o['owner_id']==user['id'],'Only the post owner can edit this ride date.',403)
    require(o['kind']=='regular','Date exceptions apply to regular rides.')
    require(not db.execute("SELECT 1 FROM applications WHERE occurrence_id=? AND status IN ('pending','waitlisted','confirmed')",(oid,)).fetchone(),'This date already has requests. Skip this date and post a replacement so everyone can agree to the new terms.',409)
    departure=integer(data,'departure_hour',0,22);arrival=integer(data,'arrive_by',departure+1,23)
    require(dt.datetime.combine(date_value(o['trip_date']),dt.time(departure),ZONE)>now(),'Departure must be in the future.')
    override=dict(departure_hour=departure,arrive_by=arrival,note=str(data.get('note','')).strip())
    require(len(override['note'])<=1000,'Notes must be at most 1000 characters.')
    db.execute('UPDATE occurrences SET overrides=? WHERE id=?',(json.dumps(override),oid))
    event(db,oid,user['id'],'Departure and notes changed for this date only.')


def demo_views(db,user):
    output=[]
    for row in db.execute('SELECT * FROM demo_scenarios WHERE creator_id=? ORDER BY id DESC LIMIT 30',(user['id'],)):
        r=dict(row);o=joined_occurrence(db,r['occurrence_id']);r.update(trip_date=o['trip_date'],departure_hour=o['departure_hour'],available_seats=max(0,o['capacity']-occupied(db,o['id'])))
        r['members']=[]
        for a in db.execute('SELECT * FROM applications WHERE occurrence_id=? ORDER BY created_at,id',(o['id'],)):
            name,revealed=identity_name(db,user['id'],a['requester_id'],o['id'])
            r['members'].append(dict(id=a['id'],name='You' if a['requester_id']==user['id'] else name,status=a['status'],party_size=a['party_size'],auto_confirm=bool(a['auto_confirm']),is_you=a['requester_id']==user['id'],can_release=a['id'] in json.loads(r['releasable_ids']) and a['status']=='confirmed'))
        r['rating_targets']=rating_targets(db,user['id'],o)
        r['completed']=completed(o)
        r.pop('releasable_ids');output.append(r)
    return output


def create_demo(db,user):
    """Add fresh fixtures without touching existing trips, accounts, passwords or queues."""
    require(user['verified'],'Verify your email first.',403)
    fixtures=[]
    for i,name in enumerate(('Alex Demo','Blair Demo','Casey Demo','Drew Demo')):
        email=f'lab-{user["id"]}-{i}@campusloop.invalid'
        db.execute("INSERT OR IGNORE INTO users(name,email,password_hash,verified,vehicle,is_demo_fixture) VALUES(?,?,'!fixture-login-disabled',1,'Demo Toyota Prius · Silver',1)",(name,email))
        fixtures.append(dict(db.execute('SELECT * FROM users WHERE email=? AND is_demo_fixture=1',(email,)).fetchone()))
    driver,a,b,c=fixtures;day=today()+dt.timedelta(days=2)
    origin={**{k:v for k,v in PLACES[0].items() if k!='id'},'mode':'exact','radius_miles':0}
    destination={**{k:v for k,v in PLACES[4].items() if k!='id'},'mode':'exact','radius_miles':0}
    def ride(owner,capacity=1,regular=False):
        data=dict(role='driver',kind='regular' if regular else 'one',origin=origin,destination=destination,departure_hour=8,arrive_by=9,start_date=str(day),end_date=str(day+dt.timedelta(days=14)),weekdays=[day.weekday()],seats=capacity,price_cents=400,detour_minutes=10,note='Demo Lab fixture · created explicitly for waitlist or rating practice.')
        tid=trip_create(db,owner,data)
        return db.execute('SELECT id FROM occurrences WHERE trip_id=? ORDER BY trip_date',(tid,)).fetchone()[0]
    def apply(person,oid,party=1,auto=True,approve=True,owner=driver):
        aid=request_ride(db,person,oid,dict(party_size=party,auto_confirm=auto,meeting_origin=origin,meeting_destination=destination))
        if approve: decide(db,owner,aid,True)
        return aid
    def scenario(oid,title,description,releases=()):
        db.execute('INSERT INTO demo_scenarios(creator_id,occurrence_id,title,description,releasable_ids,created_at) VALUES(?,?,?,?,?,?)',(user['id'],oid,title,description,json.dumps(list(releases)),now().timestamp()))
    oid=ride(driver,regular=True);apply(user,oid);apply(a,oid)
    scenario(oid,'1. Automatic promotion','You hold the only seat. Cancel your seat below; the approved auto-confirm passenger will be promoted. Later weekly dates remain active.')
    oid=ride(driver);release=apply(b,oid);apply(user,oid,auto=False)
    scenario(oid,'2. Manual claim','Release the example booking. Your approved waitlist stays waiting until you click Confirm open seat.',[release])
    oid=ride(driver,3);two=apply(b,oid,2);one=apply(c,oid);apply(user,oid,2);apply(a,oid)
    scenario(oid,'3. Whole-party fit','Release the one-person booking first: the later one-person party fits, but your two-person party waits. Release the two-person booking next to confirm your whole party.',[one,two])
    oid=ride(driver);release=apply(b,oid);apply(user,oid,approve=False);apply(a,oid)
    scenario(oid,'4. Approval required','Your request is pending, not approved. Release the example seat: the approved waitlisted passenger is promoted; your pending request stays pending.',[release])
    oid=ride(driver);apply(user,oid)
    db.execute('UPDATE occurrences SET trip_date=? WHERE id=?',(str(today()-dt.timedelta(days=2)),oid))
    scenario(oid,'5. End-of-ride rating · passenger','Use Rate this ride below (or My rides → Past). Rate your driver after the trip ends. Editing a rating does not add another vote.')
    if user['vehicle'].strip():
        oid=ride(user);apply(a,oid,owner=user);apply(b,oid,owner=user)
        db.execute('UPDATE occurrences SET trip_date=? WHERE id=?',(str(today()-dt.timedelta(days=1)),oid))
        scenario(oid,'6. End-of-ride rating · driver','Use Rate this ride below. Drivers rate each confirmed passenger separately after the trip ends.')
    return demo_views(db,user)


def release_demo(db,user,sid,aid):
    row=db.execute('SELECT * FROM demo_scenarios WHERE id=? AND creator_id=?',(sid,user['id'])).fetchone()
    require(row is not None and aid in json.loads(row['releasable_ids']),'This booking is not a releasable example created by you.',403)
    a=db.execute('SELECT * FROM applications WHERE id=? AND occurrence_id=?',(aid,row['occurrence_id'])).fetchone()
    fixture=db.execute('SELECT * FROM users WHERE id=? AND is_demo_fixture=1',(a['requester_id'],)).fetchone() if a else None
    require(fixture is not None,'Only generated example bookings can be released.',403)
    return cancel_application(db,fixture,aid)
