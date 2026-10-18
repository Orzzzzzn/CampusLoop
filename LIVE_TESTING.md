# Perform the ride flow in CampusLoop

Use normal posts, requests, approvals and cancellations. There is no scenario picker and no preconfirmed booking. Each action changes the application's saved state. All prepared posts wait for a successful Google quote before accepting requests; they have no fixed demonstration fare.

## Before starting

Start Docker Desktop, update the app and open port 8010. The server needs `GOOGLE_MAPS_API_KEY`, Routes API access and billing. If needed use the updater's `--google-env` option described in README.md. Wait for the board's route prices to finish loading. A priced card shows Google distance/traffic-aware minutes and a rider price range. If it says Google price unavailable, correct the configuration and retry; it cannot be booked at an invented price.

Use separate browser profiles/private windows for Kate, Yelyn, Hannah, Emily and Noah. Default addresses are their lowercase names at usc.edu; default password is heky-local-2026. Use the actual collision-safe addresses shown on the sign-in screen. Check the profile name before acting.

## Begin at Kate's offer

After the update, open Find a ride → **Tuesday class commute · 1 PM → View ride offer**. The offer is Wilshire / Vermont Station → USC Downey Way, every Tuesday at 13:00, two passenger seats, four dates. No rider has requested, confirmed, joined a waitlist or canceled. All other prepared routes also start unbooked. The one-time migration archives the earlier generated demo state; later restarts keep actions you perform.

This optional command only reports the initial offer and its saved Google price. It never creates a request, confirmation or cancellation:

```bash
python3 ~/Downloads/CampusLoop-2.4.1/run_flow.py --base http://127.0.0.1:8010
```

For an explicitly automated execution on a separate new post, use `--perform-sequence`. It performs real requests, acceptance and a weekly cancellation through ordinary APIs; it intentionally leaves the state after Yelyn cancels, so do not use that option before a presentation that starts at Kate's offer. Its private state file makes repeated executions resume/show the same sequence; `--new` is available only with `--perform-sequence`.

## Kate, Yelyn, Hannah and Emily

1. **Kate posts:** either use the existing Wilshire / Vermont Station → USC Downey Way offer or create a new post. To create one, select Driver, choose pickup/drop-off, Recurring, the next Tuesday at 13:00, Tuesdays through three weeks later, two passenger seats and Google Maps pricing. Review the Google-derived estimate and publish. Use the same post consistently afterward; a new post is distinct from an existing offer on that route.
2. **Yelyn requests:** browse Rides offered → Recurring rides, select the first Tuesday and 13:00, then select the intended route/post. Review meeting points and the quoted range, request one seat, and leave auto-confirm checked. The request is pending in Sent; Kate stays anonymous to Yelyn.
3. **Kate accepts:** open Requests → Incoming, filter that date and accept Yelyn's request. Review current price and confirm again in the price dialog. It becomes a real confirmed booking. Yelyn now sees Kate and her Honda Civic in My rides → Confirmed passenger.
4. **Hannah joins:** Hannah requests the same post/date for one passenger. Kate accepts after price review. Two passenger seats are occupied; the driver is excluded. With base B, driver earnings are 1.65B and each rider pays 0.825B.
5. **Emily waits:** Emily opens the now-full date and requests a waitlist spot. Kate approves the request. It appears once under Emily's My waitlist; before approval it was pending in Sent. Emily is excluded from rider-count pricing until confirmed.
6. **Prepare next week:** repeat Yelyn, Hannah and Emily's request/approval steps for the following Tuesday if you want to compare weekly isolation. Each date has separate bookings, its own Google traffic-aware quote and a separate queue.
7. **Yelyn cancels this week:** in Yelyn's My rides → Confirmed passenger → Regular rides, filter the first Tuesday and choose Can't make this week. Confirm. Only Yelyn's bookings on this post in that Monday–Sunday week are canceled. Emily promotes into the one opened seat; Hannah stays booked. The next Tuesday's bookings and waitlist stay unchanged.
8. **Emily checks:** open My rides to fetch current state. Emily now sees Kate's real name/vehicle, the first date and the current Google-derived price. That date leaves My waitlist. With Hannah still riding, n remains two and each rider still pays 0.825B.
9. **Kate cancels a week:** on another booked Tuesday, Kate uses My rides → You're driving → Regular rides → Can't make this week. That whole date and all its applications are canceled. No passenger promotes into a canceled offer. Other weeks stay active.

Switching Requests tabs or opening My rides fetches current server state after another account acts. Use the date filters to distinguish recurring dates. One request on each of two Tuesdays means two legitimate applications, not a duplicate.

## Other routes and branches to perform

Every route below starts without applications. Set up its state using the same Request and Accept actions. Prepared one-time dates use the next Tuesday still in the future at that hour; consult the date shown in the app.

| Route / schedule | Seats | Actions to perform |
| --- | --- | --- |
| USC Village → USC Downey Way, Tuesdays 13:00 | 2 | Confirm Yelyn and Hannah; approve Emily's waitlist; cancel Hannah instead of Yelyn and observe Emily replace her |
| Wilshire / Western Station → USC Leavey Library, one-time 09:00 | 2 | Confirm Yelyn + Hannah. Emily unchecks auto-confirm before requesting; Kate approves while full. Cancel one booking, then Emily explicitly clicks Confirm open seat |
| Wilshire / Vermont Station → USC Village, one-time 11:00 | 2 | Confirm Yelyn + Hannah; leave Emily pending. Cancel Yelyn: Emily must stay pending until Kate approves. Alternatively decline and let Emily reapply |
| Memorial Park Station → USC Village, one-time 14:00 | 1 | Confirm Yelyn; approve Hannah before Emily while full. Cancel Yelyn: Hannah promotes first. Cancel Hannah: Emily promotes next |
| Santa Monica Public Library → USC Leavey Library, one-time 10:00 | 2 | Confirm Yelyn + Hannah with one seat each. Emily requests a party of two, then Noah requests one; Kate approves both waitlists. Cancel Yelyn: only Noah fits. Cancel Hannah, then Noah: Emily's whole party can finally confirm together |
| Memorial Park Station → USC Downey Way, Tuesdays 13:00 | 2 | Book two weeks with passengers and a waitlist, then Kate cancels only the first week. Later bookings remain unchanged |
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
