"""Application clock and Pacific time zone helpers."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    ZONE = ZoneInfo('America/Los_Angeles')
except ZoneInfoNotFoundError:
    with (Path(__file__).parent / 'zoneinfo/Los_Angeles').open('rb') as zone_file:
        ZONE = ZoneInfo.from_file(zone_file, key='America/Los_Angeles')


def now():
    return dt.datetime.now(ZONE)


def today():
    return now().date()
