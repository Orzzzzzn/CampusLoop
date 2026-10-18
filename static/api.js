'use strict';

const $ = (s) => document.querySelector(s);

const esc = (v) =>
  String(v ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]),
  );

const app = {
  config: null,
  user: null,
  csrf: '',
  page: 'browse',
  boardRole: 'all',
  authTab: 'login',
  requestTab: 'incoming',
  criteria: {},
  rides: [],
  myRides: [],
  applications: [],
  myDate: '',
  rag: null,
};

const hour = (n) => String(n).padStart(2, '0') + ':00';
const money = (n) => '$' + (n / 100).toFixed(2);
const fmt = (d) =>
  new Date(d + 'T12:00:00').toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    weekday: 'short',
  });
const weekday = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function toast(message) {
  $('#toast').textContent = message;
  $('#toast').classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => $('#toast').classList.remove('show'), 4500);
}

async function api(path, body, method) {
  const response = await fetch(path, {
    method: method || (body === undefined ? 'GET' : 'POST'),
    credentials: 'same-origin',
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      ...(app.csrf ? { 'X-CSRF-Token': app.csrf } : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!(response.headers.get('content-type') || '').includes('application/json')) {
    throw Error('This address did not return the CampusLoop API. Open http://127.0.0.1:8010.');
  }
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && app.user) {
      app.user = null;
      app.csrf = '';
      render();
    }
    throw Error(data.error || `Request failed (HTTP ${response.status}).`);
  }
  return data;
}
