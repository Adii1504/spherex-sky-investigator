// React interaction tests in a simulated DOM. These do not prove browser layout,
// native fullscreen, touch gestures or live astronomical correctness.
import test, { before, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { Window } from 'happy-dom';
import React, { act } from 'react';
import App from './App.jsx';
import { fixtureSearch } from './fixtures/developmentData.js';

let window, root, createRoot;
const originalFetch = globalThis.fetch;
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

before(async () => {
  window = new Window({ url: 'http://127.0.0.1:5173' });
  for (const key of ['window', 'document', 'HTMLElement', 'HTMLInputElement', 'HTMLSelectElement', 'Event', 'MouseEvent', 'KeyboardEvent', 'Node']) globalThis[key] = key === 'window' ? window : window[key];
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.requestAnimationFrame = callback => setTimeout(callback, 0);
  globalThis.cancelAnimationFrame = clearTimeout;
  globalThis.ResizeObserver = class { observe() {} disconnect() {} };
  Object.defineProperty(window.HTMLElement.prototype, 'clientWidth', { configurable: true, get: () => 800 });
  Object.defineProperty(window.HTMLElement.prototype, 'clientHeight', { configurable: true, get: () => 500 });
  ({ createRoot } = await import('react-dom/client'));
});

beforeEach(async () => {
  document.body.innerHTML = '<div id="root"></div>';
  globalThis.fetch = async () => { throw new TypeError('Test backend offline'); };
  root = createRoot(document.getElementById('root'));
  await act(async () => { root.render(React.createElement(App)); });
});
afterEach(async () => {
  await act(async () => root.unmount());
  globalThis.fetch = originalFetch;
});

const all = selector => [...document.querySelectorAll(selector)];
const text = () => document.body.textContent;
function button(label) {
  const found = all('button').find(item => item.textContent.trim() === label || item.getAttribute('aria-label') === label);
  assert.ok(found, `Button exists: ${label}`);
  return found;
}
async function click(item) {
  const element = typeof item === 'string' ? button(item) : item;
  assert.ok(!element.disabled, `Control enabled: ${element.textContent}`);
  await act(async () => element.click());
}
async function value(selector, next) {
  const element = document.querySelector(selector);
  assert.ok(element, `Field exists: ${selector}`);
  await act(async () => {
    const proto = element.tagName === 'SELECT' ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(element, next);
    element.dispatchEvent(new window.Event(element.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
  });
}
async function settle(ms = 500) { await act(async () => { await wait(ms); }); }
async function fixtureReady(scenario = 'success') {
  await click('Sky regions ⌄');
  await click(document.querySelector('input[value="fixture"]'));
  await value('#ra_deg', '12'); await value('#dec_deg', '-5');
  if (scenario !== 'success') await value('#fixture-scenario', scenario);
  await click('Search fixture →'); await settle();
}
async function selectAndBuild() {
  for (const checkbox of all('.observation-choice input')) await click(checkbox);
  await click('Generate sequence →'); await settle(800);
}
async function loadImages() {
  await act(async () => {
    for (const img of all('.preview-image')) {
      Object.defineProperty(img, 'naturalWidth', { configurable: true, value: 512 });
      Object.defineProperty(img, 'naturalHeight', { configurable: true, value: 512 });
      img.dispatchEvent(new window.Event('load'));
    }
  });
}

test('offline initial state stays live, presets remain disabled, and validation focuses invalid input', async () => {
  assert.match(text(), /No astronomical imagery is loaded/);
  assert.match(text(), /Backend offline/);
  assert.equal(document.querySelector('.fixture-banner'), null);
  await click('Sky regions ⌄');
  assert.equal(button('Search observations →').disabled, true);
  assert.equal(all('.preset-buttons button:disabled').length, 5);
  await click(document.querySelector('input[value="fixture"]'));
  await click('Search fixture →');
  assert.match(text(), /Right ascension is required/);
  assert.equal(document.activeElement.id, 'ra_deg');
  await value('#ra_deg', '360'); await value('#dec_deg', '-5');
  await click('Search fixture →');
  assert.match(text(), /not including, 360/);
  assert.equal(document.querySelector('.observation-list'), null);
});

test('fixture search, selection, queued processing, metadata, player and viewer controls work together', async () => {
  await fixtureReady();
  assert.match(text(), /3 observations returned/);
  assert.match(text(), /Development fixture — not real SPHEREx data/);
  assert.equal(button('Generate sequence →').disabled, true);
  for (const checkbox of all('.observation-choice input')) await click(checkbox);
  assert.match(text(), /3 selected/);
  assert.match(text(), /2000-01-01 00:00:00 UTC/);
  await click('Clear selection'); assert.match(text(), /0 selected/);
  for (const checkbox of all('.observation-choice input')) await click(checkbox);
  await click('Generate sequence →');
  assert.match(text(), /Preparing sequence/);
  await settle(800); await loadImages();
  assert.equal(all('.preview-image').length, 1);
  assert.match(text(), /0.0%/); // zero remains zero, not missing
  assert.match(text(), /Not assessed/);
  const first = document.querySelector('.preview-image').src;
  await click('Next observation'); await loadImages();
  assert.notEqual(document.querySelector('.preview-image').src, first);
  assert.match(document.querySelector('.timeline-current').textContent, /2000-01-02/);
  await value('input[aria-label="Observation frame"]', '2');
  assert.match(document.querySelector('.timeline-current').textContent, /2000-01-03/);
  await click('Previous observation'); await loadImages();
  await value('select[aria-label="Playback speed"]', '2');
  await click('Play sequence'); await settle(650);
  assert.match(document.querySelector('.timeline-current').textContent, /2000-01-03/);
  await click('Pause playback');
  await loadImages(); await click('Zoom in A');
  assert.equal(document.querySelector('.viewer-zoom-label').textContent, '1.3×');
  assert.ok(document.querySelector('.navigator-window'));
  await click('Toggle display grid for A'); assert.ok(document.querySelector('.viewer-grid'));
  await click('Reset A view'); assert.equal(document.querySelector('.viewer-zoom-label').textContent, '1.0×');
  await click('Compare'); await click('Side by side');
  assert.equal(all('.comparison-frame').length, 2);
  assert.match(text(), /Views pan and zoom independently/);
  assert.equal(button('Difference unavailable').disabled, true);
});

test('blink pauses ordinary playback, synchronizes metadata, and reset discards frames', async () => {
  await fixtureReady(); await selectAndBuild();
  await click('Play sequence'); await click('Compare'); await click('Blink');
  assert.ok(button('Start blink comparison'));
  await click('Start blink comparison'); await settle(850);
  assert.match(document.querySelector('.comparison-caption').textContent, /Showing B/);
  assert.match(document.querySelector('.context-heading').textContent, /Observation 02/);
  await click('Pause playback');
  await click('Investigate');
  assert.equal(button('Run exploratory verification').disabled, true);
  await click('Evidence'); assert.equal(button('Download evidence JSON').disabled, true);
  await click('Sky regions ⌄'); await click('Reset workspace'); await settle();
  assert.equal(all('.preview-image').length, 0);
  assert.equal(document.querySelector('#ra_deg').value, '');
  assert.equal(document.querySelector('#fov_arcmin').value, '2');
});

test('cancelled fixture search does not publish and empty/error scenarios recover', async () => {
  await click('Sky regions ⌄'); await click(document.querySelector('input[value="fixture"]'));
  await value('#ra_deg', '12'); await value('#dec_deg', '-5');
  await click('Search fixture →'); await click('Reset workspace'); await settle();
  assert.equal(document.querySelector('.observation-list'), null);
  await value('#ra_deg', '12'); await value('#dec_deg', '-5'); await value('#fixture-scenario', 'empty');
  await click('Search fixture →'); await settle();
  assert.match(text(), /No observations found for this query/);
  await click('Start new search'); await value('#fixture-scenario', 'error');
  await click('Search fixture →'); await settle();
  assert.match(text(), /simulated archive failure/);
  assert.ok(button('Retry search'));
  await click('Start new search');
  assert.equal(document.querySelector('#ra_deg').value, '12');
});

test('partial results keep available previews and image retry preserves details', async () => {
  await fixtureReady('partial'); await selectAndBuild();
  assert.equal(document.querySelector('.frame-position').textContent, '01 / 02');
  assert.match(text(), /no preview returned for demo_obs_3/);
  await click('Sky regions ⌄'); await value('#fixture-scenario', 'image-error');
  await click('Search fixture →'); await settle(); await selectAndBuild();
  const image = document.querySelector('.preview-image');
  await act(async () => image.dispatchEvent(new window.Event('error')));
  assert.match(text(), /preview could not be loaded/);
  assert.match(document.querySelector('.context-panel').textContent, /demo_product_1/);
  await click('Retry image');
  assert.notEqual(document.querySelector('.preview-image'), image);
});

test('failed asynchronous fixture sequence displays a recoverable error', async () => {
  await fixtureReady('job-error'); await selectAndBuild();
  assert.match(text(), /demo_processing_failed/);
  assert.equal(all('.preview-image').length, 0);
  assert.ok(button('Review observations / rebuild'));
});

test('live API contract stub completes save, independent verification and evidence export through the app', async () => {
  // Synthetic HTTP stub only: this proves wiring, never live astronomy success.
  const sample = await fixtureSearch('success', undefined, 0);
  const fourth = { ...sample.observations[2], id: 'test_obs_4', exposure_id: 'test_exposure_4', observed_at: '2000-01-04T00:00:00Z', product_id: 'TEST_ONLY_4' };
  const observations = [...sample.observations, fourth];
  let selection;
  let evidenceRequests = 0;
  const output = { outcome: 'insufficient_evidence', assumptions: ['Test assumption'], limitations: ['Synthetic test only'], warnings: [], measurements: { test_value: 0 }, processing_version: 'test-only' };
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/health')) return new Response(JSON.stringify({ status: 'ok', capabilities: { archive_access: 'available', image_processing: 'available', motion_verification: 'available' } }));
    if (url.endsWith('/observations/search/local')) return new Response(JSON.stringify({ search_id: 'test_live_search', observations, coverage_summary: { count: 4, source:'imported-local' }, warnings: ['Synthetic HTTP test only'] }));
    if (url.endsWith('/test_live_search/sync')) return new Response(JSON.stringify({message:'Test archive unavailable'}), {status:503});
    if (url.endsWith('/sequences')) { selection = JSON.parse(options.body); return new Response('{"job_id":"test_sequence"}', { status: 202 }); }
    if (url.endsWith('/jobs/test_sequence')) return new Response(JSON.stringify({ status: 'succeeded', progress: null, result: {
      search_id: 'test_live_search', observation_ids: selection.observation_ids,
      previews: observations.map(observation => ({ observation, preview_url: '/api/v1/previews/test', metadata: {} })),
      processing_settings: {}, shared_display_settings: {}, processing_version: 'test-only', warnings: [], measurements: {},
    } }));
    if (url.endsWith('/investigations')) {
      assert.deepEqual(JSON.parse(options.body), { ...selection, sequence_job_id: 'test_sequence' });
      return new Response('{"investigation_id":"test_investigation"}', { status: 201 });
    }
    if (url.endsWith('/test_investigation/verify')) {
      const body = JSON.parse(options.body);
      assert.deepEqual(Object.keys(body).sort(), ['reserved_observation_ids', 'training_observation_ids']);
      assert.equal(body.training_observation_ids.length, 3); assert.equal(body.reserved_observation_ids.length, 1);
      return new Response('{"job_id":"test_verify"}', { status: 202 });
    }
    if (url.endsWith('/jobs/test_verify')) return new Response(JSON.stringify({ status: 'succeeded', progress: null, result: output }));
    if (url.endsWith('/test_investigation/evidence')) { evidenceRequests++; return new Response(JSON.stringify({ schema_version: '1.0', verification: [output] })); }
    assert.fail(`Unexpected API URL: ${url}`);
  };
  await click('Retry connection');
  await click('Sky regions ⌄'); await value('#ra_deg', '12'); await value('#dec_deg', '-5');
  await click('Search observations →');
  for (const checkbox of all('.observation-choice input')) await click(checkbox);
  await click('Generate sequence →');
  assert.equal(all('.preview-image').length, 1);
  await click('Investigate'); await click('Save investigation');
  assert.ok(button('Investigation saved'));
  await click('Run exploratory verification');
  assert.match(document.querySelector('.context-panel').textContent, /Insufficient evidence/);
  assert.match(text(), /Test assumption/);
  await click('Download evidence JSON');
  assert.equal(evidenceRequests, 1);
  assert.match(text(), /Evidence JSON downloaded/);
});

test('downloaded results appear before archive sync, which preserves checked observations', async () => {
  const sample = await fixtureSearch('success', undefined, 0);
  const observations = sample.observations.map(o=>({...o,release:'imported-local'}));
  let finishSync;
  globalThis.fetch = async url => {
    if(url.endsWith('/health')) return new Response(JSON.stringify({status:'ok',capabilities:{archive_access:'available',image_processing:'available',motion_verification:'available'}}));
    if(url.endsWith('/observations/search/local')) return new Response(JSON.stringify({search_id:'local-first',observations,coverage_summary:{source:'imported-local',complete:false},warnings:[]}));
    if(url.endsWith('/local-first/sync')) return new Promise(resolve=>{finishSync=resolve;});
    return new Response('{}',{status:404});
  };
  await click('Retry connection');
  await click(all('button').find(b=>b.textContent.includes('Sky regions')));
  await value('#ra_deg','12');await value('#dec_deg','-5');
  await click(all('button').find(b=>b.textContent.includes('Search observations')));
  assert.equal(all('.observation-choice input').length,observations.length);
  assert.match(text(),/Checking IRSA in the background/);
  await click(all('.observation-choice input')[0]);
  const extra={...observations[0],id:'new-remote',release:'spherex_dr1'};
  await act(async()=>finishSync(new Response(JSON.stringify({search_id:'local-first',observations:[...observations,extra],
    coverage_summary:{source:'local-and-archive',archive_matches:1,archive_added:1,archive_coverage:{complete:true}},warnings:[]}))));
  assert.equal(all('.observation-choice input').length,observations.length+1);
  assert.equal(all('.observation-choice input')[0].checked,true);
  assert.match(text(),/1 local products matched; 1 additional archive observations added/);
});

test('opening Observations for a supplied target uses its dataset and observation-epoch query', async () => {
  const sample=await fixtureSearch('success',undefined,0);
  const observations=sample.observations.map(o=>({...o,release:'imported-local'}));
  const actualQuery={ra_deg:269.44621,dec_deg:4.76895,fov_arcmin:2};
  let requested=false;
  globalThis.fetch=async (url,options)=>{
    if(url.endsWith('/health')) return new Response(JSON.stringify({status:'ok',capabilities:{archive_access:'available',image_processing:'available',motion_verification:'available'}}));
    if(url.endsWith('/observations/search/target/barnards-star')) {
      requested=true;
      assert.notEqual(JSON.parse(options.body).dec_deg,actualQuery.dec_deg);
      return new Response(JSON.stringify({search_id:'target-data',query:actualQuery,observations,coverage_summary:{source:'imported-local',target_id:'barnards-star'},warnings:[]}));
    }
    return new Response(JSON.stringify({message:'test archive unavailable'}),{status:503});
  };
  await click('Retry connection');
  await click(all('.sky-target-list button').find(b=>b.textContent.includes('Barnard')));
  await click('Observations');
  assert.equal(requested,true);
  assert.equal(all('.observation-choice input').length,observations.length);
  assert.ok(all('.observation-choice input').every(input=>input.checked));
  assert.match(document.querySelector('.query-summary').textContent,/4.76895/);
});

test('Game Zone opens offline, switches games, pauses and returns to the science workspace', async () => {
  await click('Game Zone');await settle(100);
  assert.ok(document.querySelector('#game-zone'));
  assert.equal(document.querySelector('.workspace-layout').hidden,true);
  assert.equal(document.querySelector('.sky-homepage').hidden,true);
  await click(document.querySelector('.arcade-feature'));await settle(100);
  assert.ok(document.querySelector('.intercept-page'));
  assert.equal(document.querySelectorAll('.intercept-target-list > div').length,3);
  await click(document.querySelector('.intercept-heading > button'));await settle(100);
  assert.ok(document.querySelector('.arcade-feature'));
  await click(document.querySelectorAll('.arcade-mode')[1]);
  assert.equal(document.querySelector('.arcade-console').getAttribute('aria-label'),'Asteroid Run');
  await click(document.querySelector('.arcade-launch'));
  assert.equal(document.querySelector('.arcade-overlay'),null);
  await click('Pause');assert.match(document.querySelector('.arcade-overlay').textContent,/Flight paused/);
  await click('Sky explorer');assert.equal(document.querySelector('#game-zone'),null);
  assert.equal(document.querySelector('.sky-homepage').hidden,false);
});

test('viewer fullscreen uses the browser API and exposes rejected requests', async () => {
  Object.defineProperty(document, 'fullscreenEnabled', { configurable: true, value: true });
  await fixtureReady(); await selectAndBuild();
  let requested = false;
  const viewer = document.querySelector('.sky-viewer');
  viewer.requestFullscreen = async () => {
    requested = true;
    Object.defineProperty(document, 'fullscreenElement', { configurable: true, value: viewer });
    document.dispatchEvent(new window.Event('fullscreenchange'));
  };
  document.exitFullscreen = async () => {
    Object.defineProperty(document, 'fullscreenElement', { configurable: true, value: null });
    document.dispatchEvent(new window.Event('fullscreenchange'));
  };
  await click('Enter fullscreen'); assert.equal(requested, true); assert.ok(button('Exit fullscreen'));
  assert.match(document.querySelector('.fullscreen-warnings').textContent, /Geometric test charts are not astronomical imagery/);
  await click('Exit fullscreen');
  viewer.requestFullscreen = async () => { throw new Error('Test denied'); };
  await click('Enter fullscreen'); assert.match(text(), /Fullscreen is unavailable/);
});
