'use strict';

function modal(title, body, wide = false) {
  closeModal();
  $('#modal').classList.toggle('dialog-wide', wide);
  $('#modal-content').innerHTML = `
    <div class="modal-head">
      <h2 id="modal-title">${esc(title)}</h2>
      <button class="close" data-close aria-label="Close dialog">×</button>
    </div>
    <div class="modal-body">${body}</div>`;
  $('#modal').showModal();
}

function closeModal() {
  clearMap();
  if ($('#modal').open) $('#modal').close();
}

function roleButton(value, label) {
  return `<button type="button" role="tab" aria-selected="${app.boardRole === value}" class="${app.boardRole === value ? 'active' : ''}" data-board-role="${value}">${label}</button>`;
}

function header() {
  $('#navigation').innerHTML = app.user
    ? `<button data-nav="browse" class="${app.page === 'browse' ? 'active' : ''}">Find a ride</button>
       <button data-nav="rides" class="${app.page === 'rides' ? 'active' : ''}">My rides</button>
       <button data-nav="requests" class="${app.page === 'requests' ? 'active' : ''}">Requests
         <span class="count">${app.applications.filter((a) => a.incoming && a.status === 'pending').length}</span>
       </button>`
    : '';
  $('#account').innerHTML = app.user
    ? `<span class="server-status">● Connected</span>
       <button data-profile class="row">
         <span class="account-name" style="font-size:11px">${esc(app.user.name)}</span>
         <span class="avatar sage">${esc(app.user.name.split(' ').map((s) => s[0]).join('').slice(0, 2))}</span>
       </button>`
    : '<span class="campus-pill">USC student community</span>';
}

function render() {
  if (mapForm?.id === 'search-form') clearMap();
  header();
  const page = !app.user ? auth() : app.page === 'browse' ? browse() : app.page === 'rides' ? myRides() : requests();
  const footer = `
    <footer class="app-footer">
      <span>Student to student. Your campus, connected.</span>
      <span>USC community · ${app.config?.demo_mode ? 'Local development accounts' : 'Student email verification'} · America/Los_Angeles</span>
    </footer>`;
  $('#app').innerHTML = page + footer;
}

function auth() {
  return `
    <div class="auth-layout">
      <div class="auth-story">
        <div class="eyebrow demo-label"><span class="dot"></span> YOUR CAMPUS. YOUR LOOP.</div>
        <h1>Your commute.<br>Your people.<br>Your CampusLoop.</h1>
        <p>Find nearby rides, share a weekly routine, and meet students going your way. Your name stays private until a ride is confirmed.</p>
        <span class="badge green">Anonymous before matching · Real names after confirmation</span>
      </div>
      <section class="auth-card">
        <div class="tabs-small">
          <button type="button" data-auth-tab="login" class="${app.authTab === 'login' ? 'active' : ''}">Sign in</button>
          <button type="button" data-auth-tab="register" class="${app.authTab === 'register' ? 'active' : ''}">Create account</button>
        </div>
        <h2>${app.authTab === 'login' ? 'Welcome back.' : 'Find your campus loop.'}</h2>
        <form id="auth-form">
          <div data-form-error role="alert" hidden></div>
          ${
            app.authTab === 'register'
              ? `<label class="form-field">Full name
                   <input name="name" required minlength="2" maxlength="80" autocomplete="name">
                   <small>Shared only with confirmed ride participants.</small>
                 </label>`
              : ''
          }
          <label class="form-field">Student email
            <input name="email" type="email" required autocomplete="username" placeholder="you@usc.edu"
              ${app.config?.demo_mode && app.authTab === 'login' ? 'value="jamie@usc.edu"' : ''}>
          </label>
          <label class="form-field">Password
            <input name="password" type="password" required minlength="10" maxlength="200"
              autocomplete="${app.authTab === 'login' ? 'current-password' : 'new-password'}">
          </label>
          <button type="submit" class="btn primary">${app.authTab === 'login' ? 'Sign in →' : 'Create student account →'}</button>
        </form>
        ${
          app.config?.demo_mode
            ? `<div class="notice" style="margin-top:20px">
                 <strong>Local test accounts</strong><br>
                 jamie@usc.edu · sofia@usc.edu · mina@usc.edu · daniel@usc.edu · leo@usc.edu · ethan@usc.edu<br>
                 Password: <code>campusloop-local-2026</code><br>
                 <small>Use separate browser profiles to try both sides of a request.</small>
               </div>`
            : ''
        }
      </section>
    </div>`;
}

function route(r) {
  const a = r.origin;
  const b = r.destination;
  return `
    <div class="ride-route">
      <div class="time">${hour(r.departure_hour)}</div>
      <div class="route-point start"></div>
      <div class="place">${esc(a.label)}<small>${a.mode === 'area' ? 'Within ' + a.radius_miles + ' mi of center' : 'Exact pickup point'}</small></div>
      <div class="time" style="grid-column:1">by ${hour(r.arrive_by)}</div>
      <div class="route-point end"></div>
      <div class="place">${esc(b.label)}<small>${b.mode === 'area' ? 'Within ' + b.radius_miles + ' mi of center' : 'Exact drop-off point'}</small></div>
    </div>`;
}

function card(r) {
  const full = r.role === 'driver' && r.available_seats === 0;
  const initials = r.identity_revealed
    ? r.owner_name
        .split(' ')
        .map((x) => x[0])
        .join('')
        .slice(0, 2)
    : 'CL';
  const action = r.is_owner
    ? 'Manage date'
    : r.application && !['canceled', 'declined'].includes(r.application.status)
      ? 'View request'
      : r.role === 'rider'
        ? 'Offer a ride'
        : full
          ? 'Join waitlist'
          : 'View ride';
  const seat =
    r.role === 'rider'
      ? r.driver_id
        ? 'Driver confirmed'
        : r.capacity + ' rider' + (r.capacity === 1 ? '' : 's')
      : full
        ? 'Full · waitlist open'
        : r.available_seats + ' seats available';
  const match =
    r.match_type === 'both_locations'
      ? 'Both ends match your route'
      : r.match_type === 'pickup'
        ? 'Pickup matches your area'
        : 'Drop-off matches your area';
  return `
    <article class="ride-card">
      <div class="row between">
        <div class="person">
          <span class="avatar sage">${esc(initials)}</span>
          <div>
            <strong>${esc(r.is_owner ? 'You' : r.owner_name)}</strong>
            <small>${r.is_owner ? 'Your post' : r.identity_revealed ? 'Matched · real name shared' : 'Anonymous until a ride is confirmed'}</small>
          </div>
        </div>
        <span class="badge ${r.role === 'rider' ? 'amber' : 'green'}">${r.role === 'rider' ? 'Looking for a driver' : 'Offering seats'}</span>
      </div>
      ${route(r)}
      ${
        r.match_type
          ? `<div class="match-summary">
               <strong>${match}</strong>
               ${r.pickup_distance_miles !== null ? `<span>Pickup center · ${r.pickup_distance_miles.toFixed(1)} mi from ${esc(r.search_origin)}</span>` : ''}
               ${r.dropoff_distance_miles !== null ? `<span>Drop-off center · ${r.dropoff_distance_miles.toFixed(1)} mi from ${esc(r.search_destination)}</span>` : ''}
             </div>`
          : ''
      }
      <div class="ride-meta">
        <span>${fmt(r.trip_date)} · ${hour(r.departure_hour)}</span>
        <span>${r.kind === 'regular' ? 'Regular · ' + r.weekdays.map((n) => weekday[n]).join('/') : r.kind === 'round' ? 'Round trip · return ' + hour(r.return_hour) : 'One-time'}</span>
        <span>Detour limit +${r.detour_minutes} min</span>
      </div>
      <div class="card-bottom">
        <span class="price">${money(r.price_cents)} <small>/ ${r.role === 'rider' ? 'budget' : 'cost share'}</small></span>
        <span class="seat ${full ? 'full' : ''}">${seat}</span>
        <button type="button" class="btn ${full ? 'outline' : 'primary'}" data-open-ride="${r.id}">${action} →</button>
      </div>
    </article>`;
}

function ragResult(r) {
  return `${r.warning ? `<div class="notice alert" style="margin-top:15px">${esc(r.warning)}</div>` : ''}
    ${r.answer ? `<div class="rag-answer">${esc(r.answer)}</div>` : '<p class="help-text" style="margin-top:15px">No AI answer was generated. Retrieved documents are available below.</p>'}
    <span class="badge gray">${esc(r.mode === 'rag' ? 'Grounded answer · ' + r.retrieval : r.mode)}</span>
    ${(r.sources || [])
      .map(
        (s) => `<details class="source">
          <summary>[${esc(s.citation)}] ${esc(s.title)}</summary>
          <p>${esc(s.text)}</p>
          ${s.occurrence_id ? `<button class="link" data-open-ride="${s.occurrence_id}">View this ride</button>` : ''}
        </details>`,
      )
      .join('')}`;
}

function ragPanel() {
  const r = app.rag;
  const placeholder = 'What happens to the waitlist if someone cancels?';
  return `
    <section class="rag-card">
      <span class="eyebrow demo-label">YOUR CAMPUS COPILOT</span>
      <h3 style="margin-top:8px">Ask CampusLoop.</h3>
      <p class="help-text" style="margin-top:8px">Find answers in current ride posts and community guidance. Uses the applied date and location filters.</p>
      <form id="rag-form">
        <label class="screen-reader" for="rag-question">Ask about rides or policies</label>
        <textarea id="rag-question" name="question" required minlength="2" maxlength="2000" placeholder="${esc(placeholder)}">${esc(r?.question || '')}</textarea>
        <button class="btn primary full-width">Ask with sources ↗</button>
      </form>
      <div id="rag-result">${
        r
          ? ragResult(r)
          : '<div class="notice" style="margin-top:16px">The assistant reads sources. Bookings and seat changes always use the application buttons.</div>'
      }</div>
    </section>`;
}

function browse() {
  const c = app.criteria;
  return `
    <section class="hero">
      <div>
        <div class="eyebrow demo-label"><span class="dot"></span> YOUR CAMPUS. YOUR LOOP.</div>
        <h1>Find your people.<br>Share your CampusLoop.</h1>
        <p>All upcoming rides in one place. Search your route to find nearby pickup and drop-off areas.</p>
      </div>
      <button type="button" class="btn primary" data-post>＋ Post a ride</button>
    </section>
    <form id="search-form" class="app-search">
      <label class="form-field">Date · leave blank for all dates<input name="date" type="date" value="${esc(c.date || '')}"></label>
      <label class="form-field">Departure from<select name="departure_from">${hourOptions(c.departure_from)}</select></label>
      <label class="form-field">Departure until<select name="departure_to">${hourOptions(c.departure_to)}</select></label>
      <label class="form-field">Trip type
        <select name="kind">
          <option value="">All trips</option>
          ${[['regular', 'Regular'], ['one', 'One-time'], ['round', 'Round trip']]
            .map(([k, l]) => `<option value="${k}" ${c.kind === k ? 'selected' : ''}>${l}</option>`)
            .join('')}
        </select>
      </label>
      <button type="submit" class="btn lime">Find my loop →</button>
      <div class="location-details">
        <div class="row between">
          <strong style="font-size:12px">Match to the places you choose</strong>
          <span class="help-text">Both location areas must overlap</span>
        </div>
        <div class="location-grid">
          ${locationFields('origin', c.origin, true, !!c.origin)}
          ${locationFields('dest', c.destination, true, !!c.destination)}
        </div>
        <div id="search-map" class="mapbox" hidden></div>
        <p class="help-text">Pick a place and a range. Matching updates automatically, ranked by distance from your requested locations. Names stay anonymous until confirmation.</p>
      </div>
      <details class="location-details">
        <summary>More date and schedule filters</summary>
        <div class="form-grid" style="margin-top:15px">
          <label class="form-field">Date range · from<input name="date_from" type="date" value="${esc(c.date_from || '')}"></label>
          <label class="form-field">Date range · through<input name="date_to" type="date" value="${esc(c.date_to || '')}"></label>
          <label class="form-field">Arrive by<select name="arrive_by">${hourOptions(c.arrive_by)}</select></label>
          <label class="form-field">Maximum listed detour
            <select name="detour_minutes">
              <option value="">Any</option>
              ${[5, 10, 15, 30, 60]
                .map((n) => `<option value="${n}" ${c.detour_minutes === n ? 'selected' : ''}>${n} minutes</option>`)
                .join('')}
            </select>
          </label>
          <div class="form-field span2">Required recurring weekdays
            <div class="weekdays">${weekday
              .map(
                (name, n) =>
                  `<label><input name="required_weekdays" type="checkbox" value="${n}" ${(c.weekdays || []).includes(n) ? 'checked' : ''}><span>${name}</span></label>`,
              )
              .join('')}</div>
          </div>
        </div>
      </details>
    </form>
    <div class="controls board-title">
      <div class="segmented" role="tablist" aria-label="Ride board">
        ${roleButton('all', 'All rides')}${roleButton('driver', 'Rides offered')}${roleButton('rider', 'Riders looking')}
      </div>
      <span class="muted" style="font-size:11px">${app.rides.length} rides · ${c.date ? fmt(c.date) : 'All upcoming dates'} ${c.origin || c.destination ? '· nearest matches first' : ''}</span>
    </div>
    <div class="layout">
      <section class="ride-list">${
        app.rides.length
          ? app.rides.map(card).join('')
          : `<div class="empty">
               <h3>No rides match these filters</h3>
               <p>Widen the pickup or drop-off range, or choose more dates and hours.</p>
               <button type="button" class="btn outline" data-clear-search>Show all rides</button>
             </div>`
      }</section>
      <aside>${ragPanel()}</aside>
    </div>`;
}

function weekdayInputs() {
  return `<div class="weekdays">${weekday
    .map(
      (name, n) =>
        `<label><input name="weekdays" type="checkbox" value="${n}" ${[0, 2, 4].includes(n) ? 'checked' : ''}><span>${name}</span></label>`,
    )
    .join('')}</div>`;
}

function postRide() {
  const first = app.criteria.date || app.config.default_date;
  const endDefault = new Date(new Date(first + 'T12:00:00').getTime() + 27 * 86400000).toISOString().slice(0, 10);
  modal(
    'Create your CampusLoop',
    `<p>Choose places and allowed ranges for pickup and drop-off. Your real name is shared only after a match is confirmed.</p>
     <form id="post-form">
       <div data-form-error role="alert" hidden></div>
       <div class="form-grid">
         <label class="form-field">I am a
           <select name="role">
             <option value="driver">Driver · offering seats</option>
             <option value="rider">Rider · looking for a driver</option>
           </select>
         </label>
         <label class="form-field">Trip type
           <select name="kind" data-trip-type>
             <option value="regular">Regular commute</option>
             <option value="one">One-time</option>
             <option value="round">Round trip</option>
           </select>
         </label>
         <div class="location-grid">${locationFields('origin')}${locationFields('dest')}</div>
         <div class="span2">
           <div class="map-toolbar">Click the map to set:
             <button type="button" class="chip active" data-pin-side="origin">Pickup</button>
             <button type="button" class="chip" data-pin-side="dest">Drop-off</button>
           </div>
           <div id="location-map" class="mapbox">Loading map…</div>
           <p class="help-text">Map tiles © OpenStreetMap contributors. Check the actual meeting entrance.</p>
         </div>
         <label class="form-field">Start / travel date<input name="start_date" type="date" value="${first}" required></label>
         <label class="form-field" data-repeat-field>Repeat through<input name="end_date" type="date" value="${endDefault}" required></label>
         <label class="form-field">Departure hour<select name="departure_hour">${hourOptions(8, false)}</select></label>
         <label class="form-field">Arrive by<select name="arrive_by">${hourOptions(9, false)}</select></label>
         <div class="form-field span2" data-repeat-field>Weekdays${weekdayInputs()}</div>
         <label class="form-field">Passenger capacity / rider party size<input name="seats" type="number" min="1" max="4" value="2" required></label>
         <label class="form-field">Cost share / rider budget ($)<input name="price" type="number" min="0" max="100" step="0.01" value="4" required></label>
         <label class="form-field">Driver detour limit (minutes)<input name="detour_minutes" type="number" min="0" max="60" value="10" required></label>
         <label class="form-field" data-return-field hidden>Return departure<select name="return_hour">${hourOptions(17, false)}</select></label>
         <label class="form-field span2">Meeting notes & preferences
           <textarea name="note" maxlength="1000" placeholder="Pickup notes, luggage, or timing flexibility. Keep your name private until matching."></textarea>
         </label>
       </div>
       <div class="notice">Round trip bookings cover both legs on that date. Each recurring date keeps its own seats and requests.</div>
       <div class="modal-actions post-submit">
         <button type="button" class="btn outline" data-close>Cancel</button>
         <button type="submit" class="btn primary">Publish ride →</button>
       </div>
     </form>`,
    true,
  );
  initMap($('#post-form'));
}

function allRides() {
  return [...app.rides, ...app.myRides];
}

async function showRide(id) {
  const r = allRides().find((ride) => ride.id === id);
  if (!r) {
    toast('Open the corresponding ride list to view this ride.');
    return;
  }
  if (r.is_owner) {
    app.myDate = r.trip_date;
    await navigate('rides');
    return;
  }
  const existing = r.application && !['canceled', 'declined'].includes(r.application.status);
  const body = existing
    ? `<div class="notice">Your request is ${esc(r.application.status)}. Manage it under Requests → Sent.</div>`
    : r.departed
      ? '<div class="notice">This ride has departed.</div>'
      : r.role === 'rider' && r.driver_id
        ? '<div class="notice">This student already accepted a driver.</div>'
        : `<form id="request-form" data-occurrence="${r.id}">
             <div data-form-error role="alert" hidden></div>
             <p class="help-text">The suggested meeting points fall in the shared area between your requested places and this ride. Both sides agree to these points when the request is accepted.</p>
             <div class="location-grid">
               ${locationFields('origin', r.suggested_meeting_origin, false, true, true)}
               ${locationFields('dest', r.suggested_meeting_destination, false, true, true)}
             </div>
             <div id="location-map" class="mapbox" hidden></div>
             ${
               r.role === 'driver'
                 ? `<label class="form-field" style="margin-top:15px">Passengers in your party
                      <input name="party_size" type="number" min="1" max="4" value="1" required>
                    </label>
                    <label class="check" style="margin-top:15px">
                      <input name="auto_confirm" type="checkbox" checked>
                      After driver approval, automatically confirm my party if enough seats open at these exact terms.
                    </label>`
                 : ''
             }
             <div class="modal-actions">
               <button type="submit" class="btn primary">${r.role === 'rider' ? 'Send ride offer' : 'Send seat request'} →</button>
             </div>
           </form>`;
  modal(
    r.role === 'rider' ? 'Offer a ride' : 'Join this CampusLoop',
    `<div class="person">
       <span class="avatar sage">${
         r.identity_revealed
           ? esc(
               r.owner_name
                 .split(' ')
                 .map((x) => x[0])
                 .join('')
                 .slice(0, 2),
             )
           : 'CL'
       }</span>
       <div>
         <strong>${esc(r.owner_name)}</strong>
         <small>${r.identity_revealed ? 'Matched · real name shared' : 'Anonymous · identity shared after confirmation'}</small>
       </div>
     </div>
     ${route(r)}
     <div class="notice">${esc(r.note)}</div>
     <div class="summary-box">
       <div class="summary-line"><span>Trip date</span><strong>${fmt(r.trip_date)} · ${hour(r.departure_hour)}</strong></div>
       <div class="summary-line"><span>${r.role === 'rider' ? 'Rider party size' : 'Seats available'}</span><strong>${r.role === 'rider' ? r.capacity : r.available_seats}</strong></div>
       <div class="summary-line"><span>Cost share / budget</span><strong>${money(r.price_cents)}</strong></div>
       ${r.kind === 'round' ? `<div class="summary-line"><span>Return departure</span><strong>${hour(r.return_hour)} · both legs</strong></div>` : ''}
     </div>
     ${body}`,
    true,
  );
}

function proposal(a) {
  return `
    <div class="party-proposal">
      <strong>Agreed meeting proposal</strong>
      <span>↑ ${esc(a.meeting_origin.label)}</span>
      <span>↓ ${esc(a.meeting_destination.label)}</span>
      <small>${a.identity_revealed ? 'Ride confirmed · real names shared' : 'Names stay anonymous until confirmation'}</small>
    </div>`;
}

function requests() {
  const list = app.applications.filter((a) =>
    app.requestTab === 'incoming'
      ? a.incoming
      : app.requestTab === 'waitlist'
        ? !a.incoming && a.status === 'waitlisted'
        : !a.incoming,
  );
  return `
    <div class="page-top">
      <span class="eyebrow demo-label">YOUR SHARED PLANS</span>
      <h1>Good company starts here.</h1>
      <p>The post owner accepts requests. Only confirmed bookings occupy passenger seats.</p>
    </div>
    <div class="tabs-small">${[['incoming', 'Incoming'], ['sent', 'Sent'], ['waitlist', 'My waitlist']]
      .map(([k, v]) => `<button data-request-tab="${k}" class="${app.requestTab === k ? 'active' : ''}">${v}</button>`)
      .join('')}</div>
    <div class="stack">${
      list.length
        ? list
            .map(
              (a) => `<article class="request">
                <div class="row between">
                  <strong>${esc(a.incoming ? a.requester_name : a.owner_name)}</strong>
                  <span class="badge ${a.status === 'confirmed' ? 'green' : 'gray'}">${esc(a.status)}</span>
                </div>
                <p>${esc(a.origin.label)} → ${esc(a.destination.label)}<br>
                   ${fmt(a.trip_date)} · ${hour(a.departure_hour)} · ${a.party_size} passenger${a.party_size === 1 ? '' : 's'}
                   ${a.role === 'rider' ? '· driver offer' : ''}</p>
                ${proposal(a)}
                <div class="request-actions">
                  ${
                    a.incoming && !a.closed && a.status === 'pending'
                      ? `<button class="btn primary" data-application="${a.id}" data-action="accept">Accept request</button>
                         <button class="btn outline" data-application="${a.id}" data-action="decline">Decline</button>`
                      : ''
                  }
                  ${
                    !a.incoming && !a.closed && ['pending', 'waitlisted', 'confirmed'].includes(a.status)
                      ? `<button class="btn ${a.status === 'confirmed' ? 'danger' : 'outline'}" data-application="${a.id}" data-action="cancel">${
                          a.status === 'confirmed' ? 'Cancel this date' : 'Withdraw request'
                        }</button>`
                      : ''
                  }
                  ${
                    !a.incoming && !a.closed && a.status === 'waitlisted' && !a.auto_confirm
                      ? `<button class="btn primary" data-application="${a.id}" data-action="claim">Confirm open seat</button>`
                      : ''
                  }
                  ${a.status === 'confirmed' ? `<button class="btn outline" data-chat="${a.occurrence_id}">Ride chat</button>` : ''}
                </div>
                ${
                  a.status === 'waitlisted'
                    ? `<p class="help-text">Approved waitlist · ${
                        a.auto_confirm
                          ? 'Auto-confirm enabled; promotion requires enough seats for your whole party.'
                          : 'You must confirm an open seat manually.'
                      }</p>`
                    : ''
                }
              </article>`,
            )
            .join('')
        : `<div class="empty">
             <h3>No requests here yet</h3>
             <p>Find a ride or post your route to get started.</p>
             <button class="btn primary" data-nav="browse">Find your people →</button>
           </div>`
    }</div>`;
}

function myRides() {
  const dates = [...new Set(app.myRides.map((r) => r.trip_date))];
  if (!dates.includes(app.myDate)) app.myDate = dates[0] || app.criteria.date;
  const rides = app.myRides.filter((r) => r.trip_date === app.myDate);
  return `
    <div class="page-top row between">
      <div>
        <span class="eyebrow demo-label">YOUR TRAVEL PLANS</span>
        <h1>One routine. Less to think about.</h1>
        <p>Cancel one date while the rest of the recurring schedule stays intact.</p>
      </div>
      <button class="btn primary" data-post>＋ Post a ride</button>
    </div>
    <label class="row" style="font-size:12px;margin:18px 0">Travel date
      <select id="my-date" class="date-chooser">${dates
        .map((d) => `<option value="${d}" ${app.myDate === d ? 'selected' : ''}>${fmt(d)}</option>`)
        .join('')}</select>
    </label>
    <div class="stack">${
      rides.length
        ? rides
            .map(
              (r) => `<section class="panel">
                <div class="row between">
                  <strong>${esc(r.origin.label)} → ${esc(r.destination.label)}</strong>
                  <span class="badge green">${r.my_role === 'driver' ? 'You’re driving' : r.driver_id ? 'Confirmed rider' : 'Looking for a driver'}</span>
                </div>
                ${route(r)}
                <div class="row wrap between">
                  <small class="muted">${fmt(r.trip_date)} · ${r.confirmed_seats} / ${r.capacity} passenger seats booked</small>
                  <div class="request-actions">
                    ${
                      r.is_owner || r.application?.status === 'confirmed'
                        ? `<button class="btn outline" data-chat="${r.id}">Ride chat</button>
                           <button class="btn outline" data-activity="${r.id}">Seats & activity</button>`
                        : ''
                    }
                    ${
                      r.is_owner
                        ? `<button class="btn danger" ${r.departed ? 'disabled' : ''} data-cancel-occurrence="${r.id}">Cancel whole ride date</button>`
                        : r.application
                          ? `<button class="btn danger" ${r.departed ? 'disabled' : ''} data-application="${r.application.id}" data-action="cancel">Cancel my seat · this date</button>`
                          : ''
                    }
                  </div>
                </div>
              </section>`,
            )
            .join('')
        : `<div class="empty">
             <h3>No confirmed rides yet</h3>
             <p>Your own posts and accepted rides appear here.</p>
             <button class="btn primary" data-nav="browse">Explore the board</button>
           </div>`
    }</div>`;
}

async function activity(id) {
  const data = await api(`/api/occurrences/${id}/activity`);
  modal(
    'Seats & ride activity',
    `${data.members
      .map(
        (m) => `<div class="member">
          <strong>${esc(m.name)} · ${m.party_size} passenger${m.party_size === 1 ? '' : 's'}</strong>
          <span class="badge ${m.status === 'confirmed' ? 'green' : 'gray'}">${esc(m.status)}${m.status === 'waitlisted' && m.auto_confirm ? ' · auto' : ''}</span>
        </div>`,
      )
      .join('')}
     <div class="timeline">${data.events.map((e) => `<p>${esc(e.message)}</p>`).join('')}</div>`,
  );
}

async function chat(id) {
  const data = await api(`/api/occurrences/${id}/messages`);
  modal(
    'Ride chat',
    `<p>Visible only to the post owner and confirmed participants.</p>
     <div class="messages" aria-live="polite">${
       data.messages.map((m) => `<div class="message"><strong>${esc(m.name)}</strong>${esc(m.body)}</div>`).join('') ||
       '<p class="help-text">Start with a meeting point or a quick hello.</p>'
     }</div>
     <form id="chat-form" data-occurrence="${id}" class="row">
       <label class="form-field grow">Message
         <input name="body" maxlength="1000" required placeholder="See you at the entrance…">
       </label>
       <button class="btn primary">Send</button>
     </form>
     <button class="link" data-chat="${id}" style="margin-top:15px;font-size:11px">Refresh messages</button>`,
  );
}

function profile() {
  modal(
    'Your campus profile',
    `<div class="notice">${
      app.config.demo_mode
        ? 'Local development mode · verification codes are shown on-screen.'
        : 'Student email verification enabled.'
    }</div>
     <div class="summary-line"><span>Email</span><strong>${esc(app.user.email)}</strong></div>
     <div class="summary-line"><span>Status</span><strong>${app.user.verified ? 'Email verified' : 'Email verification required'}</strong></div>
     <form id="profile-form">
       <label class="form-field" style="margin-top:15px">Full name
         <input name="name" value="${esc(app.user.name)}" required minlength="2" maxlength="80">
       </label>
       <label class="form-field" style="margin-top:15px">Vehicle · required before driving
         <input name="vehicle" value="${esc(app.user.vehicle)}" maxlength="120" placeholder="Model, color, meeting details">
       </label>
       <div class="modal-actions">
         <button type="button" class="btn outline" data-logout>Sign out</button>
         <button class="btn primary">Save profile</button>
       </div>
     </form>
     ${
       !app.user.verified
         ? `<form id="resend-form" style="margin-top:15px">
              <label class="form-field">Password to request a new email code
                <input name="password" type="password" required>
              </label>
              <button class="btn outline" style="margin-top:10px">Send verification code</button>
            </form>`
         : ''
     }`,
  );
}

function verification(email, developmentCode) {
  modal(
    'Verify your student email',
    `<p>Enter the six-digit code sent to ${esc(email)}.</p>
     ${
       developmentCode
         ? `<div class="notice">Development mode: no email was sent. Your test code is <strong>${esc(developmentCode)}</strong>.</div>`
         : ''
     }
     <form id="verify-form">
       <input name="email" type="hidden" value="${esc(email)}">
       <label class="form-field" style="margin-top:15px">Verification code
         <input name="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required autocomplete="one-time-code">
       </label>
       <div class="modal-actions"><button class="btn primary">Verify and continue</button></div>
     </form>`,
  );
}

function confirmAction(title, message, attributes) {
  modal(
    title,
    `<p>${esc(message)}</p>
     <div class="modal-actions">
       <button class="btn outline" data-close>Keep it</button>
       <button class="btn danger" ${attributes}>Confirm cancellation</button>
     </div>`,
  );
}
