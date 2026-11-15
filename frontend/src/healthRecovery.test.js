import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act} from 'react';
import {Window} from 'happy-dom';
import {useHealth} from './hooks/useHealth.js';

test('the workspace reconnects after a transient backend failure without reloading',async()=>{
  const win=new Window({url:'http://localhost:8010'});
  for(const key of ['window','document','HTMLElement','Event','Node']) globalThis[key]=key==='window'?win:win[key];
  globalThis.IS_REACT_ACT_ENVIRONMENT=true;
  const {createRoot}=await import('react-dom/client');
  const oldFetch=globalThis.fetch;let calls=0;
  globalThis.fetch=async()=>{
    calls++;
    if(calls===1)throw new Error('Temporary connection problem');
    return new Response(JSON.stringify({status:'ok',capabilities:{archive_access:'available',image_processing:'available',motion_verification:'available'}}));
  };
  document.body.innerHTML='<div id="root"></div>';
  const root=createRoot(document.getElementById('root'));
  function State(){const {health}=useHealth();return React.createElement('p',{id:'health'},health.status);}
  try {
    await act(async()=>root.render(React.createElement(State)));
    assert.equal(document.getElementById('health').textContent,'error');
    await act(async()=>window.dispatchEvent(new Event('online')));
    assert.equal(document.getElementById('health').textContent,'ready');
    assert.equal(calls,2);
    await act(async()=>window.dispatchEvent(new Event('focus')));
    assert.equal(calls,2);
  } finally {
    await act(async()=>root.unmount());globalThis.fetch=oldFetch;await win.close();
  }
});
