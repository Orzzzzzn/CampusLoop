# GitHub Pages validation

These results are local checks, not a claim that a GitHub deployment has already succeeded.

## New Pages checks

- JavaScript syntax checks passed for the static bootstrap, public configuration, and existing landing script.
- `node --test tests/pages_contract.cjs`: **6 tests passed**.
- Workflow YAML parsed; deployment is restricted to `main` and uploads only `_site/`.
- Confirmed the original Python backend, Docker configuration, `static/index.html`, `static/app.js`, `static/style.css`, `static/landing.js`, and `static/landing.css` are byte-for-byte unchanged.

## Browser rendering and interactions

Chromium checks covered these document base URLs and viewport sizes:

| Document base path | Viewport |
| --- | --- |
| `/` | 1440 × 1000 |
| `/CampusLoop/` | 1440 × 1000 |
| `/CampusLoop/` | 1024 × 900 |
| `/CampusLoop/` | 768 × 1024 |
| `/CampusLoop/` | 390 × 844 |
| `/CampusLoop/` | 320 × 780 |

In all six previews, styles and all five photos loaded; there were no HTTP asset failures, JavaScript errors, horizontal page overflow, or backend API requests. Pricing controls updated correctly from one through four riders and disabled at their limits. FAQ expansion, the backend-information dialog, Escape-to-close, and the return-to-top control worked.

**Browser harness limitation:** The environment's managed Chromium policy blocks top-level URL navigation. The previews therefore injected the actual HTML with an explicit document base, loaded the real CSS/JavaScript/images from a local HTTP server, and intercepted same-page anchor clicks for scrolling. This verifies asset resolution, rendered layout, and component interactions, but not a live GitHub URL, deployed response headers, or real top-level/deep-link navigation. Verify those on the URL GitHub reports after deployment.

## Existing application suite

Command:

```bash
PYTHONPATH=tests:. python -m unittest discover -s tests -v
```

Result: **132 tests run; 128 passed, 2 failed, and 2 errored.** The four non-passing tests were rerun against an untouched extraction of the uploaded archive and produced the same failures/errors:

- `test_app.AppTests.test_rider_offer_accept_and_cancel`: expected one rider posting; received none.
- `test_features.FeatureTests.test_passenger_skip_week_promotes_only_their_bookings`: missing expected fixture ride (`StopIteration`).
- `test_features.FeatureTests.test_per_date_exception_filters_and_booking_terms`: missing expected fixture ride (`StopIteration`).
- `test_live.LiveTests.test_live_frontend_post_accept_waitlist_cancel_and_landing`: existing landing-title assertion failed.

These are existing baseline issues in this test environment, not changes introduced by the Pages entry point. Their root causes were not investigated or repaired in this hosting update. Existing application tests were not edited to hide failures.

## Not performed

- No push, pull request, or settings change was made in the user's GitHub account.
- The GitHub-hosted Actions job has not been executed here.
- No public backend, production database, Ollama service, or Google Routes API credentials were deployed.
