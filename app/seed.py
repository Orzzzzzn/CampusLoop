"""Demo catalog places and seeded development accounts."""
from __future__ import annotations

import datetime as dt
import json
import os

from .auth_crypto import hash_password
from .clock import now, today
from .identity import event
from .paths import DEFAULT_DEMO_PASSWORD
from .rides import trip_create

PLACES = [
    dict(id='wv', label='Wilshire / Vermont Station (sample pin)', lat=34.0621, lon=-118.2904),
    dict(id='ww', label='Wilshire / Western Station (sample pin)', lat=34.0617, lon=-118.3088),
    dict(id='pa', label='Memorial Park Station (sample pin)', lat=34.1484, lon=-118.1478),
    dict(id='sm', label='Santa Monica Public Library (sample pin)', lat=34.0195, lon=-118.4914),
    dict(id='usc', label='USC Downey Way (sample pin)', lat=34.0203, lon=-118.2915),
    dict(id='village', label='USC Village (sample pin)', lat=34.0257, lon=-118.2857),
    dict(id='leavey', label='USC Leavey Library (sample pin)', lat=34.0217, lon=-118.2828),
]


def seed(store):
    with store.tx() as db:
        if db.execute('SELECT count(*) FROM users').fetchone()[0]:
            return
        password = hash_password(os.getenv('DEMO_PASSWORD', DEFAULT_DEMO_PASSWORD))
        people = [
            ('Jamie Lee', 'jamie', 'Honda Civic · Blue'),
            ('Mina Park', 'mina', 'Toyota Prius · Silver'),
            ('Sofia Lee', 'sofia', 'Hyundai Ioniq · White'),
            ('Daniel Kim', 'daniel', ''),
            ('Leo Kim', 'leo', ''),
            ('Ethan Wu', 'ethan', ''),
        ]
        ids = {}
        for name, email, vehicle in people:
            ids[email] = db.execute(
                'INSERT INTO users(name,email,password_hash,verified,vehicle) VALUES(?,?,?,1,?)',
                (name, email + '@usc.edu', password, vehicle),
            ).lastrowid
        start = today() + dt.timedelta(days=(7 - today().weekday()) % 7 or 7)

        def loc(i, mode='exact', radius=0):
            return {**{k: v for k, v in PLACES[i].items() if k != 'id'}, 'mode': mode, 'radius_miles': radius}

        base = dict(
            departure_hour=8,
            arrive_by=9,
            kind='regular',
            weekdays=[0, 2, 4],
            start_date=str(start),
            end_date=str(start + dt.timedelta(days=27)),
            seats=2,
            price_cents=400,
            detour_minutes=10,
            note='Meet five minutes early. Please confirm the exact meeting points in your request.',
        )
        created = []
        for who, role, ori, dest in [
            ('mina', 'driver', loc(0, 'area', 1), loc(4)),
            ('sofia', 'driver', loc(3, 'area', 1), loc(4, 'area', 0.5)),
            ('jamie', 'driver', loc(2, 'area', 1), loc(5)),
            ('daniel', 'rider', loc(0, 'area', 0.5), loc(4)),
        ]:
            user = db.execute('SELECT * FROM users WHERE id=?', (ids[who],)).fetchone()
            tid = trip_create(db, user, {**base, 'role': role, 'origin': ori, 'destination': dest, 'seats': 1 if role == 'rider' else 2})
            created.append(tid)
        # Every recurring date keeps its own bookings and queue.
        for occurrence in db.execute(
            'SELECT id FROM occurrences WHERE trip_id=? ORDER BY trip_date',
            (created[1],),
        ).fetchall():
            oid = occurrence['id']
            for who, status in [('jamie', 'confirmed'), ('ethan', 'confirmed'), ('leo', 'waitlisted')]:
                db.execute(
                    '''INSERT INTO applications(occurrence_id,requester_id,status,party_size,auto_confirm,meeting_origin,meeting_destination,created_at)
                    VALUES(?,?,?,1,1,?,?,?)''',
                    (oid, ids[who], status, json.dumps(loc(3)), json.dumps(loc(4)), now().timestamp()),
                )
            event(
                db,
                oid,
                ids['sofia'],
                'Sample weekly commute created. Cancel one passenger seat to try real waitlist promotion.',
            )
