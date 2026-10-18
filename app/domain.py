"""Compatibility facade: re-export domain pieces used across the app and tests."""
from __future__ import annotations

from .auth_crypto import check_password, hash_password
from .clock import ZONE, now, today
from .db import SCHEMA, Store
from .errors import Problem, require
from .geo import distance_miles, fixed_point, overlaps, shared_meeting_point
from .identity import event, identity_name, private_text, public_user
from .occurrence import ensure_open, joined_occurrence, occupied
from .paths import DEFAULT_DATABASE_NAME, DEFAULT_DEMO_PASSWORD, ROOT
from .rides import (
    application_views,
    can_chat,
    cancel_application,
    claim,
    decide,
    list_trips,
    promote,
    request_ride,
    trip_create,
)
from .seed import PLACES, seed
from .validation import boolean, date_value, integer, location, text

__all__ = [
    'DEFAULT_DATABASE_NAME',
    'DEFAULT_DEMO_PASSWORD',
    'PLACES',
    'Problem',
    'ROOT',
    'SCHEMA',
    'Store',
    'ZONE',
    'application_views',
    'boolean',
    'can_chat',
    'cancel_application',
    'check_password',
    'claim',
    'date_value',
    'decide',
    'distance_miles',
    'ensure_open',
    'event',
    'fixed_point',
    'hash_password',
    'identity_name',
    'integer',
    'joined_occurrence',
    'list_trips',
    'location',
    'now',
    'occupied',
    'overlaps',
    'private_text',
    'promote',
    'public_user',
    'request_ride',
    'require',
    'seed',
    'shared_meeting_point',
    'text',
    'today',
    'trip_create',
]
