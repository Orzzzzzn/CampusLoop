'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');

test('Pages has its own entry point without the backend bootstrap', () => {
  const html = read('index.html');
  assert.match(html, /static\/landing\.js/);
  assert.match(html, /static\/pages\.js/);
  assert.doesNotMatch(html, /src=["'][^"']*\/app\.js/);
  assert.match(html, /project showcase/i);
  assert.match(read('static/index.html'), /\/static\/app\.js/);
});

test('All page-local external assets use project-relative paths and exist', () => {
  const html = read('index.html');
  const assets = [...html.matchAll(/(?:src|href)="(\.\/static\/[^"?]+)(?:\?[^"\s]*)?"/g)];
  assert.equal(assets.length, 6);
  for (const [, asset] of assets) assert.ok(fs.existsSync(path.join(root, asset)), asset);
  assert.doesNotMatch(html, /(?:href|src)="\/static\//);
});

test('Landing content retains pricing, roadmap, FAQs, and real local images', () => {
  const context = vm.createContext({document: {addEventListener() {}}});
  vm.runInContext(read('static/landing.js'), context);
  const html = vm.runInContext('landing()', context);
  for (const id of ['ways-to-ride','how-it-works','why-campusloop','faqs','pricing-model','whats-next']) {
    assert.ok(html.includes(`id="${id}"`), id);
    assert.ok(read('index.html').includes(`href="#${id}"`));
  }
  for (const [, source] of html.matchAll(/src="\/([^"?]+)"/g)) {
    assert.ok(fs.existsSync(path.join(root, source)), source);
  }
  assert.match(html, /data-rider-delta/);
  assert.match(html, /Base Price = Distance/);
});

test('Static mode makes no backend or external data requests', () => {
  const code = read('static/pages.js');
  assert.doesNotMatch(code, /\bfetch\s*\(/);
  assert.doesNotMatch(code, /new\s+(?:XMLHttpRequest|WebSocket|EventSource)\s*\(/);
  assert.match(code, /createElement\('template'\)/);
  assert.match(code, /showModal\(\)/);
  assert.match(code, /protocol !== 'https:'/);
});

test('Pages config contains no secrets and defaults to no live backend', () => {
  const context = vm.createContext({window: {}});
  vm.runInContext(read('static/pages-config.js'), context);
  assert.equal(context.window.CAMPUSLOOP_PAGES.liveAppUrl, '');
  assert.deepEqual(Object.keys(context.window.CAMPUSLOOP_PAGES).sort(), ['liveAppUrl','repositoryUrl']);
});

test('Deployment uploads only the explicit static artifact', () => {
  const workflow = read('.github/workflows/deploy-pages.yml');
  assert.match(workflow, /path: _site/);
  assert.doesNotMatch(workflow, /cp\s+-[rR]\s+\.\s/);
  assert.match(workflow, /branches: \[main\]/);
  assert.match(workflow, /pages: write/);
  assert.match(workflow, /id-token: write/);
});
