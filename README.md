# CampusLoop

A working student carpool application with an English interface, Python API, SQLite database, Docker Compose, and a local Ollama RAG assistant. Release **2.2.0**.

## New in 2.2.0

- **Find a ride** separates Regular rides from One-time & round trips while retaining all matching dates. **My rides** has two role tabs: **You’re driving** and **Confirmed passenger**. Each separates **Regular rides** from **One-time & round trips**. A rider post awaiting a driver stays on the board and in Requests until accepted. Both directions of a driver offer are supported.
- Select a date, an inclusive departure-hour window, and Upcoming / Past / All dates. Filters are sent to the API and persist across role tabs. Clear filters restores upcoming rides. Upcoming excludes departed dates; use Past or All to review history.
- Confirmed passengers see the actual driver's full name, vehicle and driver rating. Drivers see confirmed passengers and rider ratings. Before confirmation, members use aliases and a generic anonymous icon; after confirmation, initials come from the revealed real name.
- Cost shares appear on posts, requests, and confirmed rides, per passenger and as a party total. The amount at request time is saved with the application and kept after acceptance or waitlist promotion.
- Each ride card has a route picture. Automatic pricing and explainable recommendation sorting are available. Driver and rider ratings show an average out of five and a rating count below the avatar.

### Try four waitlist scenarios without a second browser

Sign in as **jamie@usc.edu**, then open **Demo Lab → Create fresh examples**. This adds fresh future examples to an existing database; it never requires a reset. Click again for another independent batch.

| Example | Action | Expected result |
| --- | --- | --- |
| Automatic promotion | Cancel your confirmed seat | The approved auto-confirm passenger becomes confirmed |
| Manual claim | Release the example booking, then Confirm open seat | You remain waitlisted until your explicit claim |
| Whole-party fit | Release the one-person booking, then the two-person booking | A later one-person party fits first; your party of two confirms together when two seats open |
| Approval required | Release the example booking | The approved waitlisted passenger confirms; your unapproved pending request stays pending |

The batch also adds completed passenger and driver rides for rating practice. Open **My rides → Confirmed passenger → Past** to rate your driver; switch to **You’re driving → Past** to rate a passenger. The completed driver example requires a vehicle in your profile; Jamie already has one. Ratings from generated examples are synthetic development activity.

Generated fixture members have disabled logins. Release buttons only cancel generated example bookings belonging to scenarios you created. These use the same production cancellation, capacity, approval, and promotion functions as normal bookings. `DEMO_MODE=0` disables the lab endpoints and navigation, but does not delete existing records or fixtures.

### Change one recurring date or skip one week

In My rides, use **Change this date only** to change departure, arrival deadline and notes for an unrequested regular-ride date. All other dates keep their normal schedule. Once a date has pending, waitlisted or confirmed requests, skip it and post a replacement to obtain agreement to new terms.

**Skip / cancel this date** affects only the selected date. **Can’t make this week** affects future dates for that recurring ride in the selected date's Monday–Sunday week. As the owner, this cancels those whole ride dates; as a passenger or a driver who accepted a rider's post, this cancels only your applications. Passenger cancellations run the normal waitlist promotion rules. Later weeks remain unchanged.

### Prices, recommendations and ratings

Suggested one-way cost share per passenger is **$1 + $0.35 × route miles**, rounded to the nearest **$0.25**, with a **$2 minimum** and **$30 maximum per leg**. A round trip doubles the amount and includes both legs; regular rides charge the listed amount per booked date. When OSRM is unavailable, distance is explicitly estimated as straight-line distance × 1.25. Choose **Set my own price / budget** to override. Server calculation is authoritative; this is a demo cost-sharing formula, not a fare-market estimate. CampusLoop does not collect payments.

**Recommended** sorts by an explainable relevance score: route proximity 40, departure-time proximity 25, listed price 15, role-specific average rating 10, and seat availability 10. Unselected route/time and unrated members receive neutral scores. Driver posts favor lower cost shares; rider posts favor higher offered budgets. Required location, date, time and role filters are applied before scoring. **Why this ride?** shows the factors. Nearest places, earliest departure and lowest price are alternative sorts. The score does not predict acceptance or safety.

Only the actual driver and confirmed passengers can rate each other, after the arrival deadline (or one hour after the return departure for round trips). Drivers rate riders; passengers rate the driver. One vote is stored per partner per ride date, with 1–5 stars. Saving again edits that vote. Public summaries expose only role, average and count, so ratings do not reveal identities before matching.

### Route pictures and online services

Visible cards lazily request [OSRM](https://project-osrm.org/docs/v5.24.0/api/) road geometry between posted pickup and drop-off centers, drawn over OpenStreetMap tiles. Route requests send the two center coordinates, not names or account details. Geometry is cached for 24 hours, failed routes for one minute, with at most one new upstream request per second. Travel time is an estimate without live traffic. An offline or unavailable route shows a dashed **approximate connection**, rather than presenting a straight line as a road path.

Map tiles are loaded only for visible thumbnails, with browser HTTP caching and visible attribution, following the [OpenStreetMap tile policy](https://operations.osmfoundation.org/policies/tiles/). No offline or bulk tile download is implemented. Road previews use `ROUTER_URL` (an OSRM-compatible driving endpoint); the default public service is intended for light demo use. Set a self-hosted endpoint for a larger installation. When upgrading an older Compose installation, its Compose file is retained; the default URL still works, but a custom router setting must also be added to that file's app environment.

## Update the app that is already running

If a page shows a new version but `/health` returns only `status` and `database`, the running backend has not been updated. Rebuilding from a different download folder can leave the original app running. This release includes an updater that identifies the existing app by its published port and updates its actual build folder.

Extract this archive and open a terminal in its `heky` folder:

```bash
python3 upgrade.py
```

For an app on a different port:

```bash
python3 upgrade.py --port 8011
```

The updater:

1. Finds the running Compose app that publishes the selected port and reads its actual project, configuration files, build folder, and database mount.
2. Stops before changing files if the container is ambiguous, the project is unrecognized, or storage would differ from the existing database.
3. Backs up the previous source files, then copies the new application, frontend, English guidance, tests, and Dockerfile into the actual build folder.
4. Keeps the existing `.env`, Compose configuration, project name, database, and volume. The currently published port is passed to Compose explicitly, even if an older `.env` still names port 8000. It does not reset passwords or delete records.
5. Rebuilds that app with `--no-cache`, recreates its container, and checks the database mount, `/health`, and full served HTML/JavaScript/CSS contents against the new release before reporting success.

To inspect the identified project without making changes:

```bash
python3 upgrade.py --dry-run
```

Keep a normal database backup as part of your own operations; the updater's ZIP backs up source files only. It refuses to recreate a container whose database is not on a persistent mount. Separately mounted custom knowledge folders require an explicit manual update. A Docker build failure leaves the existing container running; a startup failure is reported without deleting its volume.

After a successful update, open **http://127.0.0.1:8010** and refresh with `Cmd+Shift+R` on macOS. Both the page and server must report release 2.2.0. The page now detects an older backend and shows an explicit version mismatch instead of silently presenting an updated shell over an old API.

```bash
curl http://127.0.0.1:8010/health
```

The response includes `"app": "CampusLoop"`, `"version": "2.2.0"`, and `"database": "ok"`.

## First installation with Docker

Install and start Docker Desktop, or Docker Engine with Compose. From this archive's `heky` directory:

```bash
cp .env.example .env
docker compose up --build -d
```

Open http://127.0.0.1:8010. If that port is occupied, set `HEKY_PORT=8011` in `.env` and use port 8011 in your browser. Port 8000 is internal to the container.

```bash
docker compose ps -a
docker compose logs --tail=100 app model-init
# Retry the initial model download if needed.
docker compose up model-init
# Stop while retaining the database and models.
docker compose down
```

The first run downloads `qwen2.5:1.5b` and `nomic-embed-text:v1.5`. Booking and search work before model readiness. The assistant explicitly returns retrieved sources without a model answer while Ollama is unavailable. CPU execution is the default; no cloud model API key is needed.

The `heky/` archive root, `HEKY_PORT`, `heky_data` volume key, database filename, legacy cookie fallback, and existing development password are compatibility identifiers. They retain access to previous accounts and data. The public product name, page title, logo, assistant, and email messages are CampusLoop. Use the same existing Compose project when updating; changing a project name can select a different database volume.

## Places and ranges chosen by you

Pickup and drop-off start **empty** in both search and new posts. There is no preset station, campus pin, or inferred route. The controls are directly usable without enabling a disabled fieldset.

1. Enter your pickup place or address and click **Find place** (or press Enter).
2. Select the specific result you want. Typing a label or running a search does not automatically select the first result.
3. Choose **Exact place** or **Nearby area**. For an area, set a radius from **0.1 to 10 miles**; quick choices include 0.25, 0.5, 1, 2, 3, and 5 miles.
4. Choose your drop-off independently. You can also select a point on the online map. Use my location asks for browser permission only when you click it.

Cards show place names and allowed ranges, such as “Within 1 mi of USC Village.” Latitude and longitude are not editable interface fields. Coordinates are stored internally for geographic matching. Old sample-marker suffixes are removed from stored ride and application location labels during startup; coordinates, radii, bookings, and account records are preserved.

With both location filters selected, **pickup areas must overlap AND drop-off areas must overlap**. A nearby pickup with an unrelated destination is excluded. With only one selected location, only that end is checked. Results update after a place, range, or valid filter changes. Recommended is the default UI order; Nearest places sorts by the sum of pickup-center and drop-off-center distances from your requested places. Distances are shown relative to the places you chose.

**Clear pickup**, **Clear drop-off**, and **Clear all filters** remove route constraints. An unresolved typed address is never matched using the previously selected point. Before sending a request, the app suggests exact meeting points inside both shared areas; the owner agrees to the proposed terms by accepting.

Geographic radius is straight-line distance, not a road route, walking time, traffic estimate, or computed driving detour. Listed detour minutes remain a preference reviewed by the driver.

Specific saved place names such as Wilshire / Vermont Station, USC Village, and USC Leavey Library can be searched without the external provider. A broad region search such as Koreatown or Pasadena is **not** silently substituted with a saved station. Other searches use [Photon](https://github.com/komoot/photon) with an English result request, 24-hour cache, one-request-per-second app limit, and a per-user limit. Place queries and a rounded optional location bias are sent to the configured provider. Use a self-hosted Photon-compatible `GEOCODER_URL` for larger deployments. Failure returns a visible error; it does not invent a point.

Online maps load Leaflet from unpkg and tiles from OpenStreetMap. Online search, maps, and model downloads require internet access. Check the actual meeting entrance before traveling.

## All rides with date and time filters

**All rides** initially lists every upcoming active driver post and rider request across dates. No date or role is selected implicitly.

- Switch to **Rides offered** or **Riders looking** to narrow the post role.
- Leave Date blank for all upcoming dates, or choose one date.
- Departure from / Departure until applies an inclusive hour window.
- More date and schedule filters includes a date range, requested arrival deadline, recurring weekdays, and a listed detour limit. Trip type can also be filtered.
- Route, date, time, and role filters combine. **Clear all filters** restores the entire upcoming board.

Times use **America/Los_Angeles** with whole-hour precision. Arrival is a requested deadline, not a live traffic ETA. A specific-date search can show departed records, but actions close after departure. Posting a new ride returns to the all-rides board.

## Anonymous before matching; real names after confirmation

Before confirmation, another student's display name is a stable **Loop Member XXXXXX** alias. Pending and waitlisted requests remain anonymous. Your own account can show your real name to you.

Once a request is **confirmed**, the owner and currently confirmed participants on that specific ride date can see one another's real names. This applies to ride records, requests, matched rides, activity, chat, and RAG ride sources. A third-party viewer still sees aliases. A confirmed participant on one recurring date does not gain disclosure on other unconfirmed dates. Canceling ends the platform's disclosure for that date; it cannot erase what someone already saw.

Your account name remains in the database. This is a participant disclosure policy, not database anonymization. Known registered names/emails in public notes and activity are masked for unmatched viewers, but voluntarily supplied free-form text or locations can still identify someone. Avoid putting contact details in public ride notes.

## Accounts and a complete request flow

With `DEMO_MODE=1`, a new database creates fictional test accounts:

| Email | Scenario |
| --- | --- |
| jamie@usc.edu | Own driver posts and already confirmed seats on Sofia's recurring dates |
| mina@usc.edu | Driver who can accept incoming requests |
| sofia@usc.edu | Owner of a full recurring carpool |
| daniel@usc.edu | Rider request that can accept a driver's offer |
| leo@usc.edu | Approved waitlisted rider with automatic confirmation |
| ethan@usc.edu | Another confirmed rider in the seeded carpool |

The existing test password remains **`heky-local-2026`**. Changing `DEMO_PASSWORD` only affects a newly created database. The login field no longer preselects an already matched student. Seeded Jamie is already matched with Sofia, so seeing Sofia's real name on those dates is expected; use a new verified development account to inspect a fully unmatched board. Existing matches are retained when updating.

Use two browser profiles for the two sides of a request. A driver accepts or declines passenger requests. A rider post accepts one driver offer; other pending driver offers are declined. Add a vehicle in your profile before offering to drive. Pending requests do not reserve seats. Confirmed parties reserve their whole passenger count; the driver does not count as a passenger seat.

When a confirmed seat opens, the earliest approved waitlisted party that fits and explicitly opted into automatic confirmation is promoted in a database transaction. Manual-confirm parties use Confirm open seat. Parties are never split. Recurring dates have independent seats and cancellation; a round-trip booking covers both legs on its date. Chat is restricted to the owner and confirmed participants. Updates are in-app; no push/SMS or payment collection is implemented.

The initial sample schedule starts on the next Monday when the database is created. Existing databases retain their schedules and expired posts are not automatically recreated. Create a new future post or use Demo Lab to add a fresh set if an old development schedule has expired.

## RAG assistant

**Ask CampusLoop** and its description are English. Retrieval combines live permission-filtered ride records with English Markdown guidance in `knowledge/`, applies the current search filters, and combines BM25 and Ollama embeddings using reciprocal rank fusion. The local model is instructed to answer in English with source references. Ride sources are bounded to the first 100 matches; the board itself is not limited to 100.

The assistant has no booking tools and cannot read private chat, password hashes, or session secrets. Use the app's buttons for state changes. Model failure returns an explicit warning and retrieved sources rather than a fabricated answer. Source citations allow you to inspect supporting records. User-authored database content is preserved as entered rather than automatically translated.

## Native Python

Python **3.11+** is required; Python 3.12 is tested. From the new release folder:

```bash
python3 -m app.server
```

Open http://127.0.0.1:8010. No third-party Python packages are required. Ollama can run separately at `http://localhost:11434`.

For an existing native installation, stop its old server in the terminal where it is running, then start the new code with the **existing database path**:

```bash
DATABASE_PATH=/absolute/path/to/existing/data/heky.sqlite3 python3 -m app.server
```

Native Python does not automatically load `.env`; export desired settings. `upgrade.py` targets an already running Compose app, and stops without modifying files if the port belongs to a native process.

## Configuration and troubleshooting

Use `.env.example` for Compose settings. Keep `COOKIE_SECURE=0` for local HTTP; set it to 1 only behind HTTPS. Use the same hostname consistently because cookies belong to a hostname. Sign-in errors stay visible in the form, and the app verifies its session immediately after sign-in. A healthy database does not prove the browser is using the same backend or retaining its cookie.

`DEMO_MODE=1` shows development verification codes. Real student email delivery requires `DEMO_MODE=0`, SMTP configuration, and allowed `STUDENT_DOMAINS`; a separate fresh database avoids retaining fictional accounts. Email verification does not verify enrollment or driver eligibility. Do not delete the existing database to troubleshoot login.

The earlier standalone HTML demo is now a launcher for the actual local app, so there is one working implementation of search, identity, and booking rather than a second outdated simulation.

## Verification

```bash
python3 -m unittest discover -s tests -v
node --check static/app.js
```

Node.js 18+ is optional for the JavaScript handler integration test; Python application operation does not require Node. See `TEST_RESULTS.md` for exactly what was run, including the limits on Docker, browser, public geocoding, and actual model execution.

The updater uses documented [Compose configuration output](https://docs.docker.com/reference/cli/docker/compose/config/) and retains the existing [Compose project name](https://docs.docker.com/compose/how-tos/project-name/).
