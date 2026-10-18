"""Trip posting, search, requests, waitlist, and chat gates."""
from __future__ import annotations

import datetime as dt
import json

from .clock import ZONE, now, today
from .errors import Problem, require
from .geo import distance_miles, fixed_point, overlaps, shared_meeting_point
from .identity import event, identity_name, private_text
from .occurrence import ensure_open, joined_occurrence, occupied
from .validation import boolean, date_value, integer, location, text


def promote(db, o):
    if o['role'] != 'driver' or o['status'] != 'active':
        return []
    try:
        ensure_open(o)
    except Problem:
        return []
    free = o['capacity'] - occupied(db, o['id'])
    promoted = []
    for a in db.execute(
        "SELECT a.*,u.name FROM applications a JOIN users u ON u.id=a.requester_id "
        "WHERE occurrence_id=? AND status='waitlisted' AND auto_confirm=1 ORDER BY created_at,id",
        (o['id'],),
    ).fetchall():
        if a['party_size'] <= free:
            db.execute("UPDATE applications SET status='confirmed' WHERE id=? AND status='waitlisted'", (a['id'],))
            free -= a['party_size']
            promoted.append(a['id'])
            event(db, o['id'], a['requester_id'], a['name'] + ' automatically confirmed from the approved waitlist.')
    return promoted


def trip_create(db, user, data):
    require(user['verified'], 'Verify your student email first.', 403)
    role, kind = data.get('role'), data.get('kind')
    require(role in ('driver', 'rider'), 'Choose driver or rider.')
    require(kind in ('regular', 'one', 'round'), 'Choose regular, one, or round.')
    require(role != 'driver' or bool(user['vehicle'].strip()), 'Add a vehicle in your profile before offering rides.')
    origin, destination = location(data.get('origin')), location(data.get('destination'))
    require(distance_miles(origin, destination) > 0.001, 'Pickup and drop-off centers must be different.')
    departure = integer(data, 'departure_hour', 0, 22)
    deadline = integer(data, 'arrive_by', departure + 1, 23)
    seats = integer(data, 'seats', 1, 4)
    price = integer(data, 'price_cents', 0, 10000)
    detour = integer(data, 'detour_minutes', 0, 60)
    start = date_value(data.get('start_date'))
    end = date_value(data.get('end_date', data.get('start_date'))) if kind == 'regular' else start
    require(today() <= start <= end <= today() + dt.timedelta(days=120), 'Schedule dates must be within the next 120 days.')
    weekdays = data.get('weekdays', []) if kind == 'regular' else []
    require(
        isinstance(weekdays, list) and all(type(d) is int and 0 <= d <= 6 for d in weekdays),
        'Weekdays must be numbers 0 (Monday) to 6 (Sunday).',
    )
    require(kind != 'regular' or len(set(weekdays)) > 0, 'Choose at least one recurring weekday.')
    note = text(data, 'note', 0, 1000)
    return_hour = integer(data, 'return_hour', deadline, 23) if kind == 'round' else None
    dates = [
        start + dt.timedelta(days=i)
        for i in range((end - start).days + 1)
        if kind != 'regular' or (start + dt.timedelta(days=i)).weekday() in weekdays
    ]
    require(dates, 'No selected weekdays fall inside this date range.')
    for day in dates:
        require(dt.datetime.combine(day, dt.time(departure), ZONE) > now(), 'Departure must be in the future.')
    trip_id = db.execute(
        '''INSERT INTO trips(owner_id,role,origin,destination,departure_hour,arrive_by,kind,weekdays,start_date,end_date,seats,price_cents,detour_minutes,note,return_hour,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (
            user['id'],
            role,
            json.dumps(origin),
            json.dumps(destination),
            departure,
            deadline,
            kind,
            json.dumps(sorted(set(weekdays))),
            str(start),
            str(end),
            seats,
            price,
            detour,
            note,
            return_hour,
            now().timestamp(),
        ),
    ).lastrowid
    for day in dates:
        db.execute(
            'INSERT INTO occurrences(trip_id,trip_date,capacity,driver_id) VALUES(?,?,?,?)',
            (trip_id, str(day), seats, user['id'] if role == 'driver' else None),
        )
    return trip_id


def list_trips(db, actor_id, criteria=None):
    criteria = criteria or {}
    require(isinstance(criteria, dict), 'Search filters must be an object.')
    require(not criteria.get('role') or criteria['role'] in ('all', 'driver', 'rider'), 'Invalid board role.')
    require(not criteria.get('kind') or criteria['kind'] in ('regular', 'one', 'round'), 'Invalid trip type.')
    for key, lo, hi in [
        ('departure_hour', 0, 23),
        ('departure_from', 0, 23),
        ('departure_to', 0, 23),
        ('arrive_by', 0, 23),
        ('detour_minutes', 0, 60),
    ]:
        if criteria.get(key) is not None:
            integer(criteria, key, lo, hi)
    from_hour = criteria['departure_from'] if criteria.get('departure_from') is not None else 0
    to_hour = criteria['departure_to'] if criteria.get('departure_to') is not None else 23
    require(from_hour <= to_hour, 'The end hour must be after the start hour.')
    required_days = criteria.get('weekdays', [])
    require(
        isinstance(required_days, list) and all(type(d) is int and 0 <= d <= 6 for d in required_days),
        'Invalid weekdays.',
    )
    clauses = ['o.status=?']
    args = ['active']
    if criteria.get('date'):
        clauses.append('o.trip_date=?')
        args.append(str(date_value(criteria['date'])))
    else:
        clauses.append('o.trip_date>=?')
        args.append(str(date_value(criteria['date_from'])) if criteria.get('date_from') else str(today()))
        if criteria.get('date_to'):
            clauses.append('o.trip_date<=?')
            args.append(str(date_value(criteria['date_to'])))
        require(
            not criteria.get('date_from') or not criteria.get('date_to') or criteria['date_from'] <= criteria['date_to'],
            'Invalid date range.',
        )
    query = (
        '''SELECT o.*,t.owner_id,t.role,t.origin,t.destination,t.departure_hour,t.arrive_by,t.kind,t.weekdays,t.start_date,t.end_date,t.price_cents,t.detour_minutes,t.note,t.return_hour,u.name AS owner_name,u.vehicle
        FROM occurrences o JOIN trips t ON t.id=o.trip_id JOIN users u ON u.id=t.owner_id WHERE '''
        + ' AND '.join(clauses)
    )
    rows = db.execute(query, args).fetchall()
    output = []
    origin_filter = location(criteria['origin']) if criteria.get('origin') else None
    dest_filter = location(criteria['destination']) if criteria.get('destination') else None
    for raw in rows:
        r = dict(raw)
        r['origin'], r['destination'], r['weekdays'] = (
            json.loads(r['origin']),
            json.loads(r['destination']),
            json.loads(r['weekdays']),
        )
        if criteria.get('role') in ('driver', 'rider') and r['role'] != criteria['role']:
            continue
        if origin_filter and not overlaps(origin_filter, r['origin']):
            continue
        if dest_filter and not overlaps(dest_filter, r['destination']):
            continue
        if criteria.get('departure_hour') is not None and r['departure_hour'] != criteria['departure_hour']:
            continue
        if not from_hour <= r['departure_hour'] <= to_hour:
            continue
        if criteria.get('arrive_by') is not None and r['arrive_by'] > criteria['arrive_by']:
            continue
        if criteria.get('kind') and r['kind'] != criteria['kind']:
            continue
        if required_days and not all(d in r['weekdays'] for d in required_days):
            continue
        if criteria.get('detour_minutes') is not None and r['detour_minutes'] > criteria['detour_minutes']:
            continue
        r['departed'] = dt.datetime.combine(date_value(r['trip_date']), dt.time(r['departure_hour']), ZONE) <= now()
        if not criteria.get('date') and r['departed']:
            continue
        r['confirmed_seats'] = occupied(db, r['id'])
        r['available_seats'] = (
            max(0, r['capacity'] - r['confirmed_seats']) if r['role'] == 'driver' else (0 if r['driver_id'] else r['capacity'])
        )
        own = db.execute(
            'SELECT id,status,party_size FROM applications WHERE occurrence_id=? AND requester_id=?',
            (r['id'], actor_id),
        ).fetchone()
        r['application'] = dict(own) if own else None
        r['is_owner'] = r['owner_id'] == actor_id
        r['owner_name'], r['identity_revealed'] = identity_name(db, actor_id, r['owner_id'], r['id'])
        r['note'] = private_text(db, r['note'], actor_id, r['id'])
        r['vehicle'] = private_text(db, r['vehicle'], actor_id, r['id'])
        r['pickup_distance_miles'] = round(distance_miles(origin_filter, r['origin']), 3) if origin_filter else None
        r['dropoff_distance_miles'] = round(distance_miles(dest_filter, r['destination']), 3) if dest_filter else None
        r['search_origin'] = origin_filter['label'] if origin_filter else None
        r['search_destination'] = dest_filter['label'] if dest_filter else None
        r['suggested_meeting_origin'] = shared_meeting_point(origin_filter, r['origin'])
        r['suggested_meeting_destination'] = shared_meeting_point(dest_filter, r['destination'])
        r['match_type'] = (
            'both_locations' if origin_filter and dest_filter else 'pickup' if origin_filter else 'dropoff' if dest_filter else None
        )
        output.append(r)
    return sorted(
        output,
        key=lambda r: (
            (r['pickup_distance_miles'] or 0) + (r['dropoff_distance_miles'] or 0),
            r['trip_date'],
            r['departure_hour'],
            r['id'],
        ),
    )


def request_ride(db, user, oid, data):
    require(user['verified'], 'Verify your student email first.', 403)
    o = joined_occurrence(db, oid)
    ensure_open(o)
    require(o['owner_id'] != user['id'], 'You cannot request your own post.', 409)
    require(o['role'] != 'rider' or bool(user['vehicle'].strip()), 'Add your vehicle before offering to drive.')
    require(o['role'] != 'rider' or o['driver_id'] is None, 'This rider already accepted a driver.', 409)
    party = integer(data, 'party_size', 1, 4, 1) if o['role'] == 'driver' else o['seats']
    require(party <= o['capacity'], 'Your party is larger than this ride’s passenger capacity.')
    pickup = fixed_point(data.get('meeting_origin'), json.loads(o['origin']))
    dropoff = fixed_point(data.get('meeting_destination'), json.loads(o['destination']))
    auto = boolean(data, 'auto_confirm') if o['role'] == 'driver' else False
    existing = db.execute(
        'SELECT id,status FROM applications WHERE occurrence_id=? AND requester_id=?',
        (oid, user['id']),
    ).fetchone()
    require(
        not existing or existing['status'] in ('canceled', 'declined'),
        'You already have an active request for this date.',
        409,
    )
    values = (party, int(auto), json.dumps(pickup), json.dumps(dropoff), now().timestamp())
    if existing:
        aid = existing['id']
        db.execute(
            "UPDATE applications SET status='pending',party_size=?,auto_confirm=?,meeting_origin=?,meeting_destination=?,created_at=? WHERE id=?",
            (*values, aid),
        )
    else:
        aid = db.execute(
            "INSERT INTO applications(occurrence_id,requester_id,status,party_size,auto_confirm,meeting_origin,meeting_destination,created_at) VALUES(?,?,'pending',?,?,?,?,?)",
            (oid, user['id'], *values),
        ).lastrowid
    event(db, oid, user['id'], user['name'] + ' sent ' + ('a ride offer.' if o['role'] == 'rider' else 'a seat request.'))
    return aid


def decide(db, user, aid, accept):
    a = db.execute('SELECT * FROM applications WHERE id=?', (aid,)).fetchone()
    require(a is not None, 'Request not found.', 404)
    o = joined_occurrence(db, a['occurrence_id'])
    require(o['owner_id'] == user['id'], 'Only the post owner can decide this request.', 403)
    ensure_open(o)
    require(a['status'] == 'pending', 'This request has already been decided.', 409)
    if not accept:
        status = 'declined'
    elif o['role'] == 'rider':
        require(o['driver_id'] is None, 'Another driver was already confirmed.', 409)
        db.execute('UPDATE occurrences SET driver_id=? WHERE id=?', (a['requester_id'], o['id']))
        status = 'confirmed'
        # Other offers become unavailable atomically, not waitlisted passenger seats.
        db.execute(
            "UPDATE applications SET status='declined' WHERE occurrence_id=? AND id<>? AND status='pending'",
            (o['id'], aid),
        )
    else:
        status = 'confirmed' if occupied(db, o['id']) + a['party_size'] <= o['capacity'] else 'waitlisted'
    db.execute('UPDATE applications SET status=? WHERE id=?', (status, aid))
    event(db, o['id'], user['id'], 'Request #' + str(aid) + ' ' + status + '.')
    return status


def cancel_application(db, user, aid):
    a = db.execute('SELECT * FROM applications WHERE id=?', (aid,)).fetchone()
    require(a is not None, 'Request not found.', 404)
    o = joined_occurrence(db, a['occurrence_id'])
    require(a['requester_id'] == user['id'], 'Only the requesting student may cancel this request.', 403)
    ensure_open(o)
    require(a['status'] in ('pending', 'waitlisted', 'confirmed'), 'This request is already inactive.', 409)
    db.execute("UPDATE applications SET status='canceled' WHERE id=?", (aid,))
    if o['role'] == 'rider' and a['status'] == 'confirmed':
        db.execute('UPDATE occurrences SET driver_id=NULL WHERE id=?', (o['id'],))
    event(db, o['id'], user['id'], user['name'] + ' canceled this date only.')
    return promote(db, o)


def claim(db, user, aid):
    a = db.execute('SELECT * FROM applications WHERE id=?', (aid,)).fetchone()
    require(a is not None, 'Request not found.', 404)
    o = joined_occurrence(db, a['occurrence_id'])
    ensure_open(o)
    require(a['requester_id'] == user['id'], 'This waitlist entry belongs to another student.', 403)
    require(a['status'] == 'waitlisted', 'Driver approval is required before claiming a seat.', 409)
    promote(db, o)
    if db.execute('SELECT status FROM applications WHERE id=?', (aid,)).fetchone()[0] == 'confirmed':
        return
    require(occupied(db, o['id']) + a['party_size'] <= o['capacity'], 'No seat is open for your party.', 409)
    db.execute("UPDATE applications SET status='confirmed' WHERE id=?", (aid,))
    event(db, o['id'], user['id'], user['name'] + ' confirmed an open waitlist seat.')


def can_chat(db, user, oid):
    o = joined_occurrence(db, oid)
    allowed = o['owner_id'] == user['id'] or db.execute(
        "SELECT 1 FROM applications WHERE occurrence_id=? AND requester_id=? AND status='confirmed'",
        (oid, user['id']),
    ).fetchone()
    require(bool(allowed), 'Chat is available to the owner and confirmed participants only.', 403)
    return o


def application_views(db, user):
    rows = db.execute(
        '''SELECT a.*,u.name AS requester_name,t.owner_id,t.role,o.trip_date,o.status AS occurrence_status,o.trip_id,
        t.departure_hour,t.origin,t.destination,t.price_cents,owner.name AS owner_name
        FROM applications a JOIN users u ON u.id=a.requester_id JOIN occurrences o ON o.id=a.occurrence_id
        JOIN trips t ON t.id=o.trip_id JOIN users owner ON owner.id=t.owner_id
        WHERE a.requester_id=? OR t.owner_id=? ORDER BY a.created_at DESC,a.id DESC''',
        (user['id'], user['id']),
    ).fetchall()
    result = []
    for row in rows:
        r = dict(row)
        for key in ('origin', 'destination', 'meeting_origin', 'meeting_destination'):
            r[key] = json.loads(r[key])
        r['incoming'] = r['owner_id'] == user['id']
        r['requester_name'], requester_revealed = identity_name(db, user['id'], r['requester_id'], r['occurrence_id'])
        r['owner_name'], owner_revealed = identity_name(db, user['id'], r['owner_id'], r['occurrence_id'])
        r['identity_revealed'] = requester_revealed if r['incoming'] else owner_revealed
        r['closed'] = r['occurrence_status'] != 'active' or (
            dt.datetime.combine(date_value(r['trip_date']), dt.time(r['departure_hour']), ZONE) <= now()
        )
        result.append(r)
    return result
