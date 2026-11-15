import test, {before, beforeEach, afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {Window} from 'happy-dom';
import React, {act} from 'react';
import {TargetProducts, ObservationProduct} from './components/TargetProducts.jsx';
import {loadTargetObservations, loadProduct} from './skyData.js';

let root, createRoot, oldFetch;
before(async () => {
  const win = new Window({url: 'http://localhost:8000'});
  for (const key of ['window','document','HTMLElement','Event','Node']) globalThis[key] = key === 'window' ? win : win[key];
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  ({createRoot} = await import('react-dom/client'));
});
beforeEach(() => { oldFetch = globalThis.fetch; document.body.innerHTML = '<div id="root"></div>'; root = createRoot(document.getElementById('root')); });
afterEach(async () => { await act(async () => root.unmount()); globalThis.fetch = oldFetch; });
const observation = (id, target='alpha') => ({product_id: id, target_id: target, available: true,
  observed_at: '2025-01-01T00:00:00Z', detector: '1', provisional: true,
  association_status: 'unverified', astrometry_status: 'provisional',
  predicted_position: {ra_deg: 12, dec_deg: 20}, file_wavelength_um: [1,2]});
const result = (target, observations=[]) => ({target_id: target, observations, warnings: []});
const productLoader = async (id, type) => type === 'preview' ? new Blob(['png'], {type: 'image/png'})
  : `{"product_id":"${id}","flags":{"bitwise_or":9223372036854775811}}`;

test('supplied dataset retains exact catalogue IDs, uncertainty and non-detection labels', async () => {
  const item = {...observation('dataset-product'), fits_url:'/api/observations/dataset-product/fits',
    sha256:'abc123', file_wavelength:{min:.015,max:1.12,unit:null},
    dataset:{filename:'supplied.fits',
      adopted_astrometry:{source_catalogue:'CatWISE2020', source_id:'4472832130942575872', ref_epoch_jyear:'2015.405', notes:'Provisional; about 2 arcsec uncertainty.'},
      propagation:{rv_status:'NOT_APPLICABLE',time_scale_assumption:'UTC assumption',note:'Space motion only.'},
      coverage:{status:'EDGE',edge_distance_px:2.1,note:'Coverage is not detection.'},
      detection_screen:{verdict:'ABOVE_THRESHOLD_NOT_UNUSUAL',snr_peak:6,control_p99_snr:9,control_n:300,
        method_note:'Not confirmed source identification or photometry.',note:'Possible contamination.'}}};
  await act(async () => root.render(React.createElement(ObservationProduct,{observation:item,productLoader})));
  const evidence = document.querySelector('[aria-label="Supplied dataset evidence"]');
  assert.match(evidence.textContent,/4472832130942575872/);
  assert.match(evidence.textContent,/ABOVE_THRESHOLD_NOT_UNUSUAL/);
  assert.match(evidence.textContent,/Not confirmed source identification/);
  assert.match(evidence.textContent,/Unit absent; no conversion to microns/);
  assert.match(evidence.textContent,/about 2 arcsec uncertainty/);
  assert.equal(document.querySelector('.target-product a[download]').getAttribute('href'),'/api/observations/dataset-product/fits');
});

test('observation choice loads matching preview/quality and retains exact raw flags and provisional labels', async () => {
  const calls = [];
  const loader = async (id, type) => { calls.push([id,type]); return productLoader(id,type); };
  const observations = [observation('a'), observation('b')];
  await act(async () => root.render(React.createElement(TargetProducts, {targetId:'alpha', observationLoader:async () => result('alpha',observations), productLoader:loader})));
  assert.match(document.body.textContent, /9223372036854775811/);
  assert.match(document.body.textContent, /Provisional.*unverified.*provisional/);
  assert.match(document.body.textContent, /1 µm – 2 µm/);
  const select = document.querySelector('select');
  await act(async () => { select.value = 'b'; select.dispatchEvent(new Event('change',{bubbles:true})); });
  assert.deepEqual(calls.slice(-2), [['b','preview'],['b','quality']]);
  assert.match(document.querySelector('.target-product').textContent, /"product_id":"b"/);
  assert.doesNotMatch(document.querySelector('.target-product').textContent, /"product_id":"a"/);
});

test('late target responses are ignored even when loader ignores cancellation', async () => {
  let finishAlpha;
  const loader = id => id === 'alpha' ? new Promise(resolve => { finishAlpha=resolve; }) : Promise.resolve(result('beta',[observation('beta-product','beta')]));
  await act(async () => root.render(React.createElement(TargetProducts, {targetId:'alpha', observationLoader:loader, productLoader})));
  await act(async () => root.render(React.createElement(TargetProducts, {targetId:'beta', observationLoader:loader, productLoader})));
  await act(async () => finishAlpha(result('alpha',[observation('wrong-product')])));
  assert.match(document.body.textContent, /beta-product/);
  assert.doesNotMatch(document.body.textContent, /wrong-product/);
});

test('late preview and quality responses cannot replace a newer selected product', async () => {
  const resolvers = {};
  const loader=(id,type) => id === 'old' ? new Promise(resolve => {resolvers[type]=resolve;}) : productLoader(id,type);
  await act(async () => root.render(React.createElement(ObservationProduct,{key:'old',observation:observation('old'),productLoader:loader})));
  await act(async () => root.render(React.createElement(ObservationProduct,{key:'new',observation:observation('new'),productLoader:loader})));
  await act(async () => {
    resolvers.preview(new Blob(['old']));
    resolvers.quality('{"product_id":"old"}');
  });
  assert.match(document.querySelector('.target-product').textContent,/"product_id":"new"/);
  assert.doesNotMatch(document.querySelector('.target-product').textContent,/"product_id":"old"/);
});

test('empty products, request failures and unavailable product data have explicit states', async () => {
  await act(async () => root.render(React.createElement(TargetProducts, {targetId:'alpha', observationLoader:async () => result('alpha')})));
  assert.match(document.body.textContent, /No approved local products/);
  await act(async () => root.render(React.createElement(TargetProducts, {key:'error', targetId:'alpha', observationLoader:async () => {throw new Error('Archive unavailable');}})));
  assert.match(document.querySelector('[role="alert"]').textContent, /Archive unavailable/);
  await act(async () => root.render(React.createElement(TargetProducts, {key:'missing', targetId:'alpha', observationLoader:async () => result('alpha',[{...observation('missing'), available:false}])})));
  assert.match(document.body.textContent, /Preview unavailable/);
  assert.match(document.body.textContent, /Quality unavailable/);
});

test('API client uses target/observation routes and rejects mismatched associations', async () => {
  const calls=[];
  globalThis.fetch=async url => {calls.push(url); return new Response(JSON.stringify(result('alpha',[observation('a')])));};
  await loadTargetObservations('alpha');
  assert.equal(calls[0], '/api/targets/alpha/observations');
  globalThis.fetch=async url => {calls.push(url); return new Response('raw quality');};
  assert.equal(await loadProduct('a','quality'), 'raw quality');
  assert.equal(calls.at(-1), '/api/observations/a/quality');
  globalThis.fetch=async () => new Response(JSON.stringify(result('beta')));
  await assert.rejects(loadTargetObservations('alpha'), /does not match/);
});
