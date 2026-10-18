# CampusLoop 2.4.1

CampusLoop is a Python / SQLite carpool app with a shared landing page, place-and-radius matching, recurring rides, waitlists, Google traffic-aware pricing and a local RAG assistant. Python 3.11+ is required; no third-party Python packages are needed.

## This release

There is no Ride example selector, lettered scenario label or preset-booking page. Local accounts operate the normal app. Ten prepared posts start with **zero applications**: riders must request, owners must accept, and participants must cancel through the actual API and database.

All upcoming active ride dates use **real Google Maps Routes API quotes**, including existing posts, rider requests and each recurring date. Manual entry is removed from new posts. The old fixed $4 setup is removed from the default flow. No key or failed route data means **Google price unavailable** and booking is blocked until a valid quote is saved. A successful route quote supplies distance, traffic-aware time, quote timestamp and rider-count pricing. The app never calls a manual or synthetic price a Google quote.

The landing page explains why the service helps drivers and riders, Post → Request → Accept, the pricing equations, and planned service-area expansion and pickup stops. Pickup stops are future work, not an implemented feature.

## Update the existing app on port 8010

Extract this archive to `~/Downloads/CampusLoop-2.4.1`, start Docker Desktop and run:

```bash
python3 ~/Downloads/CampusLoop-2.4.1/upgrade.py --port 8010
```

This preserves the running Compose project, database, accounts, passwords, mounts and existing key/settings. It updates the actual build folder, backs up source files and replaces bundled guidance while retaining custom documents. It rebuilds only the app and verifies the actual served backend, HTML, JavaScript, CSS and landing assets. Source backups are not database backups.

If the old Compose folder has moved or disappeared:

```bash
python3 ~/Downloads/CampusLoop-2.4.1/upgrade.py \
  --compose-dir ~/Downloads/CampusLoop-2.4.1 --port 8010
```

Recovery retains the exact live database and app environment in a private Compose configuration. Ambiguous containers, unpersisted databases and code bind mounts hiding the new release stop before recreation. `--dry-run` inspects without updating. No volume deletion or Docker prune is used.

Open [http://127.0.0.1:8010](http://127.0.0.1:8010) and refresh with **Cmd+Shift+R**. Check:

```bash
curl http://127.0.0.1:8010/health
```

Expect CampusLoop 2.4.1 and database ok. `google_maps: configured` means a server key is present; it does not establish that Google accepted the key or returned a route. Successful priced cards show the Google distance/time and current contribution.

## Apply a Google key to an existing installation

If a key is already configured on the running container, the updater keeps it. Otherwise create a local `.env` in this extracted release folder and fill in `GOOGLE_MAPS_API_KEY`:

```bash
cd ~/Downloads/CampusLoop-2.4.1
cp .env.example .env
```

Edit `.env`, enable Routes API and billing for that key's Google Cloud project, then run:

```bash
python3 ~/Downloads/CampusLoop-2.4.1/upgrade.py --port 8010 \
  --google-env ~/Downloads/CampusLoop-2.4.1/.env
```

`--google-env` explicitly applies **only** that file's `GOOGLE_MAPS_API_KEY`, using a private Compose override outside the source folder. It works even when the installation uses a retained recovery configuration. It checks that the recreated container received the key while retaining the original database. It does not print the key, replace other environment values or copy `.env` into the image. An absent/empty key stops before updating.

Prepared route quotes load in the background so health, sign-in and the landing page can open immediately. The ride board refreshes while quotes load. A failed quote stays unavailable; **Retry route prices** retries unpriced prepared posts after the server configuration has been corrected. A quote already saved is not continuously re-requested. The key is backend-only.

See [Google Routes documentation](https://developers.google.com/maps/documentation/routes/compute_route_directions) for `computeRoutes`, distance and duration fields, and traffic-aware driving requests.

## First installation

From the extracted folder:

```bash
cp .env.example .env
# Edit .env and set GOOGLE_MAPS_API_KEY.
docker compose up --build -d
```

Open port 8010. Set `HEKY_PORT=8011` in `.env` if needed. Port 8000 is internal. `HEKY_PORT`, `heky_data`, the database filename and old cookie support are compatibility identifiers; the product is CampusLoop. Updating an existing app under a different Compose project can select a different database, so use the updater for an existing installation.

```bash
docker compose ps -a
docker compose logs --tail=100 app model-init
docker compose up model-init
docker compose down
```

Stopping with `down` retains data/model volumes. Initial Ollama model download needs internet; search and booking do not use a cloud model key. No payments are collected.

## Use the actual app

With `DEMO_MODE=1`, five local login accounts are available:

| Person | Default email | Vehicle / initial role |
| --- | --- | --- |
| Kate | kate@usc.edu | Honda Civic; posts driver offers |
| Yelyn | yelyn@usc.edu | Requests seats; also has an open rider post |
| Hannah | hannah@usc.edu | Requests a second passenger seat |
| Emily | emily@usc.edu | Can request a full ride and join its approved waitlist |
| Noah | noah@usc.edu | Can ride or offer to drive in a Toyota Prius |

Default password: **heky-local-2026**. `DEMO_PASSWORD` applies only when a new local account is created. Existing accounts, passwords and profile edits are preserved; email collisions create separate `.demo` accounts shown on the sign-in screen. Use separate browser profiles/private windows for each person.

Prepared posts cover ten routes with recurring, one-time, round-trip, one-seat and two-seat offers, plus a rider request. They are ordinary stored offers, not canned booking states. The first class offer is Wilshire / Vermont Station → USC Downey Way, Tuesdays at 13:00, two passenger seats, four dates. No applications are inserted at startup. See **[LIVE_TESTING.md](LIVE_TESTING.md)** for exact live steps and alternate branches.

1. Kate can use her existing class offer, or Post a ride with Google Maps pricing, a Tuesday 13:00 recurring schedule and capacity two.
2. Yelyn requests one date. Kate accepts under Requests → Incoming after reviewing the Google-derived current price.
3. Hannah requests that same date. Kate accepts; both seats are confirmed and the per-person price updates.
4. Emily requests that full date. Kate approves the request; it moves from Sent to My waitlist and does not count as a confirmed passenger.
5. Yelyn selects that date in My rides and chooses Can't make this week. Emily promotes into the opened seat, with the current price and Kate's driver information. Other weeks stay unchanged. Book a second Tuesday as well to verify this directly.
6. Kate's week cancellation affects the whole offer date, including its waitlist; no one promotes into a canceled ride. Other weeks remain active.

Requests and approvals are **date-specific**. Sending once does not subscribe someone to every recurring date. Repeated active retries reuse the same application without changing queue time, status, price or events. Submit/decision actions are protected while in flight. Sent and My waitlist have disjoint outgoing statuses; tab switches fetch current state. Requests has a date filter.

## Run the complete flow through the actual API

The app starts with Kate's existing offer, **zero applications and no canceled dates**. Open Find a ride and use **Tuesday class commute → View ride offer**. This command only shows that initial offer; it does not create bookings:

```bash
python3 ~/Downloads/CampusLoop-2.4.1/run_flow.py --base http://127.0.0.1:8010
```

Then sign in as Yelyn and request a seat. Kate accepts; Hannah can request the second seat and Emily can join the approved waitlist. Perform each action in the ordinary app. To explicitly execute the entire sequence automatically on a separate new post, add `--perform-sequence`. That option creates real requests, confirmations and a cancellation; omit it when beginning the presentation.

## Existing data and the clean demo start

The first 2.4.1 startup archives the tracked older generated demo offers and the exact old runner-generated post signature. Their application rows, agreed amounts, messages and passwords stay in the database. Archived demo records and notifications no longer appear in normal lists, including All dates. Ten fresh ordinary posts have zero applications; the Tuesday 13:00 offer has two passenger seats and four dates. The reset happens once, so restarting does not undo actions performed during the presentation.

Other users' posts remain. All of their upcoming active dates receive a Google quote in a per-date override, including dates with existing requests; displayed current contributions follow the Google formula and confirmed passenger count. Original stored agreement amounts and historical/canceled dates are retained. Pending or failed quotes suppress old manual amounts and prevent new confirmations until pricing succeeds. No database volume is deleted, and account passwords/profiles are unchanged.

The old preset-booking endpoints and `python -m app.demo --reset` are disabled in the production app. They cannot recreate fixed $4 or preconfirmed setup records. Legacy helper functions remain only for isolated regression fixtures.

## Pricing

```text
Base Price per Rider = Distance × Rate per Mile + Estimated Travel Time × Rate per Minute
Base = miles × $0.60 + minutes × $0.30
Driver Earnings per Ride = Base × [1 + 0.65 × (n − 1)]
Final Price per Rider = Driver Earnings per Ride / n
```

`n` is confirmed passengers, including party members and excluding the driver, pending requests and waitlisted parties. Posts show the range from one passenger through full capacity. Acceptance and manual claims show current prices again and reject stale passenger counts. Confirmed prices update as people join, cancel or promote. Amounts use unrounded route inputs and round to cents at the end; separately rounded earnings and per-person figures may differ by a few cents when multiplied. No service fee or automatic-price cap applies.

Google traffic-aware estimates use each date's scheduled America/Los_Angeles departure. Round trips sum both directions at their own departure times. Recurring dates are quoted individually; an allowed single-date departure change queues a new quote only for that date. A short cache reuses identical requests for 60 seconds. Saved quotes are not continuously refreshed. All current price fields use these quotes and confirmed passenger counts. Past agreements remain historical records. See [Google's traffic-aware routing documentation](https://developers.google.com/maps/documentation/routes/config_trade_offs).

## Places, identity and ride management

Search a named place/address and explicitly select a result. Choose Exact place or a 0.1–10 mile Nearby area independently at either end. Normal post/search locations start empty. Pickup areas and drop-off areas must both overlap when both filters are selected. Geographic ranges are straight-line flexibility, separate from road distance and traffic. Cards show names/ranges, not editable coordinates. Online Photon geocoding, Leaflet/OpenStreetMap tiles and OSRM preview geometry need internet. Map previews remain explicitly labelled OSRM and are separate from Google's pricing metrics.

Use role, date, departure hour and recurring/one-time tabs to browse. My rides separates driving, confirmed passenger and still-pending posts, with date and time filters. Departure until, advanced schedule filters and user-entered arrival deadlines remain removed. Times use whole hours in America/Los_Angeles.

Unconfirmed students appear as stable aliases. Confirmed partners see real names and driver information for that date. Approved waitlisted parties may auto-confirm when enough seats open, or explicitly claim if they opted out of automation. Parties are never split. An owner can edit departure/notes for one unrequested date or cancel a date/week; later weeks remain unchanged. Drivers and confirmed passengers can rate each other after the completion window, one editable 1–5 star vote per partner/date. Chat is limited to confirmed participants and the owner.

## Native Python and RAG

Export your server environment explicitly; native Python does not automatically load `.env`:

```bash
python3 -m app.server
```

For an existing native installation, stop the old process and use the existing database:

```bash
DATABASE_PATH=/absolute/path/to/existing/data/heky.sqlite3 python3 -m app.server
```

Keep `COOKIE_SECURE=0` for local HTTP and use one hostname consistently. Real verification email needs `DEMO_MODE=0`, SMTP and allowed student domains; email verification does not verify enrollment or driving eligibility. Do not delete a database to fix login.

Ask CampusLoop retrieves permission-filtered rides and English guidance using BM25 and optional Ollama embeddings. It cites sources and warns when the model is unavailable. It cannot book rides or access private chats/passwords/session secrets. User-authored text is preserved. Unpriced routes are described as unavailable, not free.

## Verification

```bash
python3 -m unittest discover -s tests -v
node --check static/app.js
node --check static/landing.js
```

Node 18+ enables production-handler/API integration checks. See `TEST_RESULTS.md` for executed flows and external-service limits.
