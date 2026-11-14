import { ApiError, exposureConflict, pollJob, request } from './api.js';
import { createFixtureSequence, getFixtureJob } from './fixtures/developmentData.js';

export const MAX_OBSERVATIONS = 100;

export function selectionSummary(observations, ids) {
  const chosen = observations.filter(item => ids.includes(item.id));
  const dates = chosen.filter(item => item.observed_at != null && item.observed_at !== '').map(item => new Date(item.observed_at).getTime()).filter(Number.isFinite);
  return { count: chosen.length, earliest: dates.length ? new Date(Math.min(...dates)).toISOString() : null, latest: dates.length ? new Date(Math.max(...dates)).toISOString() : null };
}

export function makeSelection(search, query, ids) {
  if (!search?.search_id || !query || !ids.length || ids.length > MAX_OBSERVATIONS
      || new Set(ids).size !== ids.length || ids.some(id => !search.observations.some(item => item.id === id))) {
    throw new ApiError('Choose unique observations from the active search (up to 100).', { code: 'invalid_selection' });
  }
  return { search_id: search.search_id, observation_ids: [...ids], ra_deg: query.ra_deg, dec_deg: query.dec_deg, fov_arcmin: query.fov_arcmin };
}

export function verificationIssues(observations, groups) {
  const training = observations.filter(item => groups[item.id] === 'training');
  const reserved = observations.filter(item => groups[item.id] === 'reserved');
  const issues = [];
  if (training.length < 3) issues.push('Choose at least three training exposures.');
  if (!reserved.length) issues.push('Reserve at least one independent exposure.');
  if (exposureConflict(observations, groups)) issues.push('Training and reserved groups must use unique canonical exposure IDs, including within each group.');
  return issues;
}

export function missingPreviewIds(sequence) {
  const present = new Set(sequence.previews.map(item => item.observation.id));
  return sequence.observation_ids.filter(id => !present.has(id));
}

function validateSequence(result, selection) {
  const ids = Array.isArray(result?.previews) ? result.previews.map(item => item?.observation?.id) : null;
  if (result?.search_id !== selection.search_id || !Array.isArray(ids) || !ids.length
    || new Set(ids).size !== ids.length || ids.some(id => !selection.observation_ids.includes(id))
    || !Array.isArray(result.observation_ids) || new Set(result.observation_ids).size !== selection.observation_ids.length || result.observation_ids.length !== selection.observation_ids.length
    || result.observation_ids.some(id => !selection.observation_ids.includes(id))
    || result.previews.some(item => typeof item.preview_url !== 'string') || !Array.isArray(result.warnings)) {
    throw new ApiError('The backend returned an invalid preview sequence. Rebuild the sequence.', { code: 'invalid_response' });
  }
  return result;
}

export async function buildSequence(selection, { mode = 'live', scenario = 'success', observations = [], signal, onStatus = () => {} } = {}) {
  const fixture = mode === 'fixture';
  const queued = fixture ? createFixtureSequence(selection, scenario, observations) : await request('/sequences', selection, signal);
  if (!queued?.job_id) throw new ApiError('Missing sequence job ID.', { code: 'invalid_response' });
  const result = await pollJob(queued.job_id, onStatus, signal, fixture ? { intervalMs: 350, loadJob: getFixtureJob } : {});
  return { jobId: queued.job_id, selection, ...validateSequence(result, selection) };
}

export async function saveInvestigation(selection, sequenceJobId, signal) {
  const result = await request('/investigations', { ...selection, sequence_job_id: sequenceJobId }, signal);
  if (!result?.investigation_id) throw new ApiError('Missing investigation ID.', { code: 'invalid_response' });
  return result.investigation_id;
}

export async function verifyInvestigation(id, observations, groups, signal, onStatus) {
  const issues = verificationIssues(observations, groups);
  if (issues.length) throw new ApiError(issues.join(' '), { code: 'invalid_selection' });
  const body = { training_observation_ids: [], reserved_observation_ids: [] };
  for (const item of observations) {
    if (groups[item.id] === 'training') body.training_observation_ids.push(item.id);
    if (groups[item.id] === 'reserved') body.reserved_observation_ids.push(item.id);
  }
  const queued = await request(`/investigations/${encodeURIComponent(id)}/verify`, body, signal);
  if (!queued?.job_id) throw new ApiError('Missing verification job ID.', { code: 'invalid_response' });
  const result = await pollJob(queued.job_id, onStatus, signal);
  if (!['supported', 'not_supported', 'insufficient_evidence'].includes(result?.outcome)) throw new ApiError('Unexpected verification outcome.', { code: 'invalid_response' });
  return result;
}

export async function getEvidence(id, signal) {
  return request(`/investigations/${encodeURIComponent(id)}/evidence`, undefined, signal);
}

// One request generation owns all asynchronous writes; cancelled work cannot publish.
export function createRequestOwner() {
  let generation = 0;
  let controller;
  return {
    cancel() { generation++; controller?.abort(); controller = undefined; },
    start() {
      this.cancel();
      controller = new AbortController();
      const current = generation;
      const signal = controller.signal;
      return { signal, isCurrent: () => current === generation && !signal.aborted };
    },
  };
}
