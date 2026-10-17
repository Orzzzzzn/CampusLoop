# Cancellation and waitlist
A confirmed passenger may cancel before departure. That cancels only the selected date; other recurring dates stay unchanged. A post owner can cancel an entire ride date, which cancels every pending, confirmed, or waitlisted application on that date. No passengers are promoted into a canceled ride.

When passenger seats open on an active driver ride, the server checks approved waitlisted parties in queue order. The earliest party that fits the available capacity and explicitly enabled automatic confirmation is confirmed atomically. A party is never split. Unapproved pending requests are not promoted. Manual-confirm parties stay waitlisted until they choose Confirm open seat, and capacity is rechecked then.

Automatic promotion uses the previously agreed exact meeting points and trip terms. Leaving and rejoining gives the application a new queue timestamp. There is no automated cancellation charge or payment collection. Approved waitlisted users remain pseudonymous until they become confirmed; real names are shared with the owner and confirmed participants at that time.

Updates appear in Requests and Seats & activity. External push and SMS notifications are not included.
