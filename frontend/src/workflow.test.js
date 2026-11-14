import test, { afterEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildSequence, createRequestOwner, getEvidence, makeSelection, MAX_OBSERVATIONS,
  missingPreviewIds, saveInvestigation, selectionSummary, verificationIssues, verifyInvestigation,
} from './workflow.js';
import { fixtureSearch } from './fixtures/developmentData.js';

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

const query = { ra_deg: 12, dec_deg: -5, fov_arcmin: 2 };
const observations = Array.from({ length: 4 }, (_, index) => ({
  id: `test_observation_${index + 1}`,
  exposure_id: `test_exposure_${index + 1}`,
  observed_at: `2000-01-0${index + 1}T00:00:00Z`,
  product_id: `test_product_${index + 1}`,
}));
const search = { search_id: 'test_search', observations };
const selectedIds = observations.map(observation => observation.id);
const selection = { search_id: search.search_id, observation_ids: selectedIds, ...query };
const groups = {
  test_observation_1: 'training', test_observation_2: 'training',
  test_observation_3: 'training', test_observation_4: 'reserved',
};

function sequenceResult(chosen = selection) {
  return {
    search_id: chosen.search_id,
    observation_ids: [...chosen.observation_ids],
    previews: observations.filter(observation => chosen.observation_ids.includes(observation.id)).map(observation => ({
      observation, preview_url: `/api/v1/previews/test_${observation.id}`, metadata: {},
    })),
    processing_version: 'test-only', processing_settings: {}, shared_display_settings: {},
    measurements: {}, warnings: ['Synthetic HTTP contract test only'],
  };
}

test('selection snapshots exact searched coordinates and opaque IDs', () => {
  const ids = [...selectedIds];
  const input = { ...query, start_utc: '2000-01-01T00:00:00Z' };
  const result = makeSelection(search, input, ids);
  ids.pop();
  input.ra_deg = 30;
  assert.deepEqual(result, selection);
  assert.equal('start_utc' in result, false);
});

test('selection requires an active search, query and nonempty unique search members', () => {
  for (const [searchValue, queryValue, ids] of [
    [null, query, selectedIds], [search, null, selectedIds], [search, query, []],
    [search, query, ['unknown_observation']],
    [search, query, [selectedIds[0], selectedIds[0]]],
  ]) {
    assert.throws(() => makeSelection(searchValue, queryValue, ids), error => error.code === 'invalid_selection');
  }
});

test('selection respects the backend default observation count limit', () => {
  const many = Array.from({ length: MAX_OBSERVATIONS + 1 }, (_, index) => ({ id: `test_${index}` }));
  const response = { search_id: 'test_many', observations: many };
  assert.equal(makeSelection(response, query, many.slice(0, MAX_OBSERVATIONS).map(item => item.id)).observation_ids.length, MAX_OBSERVATIONS);
  assert.throws(() => makeSelection(response, query, many.map(item => item.id)), error => error.code === 'invalid_selection');
});

test('selection summary derives the selected count and UTC date endpoints', () => {
  assert.deepEqual(selectionSummary([...observations].reverse(), [selectedIds[0], selectedIds[3]]), {
    count: 2, earliest: '2000-01-01T00:00:00.000Z', latest: '2000-01-04T00:00:00.000Z',
  });
  assert.deepEqual(selectionSummary(observations, []), { count: 0, earliest: null, latest: null });
});

test('selection summary tolerates unavailable dates without inventing a range', () => {
  assert.deepEqual(selectionSummary([{ id: 'test_invalid_date', observed_at: 'unavailable' }], ['test_invalid_date']), {
    count: 1, earliest: null, latest: null,
  });
});

test('verification accepts three training and one independent reserved exposure', () => {
  assert.deepEqual(verificationIssues(observations, groups), []);
});

test('verification reports minimum training and reserved requirements', () => {
  const issues = verificationIssues(observations, { [selectedIds[0]]: 'training' });
  assert.ok(issues.some(issue => issue.includes('three training')));
  assert.ok(issues.some(issue => issue.includes('Reserve')));
});

for (const [label, duplicateIndex] of [['within training', 1], ['across training and reserved', 3]]) {
  test(`verification rejects canonical exposure duplication ${label}`, () => {
    const duplicated = observations.map(item => ({ ...item }));
    duplicated[duplicateIndex].exposure_id = duplicated[0].exposure_id;
    assert.ok(verificationIssues(duplicated, groups).some(issue => issue.includes('canonical exposure')));
  });
}

test('verification detects duplicates within the reserved group', () => {
  const extra = { ...observations[3], id: 'test_observation_5' };
  assert.ok(verificationIssues([...observations, extra], { ...groups, [extra.id]: 'reserved' }).some(issue => issue.includes('canonical exposure')));
});

test('excluded products sharing an exposure do not invalidate assigned groups', () => {
  const extra = { ...observations[0], id: 'test_duplicate_product' };
  assert.deepEqual(verificationIssues([...observations, extra], { ...groups, [extra.id]: 'exclude' }), []);
});

for (const scenario of ['success', 'partial']) {
  test(`fixture sequence ${scenario} follows queued/running/succeeded with null progress`, async () => {
    globalThis.fetch = async () => assert.fail('Explicit fixture processing must stay local');
    const response = await fixtureSearch(scenario, undefined, 0);
    const chosen = makeSelection(response, query, response.observations.map(item => item.id));
    const statuses = [];
    const result = await buildSequence(chosen, {
      mode: 'fixture', scenario, observations: response.observations,
      onStatus: job => { statuses.push(job.status); assert.equal(job.progress, null); },
    });
    assert.deepEqual(statuses, ['queued', 'running', 'succeeded']);
    assert.deepEqual(result.selection, chosen);
    assert.match(result.jobId, /^demo_job_/);
    assert.equal(result.previews.length, scenario === 'partial' ? 2 : 3);
    assert.equal(missingPreviewIds(result).length, scenario === 'partial' ? 1 : 0);
    assert.ok(result.warnings.some(warning => warning.includes('Development fixture')));
  });
}

test('fixture job errors terminate polling and expose their structured failure', async () => {
  const response = await fixtureSearch('job-error', undefined, 0);
  const chosen = makeSelection(response, query, response.observations.map(item => item.id));
  const statuses = [];
  await assert.rejects(buildSequence(chosen, {
    mode: 'fixture', scenario: 'job-error', observations: response.observations,
    onStatus: job => statuses.push(job.status),
  }), error => error.code === 'demo_processing_failed');
  assert.deepEqual(statuses, ['queued', 'running', 'failed']);
});

test('live sequence uses the actual selection payload and job/preview response fields', async () => {
  const calls = [];
  const result = sequenceResult();
  globalThis.fetch = async (url, options) => {
    calls.push(url);
    if (url === '/api/v1/sequences') {
      assert.equal(options.method, 'POST');
      assert.deepEqual(JSON.parse(options.body), selection);
      return new Response('{"job_id":"test_sequence_job"}', { status: 202 });
    }
    assert.equal(url, '/api/v1/jobs/test_sequence_job');
    assert.equal(options.method, 'GET');
    return new Response(JSON.stringify({ job_id: 'test_sequence_job', status: 'succeeded', progress: null, result, error: null }));
  };
  const completed = await buildSequence(selection);
  assert.deepEqual(completed.previews, result.previews);
  assert.equal(completed.jobId, 'test_sequence_job');
  assert.deepEqual(calls, ['/api/v1/sequences', '/api/v1/jobs/test_sequence_job']);
});

test('live sequence rejects previews from a different search', async () => {
  globalThis.fetch = async url => new Response(JSON.stringify(url === '/api/v1/sequences'
    ? { job_id: 'test_job' }
    : { status: 'succeeded', result: { ...sequenceResult(), search_id: 'old_search' } }));
  await assert.rejects(buildSequence(selection), error => error.code === 'invalid_response');
});

test('saving an investigation sends selection plus sequence_job_id', async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/v1/investigations');
    assert.deepEqual(JSON.parse(options.body), { ...selection, sequence_job_id: 'test_sequence_job' });
    return new Response('{"investigation_id":"test_investigation"}', { status: 201 });
  };
  assert.equal(await saveInvestigation(selection, 'test_sequence_job'), 'test_investigation');
});

for (const outcome of ['supported', 'not_supported', 'insufficient_evidence']) {
  test(`verification sends actual group fields and preserves ${outcome}`, async () => {
    const result = { outcome, measurements: {}, assumptions: ['Synthetic assumption'], limitations: ['Test only'], warnings: [], processing_version: 'test-only' };
    globalThis.fetch = async (url, options) => {
      if (url === '/api/v1/investigations/test_investigation/verify') {
        assert.deepEqual(JSON.parse(options.body), { training_observation_ids: selectedIds.slice(0, 3), reserved_observation_ids: selectedIds.slice(3) });
        assert.equal('model' in JSON.parse(options.body), false);
        return new Response('{"job_id":"test_verification_job"}', { status: 202 });
      }
      assert.equal(url, '/api/v1/jobs/test_verification_job');
      return new Response(JSON.stringify({ status: 'succeeded', progress: null, result }));
    };
    assert.deepEqual(await verifyInvestigation('test_investigation', observations, groups, undefined, () => {}), result);
  });
}

test('invalid verification assignments never reach the backend', async () => {
  globalThis.fetch = async () => assert.fail('Invalid groups must be rejected before submission');
  await assert.rejects(verifyInvestigation('test_investigation', observations, {}), error => error.code === 'invalid_selection');
});

test('unsupported old-guide outcome codes are rejected', async () => {
  globalThis.fetch = async url => new Response(JSON.stringify(url.includes('/verify')
    ? { job_id: 'test_job' }
    : { status: 'succeeded', result: { outcome: 'motion_supported' } }));
  await assert.rejects(verifyInvestigation('test_investigation', observations, groups, undefined, () => {}), error => error.code === 'invalid_response');
});

test('evidence GET preserves backend JSON and encodes the investigation ID', async () => {
  const evidence = { schema_version: '1.0', investigation_id: 'test/id', selection, observations, processing: null, warnings: ['No processed sequence attached'], verification: [] };
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/v1/investigations/test%2Fid/evidence');
    assert.equal(options.method, 'GET');
    assert.equal(options.body, undefined);
    return new Response(JSON.stringify(evidence));
  };
  assert.deepEqual(await getEvidence('test/id'), evidence);
});

test('request ownership invalidates stale tickets across replacement and reset', () => {
  const owner = createRequestOwner();
  const first = owner.start();
  assert.equal(first.isCurrent(), true);
  const second = owner.start();
  assert.equal(first.signal.aborted, true);
  assert.equal(first.isCurrent(), false);
  assert.equal(second.isCurrent(), true);
  owner.cancel();
  assert.equal(second.signal.aborted, true);
  assert.equal(second.isCurrent(), false);
  const afterReset = owner.start();
  assert.equal(afterReset.isCurrent(), true);
  assert.equal(first.isCurrent(), false);
});

test('cancelling during fixture polling prevents a successful late publication', async () => {
  const response = await fixtureSearch('success', undefined, 0);
  const chosen = makeSelection(response, query, response.observations.map(item => item.id));
  const owner = createRequestOwner();
  const ticket = owner.start();
  const statuses = [];
  await assert.rejects(buildSequence(chosen, {
    mode: 'fixture', observations: response.observations, signal: ticket.signal,
    onStatus: job => { statuses.push(job.status); owner.cancel(); },
  }), error => error.name === 'AbortError');
  assert.deepEqual(statuses, ['queued']);
  assert.equal(ticket.isCurrent(), false);
});
