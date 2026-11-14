import test, { afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { formatUtc, formatWavelength, getHealth, safeProvenanceUrl, searchObservations, validateSearch } from './search.js';
import { fixtureSearch, FIXTURE_LABEL } from './fixtures/developmentData.js';
import { targetPresets } from './data/targetPresets.js';

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });
const valid = {ra_deg: '12', dec_deg: '-5', fov_arcmin: '2'};

test('validation returns numeric query without extra fields', () => {
 assert.deepEqual(validateSearch(valid), {errors: {}, query: {ra_deg: 12, dec_deg: -5, fov_arcmin: 2}});
});

for (const [field, value] of [
 ['ra_deg', ''], ['ra_deg', '   '], ['ra_deg', '-1'], ['ra_deg', '360'], ['ra_deg', 'NaN'],
 ['dec_deg', ''], ['dec_deg', '-90.1'], ['dec_deg', '90.1'], ['dec_deg', 'Infinity'],
 ['fov_arcmin', ''], ['fov_arcmin', '0'], ['fov_arcmin', '-1'], ['fov_arcmin', '30.1'], ['fov_arcmin', 'abc'],
]) {
 test(`validation rejects ${field}=${JSON.stringify(value)}`, () => {
  const result = validateSearch({...valid, [field]: value});
  assert.equal(result.query, null);
  assert.equal(typeof result.errors[field], 'string');
 });
}

test('valid coordinate boundaries and small positive FOV are accepted', () => {
 for (const query of [{ra_deg: '0', dec_deg: '-90', fov_arcmin: '0.0001'}, {ra_deg: '359.999999', dec_deg: '90', fov_arcmin: '30'}]) {
  assert.deepEqual(validateSearch(query).errors, {});
 }
});

test('empty inputs never coerce to zero', () => {
 const result = validateSearch({});
 assert.equal(Object.keys(result.errors).length, 3);
 assert.equal(result.query, null);
});

test('all five presets remain disabled data placeholders', () => {
 assert.deepEqual(targetPresets.map(target => target.name), ["Barnard's Star", 'Epsilon Indi B', 'WISE 0855', 'RW Aurigae', 'R Draconis']);
 assert.ok(targetPresets.every(target => target.ra_deg === null && target.dec_deg === null && target.fov_arcmin === null));
});

test('live search preserves coverage_summary, null science values and warnings', async () => {
 const response = await fixtureSearch('success', undefined, 0);
 // This is an HTTP contract stub, never an astronomical validation.
 globalThis.fetch = async (url, options) => {
  assert.equal(url, '/api/v1/observations/search');
  assert.deepEqual(JSON.parse(options.body), {ra_deg: 12, dec_deg: -5, fov_arcmin: 2});
  return new Response(JSON.stringify(response));
 };
 const result = await searchObservations(validateSearch(valid).query);
 assert.deepEqual(result, response);
 assert.equal(result.observations[0].detector, null);
 assert.equal(result.observations[0].quality, null);
 assert.equal(result.observations[1].quality.flagged_fraction, 0);
 assert.equal('coverage' in result, false);
});

test('empty coverage is a successful response', async () => {
 const response = {search_id: 'test_empty', observations: [], coverage_summary: {count: 0}, warnings: []};
 globalThis.fetch = async () => new Response(JSON.stringify(response));
 assert.deepEqual(await searchObservations(validateSearch(valid).query), response);
});

test('live failures never switch to fixtures', async () => {
 let calls = 0;
 globalThis.fetch = async () => { calls++; return new Response('{"code":"capability_unavailable","message":"Archive unavailable"}', {status: 503}); };
 await assert.rejects(searchObservations(validateSearch(valid).query, {scenario: 'success'}), error => error.code === 'capability_unavailable');
 assert.equal(calls, 1);
});

test('old-guide and malformed responses are rejected', async () => {
 for (const response of [null, {search_id: 'test', observations: [], coverage: {}, warnings: []}, {search_id: 'test', observations: [], coverage_summary: [], warnings: []}]) {
  globalThis.fetch = async () => new Response(JSON.stringify(response));
  await assert.rejects(searchObservations(validateSearch(valid).query), error => error.code === 'invalid_response');
 }
});

test('health retains independent capability states', async () => {
 const response = {status: 'ok', capabilities: {archive_access: 'available', image_processing: 'unavailable', motion_verification: 'unavailable'}};
 globalThis.fetch = async () => new Response(JSON.stringify(response));
 assert.deepEqual(await getHealth(), response);
});

test('unknown capability values never become available', async () => {
 globalThis.fetch = async () => new Response('{"status":"ok","capabilities":{"archive_access":true}}');
 await assert.rejects(getHealth(), error => error.code === 'invalid_response');
});

test('explicit fixture mode does not request the backend', async () => {
 globalThis.fetch = async () => assert.fail('Fixture search must stay local');
 const result = await searchObservations(validateSearch(valid).query, {mode: 'fixture'});
 assert.match(result.search_id, /^demo_/);
 assert.equal(result.observations.length, 3);
 assert.ok(result.observations.every(observation => observation.id.startsWith('demo_')));
 assert.ok(result.warnings.includes(FIXTURE_LABEL));
});

test('fixture empty and error scenarios use truthful shapes and messages', async () => {
 const result = await fixtureSearch('empty', undefined, 0);
 assert.deepEqual(result.observations, []);
 assert.equal(result.coverage_summary.count, 0);
 await assert.rejects(fixtureSearch('error', undefined, 0), error => error.code === 'demo_archive_unavailable');
});

test('cancelling fixture work rejects it instead of publishing old results', async () => {
 const controller = new AbortController();
 const pending = fixtureSearch('success', controller.signal, 1000);
 controller.abort();
 await assert.rejects(pending, error => error.name === 'AbortError');
 await assert.rejects(fixtureSearch('success', controller.signal, 0), error => error.name === 'AbortError');
});

test('fixture responses do not share mutable observation state', async () => {
 const first = await fixtureSearch('success', undefined, 0);
 first.observations[0].detector = 'changed';
 assert.equal((await fixtureSearch('success', undefined, 0)).observations[0].detector, null);
});

test('timestamps are formatted as UTC and invalid values remain unavailable', () => {
 assert.equal(formatUtc('2000-01-01T05:30:00+05:30'), '2000-01-01 00:00:00 UTC');
 for (const value of [null, undefined, '', 'invalid']) assert.equal(formatUtc(value), 'Unavailable');
});

test('zero-valued metadata is distinct from missing metadata', () => {
 assert.equal(formatWavelength(0), '0 µm');
 assert.equal(formatWavelength(null), 'Unavailable');
});

test('provenance links only allow web URLs', () => {
 assert.equal(safeProvenanceUrl('https://irsa.ipac.caltech.edu/'), 'https://irsa.ipac.caltech.edu/');
 for (const value of [null, '', 'javascript:alert(1)', 'file:///private/file']) assert.equal(safeProvenanceUrl(value), null);
});
