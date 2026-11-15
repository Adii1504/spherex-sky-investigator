import { ApiError, request } from './api.js';
import { fixtureSearch } from './fixtures/developmentData.js';

// Must match WHYLAB_MAX_FOV_ARCMIN in deployment; health does not expose it.
export const MAX_FOV_ARCMIN = 30;
export const INITIAL_INPUTS = { ra_deg: '', dec_deg: '', fov_arcmin: '2' };

export function validateSearch(inputs) {
  const errors = {};
  const query = {};
  for (const [key, label] of [['ra_deg', 'Right ascension'], ['dec_deg', 'Declination'], ['fov_arcmin', 'Field of view']]) {
    const value = String(inputs[key] ?? '').trim();
    if (!value) errors[key] = `${label} is required.`;
    else if (!Number.isFinite(Number(value))) errors[key] = `${label} must be a finite number.`;
    else query[key] = Number(value);
  }
  if ('ra_deg' in query && (query.ra_deg < 0 || query.ra_deg >= 360)) errors.ra_deg = 'Enter a value from 0 up to, but not including, 360 degrees.';
  if ('dec_deg' in query && (query.dec_deg < -90 || query.dec_deg > 90)) errors.dec_deg = 'Enter a value between −90 and 90 degrees.';
  if ('fov_arcmin' in query && (query.fov_arcmin <= 0 || query.fov_arcmin > MAX_FOV_ARCMIN)) errors.fov_arcmin = `Enter a value greater than 0 and no more than ${MAX_FOV_ARCMIN} arcminutes.`;
  return { errors, query: Object.keys(errors).length ? null : query };
}

export async function getHealth(signal) {
  const health = await request('/health', undefined, signal, { timeoutMs: 8000 });
  const keys = ['archive_access', 'image_processing', 'motion_verification'];
  if (health?.status !== 'ok' || keys.some(key => !['available', 'unavailable'].includes(health.capabilities?.[key]))) {
    throw new ApiError('The backend returned an unexpected capability response.', { code: 'invalid_response' });
  }
  return health;
}

export async function searchObservations(query, { mode = 'live', targetId, scenario = 'success', signal } = {}) {
  const route = mode === 'local' && targetId ? `/observations/search/target/${encodeURIComponent(targetId)}`
    : mode === 'local' ? '/observations/search/local' : '/observations/search';
  const result = mode === 'fixture' ? await fixtureSearch(scenario, signal) : await request(route, query, signal);
  if (typeof result?.search_id !== 'string' || !Array.isArray(result.observations)
    || !result.coverage_summary || typeof result.coverage_summary !== 'object'
    || Array.isArray(result.coverage_summary) || !Array.isArray(result.warnings)) {
    throw new ApiError('The service returned an unexpected search response. Please retry.', { code: 'invalid_response' });
  }
  return result;
}

export async function syncObservations(searchId, signal) {
  const result = await request(`/observations/search/${encodeURIComponent(searchId)}/sync`, {}, signal);
  if (result?.search_id !== searchId || !Array.isArray(result.observations) || !Array.isArray(result.warnings)
      || result.coverage_summary?.source !== 'local-and-archive') {
    throw new ApiError('Archive sync returned an invalid response. Local observations remain available.', {code:'invalid_response'});
  }
  return result;
}

export function formatUtc(value) {
  if (value == null || value === '') return 'Unavailable';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Unavailable' : date.toISOString().replace('T', ' ').replace('.000Z', ' UTC');
}

export function formatWavelength(value) {
  return value == null ? 'Unavailable' : `${value} µm`;
}

export function safeProvenanceUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null;
  } catch {
    return null;
  }
}
