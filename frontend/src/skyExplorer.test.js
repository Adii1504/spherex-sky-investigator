import test, { before, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { Window } from 'happy-dom';
import React, { act } from 'react';
import { SkyExplorer } from './components/SkyExplorer.jsx';
import { targetCoordinates } from './aladin.js';

let window, root, createRoot;
const targets = [
  { id: 'test-alpha', name: 'Test Alpha', object_type: 'Test star', ra_deg: 10, dec_deg: -20, coordinate_frame: 'ICRS', reference_epoch: 'J2000', provisional: true, references: [] },
  { id: 'test-beta', name: 'Test Beta', object_type: 'Test variable', ra_deg: 30, dec_deg: 40, coordinate_frame: 'ICRS', reference_epoch: 'J2000', provisional: true, references: [] },
  { id: 'test-pending', name: 'Test Pending', object_type: 'Unknown', ra_deg: null, dec_deg: null, references: [] },
];
before(async () => {
  window = new Window({ url: 'http://localhost:5173' });
  for (const key of ['window', 'document', 'HTMLElement', 'HTMLInputElement', 'HTMLSelectElement', 'Event', 'MouseEvent', 'Node']) globalThis[key] = key === 'window' ? window : window[key];
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  ({ createRoot } = await import('react-dom/client'));
});
beforeEach(() => { document.body.innerHTML = '<div id="test-root"></div>'; root = createRoot(document.getElementById('test-root')); });
afterEach(async () => { await act(async () => root.unmount()); });

test('catalogue coordinates preserve degrees and reject null, nonfinite or unsupported frames', () => {
  assert.deepEqual(targetCoordinates(targets[0]), { ra: 10, dec: -20 });
  assert.equal(targetCoordinates(targets[2]), null);
  assert.equal(targetCoordinates({ ra_deg: 360, dec_deg: 0, frame: 'ICRS' }), null);
  assert.equal(targetCoordinates({ ra_deg: 0, dec_deg: Infinity, frame: 'ICRS' }), null);
  assert.equal(targetCoordinates({ ra_deg: 10, dec_deg: 20, frame: 'Galactic' }), null);
});

test('one map instance survives A to B to A selection and equivalent list/marker selection', async () => {
  let starts = 0, mapOptions;
  const selected = [];
  const active = [];
  let disposed = 0;
  const instance = { setTargets: () => {}, select: id => active.push(id), center: () => {}, zoom: () => {}, reset: () => {}, dispose: () => { disposed++; } };
  const factory = async (element, options) => { starts++; mapOptions = options; return instance; };
  const render = async target => act(async () => { root.render(React.createElement(SkyExplorer, { targets, selectedTarget: target, mapFactory: factory, onSelectTarget: id => selected.push(id) })); });
  await render(targets[0]); await render(targets[1]); await render(targets[0]);
  assert.equal(starts, 1);
  assert.equal(disposed, 0);
  assert.deepEqual(active.slice(-3), ['test-alpha', 'test-beta', 'test-alpha']);
  await act(async () => document.querySelectorAll('.sky-target-list button')[1].click());
  assert.equal(selected.at(-1), 'test-beta');
  await act(async () => mapOptions.onSelect('test-alpha'));
  assert.equal(selected.at(-1), 'test-alpha');
  assert.match(document.querySelector('.sky-target-details').textContent, /J2000/);
  assert.match(document.querySelector('.sky-survey-credit').textContent, /not SPHEREx observations/);
});

test('search, centre, zoom, reset and field search invoke the actual adapter callbacks', async () => {
  const actions = [];
  const searched = [];
  const instance = { setTargets: () => {}, select: () => {}, center: target => actions.push(target.id), zoom: value => actions.push(value), reset: () => actions.push('reset'), dispose: () => {} };
  const factory = async () => instance;
  await act(async () => root.render(React.createElement(SkyExplorer, { targets, selectedTarget: targets[0], mapFactory: factory, onSearchTarget: target => searched.push(target.id) })));
  const buttons = [...document.querySelectorAll('button')];
  await act(async () => {
    buttons.find(button => button.textContent === 'Reset / all sky').click();
    buttons.find(button => button.getAttribute('aria-label') === 'Zoom in reference sky').click();
    buttons.find(button => button.textContent === 'Centre on target').click();
    buttons.find(button => button.textContent === 'Search SPHEREx field').click();
  });
  assert.deepEqual(actions, ['reset', .5, 'test-alpha']);
  assert.deepEqual(searched, ['test-alpha']);
  const field = document.querySelector('input[type="search"]');
  await act(async () => {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(field, 'Beta');
    field.dispatchEvent(new window.Event('input', { bubbles: true }));
  });
  assert.equal(document.querySelectorAll('.sky-target-list button').length, 1);
  assert.match(document.querySelector('.sky-target-list').textContent, /Test Beta/);
});

test('initialization failure preserves catalogue selection, shows retry and does not fabricate imagery', async () => {
  let calls = 0;
  const chosen = [];
  const factory = async () => { calls++; throw new Error('Test WebGL2 unavailable'); };
  await act(async () => root.render(React.createElement(SkyExplorer, { targets, selectedTarget: targets[2], mapFactory: factory, onSelectTarget: id => chosen.push(id) })));
  assert.match(document.body.textContent, /Reference sky unavailable/);
  assert.match(document.body.textContent, /Test WebGL2 unavailable/);
  assert.equal(document.querySelectorAll('img').length, 0);
  assert.equal([...document.querySelectorAll('button')].find(button => button.textContent === 'Search SPHEREx field').disabled, true);
  await act(async () => document.querySelector('.sky-target-list button').click());
  assert.deepEqual(chosen, ['test-alpha']);
  await act(async () => [...document.querySelectorAll('button')].find(button => button.textContent === 'Retry reference sky').click());
  assert.equal(calls, 2);
});

test('late initialization after unmount disposes its map instead of publishing stale content', async () => {
  let finish;
  let disposed = 0;
  const factory = () => new Promise(resolve => { finish = resolve; });
  await act(async () => root.render(React.createElement(SkyExplorer, { targets, mapFactory: factory })));
  await act(async () => root.unmount());
  await act(async () => finish({ dispose: () => { disposed++; } }));
  assert.equal(disposed, 1);
});
