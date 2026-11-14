export const API_BASE = (import.meta.env?.VITE_API_BASE || '').replace(/\/+$/, '');
export const POLL_INTERVAL_MS = 1000;

export class ApiError extends Error {
  constructor(message, { code, details, status } = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.details = details;
    this.status = status;
  }
}

// All live API traffic goes through this function. A failed request stays failed.
export async function request(path, body, signal, { timeoutMs = 90_000 } = {}) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  else signal?.addEventListener('abort', abort, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    if (controller.signal.aborted) throw new DOMException('Aborted', 'AbortError');
    const response = await fetch(API_BASE + '/api/v1' + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    let data;
    try {
      data = await response.json();
    } catch (error) {
      if (controller.signal.aborted) throw error;
      // A proxy can return HTML or an empty body when the backend is offline.
      if (response.ok) {
        throw new ApiError('The service returned an unreadable response. Please retry.', {
          code: 'invalid_response', status: response.status,
        });
      }
    }
    if (!response.ok) {
      throw new ApiError(data?.message || `The service request failed (HTTP ${response.status}). Please retry.`, {
        code: data?.code || 'http_error', details: data?.details, status: response.status,
      });
    }
    if (controller.signal.aborted) throw new DOMException('Aborted', 'AbortError');
    return data;
  } catch (error) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    if (timedOut) {
      throw new ApiError('The service took too long to respond. Please retry.', { code: 'request_timeout' });
    }
    if (error instanceof ApiError) throw error;
    throw new ApiError('Could not connect to the backend. Check that it is running, then retry.', { code: 'network_error' });
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}
export async function pollJob(id, onStatus, signal, { intervalMs = POLL_INTERVAL_MS, loadJob } = {}) {
  for (let i=0; i<900; i++) {
    if(signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    const job = await (loadJob ? loadJob(id, signal) : request('/jobs/' + encodeURIComponent(id), undefined, signal));
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    if (!['queued', 'running', 'succeeded', 'failed'].includes(job?.status)) throw new ApiError('Unexpected job status.', { code: 'invalid_response' });
    onStatus(job);
    if(job.status === 'succeeded') return job.result;
    if(job.status === 'failed') throw new ApiError(job.error?.message || 'Job failed', job.error || {});
    await new Promise((resolve,reject)=>{
      const abort=()=>{clearTimeout(timer); reject(new DOMException('Aborted','AbortError'));};
      const timer=setTimeout(()=>{signal?.removeEventListener('abort',abort);resolve();},intervalMs);
      signal?.addEventListener('abort',abort,{once:true});
      if(signal?.aborted) abort();
    });
  }
  throw new Error('Polling stopped after 15 minutes. The server job may still be running.');
}

export function resolvePreviewUrl(path, fixture = false) {
  if (typeof path !== 'string' || !path) return '';
  // Fixtures belong to this frontend. Scientific previews belong to the API origin.
  if (fixture) return path.startsWith('/fixtures/') ? (import.meta.env?.BASE_URL || '/') + path.slice(1) : '';
  try {
    if (/^https?:\/\//i.test(path)) return new URL(path).href;
    if (!path.startsWith('/api/v1/previews/')) return '';
    return API_BASE ? new URL(path, API_BASE + '/').href : path;
  } catch { return ''; }
}
export function defaultSelection(observations) {
  const detector=observations[0]?.detector;
  const seen=new Set();
  return observations.filter(o=>{ if(o.detector!==detector || seen.has(o.exposure_id)) return false;seen.add(o.exposure_id);return true; }).slice(0,6).map(o=>o.id);
}
export function exposureConflict(observations, groups) {
  const seen=new Set();
  for(const o of observations.filter(o=>groups[o.id] && groups[o.id]!=='exclude')) {
    if(seen.has(o.exposure_id)) return true;
    seen.add(o.exposure_id);
  }
  return false;
}
