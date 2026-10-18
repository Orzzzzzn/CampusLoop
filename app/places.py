"""Cached, user-triggered place search with a local catalog and configurable Photon endpoint."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import time
import urllib.parse
import urllib.request

from .errors import Problem, require
from .seed import PLACES


class Places:
    def __init__(self, store, base_url=None):
        self.store = store
        default = os.getenv('GEOCODER_URL', 'https://photon.komoot.io/api/')
        self.base = (base_url if base_url is not None else default).rstrip('/') + '/'
        self.lock = threading.Lock()
        self.next_request = 0.0

    def search(self, query, bias=None):
        query = query.strip()
        require(2 <= len(query) <= 180, 'Enter at least two characters for a place search.')
        params = {'q': query, 'limit': 5, 'lang': 'en'}
        if bias is not None:
            require(isinstance(bias, dict), 'Invalid place search center.')
            lat, lon = bias.get('lat'), bias.get('lon')
            require(
                type(lat) in (int, float)
                and type(lon) in (int, float)
                and math.isfinite(lat)
                and math.isfinite(lon)
                and -90 <= lat <= 90
                and -180 <= lon <= 180,
                'Invalid place search center.',
            )
            params.update(lat=round(lat, 4), lon=round(lon, 4))
        normalized = re.sub(r'[^a-z0-9]+', ' ', query.lower()).strip()
        aliases = {
            'usc': 'usc',
            'university of southern california': 'usc',
            'koreatown': 'wv',
            'pasadena': 'pa',
            'santa monica': 'sm',
        }
        local = []
        for place in PLACES:
            name = re.sub(r'[^a-z0-9]+', ' ', place['label'].lower()).strip()
            if normalized and (normalized in name or aliases.get(normalized) == place['id']):
                local.append({
                    **place,
                    'label': place['label'].replace(' (sample pin)', ''),
                    'source': 'catalog',
                })
        if local:
            return {
                'places': local,
                'source': 'catalog',
                'attribution': 'Bundled sample places; verify the meeting entrance.',
            }
        key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
        with self.store.read() as db:
            cached = db.execute(
                'SELECT results FROM place_cache WHERE cache_key=? AND expires>?',
                (key, time.time()),
            ).fetchone()
        if cached:
            return {**json.loads(cached['results']), 'cached': True}
        require(
            bool(self.base.strip('/')),
            'Online place search is disabled. Choose a catalog place or use the map.',
            503,
        )
        with self.lock:
            require(time.monotonic() >= self.next_request, 'Please wait a moment before another place search.', 429)
            self.next_request = time.monotonic() + 1
            request = urllib.request.Request(
                self.base + '?' + urllib.parse.urlencode(params),
                headers={'User-Agent': 'CampusLoop-Local-MVP/1.0', 'Accept': 'application/json'},
            )
            try:
                with urllib.request.urlopen(request, timeout=8) as response:
                    data = json.load(response)
                    if not isinstance(data, dict) or not isinstance(data.get('features'), list):
                        raise ValueError('Invalid geocoder response')
            except (OSError, ValueError) as exc:
                raise Problem(
                    503,
                    'Place search is temporarily unavailable. Choose a bundled place or pick your location on the map.',
                ) from exc
        found = []
        for feature in data.get('features', [])[:5]:
            if not isinstance(feature, dict):
                continue
            props = feature.get('properties', {})
            geometry = feature.get('geometry', {})
            if not isinstance(props, dict) or not isinstance(geometry, dict):
                continue
            point = geometry.get('coordinates', [])
            if geometry.get('type') != 'Point' or not isinstance(point, list) or len(point) < 2:
                continue
            lon, lat = point[:2]
            if (
                type(lat) not in (int, float)
                or type(lon) not in (int, float)
                or not math.isfinite(lat)
                or not math.isfinite(lon)
                or not -90 <= lat <= 90
                or not -180 <= lon <= 180
            ):
                continue
            street = ' '.join(str(props.get(k, '')) for k in ['housenumber', 'street']).strip()
            parts = list(
                dict.fromkeys(
                    str(x)
                    for x in [
                        props.get('name'),
                        street,
                        props.get('city') or props.get('district'),
                        props.get('state'),
                    ]
                    if x
                )
            )
            if not parts:
                continue
            found.append(
                dict(
                    id='photon:' + str(props.get('osm_type', '')) + ':' + str(props.get('osm_id', '')),
                    label=', '.join(parts)[:180],
                    lat=lat,
                    lon=lon,
                    source='photon',
                )
            )
        result = {
            'places': found,
            'source': 'photon',
            'attribution': '© OpenStreetMap contributors · Photon geocoding',
        }
        with self.store.tx() as db:
            db.execute(
                'INSERT OR REPLACE INTO place_cache(cache_key,results,expires) VALUES(?,?,?)',
                (key, json.dumps(result), time.time() + 86400),
            )
        return result
