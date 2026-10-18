# Perform the ride flow in CampusLoop

Use normal posts, requests, approvals and cancellations. There is no scenario picker and no preconfirmed booking. Each action changes the application's saved state. All prepared posts wait for a successful Google quote before accepting requests; they have no fixed demonstration fare.

## Before starting

Start Docker Desktop, update the app and open port 8010. The server needs `GOOGLE_MAPS_API_KEY`, Routes API access and billing. If needed use the updater's `--google-env` option described in README.md. Wait for the board's route prices to finish loading. A priced card shows Google distance/traffic-aware minutes and a rider price range. If it says Google price unavailable, correct the configuration and retry; it cannot be booked at an invented price.

Use separate browser profiles/private windows for Kate, Yelyn, Hannah, Emily and Noah. Default addresses are their lowercase names at usc.edu; default password is heky-local-2026. Use the actual collision-safe addresses shown on the sign-in screen. Check the profile name before acting.

## Begin at Kate's offer

For a fresh setup, open Find a ride → **Tuesday class commute · 1 PM → View ride offer**. The offer is Wilshire / Vermont Station → USC Downey Way, every Tuesday at 13:00, two passenger seats, four dates. No rider has requested, confirmed, joined a waitlist or canceled. All other prepared routes also start unbooked. The earlier demo migration stays one-time. This update retains existing progress and extends eligible old recurring bookings across their remaining period; restarts keep actions you perform.

This optional command only reports the initial offer and its saved Google price. It never creates a request, confirmation or cancellation:

```bash
python3 ~/Downloads/CampusLoop-2.5.0/run_flow.py --base http://127.0.0.1:8010
```

For an explicitly automated execution on a separate new post, use `--perform-sequence`. It performs real requests, acceptance and a weekly cancellation through ordinary APIs; it intentionally leaves the state after Yelyn cancels, so do not use that option before a presentation that starts at Kate's offer. Its private state file makes repeated executions resume/show the same sequence; `--new` is available only with `--perform-sequence`.

## Kate, Yelyn, Hannah and Emily

1. **Kate's offer:** use Wilshire / Vermont Station → USC Downey Way, Tuesdays at 13:00, two passenger seats. The card shows the full start/end period. A new offer needs a chosen period and weekdays. Wait until every scheduled date has a Google quote.
2. **Yelyn requests once:** open the offer, review the published period, all remaining dates, Google price ranges and exact meeting proposal. Choose **Request recurring period** for one passenger. This requests all future active dates within the period, including future dates earlier than a selected search/card date. A date filter does not narrow the enrollment period. Kate stays anonymous until confirmation.
3. **Kate accepts once:** Requests → Incoming groups the recurring request into one card. Choose **Accept recurring period**. The review lists each date's projected price and Confirm/Waitlist outcome. Choose **Confirm recurring period** once. Yelyn is confirmed on every available date; full dates are approved waitlists. My rides → Confirmed passenger shows every confirmed date and Kate's name/vehicle.
4. **Hannah joins once:** Hannah requests the same period and Kate approves it once. On each date with two confirmed passengers, driver earnings are 1.65B and each passenger pays 0.825B, using that date's Google base B.
5. **Emily waits:** Emily requests the period once and Kate approves once. Full dates are grouped under My waitlist; expand View dates to inspect them. Before approval they appear in Sent, not My waitlist. Waitlisted passengers are excluded from the pricing count until confirmation.
6. **Inspect later weeks:** Yelyn and Hannah already have bookings on the other Tuesdays, and Emily is already waitlisted there. No additional request/approval is needed. Requests → travel date and My rides → travel date filter the saved dates without changing the recurring enrollment.
7. **Yelyn skips this week:** My rides → Confirmed passenger → Recurring rides → choose the first Tuesday → Can't make this week. Only that Monday–Sunday week's bookings on this post are canceled. Emily promotes only into the opened date; Hannah stays booked. Later weeks remain confirmed/waitlisted. Retrying the original request does not undo the weekly cancellation.
8. **Emily checks:** the promoted date appears in My rides with Kate's name/vehicle and its current Google-derived contribution. The remaining dates stay waitlisted. Requests shows the counts and date breakdown; it does not create duplicate recurring requests.
9. **Kate skips another week:** My rides → You're driving → Recurring rides → choose another Tuesday → Can't make this week. That week and its applications are canceled. No waitlist promotes into a canceled offer; other weeks remain intact.
10. **End the entire period:** a requester can choose **Cancel remaining recurring dates** under Requests or My rides. The confirmation explicitly distinguishes this from skipping one week. Past records stay stored; future pending/confirmed/waitlisted applications are canceled and eligible replacement parties can promote.

Each action uses normal application APIs and database transactions. All-date approval rechecks the complete date list, Google prices, rider counts and capacity. If any date changed since review, the app requires another review before changing any pending dates. One-time and round-trip requests continue to cover one booked date (both legs for a round trip).

## Other routes and branches to perform

Every route below starts without applications. Set up its state using the same Request and Accept actions. Prepared one-time dates use the next Tuesday still in the future at that hour; consult the date shown in the app.

| Route / schedule | Seats | Actions to perform |
| --- | --- | --- |
| USC Village → USC Downey Way, Tuesdays 13:00 | 2 | Confirm Yelyn and Hannah; approve Emily's waitlist; cancel Hannah instead of Yelyn and observe Emily replace her |
| Wilshire / Western Station → USC Leavey Library, one-time 09:00 | 2 | Confirm Yelyn + Hannah. Emily unchecks auto-confirm before requesting; Kate approves while full. Cancel one booking, then Emily explicitly clicks Confirm open seat |
| Wilshire / Vermont Station → USC Village, one-time 11:00 | 2 | Confirm Yelyn + Hannah; leave Emily pending. Cancel Yelyn: Emily must stay pending until Kate approves. Alternatively decline and let Emily reapply |
| Memorial Park Station → USC Village, one-time 14:00 | 1 | Confirm Yelyn; approve Hannah before Emily while full. Cancel Yelyn: Hannah promotes first. Cancel Hannah: Emily promotes next |
| Santa Monica Public Library → USC Leavey Library, one-time 10:00 | 2 | Confirm Yelyn + Hannah with one seat each. Emily requests a party of two, then Noah requests one; Kate approves both waitlists. Cancel Yelyn: only Noah fits. Cancel Hannah, then Noah: Emily's whole party can finally confirm together |
| Memorial Park Station → USC Downey Way, Tuesdays 13:00 | 2 | Join/approve the whole period once with passengers and a waitlist, then Kate cancels only the first week. Later bookings remain unchanged |
| USC Village ↔ Santa Monica Public Library, outbound 08:00 / return 17:00 | 2 | Confirm two passengers and approve a third waitlist. Cancel one: replacement is one booking covering both legs; Google pricing includes both route directions |
| Wilshire / Western Station → USC Village, one-time 16:00 | 1 | Confirm Yelyn; approve Emily before Hannah. Emily withdraws, reapplies and receives approval again. Cancel Yelyn: Hannah now has earlier queue priority |
| USC Leavey Library → Wilshire / Vermont Station, Yelyn's rider post at 15:00 | Party of 2 | Kate and Noah each offer to drive. Yelyn accepts one; the other offer declines. The confirmed driver cancels; the other offer becomes pending again |

Pending requests never reserve seats. Only driver-approved waitlists can promote. Auto-confirm promotion selects the earliest approved party that fits; parties are not split. Manual-claim parties require their own confirmation. Reapplying reuses an application record but gives it a new queue time and requires approval again. Identical retries of an active request do not move its queue position.

## Verify the pricing with the displayed Google base

Let B be the base derived from the actual distance and traffic-aware minutes shown for this post. Do not assume a fixed dollar amount across routes or dates.

| Confirmed passengers | Driver earnings | Price per passenger |
| --- | --- | --- |
| 1 | B | B |
| 2 | 1.65B | 0.825B |
| 3, if the post allows it | 2.30B | 2.30B / 3 |
| 4, if the post allows it | 2.95B | 0.7375B |

The base is distance × $0.60/mile + estimated time × $0.30/minute. Pending/waitlisted passengers do not count. Acceptance/manual claims review current projected prices; confirmed prices update with joins/cancellations/promotions. Money is rounded at the end. The app does not collect payment.

## Repeat a flow

Create a new future post or use another unbooked date/route, then perform the actions again. Restarting the server does not reopen canceled dates, create extra applications or preconfirm passengers. The old preset-reset CLI is disabled. Earlier generated setup records and agreed amounts remain in the database, but they are excluded from normal views; unrelated user posts remain available with Google-calculated upcoming prices.
