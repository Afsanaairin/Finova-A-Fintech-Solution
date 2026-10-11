'use strict';

// Verify pause/resume, independent full-story export and cleanup after session/data changes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const elements = new Map();
for (const id of ['story-canvas', 'story-play', 'story-export', 'story-format',
  'story-sound', 'story-progress', 'story-status']) {
  const listeners = new Map();
  const classes = new Set();
  elements.set(id, {
    value: id === 'story-format' ? 'portrait' : 0,
    checked: true, disabled: false, textContent: '', style: {},
    addEventListener(name, listener) { listeners.set(name, listener); },
    dispatch(name) { return listeners.get(name)(); },
    classList: {
      toggle(name, enabled) { if (enabled) classes.add(name); else classes.delete(name); },
      contains(name) { return classes.has(name); }
    }
  });
}
const element = id => elements.get(id);
const visibleText = [];
const drawnImages = [];
function drawingContextFor(target, renderedText, images) {
const drawingContext = {
  globalAlpha: 1,
  fillText(value) { renderedText.push(value); },
  fillRect(x, y, width, height) {
    if (x === 0 && y === 0 && width === target.width && height === target.height) {
      renderedText.length = 0;
    }
  },
  drawImage(image) { images.push(image); },
  measureText(value) { return {width: String(value).length * 10}; },
  createLinearGradient() { return {addColorStop() {}}; }
};
for (const method of ['save', 'restore', 'beginPath', 'roundRect', 'arc', 'stroke', 'fill']) {
  drawingContext[method] = () => {};
}
return drawingContext;
}
const track = kind => ({kind, stops: 0, stop() { this.stops++; }});
const stream = tracks => ({
  tracks,
  getTracks() { return this.tracks; },
  getAudioTracks() { return this.tracks.filter(item => item.kind === 'audio'); },
  addTrack(item) { this.tracks.push(item); }
});
const captureStreams = [];
const canvas = element('story-canvas');
canvas.width = 720;
canvas.height = 1280;
canvas.getContext = () => drawingContext;
const drawingContext = drawingContextFor(canvas, visibleText, drawnImages);
canvas.captureStream = () => {
  const capture = stream([track('video')]);
  captureStreams.push(capture);
  return capture;
};

const audioContexts = [];
class FixtureAudioContext {
  constructor() { this.currentTime = 0; this.destination = {}; this.state = 'running'; this.monitors = 0; audioContexts.push(this); }
  createMediaStreamDestination() { this.output = {stream: stream([track('audio')])}; return this.output; }
  createGain() {
    return {connect: target => { if (target === this.destination) this.monitors++; }, gain: {value: 0, setValueAtTime() {}, exponentialRampToValueAtTime() {}}};
  }
  createOscillator() {
    return {connect() {}, start() {}, stop() {},
      frequency: {setValueAtTime() {}, exponentialRampToValueAtTime() {}}};
  }
  suspend() { this.state = 'suspended'; return Promise.resolve(); }
  resume() { this.state = 'running'; return Promise.resolve(); }
  close() { this.closed = true; this.state = 'closed'; return Promise.resolve(); }
}
const recorders = [];
class FixtureMediaRecorder {
  static isTypeSupported() { return true; }
  constructor(input) { this.stream = input; this.state = 'inactive'; this.stops = 0; recorders.push(this); }
  start() { this.state = 'recording'; }
  stop() { this.state = 'inactive'; this.stops++; }
}
const pendingImages = [];
class FixtureImage {
  constructor() { pendingImages.push(this); }
}
const frames = new Map();
const cancelledFrames = new Set();
let frameId = 0;
let clock = 0;
let downloads = 0;
const generatedURLs = [];
const revokedURLs = [];
const documentListeners = new Map();
const document = {
  getElementById: element,
  addEventListener(name, listener) { documentListeners.set(name, listener); },
  createElement(type) {
    if (type !== 'canvas') return {click() { downloads++; }, remove() {}};
    const target = {style: {}, width: 720, height: 1280};
    const context = drawingContextFor(target, [], []);
    target.getContext = () => context;
    target.captureStream = () => {
      const capture = stream([track('video')]);capture.source = target;
      captureStreams.push(capture);return capture;
    };
    return target;
  },
  body: {appendChild() {}}
};
const context = vm.createContext({
  window: {AudioContext: FixtureAudioContext}, document,
  Image: FixtureImage, MediaRecorder: FixtureMediaRecorder, Blob,
  performance: {now() { return clock; }},
  requestAnimationFrame(callback) { frames.set(++frameId, callback); return frameId; },
  cancelAnimationFrame(id) { cancelledFrames.add(id); frames.delete(id); },
  URL: {
    createObjectURL() { const url = `blob:story-${generatedURLs.length}`; generatedURLs.push(url); return url; },
    revokeObjectURL(url) { revokedURLs.push(url); }
  }
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'static', 'wrapped.js'), 'utf8'), context);
const story = context.window.FINOVAStory;
const privateData = {
  company: 'PRIVATE_CLIENT',
  wrapped: {
    period: 'Private financial year', cash_in: 90000, cash_out: 60000,
    biggest_expense_month: '2026-04', biggest_expense_month_amount: 4000,
    largest_category: 'Private supplier', largest_category_amount: 8000,
    subscription_annual: 2500
  },
  totals: {overdue_invoices: 2}, monthly: [{cash_in: 100, cash_out: 70}],
  subscriptions: [{}], anomalies: [{category: 'Private category'}], forecast: [{net: 4500}]
};
const containsPrivateText = () => visibleText.some(value => /private/i.test(value));
function step(milliseconds) {
  clock += milliseconds;
  const pending = [...frames];
  frames.clear();
  pending.forEach(([, callback]) => callback(clock));
}

async function run() {
  story.init();
  story.setData(privateData);
  assert.equal(containsPrivateText(), true);
  story.setArt('private-artwork');
  const oldArtwork = pendingImages.at(-1);
  const oldArtworkLoad = oldArtwork.onload;
  const oldArtworkError = oldArtwork.onerror;
  element('story-format').value = 'landscape';
  element('story-format').dispatch('change');
  await element('story-export').dispatch('click');

  const activeRecorder = recorders.at(-1);
  const queuedData = activeRecorder.ondataavailable;
  const queuedStop = activeRecorder.onstop;
  const queuedError = activeRecorder.onerror;
  queuedData({data: new Blob(['x'.repeat(6000)])});
  const pendingFrameId = frameId;
  const pendingFrame = frames.get(pendingFrameId);
  const activeStream = captureStreams.at(-1);
  const activeAudio = audioContexts.at(-1);
  story.reset();

  assert.equal(activeRecorder.stops, 1);
  assert.equal(activeRecorder.onstop, null);
  assert.equal(activeRecorder.ondataavailable, null);
  assert.equal(activeRecorder.onerror, null);
  assert.equal(activeAudio.closed, true);
  assert.equal(activeStream.getTracks().every(item => item.stops > 0), true);
  assert.equal(cancelledFrames.has(pendingFrameId), true);
  assert.equal(visibleText.length, 0);
  assert.equal(canvas.width, 720);
  assert.equal(canvas.height, 1280);
  assert.equal(element('story-format').value, 'portrait');
  assert.equal(element('story-sound').checked, true);
  assert.equal(element('story-progress').value, 0);
  assert.equal(element('story-play').textContent, '▶ Play Wrapped');
  assert.equal(element('story-play').disabled, false);
  assert.equal(element('story-export').disabled, false);
  assert.equal(element('story-status').textContent, 'Loading financial story…');

  // Already queued events must stay harmless even if another story has loaded.
  const publicData = {...privateData, company: 'Demo Company',
    wrapped: {...privateData.wrapped, period: 'Public demo period'}};
  story.setData(publicData);
  const publicText = [...visibleText];
  oldArtworkLoad();
  oldArtworkError();
  queuedData({data: new Blob(['y'.repeat(6000)])});
  queuedError({error: {message: 'Private recorder error'}});
  queuedStop();
  pendingFrame(1000);
  assert.deepEqual(visibleText, publicText);
  assert.equal(drawnImages.length, 0);
  assert.equal(downloads, 0);
  assert.equal(generatedURLs.length, 0);
  assert.equal(element('story-status').classList.contains('story-error'), false);

  // Playback and export remain available after resetting a session.
  await element('story-play').dispatch('click');
  for (let scene = 0; scene < 8; scene++) {
    step(scene === 0 ? 900 : 3800);
    assert.ok(visibleText.length > 0);
  }
  step(2900);
  assert.equal(element('story-play').disabled, false);
  assert.equal(element('story-progress').value, 100);

  await element('story-export').dispatch('click');
  const completeRecorder = recorders.at(-1);
  completeRecorder.ondataavailable({data: new Blob(['z'.repeat(6000)])});
  step(30400);
  completeRecorder.onstop();
  assert.equal(downloads, 1);
  assert.equal(generatedURLs.length, 1);
  assert.equal(captureStreams.at(-1).getTracks().every(item => item.stops > 0), true);
  story.reset();
  assert.deepEqual(revokedURLs, generatedURLs);

  // Pause freezes the preview and its audio; resuming excludes the paused wall time.
  story.setData(publicData);
  await element('story-play').dispatch('click');
  const previewAudio = audioContexts.at(-1);
  assert.equal(element('story-play').textContent, '⏸ Pause');
  assert.equal(element('story-export').disabled, false);
  step(2200);
  await element('story-play').dispatch('click');
  const pausedProgress = element('story-progress').value;
  const pausedText = [...visibleText];
  assert.equal(element('story-play').textContent, '▶ Resume');
  assert.equal(previewAudio.state, 'suspended');
  step(6000);
  assert.equal(element('story-progress').value, pausedProgress);
  assert.deepEqual(visibleText, pausedText);
  await element('story-play').dispatch('click');
  step(1000);
  assert.ok(Math.abs(element('story-progress').value - pausedProgress - 100 / 30.4) < 0.001);
  assert.equal(previewAudio.state, 'running');

  // An export has its own canvas, timeline and audio. Preview controls cannot pause it.
  const exportStartProgress = element('story-progress').value;
  const exportStartText = [...visibleText];
  await element('story-export').dispatch('click');
  const concurrentRecorder = recorders.at(-1);
  const exportAudio = audioContexts.at(-1);
  assert.ok(captureStreams.at(-1).source !== canvas);
  assert.equal(element('story-progress').value, exportStartProgress);
  assert.deepEqual(visibleText, exportStartText);
  assert.equal(element('story-play').disabled, false);
  assert.equal(element('story-export').disabled, true);
  assert.equal(exportAudio.monitors, 0);
  assert.equal(previewAudio.monitors, 1);
  step(1000);
  assert.ok(element('story-progress').value > exportStartProgress);
  await element('story-play').dispatch('click');
  const concurrentPausedProgress = element('story-progress').value;
  step(2000);
  assert.equal(element('story-progress').value, concurrentPausedProgress);
  assert.equal(concurrentRecorder.state, 'recording');
  assert.equal(exportAudio.state, 'running');
  assert.ok(element('story-status').textContent.includes('Preview paused'));
  await element('story-play').dispatch('click');
  step(1000);
  assert.ok(element('story-progress').value > concurrentPausedProgress);
  step(26400);
  assert.equal(concurrentRecorder.state, 'inactive');
  concurrentRecorder.ondataavailable({data: new Blob(['v'.repeat(6000)])});
  concurrentRecorder.onstop();
  assert.equal(downloads, 2);
  assert.equal(exportAudio.closed, true);
  assert.equal(element('story-export').disabled, false);

  // Export can also start while paused and completes without resuming that preview.
  await element('story-play').dispatch('click');
  step(500);
  await element('story-play').dispatch('click');
  const heldProgress = element('story-progress').value;
  const heldAudio = audioContexts.at(-1);
  await element('story-export').dispatch('click');
  const pausedRecorder = recorders.at(-1);
  step(30400);
  pausedRecorder.ondataavailable({data: new Blob(['p'.repeat(6000)])});
  pausedRecorder.onstop();
  assert.equal(downloads, 3);
  assert.equal(element('story-progress').value, heldProgress);
  assert.equal(element('story-play').textContent, '▶ Resume');
  assert.equal(heldAudio.state, 'suspended');
  assert.equal(heldAudio.closed, undefined);
  story.reset();
  assert.equal(heldAudio.closed, true);

  // Recorder failures release export resources while leaving preview playback usable.
  story.setData(publicData);
  await element('story-play').dispatch('click');
  await element('story-export').dispatch('click');
  const failingRecorder = recorders.at(-1);
  const failedStop = failingRecorder.onstop;
  failingRecorder.onerror({error: {message: 'Encoder failed'}});
  failedStop();
  assert.equal(downloads, 3);
  assert.equal(element('story-export').disabled, false);
  assert.equal(element('story-play').textContent, '⏸ Pause');
  assert.ok(element('story-status').textContent.includes('Encoder failed'));
  story.reset();

  // Replacing the dataset cancels both timelines and rejects already queued exports.
  story.setData(publicData);
  await element('story-play').dispatch('click');
  await element('story-export').dispatch('click');
  const replacedRecorder = recorders.at(-1);
  const replacedStop = replacedRecorder.onstop;
  const replacedData = replacedRecorder.ondataavailable;
  const replacedFrames = [...frames.values()];
  const replacedStream = captureStreams.at(-1);
  story.setData({...publicData, company: 'Replacement Company'});
  const replacementText = [...visibleText];
  replacedData({data: new Blob(['old'.repeat(6000)])});
  replacedStop();
  replacedFrames.forEach(callback => callback(clock + 1000));
  assert.deepEqual(visibleText, replacementText);
  assert.equal(downloads, 3);
  assert.equal(replacedStream.getTracks().every(item => item.stops > 0), true);
  assert.equal(element('story-play').textContent, '▶ Play Wrapped');
  story.reset();
  assert.deepEqual(revokedURLs, generatedURLs);

  // Formatting changes and play requests cannot redisplay the discarded dataset.
  element('story-format').dispatch('change');
  const requestsBeforeEmptyPlay = frameId;
  await element('story-play').dispatch('click');
  assert.equal(frameId, requestsBeforeEmptyPlay);
  assert.equal(visibleText.length, 0);
  story.reset();
  console.log('Story checks passed: pause/resume timing, simultaneous export, audio isolation, errors, data changes and reset cleanup.');
}

run().catch(error => { console.error(error); process.exitCode = 1; });
