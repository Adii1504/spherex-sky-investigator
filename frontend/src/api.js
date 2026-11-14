export const API_BASE = (import.meta.env?.VITE_API_BASE || '').replace(/\/$/, '');
export async function request(path, body, signal) {
  const response = await fetch(API_BASE + '/api/v1' + path, {method: body === undefined ? 'GET' : 'POST', headers:body === undefined ? {} : {'Content-Type':'application/json'}, body: body === undefined ? undefined : JSON.stringify(body), signal});
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.message || 'Request failed');
    error.code = data.code; error.details = data.details; throw error;
  }
  return data;
}
export async function pollJob(id, onStatus, signal) {
  for (let i=0; i<900; i++) {
    if(signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    const job = await request('/jobs/' + encodeURIComponent(id), undefined, signal);
    onStatus(job);
    if(job.status === 'succeeded') return job.result;
    if(job.status === 'failed') { const error = new Error(job.error?.message || 'Job failed'); error.code=job.error?.code; throw error; }
    await new Promise((resolve,reject)=>{
      const abort=()=>{clearTimeout(timer); reject(new DOMException('Aborted','AbortError'));};
      const timer=setTimeout(()=>{signal?.removeEventListener('abort',abort);resolve();},1000);
      signal?.addEventListener('abort',abort,{once:true});
    });
  }
  throw new Error('Polling stopped after 15 minutes. The server job may still be running.');
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
