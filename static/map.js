'use strict';

let map = null;
let mapLayers = [];
let activePin = 'origin';
let mapForm = null;

function hourOptions(value = '', any = true) {
  return (
    (any ? '<option value="">Any hour</option>' : '') +
    Array.from({ length: 24 }, (_, i) =>
      `<option value="${i}" ${String(value) === String(i) ? 'selected' : ''}>${hour(i)}</option>`,
    ).join('')
  );
}

function placeDefault(side) {
  const selected = side === 'origin' ? app.criteria.origin : app.criteria.destination;
  const p = selected || app.config.places[side === 'origin' ? 0 : 4];
  return {
    ...p,
    label: p.label.replace(' (sample pin)', ''),
    mode: selected?.mode || 'area',
    radius_miles: selected?.radius_miles || 1,
  };
}

function locationFields(side, loc, optional = false, enabled = true, fixed = false) {
  loc = loc || placeDefault(side);
  const label = optional && !enabled ? '' : loc.label;
  const mode = fixed ? 'exact' : loc.mode;
  const legendCore = `${side === 'origin' ? 'Pickup' : 'Drop-off'} ${fixed ? 'meeting point' : 'location'}`;
  const legend = optional
    ? `<label><input type="checkbox" name="${side}_enabled" data-location-enable="${side}" ${enabled ? 'checked' : ''}> ${legendCore}</label>`
    : legendCore;
  const modeControls = fixed
    ? `<input type="hidden" name="${side}_mode" value="exact">
       <p class="help-text">This exact point is proposed to the other student for confirmation.</p>`
    : `<div class="coords">
         <label class="form-field">Meeting flexibility
           <select name="${side}_mode" data-location-mode="${side}">
             <option value="exact" ${mode === 'exact' ? 'selected' : ''}>Exact place</option>
             <option value="area" ${mode === 'area' ? 'selected' : ''}>Nearby area</option>
           </select>
         </label>
         <label class="form-field">Allowed range
           <output data-radius-value="${side}">${mode === 'area' ? (loc.radius_miles || 1) + ' mi' : 'Exact point'}</output>
           <input name="${side}_radius" type="range" min="0.1" max="10" step="0.05" value="${loc.radius_miles || 1}" data-radius-side="${side}" ${mode === 'exact' ? 'disabled' : ''}>
         </label>
       </div>
       <div class="radius-presets">${[0.25, 0.5, 1, 2, 3, 5]
         .map(
           (n) =>
             `<button type="button" data-set-radius="${n}" data-side="${side}" ${mode === 'exact' ? 'disabled' : ''}>${n} mi</button>`,
         )
         .join('')}</div>`;
  const feedback = label
    ? esc(mode === 'area' ? `Within ${loc.radius_miles || 1} mi of ${label}` : `Exact place: ${label}`)
    : 'Choose the location you want to travel from or to.';
  return `<fieldset class="location-input" data-location="${side}" ${optional && !enabled ? 'disabled' : ''}>
    <legend>${legend}</legend>
    <input type="hidden" name="${side}_resolved" value="${esc(JSON.stringify(loc))}">
    <label class="form-field">${mode === 'area' ? 'Center place or address' : 'Place or address'}
      <div class="place-search-row">
        <input type="search" name="${side}_label" value="${esc(label)}" required minlength="3" maxlength="180" autocomplete="off" placeholder="Search a neighborhood, station, or campus…" data-place-input="${side}">
        <button type="button" class="btn outline" data-find-place="${side}">Find place</button>
      </div>
    </label>
    <div data-place-results="${side}" class="place-results" aria-live="polite"></div>
    ${modeControls}
    <div class="location-feedback" data-place-feedback="${side}">${feedback}</div>
    <div class="map-toolbar" style="margin-top:9px">
      <button type="button" class="link" data-pick-map="${side}">Choose on map</button>
      ${side === 'origin' ? `<button type="button" class="link" data-current-location="${side}">Use my location</button>` : ''}
    </div>
  </fieldset>`;
}

function resolvedPlace(form, side) {
  try {
    return JSON.parse(form.elements[side + '_resolved'].value);
  } catch {
    return null;
  }
}

function setPlace(form, side, place) {
  const label = place.label.replace(' (sample pin)', '');
  const loc = { ...place, label };
  form.elements[side + '_resolved'].value = JSON.stringify(loc);
  form.elements[side + '_label'].value = label;
  const result = form.querySelector(`[data-place-results="${side}"]`);
  if (result) result.replaceChildren();
  updateLocationFeedback(form, side);
  if (map && mapForm === form) map.panTo([loc.lat, loc.lon]);
  drawPins();
  if (form.id === 'search-form') autoSearch(form);
}

function updateLocationFeedback(form, side) {
  const mode = form.elements[side + '_mode'].value;
  const radius = form.elements[side + '_radius'];
  const value = radius?.value || 1;
  if (radius) radius.disabled = mode === 'exact';
  form.querySelectorAll(`[data-side="${side}"][data-set-radius]`).forEach((b) => {
    b.disabled = mode === 'exact';
  });
  const out = form.querySelector(`[data-radius-value="${side}"]`);
  if (out) out.textContent = mode === 'exact' ? 'Exact point' : value + ' mi';
  const feedback = form.querySelector(`[data-place-feedback="${side}"]`);
  if (feedback) {
    feedback.textContent =
      mode === 'exact'
        ? 'Exact place: ' + form.elements[side + '_label'].value
        : 'Within ' + value + ' mi of ' + form.elements[side + '_label'].value;
  }
}

async function searchPlace(form, side) {
  const value = form.elements[side + '_label'].value.trim();
  const result = form.querySelector(`[data-place-results="${side}"]`);
  if (value.length < 2) {
    toast('Enter a place name or an address.');
    return;
  }
  result.textContent = 'Finding places…';
  const center = resolvedPlace(form, side);
  const data = await api('/api/places/search', {
    query: value,
    ...(center ? { bias: { lat: center.lat, lon: center.lon } } : {}),
  });
  result.replaceChildren();
  if (!data.places.length) {
    result.textContent = 'No places found. Try a more specific address or choose on the map.';
    return;
  }
  for (const place of data.places) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'place-result';
    b.textContent = place.label;
    b.addEventListener('click', () => setPlace(form, side, place));
    result.append(b);
  }
  const note = document.createElement('small');
  note.textContent = data.attribution;
  result.append(note);
}

function autoSearch(form) {
  if (form.id !== 'search-form') return;
  try {
    app.criteria = readCriteria(form);
    app.rag = null;
    refresh().catch((e) => toast(e.message));
  } catch (e) {
    toast(e.message);
  }
}

function readLocation(form, side, exact = false) {
  const f = new FormData(form);
  const point = resolvedPlace(form, side);
  const label = (f.get(side + '_label') || '').trim();
  if (!point || !label || label !== point.label) {
    throw Error(
      'Choose ' +
        (side === 'origin' ? 'a pickup' : 'a drop-off') +
        ' place from the results, or select it on the map.',
    );
  }
  const mode = exact ? 'exact' : f.get(side + '_mode');
  return {
    label,
    lat: point.lat,
    lon: point.lon,
    mode,
    radius_miles: mode === 'area' ? Number(f.get(side + '_radius')) : 0,
  };
}

function readCriteria(form) {
  const f = new FormData(form);
  const c = {};
  if (app.boardRole !== 'all') c.role = app.boardRole;
  if (f.get('date')) c.date = f.get('date');
  for (const k of ['departure_hour', 'departure_from', 'departure_to', 'arrive_by', 'detour_minutes']) {
    if (f.get(k) !== null && f.get(k) !== '') c[k] = Number(f.get(k));
  }
  for (const k of ['date_from', 'date_to', 'kind']) {
    if (f.get(k)) c[k] = f.get(k);
  }
  const days = f.getAll('required_weekdays').map(Number);
  if (days.length) c.weekdays = days;
  for (const side of ['origin', 'destination']) {
    const field = side === 'origin' ? 'origin' : 'dest';
    if (f.get(field + '_enabled')) c[side] = readLocation(form, field);
  }
  return c;
}

function initMap(form, side = 'origin') {
  if (map) {
    map.remove();
    map = null;
  }
  mapForm = form;
  activePin = side;
  const container = form.querySelector('.mapbox');
  container.hidden = false;
  if (!window.L) {
    container.textContent = 'The online map is unavailable. Search a place name or choose a bundled location.';
    return;
  }
  map = L.map(container).setView([34.025, -118.29], 12);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  const point = resolvedPlace(form, side);
  if (point) map.setView([point.lat, point.lon], 13);
  map.on('click', (e) =>
    setPlace(form, activePin, {
      label: activePin === 'origin' ? 'Selected pickup location' : 'Selected drop-off location',
      lat: e.latlng.lat,
      lon: e.latlng.lng,
      source: 'map',
    }),
  );
  drawPins();
  setTimeout(() => map?.invalidateSize(), 0);
}

function drawPins() {
  if (!map || !mapForm) return;
  mapLayers.forEach((l) => map.removeLayer(l));
  mapLayers = [];
  for (const side of ['origin', 'dest']) {
    const enabled = mapForm.elements[side + '_enabled'];
    if (enabled && !enabled.checked) continue;
    const point = resolvedPlace(mapForm, side);
    if (!point) continue;
    const mode = mapForm.elements[side + '_mode']?.value || 'exact';
    const radius = Number(mapForm.elements[side + '_radius']?.value || 0);
    const color = side === 'origin' ? '#325e3b' : '#326e83';
    mapLayers.push(
      L.circleMarker([point.lat, point.lon], { radius: 7, color, fillOpacity: 1 })
        .bindTooltip(side === 'origin' ? 'Your pickup center' : 'Your drop-off center')
        .addTo(map),
    );
    if (mode === 'area' && radius) {
      mapLayers.push(L.circle([point.lat, point.lon], { radius: radius * 1609.344, color, fillOpacity: 0.12 }).addTo(map));
    }
  }
}

function clearMap() {
  if (map) {
    map.remove();
    map = null;
  }
  mapLayers = [];
  mapForm = null;
}
