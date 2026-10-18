# CampusLoop 2.4.1 verification

Verified on 2026-10-18 with Python 3.12.14 and Node.js 24.19.0.

## Executed

**113 tests passed** with `python3 -m unittest discover -s tests -v`. Sixteen live-app checks cover the Google-only migration and clean presentation start. Tests use temporary SQLite databases, normal HTTP application endpoints and explicit external-service HTTP fixtures. No destination user database was modified here.

- Fresh production startup creates five login accounts and ten ordinary posts (19 dates), with zero applications. No passenger is preconfirmed or waitlisted. Prepared posts load Google quotes asynchronously and cannot accept a request while pricing is unavailable.
- The production JavaScript handlers posted a new Tuesday 13:00 recurring driver offer with two seats, through the normal app API. Yelyn, Hannah and Emily requested two dates, Kate reviewed price dialogs and accepted, and the database recorded two confirmed parties plus one approved waitlist on each date. Yelyn's first-week cancellation promoted Emily only on that date; Hannah and next week's bookings remained unchanged. Kate's cancellation of another week canceled that date without promoting a waitlist into a canceled offer.
- Those handler checks ran against a real local Python HTTP server and SQLite, using a minimal DOM/form adapter. They also verify single requests for repeated submits/clicks, one outgoing waitlist rendering, disjoint Sent/My waitlist tabs, driver identity after confirmation, Google price summaries, removed example selectors and the requested landing headings/formulas. They do not establish browser layout or full browser click behavior.
- `run_flow.py` default execution was repeated and verified to create zero posts/applications/cancellations. Its initial-offer link opened the actual saved ride in the production handlers. With explicit `--perform-sequence`, the script was executed against the real local application server using normal login, quote, post, request, price-review, accept and week-cancel endpoints. Its six application rows ended as four confirmed, one canceled and one waitlisted across two dates. Repeating the command reused the saved post and did not add applications or posts. It never inserts preset booking fixtures or writes directly to the database.
- Google protocol tests use an explicitly identified HTTP fixture returning 10 miles and 20 minutes. For that fixture, the base is $12, the two-rider contribution is $9.90, and driver earnings are $19.80. These numbers verify the formula; they are **not actual Google fares for the prepared routes**. The production runtime requests Google's endpoint with its configured key; there is no fixture/mock fallback in the app.
- Missing keys block booking, rather than showing a $4 or $0 Google price. Provider failures remain unavailable; retry succeeds when the fixture recovers, without duplicating posts. Successful quotes include distance, traffic-aware duration, timestamp, source and shared-price metadata. Earlier setup records keep their exact application rows/statuses, agreed amounts, passwords and profile data, but are excluded from the default flow and read-only. Independently posted rides are retained.
- Existing Google tests continue to cover scheduled timezone conversion, traffic-aware POST/field mask/key headers, fractional precision and cent rounding, cache behavior, round-trip directions, recurring scheduling, malformed responses, party counts, stale price confirmation, cancellations, promotions and manual claims.
- Existing untracked manual posts and single-date overrides were migrated to independent scheduled Google quotes. The fixture returned different durations for different dates: 10 miles/20 minutes produced a $12 base; 10 miles/35 minutes produced $16.50. Departure edits requoted only that date; historical dates and original stored amounts stayed unchanged. Existing confirmed manual bookings displayed the computed $9.90 two-rider amount consistently in board, Requests and My rides while their original $4 agreements remained stored. Manual new-post inputs were rejected; forged client amounts were ignored. Reposting a driver-canceled request also received a new quote.
- Updating a simulated 2.4.0 database archived its generated offers and exact runner post signature, retained account/password/application bytes, removed archived notifications from normal views and created a fresh Kate offer with zero applications. Repeated startup did not reset the presentation again.
- Authentication, CSRF, ownership, aliases, private chat, date/week isolation, party capacity races, queue priority, recommendations, ratings, migrations, geocoding, map previews and RAG retrieval/citations retain regression coverage. Legacy preset data is explicitly created only in isolated regression fixtures; it is disabled in the production app.
- Twenty-four updater checks use a Docker CLI fixture. They retain database mounts, project, settings, recovery configurations and custom guidance, reject stale served assets, and cover explicit `--google-env` loading through a private override. Tests verify private file permissions, dollar escaping, no printed key, correct key delivery, unchanged original `.env`/database, and no writes on dry run.
- The extracted 49-file archive was started as a native Python process: health returned 2.4.1/database ok, all 19 future dates correctly stayed unpriced with a missing key, Kate had four 13:00 dates with two seats and zero bookings, the default runner created nothing, and all served static asset bytes matched the archive. Syntax, English-source/doc and archive checks passed. No real credentials or database are packaged.

## External-service and environment limits

This runtime has **no Google API key and no Docker executable**. Paid Google Routes requests and real Docker build/container recreation were not performed here. Production Google availability must be verified on the destination server after configuring its own key; a present key alone does not prove billing/API access or a returned route. Public Photon/OSRM services, online tiles, live SMTP, browser geolocation, full browser rendering and downloaded Ollama model inference were not executed.

The explicit sequence command performs real application activity, but its upstream Google response here was an HTTP fixture. The default command is read-only. The delivered app uses the destination server's actual Google quotes; missing/failed quotes do not receive invented fares.

## Repeat

```bash
python3 -m unittest discover -s tests -v
node --check static/app.js
node --check static/landing.js
node --check tests/live_frontend.cjs
python3 -m py_compile run_flow.py
```

Node.js 18+ enables JavaScript handler/API checks. The normal Python app does not require Node. `run_flow.py` supports macOS/Linux and needs a configured local app; see LIVE_TESTING.md for the command and normal UI actions.
