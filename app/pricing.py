"""Shared rider pricing, using the unrounded Google quote saved with a trip."""
from decimal import Decimal, ROUND_HALF_UP
import json

MODEL = 'google_shared_v1'


def cents(value):
    return int(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def amounts(base, riders):
    base = Decimal(str(base))
    earnings = base * (1 + Decimal('0.65') * (riders - 1))
    return dict(driver_earnings_cents=cents(earnings),
                rider_price_cents=cents(earnings / riders))


def summary(meta, capacity, riders=0):
    base = meta['base_amount_cents']
    single, full = amounts(base, 1), amounts(base, capacity)
    current=amounts(base, max(1, riders))
    if not riders: current['driver_earnings_cents']=0
    return dict(model=MODEL, rider_count=riders, capacity=capacity,
                **current,
                earnings_min_cents=single['driver_earnings_cents'],
                earnings_max_cents=full['driver_earnings_cents'],
                price_min_cents=full['rider_price_cents'],
                price_max_cents=single['rider_price_cents'],
                distance_miles=meta['distance_miles'],
                duration_minutes=meta['duration_minutes'],
                source='Google Maps', traffic_aware=True,
                quoted_at=meta['quoted_at'])


def occurrence_pricing(db, occurrence, party=0):
    """Pending/waitlisted parties never count until they can be confirmed whole."""
    meta = occurrence['price_meta']
    if isinstance(meta, str):
        meta = json.loads(meta)
    if meta.get('model') != MODEL:
        return None
    if occurrence['role'] == 'rider':
        current = occurrence['capacity'] if occurrence['driver_id'] else 0
        projected = occurrence['capacity'] if party else current
    else:
        current = db.execute("SELECT coalesce(sum(party_size),0) FROM applications WHERE occurrence_id=? AND status='confirmed'",
                             (occurrence['id'],)).fetchone()[0]
        projected = current + party
    waitlist = projected > occurrence['capacity']
    result = summary(meta, occurrence['capacity'], current if waitlist else projected)
    result['would_waitlist'] = waitlist
    return result
