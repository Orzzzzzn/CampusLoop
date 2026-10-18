# CampusLoop 2.5.0

CampusLoop is a Python / SQLite carpool app with a shared landing page, place-and-radius matching, recurring rides, waitlists, Google traffic-aware pricing and a local RAG assistant. Python 3.11+ is required; no third-party Python packages are needed.

## This release

Recurring rides display their published start date, end date and weekdays. **One request covers every remaining future active date in that period; one owner approval confirms every available date and approves the waitlist on full dates.** No weekly reapplication or approval is needed. Prices, capacity, identities and weekly exceptions remain date-specific. Recurring offers and requests are grouped in the board and Requests; My rides keeps individual dates for cancellations.

Existing active recurring requests are extended once during upgrade: pending requests stay pending until owner approval; already confirmed or approved-waitlist requests keep that approval for remaining dates. Canceled weeks are preserved. The extension waits for valid Google prices on all dates and retains conflicting legacy terms for review rather than overwriting agreements. Past records, accounts and passwords are retained.

There is no Ride example selector, lettered scenario label or preset-booking page. Local accounts operate the normal app. Ten prepared posts start with **zero applications**: riders must request, owners must accept, and participants must cancel through the actual API and database.

All upcoming active ride dates use **real Google Maps Routes API quotes**, including existing posts, rider requests and each recurring date. Manual entry is removed from new posts. The old fixed $4 setup is removed from the default flow. No key or failed route data means **Google price unavailable** and booking is blocked until a valid quote is saved. A successful route quote supplies distance, traffic-aware time, quote timestamp and rider-count pricing. The app never calls a manual or synthetic price a Google quote.

The landing page explains why the service helps drivers and riders, Post → Request → Accept, the pricing equations, and planned service-area expansion and pickup stops. Pickup stops are future work, not an implemented feature.

## Update the existing app on port 8010

Extract this archive to `~/Downloads/CampusLoop-2.5.0`, start Docker Desktop and run:

```bash
python3 ~/Downloads/CampusLoop-2.5.0/upgrade.py --port 8010
```

This preserves the running Compose project, database, accounts, passwords, mounts and existing key/settings. It updates the actual build folder, backs up source files and replaces bundled guidance while retaining custom documents. It rebuilds only the app and verifies the actual served backend, HTML, JavaScript, CSS and landing assets. Source backups are not database backups.

If the old Compose folder has moved or disappeared:

```bash
python3 ~/Downloads/CampusLoop-2.5.0/upgrade.py \
  --compose-dir ~/Downloads/CampusLoop-2.5.0 --port 8010
```

Recovery retains the exact live database and app environment in a private Compose configuration. Ambiguous containers, unpersisted databases and code bind mounts hiding the new release stop before recreation. `--dry-run` inspects without updating. No volume deletion or Docker prune is used.

Open [http://127.0.0.1:8010](http://127.0.0.1:8010) and refresh with **Cmd+Shift+R**. Check:

```bash
curl http://127.0.0.1:8010/health
```

Expect CampusLoop 2.5.0 and database ok. `google_maps: configured` means a server key is present; it does not establish that Google accepted the key or returned a route. Successful priced cards show the Google distance/time and current contribution.

## Apply a Google key to an existing installation

If a key is already configured on the running container, the updater keeps it. Otherwise create a local `.env` in this extracted release folder and fill in `GOOGLE_MAPS_API_KEY`:

```bash
cd ~/Downloads/CampusLoop-2.5.0
cp .env.example .env
```

Edit `.env`, enable Routes API and billing for that key's Google Cloud project, then run:

```bash
python3 ~/Downloads/CampusLoop-2.5.0/upgrade.py --port 8010 \
  --google-env ~/Downloads/CampusLoop-2.5.0/.env
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
# or: make up
```

Open port 8010. Set `HEKY_PORT=8011` in `.env` if needed. Port 8000 is internal. `HEKY_PORT`, `heky_data`, the database filename and old cookie support are compatibility identifiers; the product is CampusLoop. Updating an existing app under a different Compose project can select a different database, so use the updater for an existing installation.

```bash
docker compose ps -a
docker compose logs --tail=100 app model-init
docker compose up model-init
docker compose down
```

Stopping with `down` retains data/model volumes. Initial Ollama model download needs internet; search and booking do not use a cloud model key. No payments are collected.

## Reset to a fresh demo database

Compose keeps ride data in the `heky_data` Docker volume. Older Jamie/Mina/Sofia fixtures and half-finished bookings can stay in that volume across rebuilds, which makes Incoming look empty when a request was actually sent to a retired legacy post.

For a clean Kate → Yelyn → Hannah → Emily run (zero applications, only the five demo accounts and ten prepared offers):

```bash
make reset-demo
```

That stops the app, deletes **only** `*_heky_data` volumes (Ollama models are kept), rebuilds, and lets startup seed Kate/Yelyn/Hannah/Emily/Noah again. Hard-refresh the browser afterward (`Cmd+Shift+R`).

`docker compose down` alone does **not** wipe the database. Do not use `docker compose down -v` unless you also intend to delete downloaded Ollama models.

On an existing volume, startup also marks legacy Jamie/Mina/Sofia/Daniel/Leo/Ethan posts as retired so they leave Find a ride; `make reset-demo` is still the reliable way to clear bookings and start the scripted demo from zero.

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

Prepared posts cover ten routes with recurring, one-time, round-trip, one-seat and two-seat offers, plus a rider request. They are ordinary stored offers, not canned booking states. The first class offer is Wilshire / Vermont Station → USC Downey Way, Tuesdays at 13:00, two passenger seats, four dates. No applications are inserted at startup. Find a ride hides past dates and defaults to **Recommended** order; a Sort control under the One-time / Recurring tabs also offers Earliest departure, Nearest places and Lowest price. Round trips show outbound and return departure times. My rides and Requests always list soonest dates first. See **[LIVE_TESTING.md](LIVE_TESTING.md)** for exact live steps and alternate branches.

Use the green **Tuesday class commute · 1 PM** banner (or Kate’s Wilshire / Vermont → USC Downey Way recurring card) so every rider joins the same post.

1. Kate uses that existing offer (Google price must be ready before booking).
2. Yelyn requests the whole recurring period once. Under **Requests → Incoming**, Kate chooses **Accept recurring period**, reviews all date prices, and confirms once. Available Tuesdays confirm automatically.
3. Hannah requests the same period once. Kate accepts once; both seats fill on dates with capacity.
4. Emily requests the same period once. Until Kate accepts, Emily stays **pending** in Kate’s Incoming (not yet on the waitlist). After Kate accepts: open-seat dates confirm Emily; full dates become an **approved waitlist** under Emily’s **My waitlist**. Waitlisted parties do not occupy seats or affect confirmed-rider pricing.
5. Yelyn selects the first date in My rides and chooses Can’t make this week. Emily promotes into that week’s opened seat when auto-confirm is on; later bookings and waitlists stay unchanged.
6. Kate can skip another week without canceling the entire series. A requester can separately choose Cancel remaining recurring dates to leave the rest of the period.

If Kate’s Incoming has no Emily request, Emily joined a different post (or the DB still has leftover bookings). Run `make reset-demo`, then repeat from step 2 on the Tuesday class banner offer.

Requests and approvals cover the **remaining recurring period**. Repeated joins reuse the enrollment without changing queue times or reopening weekly cancellations. Requests groups one card per recurring request. Sent and My waitlist use disjoint outgoing statuses. My rides lists individual dates soonest-first for weekly exceptions. One-time and round-trip requests retain their one-date behavior.

## Start or perform the flow through the actual API

The app starts with Kate's existing offer, **zero applications and no canceled dates**. Open Find a ride and use **Tuesday class commute → View ride offer**. This command only shows that initial offer; it does not create bookings:

```bash
python3 ~/Downloads/CampusLoop-2.5.0/run_flow.py --base http://127.0.0.1:8010
```

Then sign in as Yelyn and request a seat. Kate accepts; Hannah can request the second seat and Emily can join the approved waitlist. Perform each action in the ordinary app. To explicitly execute the entire sequence automatically on a separate new post, add `--perform-sequence`. That option creates real requests, confirmations and a cancellation; omit it when beginning the presentation.

## Existing data and the recurring upgrade

A fresh local setup (or `make reset-demo`) starts at Kate's Tuesday 13:00 offer: two passenger seats, four dates, zero applications. Other prepared posts are also unbooked. Updating an already-used installation with `upgrade.py` retains its current demo progress and does not wipe the volume; use `make reset-demo` when you need a clean slate.

A one-time migration groups pre-upgrade future recurring requests by post and requester. Existing pending requests are extended as pending across the remaining period. Existing confirmed/driver-approved waitlist requests carry that approval forward, confirming dates with seats and waitlisting dates that are full. Existing confirmed rows keep their identities, timestamps and original stored agreements. Explicitly canceled weeks, past dates and canceled offers stay unchanged. The migration waits for Google prices and runs again when quote loading succeeds. If old party/meeting terms conflict across dates or a competing driver already holds a date, existing terms are retained for review.

New date-specific requests made after the upgrade are not reinterpreted by that migration. The production UI's normal recurring request covers the period; My rides still provides individual-date and week cancellations. **Cancel remaining recurring dates** withdraws all the requester's pending, confirmed and waitlisted future dates on that post, with a separate confirmation dialog. Repeated joins/approvals/withdrawals do not create duplicates or reopen canceled weeks. No database volume is deleted and account passwords/profiles are unchanged.

Earlier generated preset offers remain archived from normal views. Their database history is retained. The old fixture endpoints/reset CLI stay disabled.

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

Use role, date, departure hour, and recurring/one-time tabs to browse. Sort rides with Recommended, Earliest departure, Nearest places or Lowest price under those tabs. My rides separates driving, confirmed passenger and still-pending posts, with date and time filters, always soonest-first. Departure until, advanced schedule filters and user-entered arrival deadlines remain removed. Times use whole hours in America/Los_Angeles. Round-trip cards and requests show outbound and return hours.

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
