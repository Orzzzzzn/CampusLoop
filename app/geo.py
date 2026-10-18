"""Great-circle distance, area overlap, and meeting-point helpers."""
from __future__ import annotations

import math

from .errors import require
from .validation import location

EARTH_RADIUS_MILES = 3958.7613
# One metre accounts for floating-point/pin rounding; no walking radius is added to exact places.
ROUNDING_MILES = 0.000622


def distance_miles(a, b):
    lat1, lat2 = math.radians(a['lat']), math.radians(b['lat'])
    dlat, dlon = lat2 - lat1, math.radians(b['lon'] - a['lon'])
    v = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_MILES * 2 * math.asin(math.sqrt(min(1, max(0, v))))


def overlaps(a, b):
    return distance_miles(a, b) <= a['radius_miles'] + b['radius_miles'] + ROUNDING_MILES


def fixed_point(point, allowed):
    point = location(point)
    require(point['mode'] == 'exact', 'Propose an exact meeting point for confirmation.')
    require(overlaps(point, allowed), 'The proposed meeting point is outside the posted location area.')
    return point


def shared_meeting_point(requested, posted):
    if not requested:
        return {**posted, 'mode': 'exact', 'radius_miles': 0}
    distance = distance_miles(requested, posted)
    if distance <= posted['radius_miles'] + ROUNDING_MILES:
        return {**requested, 'mode': 'exact', 'radius_miles': 0}
    if distance <= requested['radius_miles'] + ROUNDING_MILES:
        return {**posted, 'mode': 'exact', 'radius_miles': 0}
    require(overlaps(requested, posted), 'These location areas do not overlap.')
    # Interpolate on the great-circle arc into the overlap, not across map pixels.
    low = max(0, distance - posted['radius_miles'])
    high = min(distance, requested['radius_miles'])
    fraction = (low + high) / (2 * distance)
    a, b = math.radians(requested['lat']), math.radians(posted['lat'])
    c, d = math.radians(requested['lon']), math.radians(posted['lon'])
    angle = distance / EARTH_RADIUS_MILES
    left = math.sin((1 - fraction) * angle) / math.sin(angle)
    right = math.sin(fraction * angle) / math.sin(angle)
    x = left * math.cos(a) * math.cos(c) + right * math.cos(b) * math.cos(d)
    y = left * math.cos(a) * math.sin(c) + right * math.cos(b) * math.sin(d)
    z = left * math.sin(a) + right * math.sin(b)
    return dict(
        label=('Shared meeting point near ' + requested['label'])[:180],
        lat=math.degrees(math.atan2(z, math.sqrt(x * x + y * y))),
        lon=math.degrees(math.atan2(y, x)),
        mode='exact',
        radius_miles=0,
    )
