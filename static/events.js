'use strict';

let refreshSequence = 0;

async function refresh() {
  if (!app.user) return;
  const seq = ++refreshSequence;
  const page = app.page;
  const criteria = structuredClone(app.criteria);
  const [requests, rides] = await Promise.all([
    api('/api/applications'),
    page === 'browse'
      ? api('/api/rides/search', criteria)
      : page === 'rides'
        ? api('/api/my-rides')
        : Promise.resolve(null),
  ]);
  if (seq !== refreshSequence || !app.user || app.page !== page) return;
  app.applications = requests.applications;
  if (page === 'browse') app.rides = rides.rides;
  if (page === 'rides') app.myRides = rides.rides;
  render();
}

async function navigate(page) {
  if (!app.user) return;
  app.page = page;
  await refresh();
}

async function handleClick(e) {
  const b = e.target.closest('button');
  if (!b) return;
  if (b.hasAttribute('data-close')) return closeModal();
  if (b.dataset.findPlace) return searchPlace(b.form, b.dataset.findPlace);
  if (b.dataset.pickMap) return initMap(b.form, b.dataset.pickMap);
  if (b.dataset.setRadius) {
    const side = b.dataset.side;
    b.form.elements[side + '_radius'].value = b.dataset.setRadius;
    updateLocationFeedback(b.form, side);
    drawPins();
    return autoSearch(b.form);
  }
  if (b.dataset.currentLocation) {
    if (!navigator.geolocation) throw Error('Location access is unavailable in this browser.');
    const form = b.form;
    const side = b.dataset.currentLocation;
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        setPlace(form, side, {
          label: 'Your current location',
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          source: 'map',
        }),
      () => toast('Location access was not granted. Search a place or choose on the map.'),
    );
    return;
  }
  if (b.dataset.nav) return navigate(b.dataset.nav);
  if (b.dataset.authTab) {
    app.authTab = b.dataset.authTab;
    return render();
  }
  if (b.dataset.boardRole) {
    const form = $('#search-form');
    if (form) app.criteria = readCriteria(form);
    app.boardRole = b.dataset.boardRole;
    app.criteria.role = app.boardRole;
    app.rag = null;
    return refresh();
  }
  if (b.hasAttribute('data-post')) return postRide();
  if (b.hasAttribute('data-profile')) return profile();
  if (b.dataset.openRide) return showRide(Number(b.dataset.openRide));
  if (b.dataset.requestTab) {
    app.requestTab = b.dataset.requestTab;
    return render();
  }
  if (b.hasAttribute('data-clear-search')) {
    app.boardRole = 'all';
    app.criteria = {};
    app.rag = null;
    return refresh();
  }
  if (b.dataset.pinSide) {
    activePin = b.dataset.pinSide;
    document.querySelectorAll('[data-pin-side]').forEach((x) => x.classList.toggle('active', x === b));
    return;
  }
  if (b.dataset.chat) return chat(Number(b.dataset.chat));
  if (b.dataset.activity) return activity(Number(b.dataset.activity));
  if (b.hasAttribute('data-logout')) {
    await api('/api/auth/logout', {});
    closeModal();
    app.user = null;
    app.csrf = '';
    return render();
  }
  if (b.dataset.application) {
    const id = Number(b.dataset.application);
    const action = b.dataset.action;
    if (action === 'cancel' && !b.hasAttribute('data-confirmed')) {
      return confirmAction(
        'Cancel only this date?',
        'Your recurring trips on other dates stay unchanged. A released seat may automatically go to an approved waitlisted party.',
        `data-application="${id}" data-action="cancel" data-confirmed`,
      );
    }
    const result = await api(`/api/applications/${id}/${action}`, {});
    closeModal();
    await refresh();
    return toast(
      result.promoted_application_ids?.length
        ? 'Canceled. The next eligible waitlisted party is confirmed.'
        : 'Request ' + (result.status || 'canceled') + '.',
    );
  }
  if (b.dataset.cancelOccurrence && !b.hasAttribute('data-confirmed')) {
    return confirmAction(
      'Cancel the whole ride date?',
      'All requests and bookings for this single date will be canceled. Other recurring dates stay active.',
      `data-cancel-occurrence="${b.dataset.cancelOccurrence}" data-confirmed`,
    );
  }
  if (b.dataset.cancelOccurrence) {
    await api(`/api/occurrences/${b.dataset.cancelOccurrence}/cancel`, {});
    closeModal();
    await refresh();
    toast('Ride canceled for this date only.');
  }
}

async function handleSubmit(e) {
  e.preventDefault();
  const form = e.target;
  const button = form.querySelector('button[type="submit"]');
  if (button) button.disabled = true;
  try {
    const f = new FormData(form);
    if (form.id === 'auth-form') {
      if (app.authTab === 'register') {
        const r = await api('/api/auth/register', Object.fromEntries(f));
        return verification(r.email, r.development_code);
      }
      const r = await api('/api/auth/login', Object.fromEntries(f));
      app.user = r.user;
      app.csrf = r.csrf;
      const session = await api('/api/me');
      app.user = session.user;
      app.csrf = session.csrf;
      await refresh();
    } else if (form.id === 'verify-form') {
      const r = await api('/api/auth/verify', Object.fromEntries(f));
      app.user = r.user;
      app.csrf = r.csrf;
      closeModal();
      await refresh();
      toast('Student email verified.');
    } else if (form.id === 'search-form') {
      app.criteria = readCriteria(form);
      app.rag = null;
      await refresh();
    } else if (form.id === 'post-form') {
      const d = Object.fromEntries(f);
      const payload = {
        role: d.role,
        kind: d.kind,
        origin: readLocation(form, 'origin'),
        destination: readLocation(form, 'dest'),
        start_date: d.start_date,
        end_date: d.end_date,
        departure_hour: Number(d.departure_hour),
        arrive_by: Number(d.arrive_by),
        weekdays: f.getAll('weekdays').map(Number),
        seats: Number(d.seats),
        price_cents: Math.round(Number(d.price) * 100),
        detour_minutes: Number(d.detour_minutes),
        note: d.note,
        return_hour: Number(d.return_hour),
      };
      const created = await api('/api/trips', payload);
      closeModal();
      app.boardRole = d.role;
      app.page = 'browse';
      app.criteria = { date: created.first_date, role: d.role };
      await refresh();
      toast('Ride published. It is now visible to other students.');
    } else if (form.id === 'request-form') {
      await api(`/api/occurrences/${form.dataset.occurrence}/request`, {
        party_size: Number(f.get('party_size') || 1),
        auto_confirm: f.has('auto_confirm'),
        meeting_origin: readLocation(form, 'origin', true),
        meeting_destination: readLocation(form, 'dest', true),
      });
      closeModal();
      app.requestTab = 'sent';
      await navigate('requests');
      toast('Sent. The post owner can now accept your request.');
    } else if (form.id === 'profile-form') {
      await api('/api/me', Object.fromEntries(f), 'PUT');
      const me = await api('/api/me');
      app.user = me.user;
      closeModal();
      render();
      toast('Profile saved.');
    } else if (form.id === 'resend-form') {
      const r = await api('/api/auth/resend', { email: app.user.email, password: f.get('password') });
      verification(app.user.email, r.development_code);
    } else if (form.id === 'chat-form') {
      await api(`/api/occurrences/${form.dataset.occurrence}/messages`, { body: f.get('body') });
      await chat(Number(form.dataset.occurrence));
    } else if (form.id === 'rag-form') {
      const question = f.get('question');
      $('#rag-result').innerHTML =
        '<div class="notice" style="margin-top:15px">Retrieving sources and asking the local model… The first request may take longer.</div>';
      const r = await api('/api/rag/ask', { question, filters: app.criteria });
      app.rag = { ...r, question };
      const output = $('#rag-result');
      if (output) output.innerHTML = ragResult(app.rag);
    }
  } finally {
    if (button) button.disabled = false;
  }
}

function handleChange(e) {
  const t = e.target;
  const form = t.form;
  if (!form) return;
  if (t.dataset.locationEnable) {
    t.closest('fieldset').disabled = !t.checked;
    if (!t.checked) return autoSearch(form);
    return;
  }
  if (t.dataset.locationMode) {
    updateLocationFeedback(form, t.dataset.locationMode);
    drawPins();
    return autoSearch(form);
  }
  if (t.dataset.radiusSide) {
    updateLocationFeedback(form, t.dataset.radiusSide);
    drawPins();
    return autoSearch(form);
  }
  if (t.dataset.placeInput) {
    const side = t.dataset.placeInput;
    const p = resolvedPlace(form, side);
    if (p?.source === 'map') {
      p.label = t.value.trim();
      form.elements[side + '_resolved'].value = JSON.stringify(p);
      updateLocationFeedback(form, side);
    }
    return;
  }
  if (t.hasAttribute('data-trip-type')) {
    form.querySelectorAll('[data-repeat-field]').forEach((x) => {
      x.hidden = t.value !== 'regular';
      x.querySelectorAll('input').forEach((input) => {
        input.disabled = t.value !== 'regular';
      });
    });
    form.querySelector('[data-return-field]').hidden = t.value !== 'round';
    return;
  }
  if (t.id === 'my-date') {
    app.myDate = t.value;
    render();
    return;
  }
  if (form.id === 'search-form') autoSearch(form);
}

function bindEvents() {
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.dataset.placeInput) {
      e.preventDefault();
      searchPlace(e.target.form, e.target.dataset.placeInput).catch((err) => toast(err.message));
    }
  });
  document.addEventListener('click', (e) => {
    Promise.resolve(handleClick(e)).catch((err) => toast(err.message));
  });
  document.addEventListener('submit', (e) => {
    handleSubmit(e).catch((err) => {
      const form = document.getElementById(e.target.id);
      let box = form?.querySelector('[data-form-error]');
      if (!box && form) {
        box = document.createElement('div');
        box.dataset.formError = '';
        box.setAttribute('role', 'alert');
        form.prepend(box);
      }
      if (box) {
        box.hidden = false;
        box.className = 'error-box';
        box.textContent = err.message;
      }
      if (e.target.id === 'rag-form' && $('#rag-result')) $('#rag-result').textContent = err.message;
      toast(err.message);
    });
  });
  document.addEventListener('change', handleChange);
  document.addEventListener('input', (e) => {
    if (e.target.dataset.radiusSide && e.target.form) {
      updateLocationFeedback(e.target.form, e.target.dataset.radiusSide);
      drawPins();
    }
  });
  $('#modal').addEventListener('close', () => {
    if (!$('#modal').open) clearMap();
  });
}

async function boot() {
  try {
    app.config = await api('/api/config');
    app.criteria = {};
    try {
      const me = await api('/api/me');
      app.user = me.user;
      app.csrf = me.csrf;
    } catch {
      /* not signed in */
    }
    if (app.user) await refresh();
    else render();
  } catch (err) {
    $('#app').innerHTML = `
      <section class="panel">
        <h1>Could not connect to CampusLoop</h1>
        <p>${esc(err.message)}</p>
        <p>Start the Python application, then refresh this page.</p>
      </section>`;
  }
}

bindEvents();
boot();
