# CampusLoop

CampusLoop is a working local student carpool MVP with an English interface, a Python HTTP API, persistent SQLite storage, and a local Ollama RAG assistant. Accounts, ride posts, requests, seats, waitlists, and chat survive page refreshes and server restarts.

## Start with Docker

Install and start Docker Desktop, or Docker Engine with Compose. Run these commands from the project root:

```bash
cp .env.example .env
docker compose up --build -d
```

Open **http://127.0.0.1:8010**. Port 8010 is the browser port; port 8000 is internal to the app container. If 8010 is occupied, set `HEKY_PORT=8011` in `.env` and use that port in your browser. `HEKY_PORT` is retained as a configuration compatibility key.

The first run downloads the chat model (`qwen2.5:1.5b`) and embedding model (`nomic-embed-text:v1.5`). The app can be used before the models are ready. Until then, the assistant returns retrieved documents with an explicit model-unavailable message.

```bash
# Check application health and identify the application on this port.
curl http://127.0.0.1:8010/health

# Inspect startup and model downloads.
docker compose ps -a
docker compose logs --tail=100 app model-init

# Retry model downloads if necessary.
docker compose up model-init

# Stop the app while retaining the database and downloaded models.
docker compose down
```

The default runs on CPU. Model downloads, online place search, and maps need internet access. No cloud LLM API key or Python package installation is required.

## Update an existing installation

Replace the source files inside your **existing project directory** with the files from this archive. Keep your existing `.env`, database, and Docker volumes. Run the update from the same directory and with the same Compose project name you used before:

```bash
HEKY_PORT=8010 docker compose up --build -d app
```

Then open http://127.0.0.1:8010 and hard-refresh the page (`Cmd+Shift+R` on macOS). If your installation previously used `docker compose -p ...`, continue using that same project name. Do not delete volumes to update.

The archive still uses the `heky/` directory, `heky_data` volume key, database filename, and existing development password for compatibility. The product, interface, email messages, and assistant are named CampusLoop. Changing the directory or Compose project name can make Compose create a different empty database volume. The update adds the alias setting and place-search cache tables without replacing existing records. Legacy session cookies are accepted; new sign-ins use a CampusLoop cookie.

## Test accounts

With `DEMO_MODE=1`, a fresh database creates these fictional accounts. Every account uses **`heky-local-2026`**. Changing `DEMO_PASSWORD` only affects the initial creation of a database; it does not reset existing users.

| Email | Seeded scenario |
| --- | --- |
| jamie@usc.edu | Own driving schedule and confirmed seats in another regular carpool |
| sofia@usc.edu | Owner of a full recurring driver ride |
| leo@usc.edu | Approved waitlisted rider with automatic confirmation enabled |
| mina@usc.edu | Driver who can receive and accept requests |
| daniel@usc.edu | Rider post under Riders looking; can accept a driver offer |
| ethan@usc.edu | Another confirmed passenger in the seeded carpool |

Use separate browser profiles or a private window to try both sides of a request. Seed dates start on the next Monday when the database is first created. Existing databases keep their original schedule. The board shows every upcoming active ride by default; expired sample rides do not reappear automatically.

## Places, ranges, and automatic nearby matching

Pickup and drop-off each support **Exact place** or **Nearby area**, independently:

1. Enable the pickup or drop-off location filter on the board.
2. Enter the place or address you want to use and click **Find place** (or press Enter in that field).
3. Select a result, then choose an exact place or a radius from **0.1 to 10 miles**. Quick buttons include 0.25, 0.5, 1, 2, 3, and 5 miles.
4. Repeat for the other end of your route. Results update automatically after selecting a place or changing a filter.

The interface displays the requested place and its range, such as “Within 1 mi of USC.” It does not ask you to type latitude or longitude. You can also choose a point on the map or explicitly allow the browser to use your current location. Coordinates are stored internally to calculate accurate geographic distances.

When both location filters are enabled, **both pickup areas and both drop-off areas must overlap**. Similar pickup locations with unrelated destinations are excluded. Results are ranked by the sum of pickup-center and drop-off-center distances from your selected places. Each card shows those distances relative to your search. When only one location filter is enabled, that end alone is checked. Clearing the filters restores all rides.

This is geographic proximity matching. Radius is straight-line distance, not a walking route, traffic ETA, or computed driving detour. Nearby matching suggests rides; the post owner still accepts the request. Requests start with suggested exact meeting points inside the shared location areas. You can adjust those points before sending; the server verifies they remain inside the posted areas.

Built-in sample searches include USC, Koreatown, Pasadena, and Santa Monica and work without the external geocoder. Other searches use [Photon](https://github.com/komoot/photon), with a 24-hour cache, a one-request-per-second app limit, and an additional per-user limit. Search requests send your query and a rounded location bias to the configured provider. Selecting Use my location requires browser permission. Map tiles come from OpenStreetMap, and the Leaflet map library loads from unpkg. For larger deployments, configure a self-hosted Photon-compatible `GEOCODER_URL`; the public demo has usage limits. If online search fails, an error is shown instead of inventing a location. A typed address becomes usable only after you select a search result or a map point.

## All rides and date/time filters

The initial **All rides** tab lists all upcoming active driver posts and rider requests across dates. Switch to **Rides offered** or **Riders looking** to narrow the role.

- Leave Date blank to browse all upcoming dates, or choose one date.
- Use Departure from / Departure until for an inclusive departure-hour window.
- More date and schedule filters includes a date range, latest requested arrival, trip type, recurring weekdays, and a listed detour limit.
- Filters combine with the selected route. Changing a valid filter updates the list automatically. Show all rides clears the filters.

Times use **America/Los_Angeles** and whole-hour precision. An arrival deadline is a requested latest arrival, not a traffic estimate. A specific-date search can display departed records from that date, but booking and cancellation actions remain closed after departure.

## Anonymous names until a confirmed match

Other students initially appear as **Loop Member XXXXXX**, with a stable pseudonym. Pending, waitlisted, declined, and canceled requests keep that identity private. Your own profile continues to show your name to you.

When a request becomes **confirmed**, the owner and confirmed participants on that specific ride date can see one another's full names. The board, request list, activity, chat, and RAG ride sources apply the same server-side policy. A different student browsing the same ride still sees an alias. Being matched on one recurring date does not reveal names on other unconfirmed dates. Canceling removes the platform's name disclosure for that date; people who already saw a name cannot be made to forget it.

The database retains real names for accounts. This feature controls what the app returns to participants; it does not anonymize the database or promise that free-form notes, locations, or an AI model cannot identify someone. Avoid sharing personal contact details in public ride notes. Known registered names and emails in notes/activity text are masked for viewers who have not matched. The assistant receives masked ride sources for the requesting user and has no access to private chat or password/session data.

The seeded Jamie account is already confirmed on some Sofia rides, so those real names are visible immediately. Use a fresh account or a new pending request to try the before/after behavior.

## Requests, seats, and chat

- A driver post offers passenger seats. The driver accepts or declines seat requests.
- A rider post asks someone to drive. The rider accepts one driver offer; other pending driver offers are declined. Add a vehicle in your profile before offering to drive.
- A pending request reserves no seats. Confirmed parties reserve their entire passenger count. Drivers are not counted as passenger seats.
- Full driver rides can have an approved waitlist. When seats open, the earliest approved party that fits and explicitly allowed automatic confirmation is promoted in a database transaction. A party is never split.
- A manual-confirm waitlisted party must choose **Confirm open seat**; capacity is checked again.
- Recurring dates have independent seats, requests, and cancellations. A round-trip booking covers both legs on the selected date.
- Chat is available only to the owner and currently confirmed participants. Requests and Seats & activity show in-app updates; external push/SMS notifications are not included.
- Amounts are proposed cost shares or rider budgets. No payments or cancellation charges are collected.

A quick walkthrough: sign in as Jamie, open Riders looking, and send an offer to an anonymous rider post. Sign in as Daniel in another browser profile, open Requests → Incoming, and accept. The request becomes confirmed and both sides can now see real names and use ride chat. You can also cancel Jamie's existing confirmed seat on one Sofia date and inspect Leo's promotion for that date only.

## RAG assistant

Ask CampusLoop combines live, permission-filtered ride records with the Markdown guidance in `knowledge/`. It applies the current board's date, time, and location filters. Retrieval combines BM25 and Ollama embeddings using reciprocal rank fusion; a local Ollama model generates an English answer with source references. The embedding cache is keyed by content hash and model. Ride sources are bounded to the first 100 matching records; the board itself is not capped at 100.

Untrusted ride notes are supplied as source data, and the assistant has no booking/cancellation tools. Use the application buttons to change a ride. Inspect citations for the underlying evidence. If a model is unavailable, the app returns retrieved sources and an explicit warning, with no fabricated model answer.

## Run without Docker

Python **3.11+** is required; Python 3.12 is the tested runtime. From the project root:

```bash
python3 -m app.server
```

Open http://127.0.0.1:8010. The default local database is `data/heky.sqlite3`. Start a separate Ollama service and pull both models for AI generation. Without Ollama, booking, search, accounts, and retrieval fallback still work. Native Python does not load `.env` automatically; export environment variables before starting it:

```bash
PORT=8011 DATABASE_PATH=./data/heky.sqlite3 python3 -m app.server
```

## Troubleshooting login or startup

```bash
# Confirm the Docker command and engine are available.
docker --version
docker info

# Confirm which application is answering on the browser port.
curl http://127.0.0.1:8010/health

# Inspect the application error and HTTP status.
docker compose logs --tail=100 app
```

The health response should contain `"app": "CampusLoop"` and `"database": "ok"`. If Docker is installed but the command is unavailable, finish Docker Desktop setup, start the app, and open a new terminal. Use the same browser hostname consistently (`127.0.0.1` or `localhost`) because cookies belong to a hostname. Use the HTTP server URL, rather than opening `index.html` directly. Sign-in failures now remain visible in the form; the app also checks that the session cookie works immediately after sign-in.

A successful DB/password diagnostic does not prove the browser reached the same server or retained its cookie. Inspect the displayed HTTP error and `/health` before changing data. Keep `COOKIE_SECURE=0` for local HTTP. Use a fresh browser session if a stale cookie persists. Do not delete the database to troubleshoot sign-in.

## Configuration and implementation

See `.env.example` for Compose settings. `DEMO_MODE=1` displays development verification codes and creates fictional seed data. For real student email delivery, use `DEMO_MODE=0` with a separate fresh database and configure SMTP and allowed `STUDENT_DOMAINS`; previously seeded accounts remain if the old database is reused. Set `COOKIE_SECURE=1` only behind HTTPS.

The Python app uses only the standard library: threaded HTTP, SQLite WAL transactions, scrypt password hashing, HttpOnly SameSite cookies, CSRF tokens, parameterized SQL, ownership checks, and rate limits. Location matching uses great-circle distance with one metre of rounding tolerance. All interface copy and project documentation are English; user-entered content is preserved as entered.

```text
app/domain.py       Database, validation, matching, aliases, booking transactions
app/places.py       Cached local/Photon place search
app/server.py       HTTP API, sessions, verification, static files
app/rag.py          Retrieval, embedding cache, Ollama generation
static/             English HTML, CSS, and JavaScript interface
knowledge/          English RAG guidance
tests/test_app.py   HTTP, SQLite, concurrency, privacy, geocoding, and RAG tests
```

## Verification

```bash
python3 -m unittest discover -s tests -v
node --check static/app.js
```

See `TEST_RESULTS.md` for the checks actually executed and their limitations. This is a local MVP: school enrollment, driver eligibility, road routes, live traffic, payment processing, password recovery, and production deployment operations are not implemented.
