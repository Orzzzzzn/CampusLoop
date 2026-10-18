from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    ZONE = ZoneInfo('America/Los_Angeles')
except ZoneInfoNotFoundError:
    with (Path(__file__).parent/'zoneinfo/Los_Angeles').open('rb') as zone_file:
        ZONE = ZoneInfo.from_file(zone_file,key='America/Los_Angeles')
ROOT = Path(__file__).resolve().parents[1]


class Problem(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def now():
    return dt.datetime.now(ZONE)


def today():
    return now().date()


def require(condition, message, status=422):
    if not condition:
        raise Problem(status, message)


def text(data, key, minimum=1, maximum=200):
    value = data.get(key)
    require(isinstance(value, str), f'{key} must be text.')
    value = value.strip()
    require(minimum <= len(value) <= maximum, f'{key} must have {minimum}–{maximum} characters.')
    return value


def integer(data, key, low, high, default=None):
    value = data.get(key, default)
    require(type(value) is int and low <= value <= high, f'{key} must be an integer from {low} to {high}.')
    return value


def boolean(data, key, default=False):
    value = data.get(key, default)
    require(type(value) is bool, f'{key} must be true or false.')
    return value


def date_value(value):
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise Problem(422, 'Use a calendar date in YYYY-MM-DD format.')


def clean_place_label(value):
    return re.sub(r'\s*\(sample\s+pin\)\s*',' ',value,flags=re.I).strip()


def location(data):
    require(isinstance(data, dict), 'Choose a location and place its pin on the map.')
    label = clean_place_label(text(data, 'label', 3, 180))
    require(len(label)>=3,'Choose a named place or a point on the map.')
    require(data.get('mode') in ('exact', 'area'), 'Location mode must be exact or area.')
    lat, lon = data.get('lat'), data.get('lon')
    require(type(lat) in (int, float) and math.isfinite(lat) and -90 <= lat <= 90, 'A valid latitude is required.')
    require(type(lon) in (int, float) and math.isfinite(lon) and -180 <= lon <= 180, 'A valid longitude is required.')
    radius = data.get('radius_miles', 0) if data['mode'] == 'area' else 0
    require(type(radius) in (int, float) and math.isfinite(radius), 'Radius must be a number.')
    require(data['mode'] == 'exact' or 0.1 <= radius <= 10, 'An area needs a radius between 0.1 and 10 miles.')
    return dict(label=label, lat=float(lat), lon=float(lon), mode=data['mode'], radius_miles=float(radius))


def distance_miles(a, b):
    lat1, lat2 = math.radians(a['lat']), math.radians(b['lat'])
    dlat, dlon = lat2-lat1, math.radians(b['lon']-a['lon'])
    v = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 3958.7613 * 2 * math.asin(math.sqrt(min(1, max(0, v))))


def overlaps(a, b):
    # One metre accounts for floating-point/pin rounding; no walking radius is added to exact places.
    return distance_miles(a, b) <= a['radius_miles'] + b['radius_miles'] + 0.000622


def fixed_point(point, allowed):
    point = location(point)
    require(point['mode'] == 'exact', 'Propose an exact meeting point for confirmation.')
    require(overlaps(point, allowed), 'The proposed meeting point is outside the posted location area.')
    return point


def hash_password(password):
    require(isinstance(password, str) and 10 <= len(password) <= 200, 'Password must contain 10–200 characters.')
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, maxmem=64*1024*1024)
    return salt.hex()+':'+digest.hex()


def check_password(password, encoded):
    if not isinstance(password, str) or len(password) > 200:
        return False
    try:
        salt, expected = encoded.split(':')
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, maxmem=64*1024*1024)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
 password_hash TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0, vehicle TEXT NOT NULL DEFAULT '',
 verification_hash TEXT, verification_expires REAL, verification_attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 csrf TEXT NOT NULL, expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS trips (
 id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id), role TEXT NOT NULL,
 origin TEXT NOT NULL, destination TEXT NOT NULL, departure_hour INTEGER NOT NULL,
 arrive_by INTEGER NOT NULL, kind TEXT NOT NULL, weekdays TEXT NOT NULL,
 start_date TEXT NOT NULL, end_date TEXT NOT NULL, seats INTEGER NOT NULL,
 price_cents INTEGER NOT NULL, detour_minutes INTEGER NOT NULL, note TEXT NOT NULL,
 return_hour INTEGER, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS occurrences (
 id INTEGER PRIMARY KEY, trip_id INTEGER NOT NULL REFERENCES trips(id), trip_date TEXT NOT NULL,
 capacity INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active',
 driver_id INTEGER REFERENCES users(id), UNIQUE(trip_id, trip_date)
);
CREATE TABLE IF NOT EXISTS applications (
 id INTEGER PRIMARY KEY, occurrence_id INTEGER NOT NULL REFERENCES occurrences(id),
 requester_id INTEGER NOT NULL REFERENCES users(id), status TEXT NOT NULL,
 party_size INTEGER NOT NULL CHECK(party_size BETWEEN 1 AND 4), auto_confirm INTEGER NOT NULL,
 meeting_origin TEXT NOT NULL, meeting_destination TEXT NOT NULL,
 created_at REAL NOT NULL, UNIQUE(occurrence_id, requester_id)
);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY, occurrence_id INTEGER NOT NULL REFERENCES occurrences(id),
 actor_id INTEGER REFERENCES users(id), message TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY, occurrence_id INTEGER NOT NULL REFERENCES occurrences(id),
 user_id INTEGER NOT NULL REFERENCES users(id), body TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS embeddings (
 content_hash TEXT NOT NULL, model TEXT NOT NULL, vector TEXT NOT NULL,
 PRIMARY KEY(content_hash,model)
);
CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS place_cache (cache_key TEXT PRIMARY KEY, results TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS ratings (
 id INTEGER PRIMARY KEY, occurrence_id INTEGER NOT NULL REFERENCES occurrences(id),
 rater_id INTEGER NOT NULL REFERENCES users(id), subject_id INTEGER NOT NULL REFERENCES users(id),
 subject_role TEXT NOT NULL CHECK(subject_role IN ('driver','rider')), stars INTEGER NOT NULL CHECK(stars BETWEEN 1 AND 5),
 created_at REAL NOT NULL, UNIQUE(occurrence_id,rater_id,subject_id)
);
CREATE TABLE IF NOT EXISTS route_cache (cache_key TEXT PRIMARY KEY, result TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS demo_scenarios (
 id INTEGER PRIMARY KEY, creator_id INTEGER NOT NULL REFERENCES users(id), occurrence_id INTEGER NOT NULL REFERENCES occurrences(id),
 title TEXT NOT NULL, description TEXT NOT NULL, releasable_ids TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
 occurrence_id INTEGER REFERENCES occurrences(id),
 application_id INTEGER REFERENCES applications(id),
 read INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS application_queue ON applications(occurrence_id,status,created_at,id);
CREATE INDEX IF NOT EXISTS occurrence_dates ON occurrences(trip_date,status);
CREATE INDEX IF NOT EXISTS notification_inbox ON notifications(user_id,read,created_at DESC);
'''


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.read() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(SCHEMA)
            for table, additions in {
                'users': [('is_demo_fixture','INTEGER NOT NULL DEFAULT 0')],
                'trips': [('price_meta',"TEXT NOT NULL DEFAULT '{}'")],
                'occurrences': [('overrides',"TEXT NOT NULL DEFAULT '{}'")],
                'applications': [('agreed_price_cents','INTEGER'), ('cancel_reason','TEXT')],
            }.items():
                columns={r['name'] for r in db.execute('PRAGMA table_info('+table+')')}
                for name, declaration in additions:
                    if name not in columns:
                        db.execute('ALTER TABLE '+table+' ADD COLUMN '+name+' '+declaration)
            db.execute('''UPDATE applications SET agreed_price_cents=(SELECT t.price_cents FROM occurrences o JOIN trips t ON t.id=o.trip_id WHERE o.id=applications.occurrence_id) WHERE agreed_price_cents IS NULL''')
            db.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('identity_salt',?)",(secrets.token_hex(32),))
        # Remove the old display suffix from stored locations without changing
        # coordinates, bookings, names, passwords, or other account data.
        with self.tx() as db:
            for table,fields in [('trips',('origin','destination')),('applications',('meeting_origin','meeting_destination'))]:
                for row in db.execute('SELECT id,'+','.join(fields)+' FROM '+table+' WHERE '+' OR '.join(field+" LIKE '%sample%pin%'" for field in fields)).fetchall():
                    for field in fields:
                        point=json.loads(row[field]);cleaned=clean_place_label(point['label'])
                        if cleaned!=point['label'] and cleaned:
                            point['label']=cleaned
                            db.execute('UPDATE '+table+' SET '+field+'=? WHERE id=?',(json.dumps(point),row['id']))
            db.execute("DELETE FROM place_cache WHERE results LIKE '%sample%pin%'")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=15000')
        return db

    @contextlib.contextmanager
    def read(self):
        db = self.connect()
        try:
            yield db
        finally:
            db.close()

    @contextlib.contextmanager
    def tx(self):
        with self.read() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise


def public_user(row):
    return dict(id=row['id'], name=row['name'], email=row['email'], verified=bool(row['verified']), vehicle=row['vehicle'])


def event(db, oid, actor, message):
    db.execute('INSERT INTO events(occurrence_id,actor_id,message,created_at) VALUES(?,?,?,?)', (oid, actor, message, now().timestamp()))


def notify(db, user_id, kind, title, body, occurrence_id=None, application_id=None):
    db.execute(
        'INSERT INTO notifications(user_id,kind,title,body,occurrence_id,application_id,created_at) VALUES(?,?,?,?,?,?,?)',
        (user_id, kind, title, body, occurrence_id, application_id, now().timestamp()),
    )


def list_notifications(db, user, limit=40):
    rows = db.execute(
        '''SELECT id,kind,title,body,occurrence_id,application_id,read,created_at
           FROM notifications WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT ?''',
        (user['id'], limit),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_notifications_read(db, user, ids=None):
    if ids is None:
        db.execute('UPDATE notifications SET read=1 WHERE user_id=? AND read=0', (user['id'],))
        return
    require(isinstance(ids, list) and all(type(n) is int and n > 0 for n in ids), 'Notification ids must be positive integers.')
    for nid in ids[:100]:
        db.execute('UPDATE notifications SET read=1 WHERE id=? AND user_id=?', (nid, user['id']))


def joined_occurrence(db, oid):
    row = db.execute('''SELECT o.*,t.owner_id,t.role,t.departure_hour,t.return_hour,
        t.origin,t.destination,t.seats,t.note,t.price_cents,t.price_meta,t.kind,t.arrive_by FROM occurrences o
        JOIN trips t ON t.id=o.trip_id WHERE o.id=?''', (oid,)).fetchone()
    require(row is not None, 'Ride date not found.', 404)
    return effective_occurrence(dict(row))


def effective_occurrence(row):
    override=json.loads(row.get('overrides') or '{}')
    for key in ('departure_hour','arrive_by','origin','destination','note','price_cents'):
        if key in override:
            row[key]=json.dumps(override[key]) if key in ('origin','destination') else override[key]
    row['has_exception']=bool(override)
    return row


def ensure_open(o):
    departure = dt.datetime.combine(date_value(o['trip_date']), dt.time(o['departure_hour']), ZONE)
    require(o['status'] == 'active' and departure > now(), 'This ride has departed or was canceled.', 409)


def occupied(db, oid):
    return db.execute("SELECT coalesce(sum(party_size),0) FROM applications WHERE occurrence_id=? AND status='confirmed'", (oid,)).fetchone()[0]


def promote(db, o):
    if o['role'] != 'driver' or o['status'] != 'active':
        return []
    try:
        ensure_open(o)
    except Problem:
        return []
    free = o['capacity'] - occupied(db, o['id'])
    promoted = []
    for a in db.execute("SELECT a.*,u.name FROM applications a JOIN users u ON u.id=a.requester_id WHERE occurrence_id=? AND status='waitlisted' AND auto_confirm=1 ORDER BY created_at,id", (o['id'],)).fetchall():
        if a['party_size'] <= free:
            db.execute("UPDATE applications SET status='confirmed' WHERE id=? AND status='waitlisted'", (a['id'],))
            free -= a['party_size']
            promoted.append(a['id'])
            event(db, o['id'], a['requester_id'], a['name']+' automatically confirmed from the approved waitlist.')
    return promoted


def trip_create(db, user, data):
    require(user['verified'], 'Verify your student email first.', 403)
    role, kind = data.get('role'), data.get('kind')
    require(role in ('driver','rider'), 'Choose driver or rider.')
    require(kind in ('regular','one','round'), 'Choose regular, one, or round.')
    require(role != 'driver' or bool(user['vehicle'].strip()), 'Add a vehicle in your profile before offering rides.')
    origin, destination = location(data.get('origin')), location(data.get('destination'))
    require(distance_miles(origin, destination) > 0.001, 'Pickup and drop-off centers must be different.')
    departure = integer(data, 'departure_hour', 0, 22)
    deadline = integer(data, 'arrive_by', departure+1, 23)
    seats = integer(data, 'seats', 1, 4)
    price = integer(data, 'price_cents', 0, 10000)
    detour = integer(data, 'detour_minutes', 0, 60)
    start = date_value(data.get('start_date'))
    end = date_value(data.get('end_date', data.get('start_date'))) if kind == 'regular' else start
    require(today() <= start <= end <= today()+dt.timedelta(days=120), 'Schedule dates must be within the next 120 days.')
    weekdays = data.get('weekdays', []) if kind == 'regular' else []
    require(isinstance(weekdays,list) and all(type(d) is int and 0 <= d <= 6 for d in weekdays), 'Weekdays must be numbers 0 (Monday) to 6 (Sunday).')
    require(kind != 'regular' or len(set(weekdays)) > 0, 'Choose at least one recurring weekday.')
    note = text(data, 'note', 0, 1000)
    return_hour = integer(data, 'return_hour', deadline, 23) if kind == 'round' else None
    dates = [start+dt.timedelta(days=i) for i in range((end-start).days+1) if kind != 'regular' or (start+dt.timedelta(days=i)).weekday() in weekdays]
    require(dates, 'No selected weekdays fall inside this date range.')
    for day in dates:
        require(dt.datetime.combine(day,dt.time(departure),ZONE)>now(), 'Departure must be in the future.')
    trip_id = db.execute('''INSERT INTO trips(owner_id,role,origin,destination,departure_hour,arrive_by,kind,weekdays,start_date,end_date,seats,price_cents,detour_minutes,note,return_hour,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (user['id'],role,json.dumps(origin),json.dumps(destination),departure,deadline,kind,json.dumps(sorted(set(weekdays))),str(start),str(end),seats,price,detour,note,return_hour,now().timestamp())).lastrowid
    db.execute('UPDATE trips SET price_meta=? WHERE id=?',(json.dumps(data.get('_price_meta',{'mode':'manual'})),trip_id))
    for day in dates:
        db.execute('INSERT INTO occurrences(trip_id,trip_date,capacity,driver_id) VALUES(?,?,?,?)',(trip_id,str(day),seats,user['id'] if role=='driver' else None))
    return trip_id


def identity_name(db, viewer_id, subject_id, oid):
    user=db.execute('SELECT name FROM users WHERE id=?',(subject_id,)).fetchone()
    if user is None:
        return 'Former member',False
    if viewer_id==subject_id:
        return user['name'],True
    o=joined_occurrence(db,oid)
    confirmed={r[0] for r in db.execute("SELECT requester_id FROM applications WHERE occurrence_id=? AND status='confirmed'",(oid,))}
    participants=confirmed|{o['owner_id']}
    revealed=viewer_id in participants and subject_id in participants
    if revealed:
        return user['name'],True
    salt=db.execute("SELECT value FROM app_settings WHERE key='identity_salt'").fetchone()[0]
    code=hmac.new(salt.encode(),str(subject_id).encode(),hashlib.sha256).hexdigest()[:6].upper()
    return 'Loop Member '+code,False


def private_text(db, value, viewer_id, oid):
    value=str(value or '')
    for person in db.execute('SELECT id,name,email FROM users').fetchall():
        display,revealed=identity_name(db,viewer_id,person['id'],oid)
        if not revealed:
            value=re.sub(re.escape(person['name']),lambda m:display,value,flags=re.I)
            value=re.sub(re.escape(person['email']),'[contact shared after matching]',value,flags=re.I)
    return value


def shared_meeting_point(requested,posted):
    if not requested:
        return {**posted,'mode':'exact','radius_miles':0}
    distance=distance_miles(requested,posted)
    if distance<=posted['radius_miles']+0.000622:
        return {**requested,'mode':'exact','radius_miles':0}
    if distance<=requested['radius_miles']+0.000622:
        return {**posted,'mode':'exact','radius_miles':0}
    require(overlaps(requested,posted),'These location areas do not overlap.')
    # Interpolate on the great-circle arc into the overlap, not across map pixels.
    low=max(0,distance-posted['radius_miles'])
    high=min(distance,requested['radius_miles'])
    fraction=(low+high)/(2*distance)
    a,b=math.radians(requested['lat']),math.radians(posted['lat'])
    c,d=math.radians(requested['lon']),math.radians(posted['lon'])
    angle=distance/3958.7613
    left=math.sin((1-fraction)*angle)/math.sin(angle)
    right=math.sin(fraction*angle)/math.sin(angle)
    x=left*math.cos(a)*math.cos(c)+right*math.cos(b)*math.cos(d)
    y=left*math.cos(a)*math.sin(c)+right*math.cos(b)*math.sin(d)
    z=left*math.sin(a)+right*math.sin(b)
    return dict(label=('Shared meeting point near '+requested['label'])[:180],lat=math.degrees(math.atan2(z,math.sqrt(x*x+y*y))),lon=math.degrees(math.atan2(y,x)),mode='exact',radius_miles=0)


def list_trips(db, actor_id, criteria=None):
    criteria=criteria or {}
    require(isinstance(criteria,dict),'Search filters must be an object.')
    require(not criteria.get('role') or criteria['role'] in ('all','driver','rider'),'Invalid board role.')
    require(not criteria.get('kind') or criteria['kind'] in ('regular','one','round'),'Invalid trip type.')
    for key,lo,hi in [('departure_hour',0,23),('departure_from',0,23),('departure_to',0,23),('arrive_by',0,23),('detour_minutes',0,60)]:
        if criteria.get(key) is not None:
            integer(criteria,key,lo,hi)
    from_hour=criteria['departure_from'] if criteria.get('departure_from') is not None else 0
    to_hour=criteria['departure_to'] if criteria.get('departure_to') is not None else 23
    require(from_hour<=to_hour,'The end hour must be after the start hour.')
    required_days=criteria.get('weekdays',[])
    require(isinstance(required_days,list) and all(type(d) is int and 0<=d<=6 for d in required_days),'Invalid weekdays.')
    clauses=['o.status=?'];args=['active']
    if criteria.get('date'):
        clauses.append('o.trip_date=?');args.append(str(date_value(criteria['date'])))
    else:
        clauses.append('o.trip_date>=?');args.append(str(date_value(criteria['date_from'])) if criteria.get('date_from') else str(today()))
        if criteria.get('date_to'):
            clauses.append('o.trip_date<=?');args.append(str(date_value(criteria['date_to'])))
        require(not criteria.get('date_from') or not criteria.get('date_to') or criteria['date_from']<=criteria['date_to'],'Invalid date range.')
    query='''SELECT o.*,t.owner_id,t.role,t.origin,t.destination,t.departure_hour,t.arrive_by,t.kind,t.weekdays,t.start_date,t.end_date,t.price_cents,t.price_meta,t.detour_minutes,t.note,t.return_hour,u.name AS owner_name,u.vehicle
        FROM occurrences o JOIN trips t ON t.id=o.trip_id JOIN users u ON u.id=t.owner_id WHERE '''+ ' AND '.join(clauses)
    rows=db.execute(query,args).fetchall()
    output=[]
    origin_filter=location(criteria['origin']) if criteria.get('origin') else None
    dest_filter=location(criteria['destination']) if criteria.get('destination') else None
    for raw in rows:
        r=effective_occurrence(dict(raw))
        r['price_meta']=json.loads(r['price_meta'])
        r['origin'],r['destination'],r['weekdays']=json.loads(r['origin']),json.loads(r['destination']),json.loads(r['weekdays'])
        if criteria.get('role') in ('driver','rider') and r['role']!=criteria['role']:
            continue
        if origin_filter and not overlaps(origin_filter,r['origin']):
            continue
        if dest_filter and not overlaps(dest_filter,r['destination']):
            continue
        if criteria.get('departure_hour') is not None and r['departure_hour']!=criteria['departure_hour']:
            continue
        if not from_hour<=r['departure_hour']<=to_hour:
            continue
        if criteria.get('arrive_by') is not None and r['arrive_by']>criteria['arrive_by']:
            continue
        if criteria.get('kind') and r['kind']!=criteria['kind']:
            continue
        if required_days and not all(d in r['weekdays'] for d in required_days):
            continue
        if criteria.get('detour_minutes') is not None and r['detour_minutes']>criteria['detour_minutes']:
            continue
        r['departed']=dt.datetime.combine(date_value(r['trip_date']),dt.time(r['departure_hour']),ZONE)<=now()
        if not criteria.get('date') and not criteria.get('_include_past') and r['departed']:
            continue
        r['confirmed_seats']=occupied(db,r['id'])
        r['available_seats']=max(0,r['capacity']-r['confirmed_seats']) if r['role']=='driver' else (0 if r['driver_id'] else r['capacity'])
        own=db.execute('SELECT id,status,party_size,agreed_price_cents FROM applications WHERE occurrence_id=? AND requester_id=?',(r['id'],actor_id)).fetchone()
        r['application']=dict(own) if own else None
        r['is_owner']=r['owner_id']==actor_id
        r['owner_name'],r['identity_revealed']=identity_name(db,actor_id,r['owner_id'],r['id'])
        from .features import rating_summary, recommend
        r['owner_rating']=rating_summary(db,r['owner_id'],r['role'])
        r['note']=private_text(db,r['note'],actor_id,r['id'])
        r['vehicle']=private_text(db,r['vehicle'],actor_id,r['id'])
        r['pickup_distance_miles']=round(distance_miles(origin_filter,r['origin']),3) if origin_filter else None
        r['dropoff_distance_miles']=round(distance_miles(dest_filter,r['destination']),3) if dest_filter else None
        r['search_origin']=origin_filter['label'] if origin_filter else None
        r['search_destination']=dest_filter['label'] if dest_filter else None
        r['suggested_meeting_origin']=shared_meeting_point(origin_filter,r['origin'])
        r['suggested_meeting_destination']=shared_meeting_point(dest_filter,r['destination'])
        r['match_type']='both_locations' if origin_filter and dest_filter else 'pickup' if origin_filter else 'dropoff' if dest_filter else None
        r['recommendation']=recommend(r,criteria)
        output.append(r)
    sort=criteria.get('sort','nearest')
    require(sort in ('nearest','recommended','soonest','price'),'Invalid sorting option.')
    if sort=='recommended':
        return sorted(output,key=lambda r:(-r['recommendation']['score'],r['trip_date'],r['departure_hour'],r['id']))
    if sort=='soonest':
        return sorted(output,key=lambda r:(r['trip_date'],r['departure_hour'],r['id']))
    if sort=='price':
        return sorted(output,key=lambda r:(r['price_cents'],r['trip_date'],r['departure_hour'],r['id']))
    return sorted(output,key=lambda r:((r['pickup_distance_miles'] or 0)+(r['dropoff_distance_miles'] or 0),r['trip_date'],r['departure_hour'],r['id']))


def request_ride(db, user, oid, data):
    require(user['verified'], 'Verify your student email first.',403)
    o = joined_occurrence(db,oid)
    ensure_open(o)
    require(o['owner_id']!=user['id'], 'You cannot request your own post.',409)
    require(o['role']!='rider' or bool(user['vehicle'].strip()), 'Add your vehicle before offering to drive.')
    require(o['role']!='rider' or o['driver_id'] is None, 'This rider already accepted a driver.',409)
    party = integer(data,'party_size',1,4,1) if o['role']=='driver' else o['seats']
    require(party<=o['capacity'],'Your party is larger than this ride’s passenger capacity.')
    pickup = fixed_point(data.get('meeting_origin'),json.loads(o['origin']))
    dropoff = fixed_point(data.get('meeting_destination'),json.loads(o['destination']))
    auto = boolean(data,'auto_confirm') if o['role']=='driver' else False
    existing = db.execute('SELECT id,status FROM applications WHERE occurrence_id=? AND requester_id=?',(oid,user['id'])).fetchone()
    require(not existing or existing['status'] in ('canceled','declined'), 'You already have an active request for this date.',409)
    values = (party,int(auto),json.dumps(pickup),json.dumps(dropoff),now().timestamp())
    if existing:
        aid = existing['id']
        db.execute("UPDATE applications SET status='pending',party_size=?,auto_confirm=?,meeting_origin=?,meeting_destination=?,created_at=?,agreed_price_cents=? WHERE id=?",(*values,o['price_cents'],aid))
    else:
        aid = db.execute("INSERT INTO applications(occurrence_id,requester_id,status,party_size,auto_confirm,meeting_origin,meeting_destination,created_at,agreed_price_cents) VALUES(?,?,'pending',?,?,?,?,?,?)",(oid,user['id'],*values,o['price_cents'])).lastrowid
    event(db,oid,user['id'],user['name']+' sent '+('a ride offer.' if o['role']=='rider' else 'a seat request.'))
    return aid


def decide(db,user,aid,accept):
    a = db.execute('SELECT * FROM applications WHERE id=?',(aid,)).fetchone()
    require(a is not None,'Request not found.',404)
    o = joined_occurrence(db,a['occurrence_id'])
    require(o['owner_id']==user['id'],'Only the post owner can decide this request.',403)
    ensure_open(o)
    require(a['status']=='pending','This request has already been decided.',409)
    if not accept:
        status='declined'
    elif o['role']=='rider':
        require(o['driver_id'] is None,'Another driver was already confirmed.',409)
        db.execute('UPDATE occurrences SET driver_id=? WHERE id=?',(a['requester_id'],o['id']))
        status='confirmed'
        # Other offers become unavailable atomically, not waitlisted passenger seats.
        db.execute("UPDATE applications SET status='declined' WHERE occurrence_id=? AND id<>? AND status='pending'",(o['id'],aid))
    else:
        status='confirmed' if occupied(db,o['id'])+a['party_size']<=o['capacity'] else 'waitlisted'
    db.execute('UPDATE applications SET status=? WHERE id=?',(status,aid))
    event(db,o['id'],user['id'],'Request #'+str(aid)+' '+status+'.')
    return status


def cancel_application(db,user,aid):
    a = db.execute('SELECT * FROM applications WHERE id=?',(aid,)).fetchone()
    require(a is not None,'Request not found.',404)
    o = joined_occurrence(db,a['occurrence_id'])
    require(a['requester_id']==user['id'],'Only the requesting student may cancel this request.',403)
    ensure_open(o)
    require(a['status'] in ('pending','waitlisted','confirmed'),'This request is already inactive.',409)
    prior=a['status']
    db.execute("UPDATE applications SET status='canceled',cancel_reason='requester' WHERE id=?",(aid,))
    if o['role']=='rider' and prior=='confirmed':
        db.execute('UPDATE occurrences SET driver_id=NULL WHERE id=?',(o['id'],))
        # Reopen other driver offers so the rider request appears active again.
        declined=db.execute(
            "SELECT count(*) FROM applications WHERE occurrence_id=? AND status='declined'",
            (o['id'],),
        ).fetchone()[0]
        db.execute(
            "UPDATE applications SET status='pending',cancel_reason=NULL WHERE occurrence_id=? AND status='declined'",
            (o['id'],),
        )
        notify(
            db, o['owner_id'], 'driver_canceled',
            'Your driver canceled',
            f"{user['name']} canceled for {o['trip_date']}. Your rider request is open again"
            + (' and other offers were restored.' if declined else '.'),
            occurrence_id=o['id'], application_id=aid,
        )
        event(db, o['id'], user['id'], user['name']+' canceled as driver. The rider request is open again.')
    else:
        event(db,o['id'],user['id'],user['name']+' canceled this date only.')
        if prior=='confirmed' and o['role']=='driver':
            notify(
                db, o['owner_id'], 'seat_freed',
                'A passenger canceled',
                f"{user['name']} canceled their seat for {o['trip_date']}. A seat is open again.",
                occurrence_id=o['id'], application_id=aid,
            )
    promoted=promote(db,o)
    if o['role']=='driver' and prior=='confirmed':
        notify_waitlist_openings(db,o,promoted)
    return promoted


def notify_waitlist_openings(db, o, promoted_ids):
    """Tell waitlisted riders when a seat opens; auto-promoted parties get a confirmation notice."""
    for aid in promoted_ids:
        row=db.execute('SELECT requester_id FROM applications WHERE id=?',(aid,)).fetchone()
        if row:
            notify(
                db, row['requester_id'], 'waitlist_promoted',
                'Seat confirmed from waitlist',
                f"A seat opened on {o['trip_date']}. Your approved party was automatically confirmed.",
                occurrence_id=o['id'], application_id=aid,
            )
    free=o['capacity']-occupied(db,o['id'])
    if free<=0:
        return
    for a in db.execute(
        "SELECT a.id,a.requester_id,a.party_size FROM applications a WHERE occurrence_id=? AND status='waitlisted' AND auto_confirm=0 ORDER BY created_at,id",
        (o['id'],),
    ).fetchall():
        if a['party_size']<=free:
            notify(
                db, a['requester_id'], 'waitlist_open',
                'A seat opened — claim it',
                f"A seat is open for {o['trip_date']}. Confirm soon to secure your spot for your party of {a['party_size']}.",
                occurrence_id=o['id'], application_id=a['id'],
            )


def cancel_occurrence(db, user, oid):
    """Owner cancels one ride date; riders keep the request visible and get a bell notification."""
    o=joined_occurrence(db,oid)
    require(o['owner_id']==user['id'],'Only the post owner can cancel the entire ride date.',403)
    ensure_open(o)
    affected=[dict(r) for r in db.execute(
        "SELECT id,requester_id,status FROM applications WHERE occurrence_id=? AND status IN ('pending','confirmed','waitlisted')",
        (oid,),
    ).fetchall()]
    db.execute("UPDATE occurrences SET status='canceled',driver_id=NULL WHERE id=?",(oid,))
    db.execute(
        "UPDATE applications SET status='canceled',cancel_reason='owner' WHERE occurrence_id=? AND status IN ('pending','confirmed','waitlisted')",
        (oid,),
    )
    event(db,oid,user['id'],'The owner canceled this ride date. No other dates were changed.')
    trip_label=f"{o['trip_date']} · {o['departure_hour']:02}:00"
    for a in affected:
        notify(
            db, a['requester_id'], 'driver_canceled',
            'Driver canceled this ride',
            f"The post owner canceled {trip_label}. Your request is back under Requests → Sent so you can find another ride.",
            occurrence_id=oid, application_id=a['id'],
        )
    return [a['id'] for a in affected]


def claim(db,user,aid):
    a=db.execute('SELECT * FROM applications WHERE id=?',(aid,)).fetchone()
    require(a is not None,'Request not found.',404)
    o=joined_occurrence(db,a['occurrence_id'])
    ensure_open(o)
    require(a['requester_id']==user['id'],'This waitlist entry belongs to another student.',403)
    require(a['status']=='waitlisted','Driver approval is required before claiming a seat.',409)
    promote(db,o)
    if db.execute('SELECT status FROM applications WHERE id=?',(aid,)).fetchone()[0]=='confirmed':
        return
    require(occupied(db,o['id'])+a['party_size']<=o['capacity'],'No seat is open for your party.',409)
    db.execute("UPDATE applications SET status='confirmed' WHERE id=?",(aid,))
    event(db,o['id'],user['id'],user['name']+' confirmed an open waitlist seat.')


def can_chat(db,user,oid):
    o=joined_occurrence(db,oid)
    allowed=o['owner_id']==user['id'] or db.execute("SELECT 1 FROM applications WHERE occurrence_id=? AND requester_id=? AND status='confirmed'",(oid,user['id'])).fetchone()
    require(bool(allowed),'Chat is available to the owner and confirmed participants only.',403)
    return o


def application_views(db,user):
    rows=db.execute('''SELECT a.*,u.name AS requester_name,t.owner_id,t.role,o.trip_date,o.status AS occurrence_status,o.trip_id,
        t.departure_hour,t.origin,t.destination,t.price_cents,owner.name AS owner_name
        FROM applications a JOIN users u ON u.id=a.requester_id JOIN occurrences o ON o.id=a.occurrence_id
        JOIN trips t ON t.id=o.trip_id JOIN users owner ON owner.id=t.owner_id
        WHERE a.requester_id=? OR t.owner_id=? ORDER BY a.created_at DESC,a.id DESC''',(user['id'],user['id'])).fetchall()
    result=[]
    for row in rows:
        r=dict(row)
        effective=joined_occurrence(db,r['occurrence_id'])
        for key in ('origin','destination','departure_hour','price_cents','kind'):
            r[key]=effective[key]
        if r['agreed_price_cents'] is None:
            r['agreed_price_cents']=r['price_cents']
        r['total_price_cents']=r['agreed_price_cents']*r['party_size']
        from .features import rating_summary
        r['counterparty_rating']=rating_summary(db,r['requester_id'] if r['owner_id']==user['id'] else r['owner_id'],('rider' if r['role']=='driver' else 'driver') if r['owner_id']==user['id'] else r['role'])
        r['waitlist_position']=1+db.execute("SELECT count(*) FROM applications WHERE occurrence_id=? AND status='waitlisted' AND (created_at<? OR (created_at=? AND id<?))",(r['occurrence_id'],r['created_at'],r['created_at'],r['id'])).fetchone()[0] if r['status']=='waitlisted' else None
        for key in ('origin','destination','meeting_origin','meeting_destination'):
            r[key]=json.loads(r[key])
        r['incoming']=r['owner_id']==user['id']
        r['requester_name'],requester_revealed=identity_name(db,user['id'],r['requester_id'],r['occurrence_id'])
        r['owner_name'],owner_revealed=identity_name(db,user['id'],r['owner_id'],r['occurrence_id'])
        r['identity_revealed']=requester_revealed if r['incoming'] else owner_revealed
        r['closed']=r['occurrence_status']!='active' or dt.datetime.combine(date_value(r['trip_date']),dt.time(r['departure_hour']),ZONE)<=now()
        r['cancel_reason']=r.get('cancel_reason')
        r['owner_canceled']=r['status']=='canceled' and r.get('cancel_reason')=='owner'
        result.append(r)
    return result


PLACES=[
 dict(id='wv',label='Wilshire / Vermont Station',lat=34.0621,lon=-118.2904),
 dict(id='ww',label='Wilshire / Western Station',lat=34.0617,lon=-118.3088),
 dict(id='pa',label='Memorial Park Station',lat=34.1484,lon=-118.1478),
 dict(id='sm',label='Santa Monica Public Library',lat=34.0195,lon=-118.4914),
 dict(id='usc',label='USC Downey Way',lat=34.0203,lon=-118.2915),
 dict(id='village',label='USC Village',lat=34.0257,lon=-118.2857),
 dict(id='leavey',label='USC Leavey Library',lat=34.0217,lon=-118.2828)
]


def seed(store):
    with store.tx() as db:
        if db.execute('SELECT count(*) FROM users').fetchone()[0]:
            return
        password=hash_password(os.getenv('DEMO_PASSWORD','heky-local-2026'))
        people=[('Jamie Lee','jamie','Honda Civic · Blue'),('Mina Park','mina','Toyota Prius · Silver'),('Sofia Lee','sofia','Hyundai Ioniq · White'),('Daniel Kim','daniel',''),('Leo Kim','leo',''),('Ethan Wu','ethan','')]
        ids={}
        for name,email,vehicle in people:
            ids[email]=db.execute('INSERT INTO users(name,email,password_hash,verified,vehicle) VALUES(?,?,?,1,?)',(name,email+'@usc.edu',password,vehicle)).lastrowid

        def user(who):
            return dict(db.execute('SELECT * FROM users WHERE id=?',(ids[who],)).fetchone())

        def loc(i, mode='exact', radius=0):
            return {**{k: v for k, v in PLACES[i].items() if k != 'id'}, 'mode': mode, 'radius_miles': radius}

        def post(who, **data):
            return trip_create(db, user(who), data)

        def first_occurrence(tid):
            return db.execute('SELECT id FROM occurrences WHERE trip_id=? ORDER BY trip_date LIMIT 1', (tid,)).fetchone()[0]

        def book(oid, who, status='confirmed', party=1, pickup=None, dropoff=None, auto=True, price=None):
            o = joined_occurrence(db, oid)
            pickup = pickup or json.loads(o['origin'])
            dropoff = dropoff or json.loads(o['destination'])
            for point in (pickup, dropoff):
                point['mode'] = 'exact'
                point['radius_miles'] = 0
            agreed = price if price is not None else o['price_cents']
            db.execute(
                '''INSERT INTO applications(occurrence_id,requester_id,status,party_size,auto_confirm,meeting_origin,meeting_destination,created_at,agreed_price_cents)
                   VALUES(?,?,?,?,?,?,?,?,?)''',
                (oid, ids[who], status, party, int(auto), json.dumps(pickup), json.dumps(dropoff), now().timestamp(), agreed),
            )
            if status == 'confirmed' and o['role'] == 'rider':
                db.execute('UPDATE occurrences SET driver_id=? WHERE id=?', (ids[who], oid))

        def rate(oid, rater, subject, role, stars):
            db.execute(
                '''INSERT INTO ratings(occurrence_id,rater_id,subject_id,subject_role,stars,created_at)
                   VALUES(?,?,?,?,?,?)''',
                (oid, ids[rater], ids[subject], role, stars, now().timestamp()),
            )

        def backdate(oid, days_ago):
            day = today() - dt.timedelta(days=days_ago)
            db.execute('UPDATE occurrences SET trip_date=? WHERE id=?', (str(day), oid))
            return day

        start = today() + dt.timedelta(days=(7 - today().weekday()) % 7 or 7)
        commute = dict(
            departure_hour=8, arrive_by=9, kind='regular', weekdays=[0, 2, 4],
            start_date=str(start), end_date=str(start + dt.timedelta(days=27)),
            seats=2, price_cents=400, detour_minutes=10,
            note='Meet five minutes early. Please confirm the exact meeting points in your request.',
        )

        # Recurring board: morning campus loops + one afternoon Tu/Th series.
        sofia_weekly = post('sofia', role='driver', origin=loc(3, 'area', 1), destination=loc(4, 'area', 0.5), **commute)
        mina_weekly = post('mina', role='driver', origin=loc(0, 'area', 1), destination=loc(4), **commute)
        jamie_weekly = post('jamie', role='driver', origin=loc(2, 'area', 1), destination=loc(5), **{**commute, 'weekdays': [1, 3], 'departure_hour': 17, 'arrive_by': 18, 'price_cents': 500, 'note': 'Afternoon Tu/Th Village drop-off. Trunk fits two backpacks.'})
        post('daniel', role='rider', origin=loc(0, 'area', 0.5), destination=loc(4), **{**commute, 'seats': 1, 'price_cents': 350, 'note': 'Looking for a steady Mon/Wed/Fri driver toward Downey Way.'})

        # Waitlist practice on Sofia’s weekly dates.
        for occurrence in db.execute('SELECT id FROM occurrences WHERE trip_id=? ORDER BY trip_date', (sofia_weekly,)).fetchall():
            oid = occurrence['id']
            book(oid, 'jamie', 'confirmed', pickup=loc(3), dropoff=loc(4))
            book(oid, 'ethan', 'confirmed', pickup=loc(3), dropoff=loc(4))
            book(oid, 'leo', 'waitlisted', pickup=loc(3), dropoff=loc(4))
            event(db, oid, ids['sofia'], 'Sample weekly commute created. Cancel one passenger seat to try real waitlist promotion.')

        # Upcoming one-time and round-trip variety on the board.
        soon = today() + dt.timedelta(days=2)
        while soon.weekday() >= 5:
            soon += dt.timedelta(days=1)
        later = soon + dt.timedelta(days=3)

        def one_day(day, **extra):
            payload = dict(kind='one', weekdays=[], start_date=str(day), end_date=str(day), seats=2, detour_minutes=12)
            payload.update(extra)
            return payload

        def round_day(day, **extra):
            payload = dict(kind='round', weekdays=[], start_date=str(day), end_date=str(day), seats=3, detour_minutes=15, return_hour=18)
            payload.update(extra)
            return payload

        mina_one = post(
            'mina', **one_day(
                soon, role='driver', origin=loc(1, 'area', 1), destination=loc(6),
                departure_hour=9, arrive_by=10, price_cents=450,
                note='One-time study-session ride to Leavey.',
            )
        )
        book(first_occurrence(mina_one), 'leo', 'pending', pickup=loc(1), dropoff=loc(6))

        jamie_round = post(
            'jamie', **round_day(
                later, role='driver', origin=loc(5), destination=loc(3, 'area', 1),
                departure_hour=10, arrive_by=11, price_cents=700,
                note='Round trip to Santa Monica for a museum afternoon. Both legs included.',
            )
        )
        book(first_occurrence(jamie_round), 'daniel', 'confirmed', pickup=loc(5), dropoff=loc(3))

        post(
            'sofia', **one_day(
                later, role='driver', origin=loc(4), destination=loc(2, 'area', 1),
                departure_hour=19, arrive_by=20, price_cents=550, seats=3,
                note='Evening one-time ride toward Pasadena after a campus event.',
            )
        )
        post(
            'leo', **one_day(
                soon + dt.timedelta(days=1), role='rider', origin=loc(6), destination=loc(0, 'area', 0.5),
                departure_hour=7, arrive_by=8, price_cents=300, seats=1,
                note='One-time early rider request toward Wilshire / Vermont.',
            )
        )
        post(
            'ethan', **round_day(
                later + dt.timedelta(days=1), role='rider', origin=loc(4), destination=loc(3),
                departure_hour=16, arrive_by=17, price_cents=650, seats=2,
                note='Round-trip rider request: two of us need both legs covered.',
            )
        )

        # Completed rides for rating practice (create upcoming, then backdate).
        # 1) One-time: Mina drove Jamie + Leo — some ratings already saved, one still open.
        past_one = post(
            'mina', **one_day(
                soon, role='driver', origin=loc(0), destination=loc(4),
                departure_hour=8, arrive_by=9, price_cents=400,
                note='Completed one-time commute · rate remaining partners in My rides → Past.',
            )
        )
        past_one_oid = first_occurrence(past_one)
        book(past_one_oid, 'jamie', 'confirmed')
        book(past_one_oid, 'leo', 'confirmed')
        backdate(past_one_oid, 3)
        # Driver already rated both riders; both passengers still need to rate Mina.
        rate(past_one_oid, 'mina', 'jamie', 'rider', 4)
        rate(past_one_oid, 'mina', 'leo', 'rider', 5)

        # 2) Round trip: Sofia drove Ethan — mutual ratings already in place.
        past_round = post(
            'sofia', **round_day(
                soon, role='driver', origin=loc(4), destination=loc(3),
                departure_hour=11, arrive_by=12, return_hour=17, price_cents=800, seats=2,
                note='Completed round trip · open Past rides to edit or review ratings.',
            )
        )
        past_round_oid = first_occurrence(past_round)
        book(past_round_oid, 'ethan', 'confirmed')
        backdate(past_round_oid, 5)
        rate(past_round_oid, 'ethan', 'sofia', 'driver', 4)
        rate(past_round_oid, 'sofia', 'ethan', 'rider', 5)

        # 3) Recurring-style past date: Jamie drove Daniel — rider still needs to rate.
        past_regular = post(
            'jamie',
            role='driver', origin=loc(2, 'area', 1), destination=loc(5),
            departure_hour=17, arrive_by=18, price_cents=500, seats=2, detour_minutes=10,
            kind='regular', weekdays=[soon.weekday()], start_date=str(soon), end_date=str(soon),
            note='Completed recurring afternoon hop · Daniel can still rate Jamie.',
        )
        past_regular_oid = first_occurrence(past_regular)
        book(past_regular_oid, 'daniel', 'confirmed')
        backdate(past_regular_oid, 4)
        rate(past_regular_oid, 'jamie', 'daniel', 'rider', 5)
        event(db, past_one_oid, ids['mina'], 'Seeded completed rides for rating practice. Open My rides → Past.')
