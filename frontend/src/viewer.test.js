import test from 'node:test';
import assert from 'node:assert/strict';
import { clampView, fittedImage, navigatorRectangle, recenterView, stepFrame } from './viewer.js';

test('image fits viewport without changing its aspect ratio', () => {
  assert.deepEqual(fittedImage(1000, 600, 200, 200), { width: 600, height: 600 });
  assert.deepEqual(fittedImage(1000, 600, 400, 200), { width: 1000, height: 500 });
  assert.deepEqual(fittedImage(0, 600), { width: 0, height: 0 });
});

test('pan is clamped so image can never leave the viewport', () => {
  assert.deepEqual(clampView({ zoom: 2, x: 10000, y: -10000 }, { width: 1000, height: 600 }, { width: 600, height: 600 }), { zoom: 2, x: 100, y: -300 });
  assert.deepEqual(clampView({ zoom: .1, x: 30, y: 30 }, { width: 1000, height: 600 }, { width: 600, height: 600 }), { zoom: 1, x: 0, y: 0 });
  assert.equal(clampView({ zoom: 100, x: 0, y: 0 }, { width: 1000, height: 600 }, { width: 600, height: 600 }).zoom, 6);
});

test('navigator rectangle follows zoom and pan in image coordinates', () => {
  const stage = { width: 400, height: 400 }, image = { width: 400, height: 400 };
  assert.deepEqual(navigatorRectangle({ zoom: 1, x: 0, y: 0 }, stage, image), { left: 0, top: 0, width: 1, height: 1 });
  assert.deepEqual(navigatorRectangle({ zoom: 2, x: 0, y: 0 }, stage, image), { left: .25, top: .25, width: .5, height: .5 });
  assert.deepEqual(navigatorRectangle({ zoom: 2, x: 200, y: -200 }, stage, image), { left: 0, top: .5, width: .5, height: .5 });
});

test('letterboxed navigator covers entire image on the fitting axis', () => {
  assert.deepEqual(navigatorRectangle({ zoom: 1, x: 0, y: 0 }, { width: 1000, height: 600 }, { width: 600, height: 600 }), { left: 0, top: 0, width: 1, height: 1 });
});

test('navigator recenter clamps to image edges', () => {
  const stage = { width: 400, height: 400 }, image = { width: 400, height: 400 };
  assert.deepEqual(recenterView({ zoom: 2 }, { x: 0, y: 1 }, stage, image), { zoom: 2, x: 200, y: -200 });
  assert.deepEqual(recenterView({ zoom: 2 }, { x: .5, y: .5 }, stage, image), { zoom: 2, x: 0, y: 0 });
});

test('frame stepping wraps in both directions and handles no frames', () => {
  assert.equal(stepFrame(0, -1, 4), 3);
  assert.equal(stepFrame(3, 1, 4), 0);
  assert.equal(stepFrame(0, 1, 0), 0);
});
