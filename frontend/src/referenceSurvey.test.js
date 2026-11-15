import test from 'node:test';
import assert from 'node:assert/strict';
import { createSurveyLoader } from './referenceSurvey.js';

function setup() {
  const layers = [], statuses = [], timers = new Map();
  let next = 0;
  const loader = createSurveyLoader({HiPS: (url, options) => ({url, options})},
    {setBaseImageLayer: layer => layers.push(layer)}, {
      urls: ['primary', 'mirror'], onStatus: status => statuses.push(status),
      schedule: callback => { timers.set(++next, callback); return next; },
      cancel: id => timers.delete(id),
    });
  return { loader, layers, statuses, timers };
}

test('failed primary retries same-survey mirror using JPEG and ignores late primary callbacks', () => {
  const {loader,layers,statuses,timers} = setup(); loader.load();
  layers[0].options.errorCallback();
  assert.deepEqual(layers.map(x => x.url), ['primary','mirror']);
  assert.equal(layers[1].options.imgFormat, 'jpeg');
  layers[0].options.successCallback();
  assert.equal(statuses.at(-1), 'loading');
  layers[1].options.successCallback();
  assert.equal(statuses.at(-1), 'ready'); assert.equal(timers.size,0);
});

test('timeout advances; all mirrors failing reports error and retry starts fresh', () => {
  const {loader,layers,statuses,timers} = setup(); loader.load();
  [...timers.values()][0]();
  layers[1].options.errorCallback();
  assert.equal(statuses.at(-1),'error');
  loader.load();
  assert.equal(layers[2].url,'primary');
  layers[1].options.successCallback();
  assert.equal(statuses.at(-1),'loading');
  layers[2].options.successCallback(); assert.equal(statuses.at(-1),'ready');
});

test('disposing cancels timers and prevents late callbacks from restarting the loader', () => {
  const {loader,layers,statuses,timers} = setup(); loader.load(); loader.dispose();
  layers[0].options.errorCallback(); loader.load();
  assert.equal(layers.length,1); assert.equal(timers.size,0);
  assert.deepEqual(statuses,['loading']);
});
