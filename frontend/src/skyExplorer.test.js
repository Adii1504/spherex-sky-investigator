import test, { before, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { Window } from 'happy-dom';
import React, { act } from 'react';
import { SkyExplorer } from './components/SkyExplorer.jsx';
import { targetCoordinates } from './aladin.js';
import { targetCatalogue } from './data/targetCatalogue.js';

let window, root, createRoot, originalFetch;
const targets = [
  { id: 'test-alpha', name: 'Test Alpha', object_type: 'Test star', ra_deg: 10, dec_deg: -20, coordinate_frame: 'ICRS', reference_epoch: 'J2000', provisional: true, references: [] },
  { id: 'test-beta', name: 'Test Beta', object_type: 'Test variable', ra_deg: 30, dec_deg: 40, coordinate_frame: 'ICRS', reference_epoch: 'J2000', provisional: true, references: [] },
  { id: 'test-pending', name: 'Test Pending', object_type: 'Unknown', ra_deg: null, dec_deg: null, references: [] },
];
const solarFixture = {observed_at:'2026-11-15T00:00:00Z',ephemeris:'test fixture',frame:'GCRS',note:'Test positions only',bodies:[
  {id:'mars',name:'Mars',kind:'Rocky planet',color:'#e58b64',description:'A rocky world.',ra_deg:33,dec_deg:12,distance_au:1.5,reference_url:'https://science.nasa.gov/mars/'},
  {id:'earth',name:'Earth',kind:'Our observing world',color:'#6abce8',description:'Earth is the viewpoint, so it has no sky marker.',ra_deg:null,dec_deg:null,distance_au:null,reference_url:'https://science.nasa.gov/earth/'},
]};
before(async () => {
  window = new Window({ url: 'http://localhost:5173' });
  for (const key of ['window', 'document', 'HTMLElement', 'HTMLInputElement', 'HTMLSelectElement', 'Event', 'MouseEvent', 'Node']) globalThis[key] = key === 'window' ? window : window[key];
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  ({ createRoot } = await import('react-dom/client'));
});
beforeEach(() => {
  document.body.innerHTML = '<div id="test-root"></div>'; root = createRoot(document.getElementById('test-root'));
  originalFetch = globalThis.fetch;
  globalThis.fetch = async url => {
    if (String(url).endsWith('/solar-system')) return new Response(JSON.stringify(solarFixture));
    const id = String(url).match(/\/targets\/([^/]+)\/observations/)?.[1];
    return new Response(JSON.stringify(id ? {target_id:id,observations:[],warnings:[]} : {observations:[]}));
  };
});

test('Solar System cards, markers, layer toggle and visit keep catalogue selection independent', async () => {
  let options; const visits=[], bodyUpdates=[], layerUpdates=[], catalogueSelections=[];
  const factory=async (_,opts) => {options=opts;return {setTargets(){},select(){},dispose(){},setBodies:items=>bodyUpdates.push(items),layers:value=>layerUpdates.push(value),center:(body,fov)=>visits.push([body.id,fov])};};
  await act(async () => root.render(React.createElement(SkyExplorer,{targets,mapFactory:factory,onSelectTarget:id=>catalogueSelections.push(id)})));
  assert.equal(document.querySelectorAll('.solar-card').length,2);
  assert.equal(bodyUpdates.at(-1)[0].id,'mars');
  await act(async () => document.querySelector('.sky-earth-observer').click());
  assert.match(document.querySelector('.solar-detail').textContent,/Earth is the viewpoint/);
  await act(async () => document.querySelector('.solar-card').click());
  assert.match(document.querySelector('.solar-detail').textContent,/A rocky world/);
  await act(async () => [...document.querySelectorAll('button')].find(b=>b.textContent==='Explore around Mars').click());
  assert.deepEqual(visits,[['mars',15]]);
  assert.deepEqual(catalogueSelections,[]);
  await act(async () => options.onBodySelect('earth'));
  assert.match(document.querySelector('.solar-detail').textContent,/no sky marker/);
  assert.equal([...document.querySelectorAll('button')].some(b=>b.textContent==='Explore around Earth'),false);
  const toggle=[...document.querySelectorAll('label')].find(n=>n.textContent.includes('Solar System bodies')).querySelector('input');
  await act(async () => toggle.click());
  assert.equal(layerUpdates.at(-1).planets,false);
});

test('Solar System request failure can retry without replacing the sky', async () => {
  let attempts=0;
  const original=globalThis.fetch;
  globalThis.fetch=async url => {
    if (String(url).endsWith('/solar-system') && attempts++===0) return new Response(JSON.stringify({message:'Positions temporarily unavailable'}),{status:503});
    return original(url);
  };
  await act(async () => root.render(React.createElement(SkyExplorer,{targets,mapFactory:async()=>({setTargets(){},select(){},dispose(){}})})));
  assert.match(document.querySelector('.solar-system [role=alert]').textContent,/temporarily unavailable/);
  await act(async () => [...document.querySelectorAll('button')].find(b=>b.textContent==='Update positions').click());
  assert.equal(document.querySelectorAll('.solar-card').length,2);
  assert.ok(document.querySelector('.sky-map-host'));
});
afterEach(async () => { await act(async () => root.unmount()); globalThis.fetch=originalFetch; });

test('all five supplied targets select correct details from keyboard-accessible buttons and markers', async () => {
  let options, starts = 0;
  const chosen = [];
  const factory = async (_, opts) => { options=opts; starts++; return {setTargets(){},select(){},dispose(){}}; };
  for (const target of targetCatalogue) {
    await act(async () => root.render(React.createElement(SkyExplorer, {targets:targetCatalogue,
      selectedTarget:target, mapFactory:factory, onSelectTarget:id => chosen.push(id)})));
    const button = [...document.querySelectorAll('.sky-target-list button')].find(b => b.textContent.includes(target.name));
    button.focus();
    assert.equal(document.activeElement, button);
    await act(async () => button.click());
    assert.equal(chosen.at(-1),target.id);
    await act(async () => options.onSelect(target.id));
    assert.equal(chosen.at(-1),target.id);
    const panel=document.querySelector('.sky-target-details');
    assert.equal(document.querySelectorAll('section[aria-label="Approved target products"]').length, 1);
    assert.ok(panel.textContent.includes(target.name));
    assert.ok(panel.textContent.includes(target.object_type));
    assert.match(panel.textContent,/J2000/);
    assert.match(panel.textContent,/Provisional/);
  }
  assert.equal(starts,1);
});

test('catalogue coordinates preserve degrees and reject null, nonfinite or unsupported frames', () => {
  assert.deepEqual(targetCoordinates(targets[0]), { ra: 10, dec: -20 });
  assert.equal(targetCoordinates(targets[2]), null);
  assert.equal(targetCoordinates({ ra_deg: 360, dec_deg: 0, frame: 'ICRS' }), null);
  assert.equal(targetCoordinates({ ra_deg: 0, dec_deg: Infinity, frame: 'ICRS' }), null);
  assert.equal(targetCoordinates({ ra_deg: 10, dec_deg: 20, frame: 'Galactic' }), null);
});

test('empty-sky coordinates do not select or invent an object and layer controls are independent', async () => {
  let options;
  const changes=[], selections=[];
  const factory=async (_, opts) => {options=opts; return {setTargets(){},select(){},dispose(){},layers:value=>changes.push(value)};};
  await act(async () => root.render(React.createElement(SkyExplorer,{targets,selectedTarget:targets[0],mapFactory:factory,onSelectTarget:id=>selections.push(id)})));
  await act(async () => options.onCoordinate({ra:0,dec:-90}));
  assert.match(document.body.textContent,/RA 0.000000°, Dec -90.000000°/);
  assert.match(document.body.textContent,/coordinate only; no object identified/);
  assert.deepEqual(selections,[]);
  assert.match(document.querySelector('.sky-target-details').textContent,/Test Alpha/);
  const toggle=document.querySelectorAll('.sky-map-toolbar input[type="checkbox"]')[1];
  await act(async () => toggle.click());
  assert.deepEqual(changes.at(-1),{sources:true,observations:false,planets:true});
});

test('one map instance survives A to B to A selection and equivalent list/marker selection', async () => {
  let starts = 0, mapOptions;
  const selected = [];
  const active = [];
  const centered = [];
  let disposed = 0;
  const instance = { setTargets: () => {}, select: id => active.push(id), center: target => centered.push(target.id), zoom: () => {}, reset: () => {}, dispose: () => { disposed++; } };
  const factory = async (element, options) => { starts++; mapOptions = options; return instance; };
  const render = async target => act(async () => { root.render(React.createElement(SkyExplorer, { targets, selectedTarget: target, mapFactory: factory, onSelectTarget: id => selected.push(id) })); });
  await render(targets[0]); await render(targets[1]); await render(targets[0]);
  assert.equal(starts, 1);
  assert.equal(disposed, 0);
  assert.deepEqual(active.slice(-3), ['test-alpha', 'test-beta', 'test-alpha']);
  assert.deepEqual(centered, [], 'selection must leave the current field and zoom unchanged');
  await act(async () => document.querySelectorAll('.sky-target-list button')[1].click());
  assert.equal(selected.at(-1), 'test-beta');
  await act(async () => mapOptions.onSelect('test-alpha'));
  assert.equal(selected.at(-1), 'test-alpha');
  assert.equal(document.querySelector('[role="dialog"]'),null,'sky star selection must leave search and details available without a 3D takeover');
  assert.ok([...document.querySelectorAll('.sky-target-actions button')].find(button=>button.textContent==='View in 3D'));
  assert.match(document.querySelector('.sky-target-details').textContent, /J2000/);
  assert.match(document.querySelector('.sky-survey-credit').textContent, /not SPHEREx observations/);
});

test('search, centre, zoom, reset and field search invoke the actual adapter callbacks', async () => {
  const actions = [];
  const searched = [];
  const instance = { setTargets: () => {}, select: () => {}, center: target => actions.push(target.id), zoom: value => actions.push(value), pan: (...direction) => actions.push(direction), fill: () => actions.push('fill'), reset: () => actions.push('reset'), allSky: () => actions.push('allSky'), dispose: () => {} };
  const factory = async () => instance;
  await act(async () => root.render(React.createElement(SkyExplorer, { targets, selectedTarget: targets[0], mapFactory: factory, onSearchTarget: target => searched.push(target.id) })));
  const buttons = [...document.querySelectorAll('button')];
  assert.deepEqual(actions, [], 'initial selection must not zoom away from the other targets');
  await act(async () => {
    buttons.find(button => button.textContent === 'All-sky overview').click();
    buttons.find(button => button.textContent === 'Reset view').click();
    buttons.find(button => button.getAttribute('aria-label') === 'Zoom in reference sky').click();
    buttons.find(button => button.textContent === 'Centre on target').click();
    buttons.find(button => button.textContent === 'Search SPHEREx field').click();
    for (const direction of ['left','right','up','down']) buttons.find(button => button.getAttribute('aria-label') === `Pan sky ${direction}`).click();
    buttons.find(button => button.textContent === 'Fill panel').click();
    document.querySelector('.sky-map-host').dispatchEvent(new window.KeyboardEvent('keydown', {key:'ArrowRight',bubbles:true,cancelable:true}));
  });
  assert.deepEqual(actions, ['allSky', 'reset', .5, 'test-alpha', [1,0], [-1,0], [0,1], [0,-1], 'fill', [-1,0]]);
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
