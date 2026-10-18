# CampusLoop verification record

Verification date: 2026-10-17. Runtime: Python 3.12.

## Executed successfully

- **21 Python tests passed** using actual local HTTP servers and temporary SQLite databases.
- All upcoming dates and both post roles are listed without a default date/role filter. Specific dates, date ranges, and inclusive departure-hour windows combine correctly; invalid windows are rejected.
- Both pickup and drop-off areas must match when both filters are supplied. A matching pickup with an unrelated destination is excluded. Results sort by distance from the requested locations. Suggested meeting points lie in both overlapping circles, including overlap where neither center lies inside the other circle.
- Board responses, incoming/outgoing requests, activity, and RAG documents mask other users' names before confirmation. Confirmed participants see real names. Third-party viewers and waitlisted users still see aliases. Canceling restores the alias for the former participant; promotion reveals names to the newly confirmed user.
- Upgrade from the previous schema preserves account, trip, occurrence, application, and session records. Existing password hashes still validate. The persisted alias salt survives repeated initialization. Session cookies use `campusloop_session`.
- Place-search endpoint, bundled places, HTTP geocoder response parsing, rounded search bias, caching, invalid coordinates, rate limiting, and unavailable-provider behavior passed. The online geocoder was exercised against an explicit local Photon-format HTTP fixture, not the public service.
- Existing authentication, CSRF, ownership, rider-offer acceptance, concurrent seat approvals, concurrent manual waitlist claims, automatic promotion, recurring-date isolation, private persisted chat, student verification, round-trip cancellation, and first actual recurrence date tests passed.
- RAG embedding and generation HTTP contracts, cache reuse, and citation handling passed with a local HTTP fixture. The fixture does not run a language model. The model-unavailable path returns retrieved sources with `answer: null`.
- A separate `python3 -m app.server` process started on the native default port **8010**. Health identified CampusLoop and a working database. HTML, JavaScript, CSS, configuration, cookie sign-in followed by `/api/me`, and all-date/all-role ride listing returned successfully.
- `node --check` on the split frontend modules (`api.js`, `map.js`, `views.js`, `events.js`), Python parsing, and compilation passed.
- Compose YAML parsed successfully; app/Ollama/model-init services, port 8010 binding, internal port 8000, escaped model environment variables, and the existing database volume key were checked.
- Project source and documentation scan found no Korean text. User-created database content is preserved as entered.

## Not executed

Docker image build or Compose container startup, actual downloaded model inference, public Photon requests, SMTP delivery, online map tiles, browser geolocation, and rendered browser interaction were not executed in this environment. Docker and a browser runtime were unavailable. These checks are not reported as passing.

Run the included tests from the project root:

```bash
python3 -m unittest discover -s tests -v
node --check static/api.js static/map.js static/views.js static/events.js
```

See README.md for startup, updates that preserve existing data, model readiness, privacy behavior, and location-search configuration.
