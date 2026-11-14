import test, { afterEach } from 'node:test';
import assert from 'node:assert/strict';
import {defaultSelection,exposureConflict,request,pollJob,resolvePreviewUrl} from './api.js';
const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });
test('initial selection uses one detector and no repeated exposure',()=>{
 const observations=[{id:'a',exposure_id:'one',detector:'1'},{id:'b',exposure_id:'one',detector:'1'},{id:'c',exposure_id:'two',detector:'2'},{id:'d',exposure_id:'three',detector:'1'}];
 assert.deepEqual(defaultSelection(observations),['a','d']);
 assert.equal(exposureConflict(observations,{a:'training',b:'reserved'}),true);
 assert.equal(exposureConflict(observations,{a:'training',b:'exclude',d:'reserved'}),false);
});
test('structured API errors retain code and details',async()=>{
 globalThis.fetch=async()=>({ok:false,json:async()=>({code:'capability_unavailable',message:'Adapter unavailable',details:{capability:'archive_access'}})});
 await assert.rejects(request('/observations/search',{}),e=>e.code==='capability_unavailable' && e.details.capability==='archive_access');
});
test('failed jobs terminate polling with structured failure',async()=>{
 globalThis.fetch=async()=>({ok:true,json:async()=>({status:'failed',error:{code:'job_timeout',message:'Deadline exceeded'}})});
 await assert.rejects(pollJob('test',()=>{}),e=>e.code==='job_timeout');
});
test('aborted polling does not fetch',async()=>{
 const controller=new AbortController();controller.abort();
 globalThis.fetch=async()=>assert.fail('Aborted operation should not fetch');
 await assert.rejects(pollJob('test',()=>{},controller.signal),e=>e.name==='AbortError');
});

test('search sends numeric JSON to the actual API path', async () => {
 const query = {ra_deg: 12, dec_deg: -5, fov_arcmin: 2};
 globalThis.fetch = async (url, options) => {
  assert.equal(url, '/api/v1/observations/search');
  assert.equal(options.method, 'POST');
  assert.equal(options.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(options.body), query);
  assert.ok(options.signal instanceof AbortSignal);
  return new Response(JSON.stringify({search_id: 'test_search'}), {status: 200});
 };
 assert.deepEqual(await request('/observations/search', query), {search_id: 'test_search'});
});

test('health uses GET without a request body', async () => {
 globalThis.fetch = async (url, options) => {
  assert.equal(url, '/api/v1/health');
  assert.equal(options.method, 'GET');
  assert.equal(options.body, undefined);
  return new Response('{"status":"ok"}');
 };
 assert.equal((await request('/health')).status, 'ok');
});

for (const status of [404, 422, 502, 503, 504]) {
 test(`flat HTTP ${status} errors retain server message, status and details`, async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({code: 'test_error', message: 'Test backend error', details: [{field: ['body', 'ra_deg'], message: 'Test correction'}]}), {status});
  await assert.rejects(request('/observations/search', {}), error => error.message === 'Test backend error'
   && error.code === 'test_error' && error.status === status && error.details[0].field[1] === 'ra_deg');
 });
}

test('non-JSON proxy errors produce a readable HTTP error', async () => {
 globalThis.fetch = async () => new Response('<h1>Bad gateway</h1>', {status: 502});
 await assert.rejects(request('/health'), error => error.code === 'http_error' && error.status === 502 && error.message.includes('502'));
});

test('successful non-JSON responses are rejected', async () => {
 globalThis.fetch = async () => new Response('<html>wrong server</html>');
 await assert.rejects(request('/health'), error => error.code === 'invalid_response');
});

test('network failures give a recoverable connection message', async () => {
 globalThis.fetch = async () => { throw new TypeError('fetch failed'); };
 await assert.rejects(request('/health'), error => error.code === 'network_error' && error.message.includes('backend'));
});

test('aborted requests do not fetch', async () => {
 const controller = new AbortController(); controller.abort();
 globalThis.fetch = async () => assert.fail('Must not fetch');
 await assert.rejects(request('/health', undefined, controller.signal), error => error.name === 'AbortError');
});

test('late responses from a fetch that ignores abort are discarded', async () => {
 const controller = new AbortController();
 let finish;
 globalThis.fetch = () => new Promise(resolve => { finish = resolve; });
 const pending = request('/health', undefined, controller.signal);
 controller.abort();
 finish(new Response('{"status":"ok"}'));
 await assert.rejects(pending, error => error.name === 'AbortError');
});

test('request timeouts abort fetch and end loading with a specific error', async () => {
 let aborted = false;
 globalThis.fetch = (url, {signal}) => new Promise((resolve, reject) => {
  signal.addEventListener('abort', () => { aborted = true; reject(new DOMException('Aborted', 'AbortError')); }, {once: true});
 });
 await assert.rejects(request('/health', undefined, undefined, {timeoutMs: 5}), error => error.code === 'request_timeout');
 assert.equal(aborted, true);
});

test('succeeded jobs return their actual preview result', async () => {
 const result = {previews: [], warnings: ['Test-only warning']};
 globalThis.fetch = async () => new Response(JSON.stringify({status: 'succeeded', progress: null, result}));
 const statuses = [];
 assert.deepEqual(await pollJob('test_job', value => statuses.push(value.status)), result);
 assert.deepEqual(statuses, ['succeeded']);
});

test('relative previews use the API proxy while fixtures remain on the frontend', () => {
 assert.equal(resolvePreviewUrl('/api/v1/previews/test'), '/api/v1/previews/test');
 assert.equal(resolvePreviewUrl('https://example.org/api/v1/previews/test'), 'https://example.org/api/v1/previews/test');
 assert.equal(resolvePreviewUrl('/fixtures/demo-frame-1.png', true), '/fixtures/demo-frame-1.png');
 for (const url of ['javascript:alert(1)', '//elsewhere.test/image', '/private/file', null]) assert.equal(resolvePreviewUrl(url), '');
 assert.equal(resolvePreviewUrl('/api/v1/previews/test', true), '');
});

test('polling visits queued/running then completes without inventing progress', async () => {
 const states = ['queued', 'running', 'succeeded'];
 const visited = [];
 const result = {previews: []};
 await pollJob('test', job => { visited.push(job.status); assert.equal(job.progress, null); }, undefined, {
  intervalMs: 0, loadJob: async () => ({status: states.shift(), progress: null, result}),
 });
 assert.deepEqual(visited, ['queued', 'running', 'succeeded']);
});
