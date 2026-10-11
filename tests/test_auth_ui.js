'use strict';

// Exercise the login event handlers with a small browser fixture and mocked HTTP responses.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'static', 'index.html'), 'utf8');
const elements = new Map();
const initialClasses = new Map();
let focusedElement = null;

for (const tag of html.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)) {
  const classes = new Set((tag[0].match(/\bclass="([^"]*)"/)?.[1] || '').split(/\s+/));
  initialClasses.set(tag[1], [...classes]);
  const listeners = new Map();
  const element = {
    value: '', textContent: '', title: '', disabled: false, open: false,
    innerHTML: '', style: {},
    classList: {
      add: name => classes.add(name),
      remove: name => classes.delete(name),
      contains: name => classes.has(name),
      reset(names) { classes.clear(); names.forEach(name => classes.add(name)); },
      toggle(name, force) {
        const enabled = force === undefined ? !classes.has(name) : force;
        if (enabled) classes.add(name); else classes.delete(name);
        return enabled;
      }
    },
    addEventListener: (name, listener) => listeners.set(name, listener),
    async dispatch(name) {
      assert.ok(listeners.has(name), `Missing ${name} handler on ${tag[1]}`);
      await listeners.get(name)({preventDefault() {}});
    },
    focus() { focusedElement = this; },
    showModal() { this.open = true; },
    close() { this.open = false; }
  };
  elements.set(tag[1], element);
}

const element = id => {
  assert.ok(elements.has(id), `Missing HTML element ${id}`);
  return elements.get(id);
};
const requests = [];
const windowListeners = new Map();
const navigation = [];
const logoutEvents = [];
const dialogIds = new Set([
  'login-dialog', 'login-title', 'login-description', 'close-login-btn',
  'send-code-form', 'login-email', 'send-code-btn', 'verify-code-form',
  'login-code', 'verify-code-btn', 'login-message'
]);
let layoutHTML = 'Initial demo page';
const layout = {
  get innerHTML() { return layoutHTML; },
  set innerHTML(markup) {
    layoutHTML = markup;
    for (const [id, item] of elements) {
      if (dialogIds.has(id)) continue;
      item.value = '';
      item.textContent = '';
      item.title = '';
      item.innerHTML = '';
      item.disabled = false;
      item.classList.reset(initialClasses.get(id));
    }
  }
};
let user = null;
let verificationFails = false;
let deliveryFails = false;
let logoutFails = false;
let delayedDashboard = null;
let storyResetCount = 0;
let now = 1_000_000;
let interval = null;
class FixtureDate extends Date {
  static now() { return now; }
}

const context = vm.createContext({
  document: {
    getElementById: element,
    querySelectorAll() { return []; },
    querySelector(selector) { assert.equal(selector, '.layout'); return layout; }
  },
  window: {
    addEventListener: (name, listener) => windowListeners.set(name, listener),
    FINOVAStory: {reset() { storyResetCount += 1; }},
    location: {replace(url) { navigation.push(url); }},
    localStorage: {setItem(key, value) { logoutEvents.push({key, value}); }}
  },
  AbortController,
  Headers,
  clearTimeout() {},
  Date: FixtureDate,
  setTimeout() { return 1; },
  setInterval(callback) { interval = callback; return 1; },
  clearInterval() { interval = null; },
  async fetch(url, options = {}) {
    const body = options.body ? JSON.parse(options.body) : null;
    requests.push({url, body});
    if (url === '/api/dashboard') {
      // Deliberately ignore abort to exercise rejection of an already-arriving response.
      return new Promise(resolve => {
        delayedDashboard = () => resolve({
          ok: true, status: 200, headers: {get() { return null; }},
          async json() { return {company: 'Private customer company'}; }
        });
      });
    }
    let status = 200;
    let payload;
    if (url === '/api/auth/me') {
      payload = {ok: true, user};
    } else if (url === '/api/auth/send-code') {
      status = deliveryFails ? 503 : 200;
      payload = deliveryFails ? {error: 'Email login is not configured.'}
        : {ok: true, message: 'Verification code sent.', retry_after: 60};
    } else if (url === '/api/auth/verify-code') {
      status = verificationFails ? 400 : 200;
      if (!verificationFails) user = {email: body.email};
      payload = verificationFails ? {error: 'Incorrect or expired verification code.'} : {ok: true, user};
    } else if (url === '/api/auth/logout') {
      status = logoutFails ? 500 : 200;
      if (!logoutFails) user = null;
      payload = logoutFails ? {error: 'Logout is unavailable.'} : {ok: true, user};
    } else {
      throw new Error(`Unexpected request ${url}`);
    }
    return {ok: status === 200, status, headers: {get() { return null; }}, async json() { return payload; }};
  }
});
vm.runInContext(fs.readFileSync(path.join(root, 'static', 'app.js'), 'utf8'), context);

async function run() {
  vm.runInContext('initAuth()', context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(element('login-btn').classList.contains('hidden'), false);
  assert.equal(element('logout-btn').classList.contains('hidden'), true);

  await element('login-btn').dispatch('click');
  assert.equal(element('login-dialog').open, true);
  assert.equal(focusedElement, element('login-email'));

  element('login-email').value = 'reader@outlook.com';
  deliveryFails = true;
  await element('send-code-form').dispatch('submit');
  assert.equal(element('login-message').classList.contains('error'), true);
  assert.equal(element('send-code-btn').disabled, false);
  assert.equal(element('verify-code-form').classList.contains('hidden'), true);

  deliveryFails = false;
  await element('send-code-form').dispatch('submit');
  assert.equal(element('verify-code-form').classList.contains('hidden'), false);
  assert.equal(element('send-code-btn').disabled, true);
  assert.equal(focusedElement, element('login-code'));
  const requestsBeforeCooldown = requests.length;
  await element('send-code-form').dispatch('submit');
  assert.equal(requests.length, requestsBeforeCooldown);

  element('login-code').value = '123456';
  verificationFails = true;
  await element('verify-code-form').dispatch('submit');
  assert.equal(element('login-dialog').open, true);
  assert.equal(element('login-message').classList.contains('error'), true);
  assert.equal(element('verify-code-btn').disabled, false);

  verificationFails = false;
  await element('verify-code-form').dispatch('submit');
  assert.equal(element('login-dialog').open, false);
  assert.equal(element('login-btn').classList.contains('hidden'), true);
  assert.equal(element('logout-btn').classList.contains('hidden'), false);
  assert.equal(element('user-email').textContent, 'reader@outlook.com');
  assert.equal(element('login-code').value, '');

  logoutFails = true;
  await element('logout-btn').dispatch('click');
  assert.equal(element('login-btn').classList.contains('hidden'), true);
  assert.equal(element('user-email').textContent, 'reader@outlook.com');
  assert.equal(navigation.length, 0);
  assert.equal(storyResetCount, 0);

  logoutFails = false;
  layoutHTML = 'Private customer financial page';
  element('question').value = 'Private financial question';
  element('transaction-search').value = 'Private vendor';
  element('ai-answer').textContent = 'Private financial answer';
  element('loaded-file').textContent = 'Private customer file.csv';
  element('login-code').value = '654321';
  vm.runInContext("DATA = {company: 'Private customer company'}; selectedAnomaly = 'private'; anomalyFilter = 'Spending spike';", context);
  const pendingResult = vm.runInContext("getJSON('/api/dashboard')", context);
  const rejectedResponse = assert.rejects(pendingResult, error => error.name === 'AbortError');
  await element('logout-btn').dispatch('click');
  delayedDashboard();
  await rejectedResponse;
  assert.equal(element('login-btn').classList.contains('hidden'), false);
  assert.equal(element('logout-btn').classList.contains('hidden'), true);
  assert.equal(element('user-email').textContent, '');
  assert.equal(element('login-email').value, '');
  assert.equal(element('login-code').value, '');
  assert.equal(element('question').value, '');
  assert.equal(element('transaction-search').value, '');
  assert.equal(element('ai-answer').textContent, '');
  assert.equal(layoutHTML, 'Initial demo page');
  assert.equal(vm.runInContext('DATA', context), null);
  assert.equal(vm.runInContext('selectedAnomaly', context), null);
  assert.equal(vm.runInContext('anomalyFilter', context), 'all');
  assert.equal(vm.runInContext('resendAvailableByEmail.size', context), 0);
  assert.equal(interval, null);
  assert.equal(storyResetCount, 1);
  assert.deepEqual(navigation, ['/']);
  assert.equal(logoutEvents[0].key, 'finova_logout');
  assert.match(logoutEvents[0].value, /^\d+$/);

  now += 61_000;
  assert.equal(element('send-code-btn').disabled, false);
  assert.equal(interval, null);
  await element('login-btn').dispatch('click');
  element('login-email').value = 'reader@outlook.com';
  await element('send-code-form').dispatch('submit');
  element('login-email').value = 'another@qq.com';
  await element('login-email').dispatch('input');
  assert.equal(element('verify-code-form').classList.contains('hidden'), true);
  assert.equal(element('login-code').value, '');
  assert.equal(element('send-code-btn').disabled, false);
  assert.equal(interval, null);
  element('login-email').value = ' reader@OUTLOOK.COM ';
  await element('login-email').dispatch('input');
  assert.equal(element('send-code-btn').textContent, 'Resend in 60s');
  assert.equal(typeof interval, 'function');
  now += 10_000;
  interval();
  assert.equal(element('send-code-btn').textContent, 'Resend in 50s');
  element('login-email').value = 'another@qq.com';
  await element('login-email').dispatch('input');
  const beforeNewEmail = requests.length;
  await element('send-code-form').dispatch('submit');
  assert.equal(requests.length, beforeNewEmail + 1);
  assert.equal(requests.at(-1).body.email, 'another@qq.com');
  element('login-email').value = 'reader@outlook.com';
  await element('login-email').dispatch('input');
  assert.equal(element('send-code-btn').textContent, 'Resend in 50s');
  await element('close-login-btn').dispatch('click');
  assert.equal(element('login-dialog').open, false);

  element('user-email').textContent = 'User from another tab';
  windowListeners.get('storage')({key: 'unrelated', newValue: '1'});
  assert.equal(navigation.length, 1);
  windowListeners.get('storage')({key: 'finova_logout', newValue: '123'});
  assert.equal(element('user-email').textContent, '');
  assert.equal(navigation.length, 2);
  assert.equal(logoutEvents.length, 1);
  element('ai-answer').textContent = 'Cached private answer';
  windowListeners.get('pageshow')({persisted: false});
  assert.equal(element('ai-answer').textContent, 'Cached private answer');
  windowListeners.get('pageshow')({persisted: true});
  assert.equal(element('ai-answer').textContent, '');
  assert.equal(navigation.length, 3);

  console.log('Login UI checks passed: cooldowns, verification, logout privacy, stale responses, tab reset, and history restoration.');
}

run().catch(error => { console.error(error); process.exitCode = 1; });
