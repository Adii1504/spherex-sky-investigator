import test from 'node:test';
import assert from 'node:assert/strict';
import {defaultSelection,exposureConflict,request,pollJob} from './api.js';
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
