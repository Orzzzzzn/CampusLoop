"""Google HTTP contract and shared-price lifecycle; no real key or paid API calls."""
import datetime as dt
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import threading
import unittest

import test_app as base
from app.domain import Problem, ZONE
from app.pricing import amounts


class PricingTests(unittest.TestCase):
    create = base.AppTests.create
    apply = base.AppTests.apply
    search = base.AppTests.search

    def setUp(self):
        base.AppTests.setUp(self)
        self.calls = []
        self.distance = 16093.44  # Explicit HTTP fixture: 10 miles, 20 minutes.
        self.duration = '1200s'
        self.error = False
        owner = self

        class GoogleFixture(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.calls.append((self.path, dict(self.headers), body))
                payload = (dict(error={'message': 'sensitive-provider-body'}) if owner.error else
                           dict(routes=[dict(distanceMeters=owner.distance, duration=owner.duration)]))
                data = json.dumps(payload).encode()
                self.send_response(403 if owner.error else 200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.google = ThreadingHTTPServer(('127.0.0.1', 0), GoogleFixture)
        self.google_thread = threading.Thread(target=self.google.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        self.google_thread.start()
        self.app.routes.google_key = 'fixture-secret'
        self.app.routes.google_url = f'http://127.0.0.1:{self.google.server_port}/directions/v2:computeRoutes'

    def tearDown(self):
        self.google.shutdown()
        self.google.server_close()
        self.google_thread.join(2)
        base.AppTests.tearDown(self)

    def automatic(self, **kwargs):
        return self.create(price_mode='automatic', **kwargs)

    def application(self, who, aid):
        return next(a for a in self.clients[who].call('/api/applications')[1]['applications'] if a['id'] == aid)

    def accept(self, aid, who='mina', action='accept'):
        client = self.clients[who]
        code, quote = client.call(f'/api/applications/{aid}/price', {})
        self.assertEqual(code, 200, quote)
        code, result = client.call(f'/api/applications/{aid}/{action}',
                                  dict(expected_rider_count=quote['pricing']['rider_count']))
        self.assertEqual(code, 200, result)
        return result

    def test_google_traffic_request_units_cache_and_no_key_exposure(self):
        ride = self.automatic(seats=4)
        quote = ride['price_meta']
        self.assertEqual(quote['price_cents'], 1200)
        self.assertEqual(quote['distance_miles'], 10)
        self.assertEqual(quote['duration_minutes'], 20)
        self.assertEqual(ride['pricing']['earnings_min_cents'], 1200)
        self.assertEqual(ride['pricing']['earnings_max_cents'], 3540)
        self.assertEqual(ride['pricing']['price_min_cents'], 885)
        self.assertEqual(ride['pricing']['price_max_cents'], 1200)
        path, headers, payload = self.calls[0]
        self.assertEqual(path, '/directions/v2:computeRoutes')
        normalized = {k.lower(): v for k, v in headers.items()}
        self.assertEqual(normalized['x-goog-api-key'], 'fixture-secret')
        self.assertEqual(normalized['x-goog-fieldmask'], 'routes.distanceMeters,routes.duration')
        self.assertEqual(payload['travelMode'], 'DRIVE')
        self.assertEqual(payload['routingPreference'], 'TRAFFIC_AWARE')
        expected = dt.datetime.combine(dt.date.fromisoformat(self.date), dt.time(8), ZONE).astimezone(dt.timezone.utc)
        self.assertEqual(dt.datetime.fromisoformat(payload['departureTime']), expected)
        self.assertEqual(payload['origin']['location']['latLng']['latitude'], ride['origin']['lat'])
        self.assertNotIn('fixture-secret', json.dumps(ride))
        self.automatic(seats=2)
        self.assertEqual(len(self.calls), 1)
        self.app.routes.google_cache.clear()
        self.duration = '2400s'
        slower = self.automatic(seats=1)
        self.assertEqual(slower['price_meta']['price_cents'], 1800)

    def test_dynamic_counts_parties_cancellation_and_waitlist_promotion(self):
        ride = self.automatic(seats=4)
        first = self.apply('jamie', ride)
        group = self.apply('leo', ride, party=2)
        waiting = self.apply('ethan', ride, party=2)
        self.assertEqual(self.accept(first)['pricing']['rider_price_cents'], 1200)
        self.assertEqual(self.accept(group)['pricing']['rider_count'], 3)
        self.assertEqual(self.application('jamie', first)['agreed_price_cents'], 920)
        self.assertEqual(self.application('leo', group)['total_price_cents'], 1840)
        self.assertEqual(self.accept(waiting)['status'], 'waitlisted')
        self.assertEqual(self.application('jamie', first)['pricing']['rider_count'], 3)
        code, result = self.clients['leo'].call(f'/api/applications/{group}/cancel', {})
        self.assertEqual(code, 200, result)
        self.assertIn(waiting, result['promoted_application_ids'])
        self.assertEqual(self.application('ethan', waiting)['pricing']['rider_count'], 3)
        self.clients['ethan'].call(f'/api/applications/{waiting}/cancel', {})
        self.assertEqual(self.application('jamie', first)['agreed_price_cents'], 1200)
        _, mine = self.clients['mina'].call('/api/my-rides/search', {'date': self.date})
        current = next(r for r in mine['rides'] if r['id'] == ride['id'])
        self.assertEqual(current['pricing']['driver_earnings_cents'], 1200)

    def test_acceptance_rejects_stale_count_and_cross_member_reads(self):
        ride = self.automatic(seats=3)
        first = self.apply('jamie', ride)
        second = self.apply('leo', ride)
        client = self.clients['mina']
        old = client.call(f'/api/applications/{second}/price', {})[1]['pricing']
        self.accept(first)
        code, result = client.call(f'/api/applications/{second}/accept', dict(expected_rider_count=old['rider_count']))
        self.assertEqual(code, 409, result)
        self.assertEqual(self.application('leo', second)['status'], 'pending')
        self.assertEqual(self.clients['ethan'].call(f'/api/applications/{second}/price', {})[0], 403)
        self.assertEqual(self.accept(second)['pricing']['rider_price_cents'], 990)

    def test_rider_post_driver_offer_and_manual_waitlist_claim(self):
        wanted = self.automatic(owner='daniel', role='rider', seats=2)
        offer = self.apply('mina', wanted)
        result = self.accept(offer, who='daniel')
        self.assertEqual(result['pricing']['rider_count'], 2)
        self.assertEqual(result['pricing']['driver_earnings_cents'], 1980)
        ride = self.automatic(seats=1)
        first = self.apply('jamie', ride)
        wait = self.apply('leo', ride, auto=False)
        self.accept(first)
        self.accept(wait)
        self.clients['jamie'].call(f'/api/applications/{first}/cancel', {})
        self.assertEqual(self.application('leo', wait)['status'], 'waitlisted')
        self.assertEqual(self.accept(wait, who='leo', action='claim')['pricing']['rider_count'], 1)

    def test_round_trip_queries_reverse_route_and_return_departure(self):
        ride = self.automatic(kind='round', seats=2)
        self.assertEqual(ride['price_meta']['price_cents'], 2400)
        self.assertEqual(len(self.calls), 2)
        out, back = self.calls[0][2], self.calls[1][2]
        self.assertEqual(out['origin'], back['destination'])
        self.assertEqual(out['destination'], back['origin'])
        self.assertNotEqual(out['departureTime'], back['departureTime'])

    def test_failure_and_invalid_duration_never_fall_back_to_fake_prices(self):
        self.app.routes.google_key = ''
        with self.assertRaisesRegex(Problem, 'GOOGLE_MAPS_API_KEY'):
            self.app.routes.quote({}, {}, 'one', seats=1, start_date=self.date, departure_hour=8)
        self.app.routes.google_key = 'fixture-secret'
        self.error = True
        # API failure must not expose provider bodies or secrets.
        origin = {**base.PLACES[0], 'mode': 'exact'}
        destination = {**base.PLACES[4], 'mode': 'exact'}
        for duration in ('1200s', 'NaNs', '-1s', None):
            self.duration = duration
            code, result = self.clients['mina'].call('/api/pricing/quote', dict(
                origin=origin, destination=destination, kind='one', seats=2, start_date=self.date, departure_hour=8))
            self.assertEqual(code, 503, result)
            self.assertNotIn('price_cents', result)
            self.assertNotIn('fixture-secret', json.dumps(result))
            self.assertNotIn('sensitive-provider-body', json.dumps(result))
            self.error = False
        # Valid long routes have no legacy $30/$100 cap.
        self.duration = '1200s'
        self.distance = 1609344
        self.assertEqual(self.automatic()['price_cents'], 60600)

    def test_fractional_units_are_not_rounded_before_pricing(self):
        self.distance = 12345
        self.duration = '1234.56789s'
        ride = self.automatic(seats=4)
        raw = Decimal('12345') / Decimal('1609.344') * 60 + Decimal('1234.56789') / 60 * 30
        self.assertEqual(Decimal(ride['price_meta']['base_amount_cents']), raw)
        self.assertEqual(amounts(raw, 4), dict(driver_earnings_cents=3179, rider_price_cents=795))

    def test_recurring_quote_uses_first_selected_weekday(self):
        day = dt.date.fromisoformat(self.date)
        target = (day.weekday() + 2) % 7
        ride = self.automatic(kind='regular', weekdays=[target], seats=2)
        departure = dt.datetime.fromisoformat(self.calls[0][2]['departureTime']).astimezone(ZONE)
        self.assertEqual(departure.date(), day + dt.timedelta(days=2))
        self.assertEqual(ride['price_meta']['model'], 'google_shared_v1')

    def test_javascript_estimates_and_acceptance_dialog(self):
        if not shutil.which('node'):
            self.skipTest('Node unavailable')
        result = subprocess.run(['node', str(Path(__file__).with_name('pricing_contract.cjs'))],
                                input=str(Path(__file__).resolve().parents[1] / 'static' / 'app.js'),
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
