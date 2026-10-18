# CampusLoop 2.2.0 verification record

## Pricing update verified on 2026-10-17

**55 tests passed** with Python 3.12.4 and Node.js 24.16.0 using `python -m unittest discover -s tests -v`. SQLite and HTTP fixtures use temporary local data; no user database or paid Google request was used. JavaScript syntax and `git diff --check` also passed.

- Google `computeRoutes` HTTP fixtures verify POST method, server-only API-key header, field mask, `DRIVE`, `TRAFFIC_AWARE`, scheduled departure converted from America/Los_Angeles to UTC, distance/duration units, short cache reuse and higher traffic duration increasing the base price.
- Automatic prices use the new $0.60/mile + $0.30/minute formula and 0.65 rider multiplier. Fractional units are preserved until final cent rounding. New automatic prices have no legacy minimum/maximum or service fee.
- Shared prices update across requests and confirmed rides for parties, acceptance, cancellation, waitlist promotion and manual claims. Pending/waitlisted parties do not occupy seats. Another member cannot inspect a private application quote; stale rider-count confirmation is rejected.
- Round trips request both directions at their own scheduled departure. Recurring estimates use the first selected weekday. Missing keys, provider errors and malformed durations return no automatic price; no OSRM/mock fallback is used for pricing.
- Production JavaScript contract checks cover driver posting earnings ranges, rider price ranges, Google metrics and acceptance price confirmation. The existing full frontend handler contract against the local Python API also passed. These checks inspect HTML/handlers, not browser layout.
- Existing fixed-price snapshots, booking/capacity, authentication/privacy, ratings, RAG, map previews and updater tests remain passing.

Real Google API access was not tested because `GOOGLE_MAPS_API_KEY` is not set in this environment. Docker deployment and full browser rendering were not performed for this change. API setup and estimate lifetime are documented in README.md.

## Repository baseline record retained below

Verification date: 2026-10-18. Runtime: Python 3.12 and Node.js 24.

## Executed successfully

**46 tests passed** using temporary SQLite databases and actual local HTTP servers. No real user database was used.

- Find a ride separates regular rides from one-time/round trips. My rides filters specific dates and inclusive departure-hour windows, distinguishes actual drivers from confirmed passengers, and shows driver name, vehicle, role-specific rating and agreed prices. Driver offers accepted by a rider post resolve to the actual offering driver.
- One-date recurring exceptions change only that occurrence's schedule and notes, apply before search filters and request views, and reject edits with active requests. Owner and passenger week-only cancellations affect the selected Monday–Sunday week, preserve later weeks, and promote eligible waitlisted passengers where seats open.
- All four fresh Demo Lab cases were exercised through HTTP: automatic promotion, manual claim, whole-party fit, and pending requests excluded from promotion. A second batch works in an existing database without resetting original trips. Cross-user release is rejected and disabled demo mode rejects the lab endpoints.
- Completed-ride ratings reject premature and nonparticipant votes, enforce 1–5 stars, and update one existing vote without increasing the count. Public averages and counts retain anonymous names. Past ride views expose eligible rating targets.
- Automatic cost-share computation uses server-calculated route miles, rounding, lower/upper bounds and round-trip multiplication. Request-time price snapshots survive a later stored post-price change and appear in confirmed rides and application party totals.
- Recommendation sorting and explanations rank the requested route, departure time, listed cost/budget, role-specific rating and available seats after filtering. Alternative sort validation passed.
- OSRM-format HTTP fixture tests verify real geometry parsing, distance and estimated duration, a named User-Agent, query options, cache reuse, queued distinct routes, automatic pricing and explicitly labelled offline approximation. No public routing call is required by the suite.
- The production JavaScript ran against the real Python API through a minimal document/form adapter. Verified boot/session, empty location defaults, explicit place selection, both-end area search, date/hour filters, unresolved-address protection, post/request/accept flows, anonymous icons, confirmed real names/initials, role tabs, My rides date retention, driver details, prices, route SVG markup, Demo Lab release/manual claim, completed-ride rating, one-date editing and week-only skipping. This is a handler/HTML contract check, not browser layout testing.
- Additive migration from the old column layout preserves users, password hashes and booking states, adding price snapshots and occurrence overrides without a reset. Older sample-marker suffix cleanup preserves coordinates and bookings. Legacy cookie compatibility passed.
- Existing authentication, CSRF, ownership, concurrent capacity/claim decisions, whole-party allocation, recurring-date isolation, round-trip handling, student verification and persisted private chat regression checks passed.
- Place lookup, Photon-format HTTP parsing, bias, cache, validation, rate limits and failure behavior passed. Broad region searches are not silently replaced by saved stations.
- RAG embedding/generation HTTP contracts, caching, permission-filtered ride sources, citations and explicit model-unavailable behavior passed using a local fixture. Actual model inference is not performed by that fixture.
- Updater Docker CLI fixture checks preserve the original project, build context, settings, port and database mount, create a source backup, and reject ambiguous or unpersisted storage. Old health responses, stale frontend contents, and stale CSS under a correct version badge are rejected.
- A separate native `python3 -m app.server` process started successfully on an assigned local port with a temporary database. Live health returned CampusLoop 2.2.0 / API 2.2 / database ok. The updater verified complete served HTML, JavaScript and CSS against release hashes. Login, creation of six fresh examples and two completed ride views worked on that process.
- Python compilation, JavaScript syntax checks, English-only source/documentation scan and ZIP integrity checks passed.

## Not executed

Docker image construction, real Compose container recreation, public Photon/OSRM calls, actual downloaded Ollama models, live SMTP, online map tiles, geolocation and full browser rendering/click verification were not executed. Docker is unavailable in this runtime. The earlier cloud browser could not reach the runtime's localhost and its URL policy disallowed local file previews. No bypass was attempted.

The update is not marked successful on the user's computer until `upgrade.py` verifies its actual running server and served frontend. Existing user-authored content remains as entered. Demo Lab records and ratings are explicitly synthetic development examples.

## Repeat

From `heky/`:

```bash
python3 -m unittest discover -s tests -v
node --check static/app.js
node --check tests/frontend_contract.cjs
```

Node.js 18+ is optional for the JavaScript handler test; without it, that one test is skipped. The application itself uses Python's standard library and does not require Node.
