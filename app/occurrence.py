"""Occurrence lookup and seat occupancy helpers."""
from __future__ import annotations

import datetime as dt

from .clock import ZONE, now
from .errors import require
from .validation import date_value


def joined_occurrence(db, oid):
    row = db.execute(
        '''SELECT o.*,t.owner_id,t.role,t.departure_hour,t.return_hour,
        t.origin,t.destination,t.seats,t.note,t.price_cents FROM occurrences o
        JOIN trips t ON t.id=o.trip_id WHERE o.id=?''',
        (oid,),
    ).fetchone()
    require(row is not None, 'Ride date not found.', 404)
    return row


def ensure_open(o):
    departure = dt.datetime.combine(date_value(o['trip_date']), dt.time(o['departure_hour']), ZONE)
    require(o['status'] == 'active' and departure > now(), 'This ride has departed or was canceled.', 409)


def occupied(db, oid):
    return db.execute(
        "SELECT coalesce(sum(party_size),0) FROM applications WHERE occurrence_id=? AND status='confirmed'",
        (oid,),
    ).fetchone()[0]
