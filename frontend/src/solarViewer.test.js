import test from 'node:test';
import assert from 'node:assert/strict';
import {Window} from 'happy-dom';
import React,{act} from 'react';
import SolarSystem3D from './components/SolarSystem3D.jsx';

test('closing 3D restores page position, body styles and focus without scrolling the target into view',async()=>{
  const window=new Window({url:'http://localhost:8010'});
  for(const key of ['window','document','HTMLElement','Node'])globalThis[key]=key==='window'?window:window[key];
  globalThis.IS_REACT_ACT_ENVIRONMENT=true;
  const {createRoot}=await import('react-dom/client');
  document.body.innerHTML='<button id="open">View in 3D</button><div id="root"></div>';
  document.body.style.paddingRight='7px';document.body.style.overflow='auto';
  const opener=document.getElementById('open');opener.focus();
  const focusCalls=[],scrollCalls=[];
  opener.focus=options=>focusCalls.push(options);
  Object.defineProperty(window,'scrollY',{value:560,configurable:true});
  Object.defineProperty(window,'scrollX',{value:0,configurable:true});
  window.scrollTo=(...position)=>scrollCalls.push(position);
  globalThis.fetch=async()=>new Response(JSON.stringify({message:'Unavailable in test'}),{status:503});
  const root=createRoot(document.getElementById('root'));
  try{
    await act(async()=>root.render(React.createElement(SolarSystem3D,{selectedId:'earth',onClose(){},onSelect(){}})));
    assert.ok(document.querySelector('[role=dialog]'));
    assert.equal(document.body.style.overflow,'hidden');
    await act(async()=>root.unmount());
    assert.equal(document.body.style.overflow,'auto');assert.equal(document.body.style.paddingRight,'7px');
    assert.deepEqual(focusCalls,[{preventScroll:true}]);assert.deepEqual(scrollCalls,[[0,560]]);
  }finally{await act(async()=>root.unmount());}
});
