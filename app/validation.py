"""Request field parsing and location payload validation."""
from __future__ import annotations

import datetime as dt
import math

from .errors import Problem, require


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


def location(data):
    require(isinstance(data, dict), 'Choose a location and place its pin on the map.')
    label = text(data, 'label', 3, 180)
    require(data.get('mode') in ('exact', 'area'), 'Location mode must be exact or area.')
    lat, lon = data.get('lat'), data.get('lon')
    require(type(lat) in (int, float) and math.isfinite(lat) and -90 <= lat <= 90, 'A valid latitude is required.')
    require(type(lon) in (int, float) and math.isfinite(lon) and -180 <= lon <= 180, 'A valid longitude is required.')
    radius = data.get('radius_miles', 0) if data['mode'] == 'area' else 0
    require(type(radius) in (int, float) and math.isfinite(radius), 'Radius must be a number.')
    require(data['mode'] == 'exact' or 0.1 <= radius <= 10, 'An area needs a radius between 0.1 and 10 miles.')
    return dict(label=label, lat=float(lat), lon=float(lon), mode=data['mode'], radius_miles=float(radius))
