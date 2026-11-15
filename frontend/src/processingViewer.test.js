import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {Window} from 'happy-dom';

const html = await readFile(new URL('../../frontend_viewspace/index.html',import.meta.url),'utf8');
const script = await readFile(new URL('../../frontend_viewspace/app.js',import.meta.url),'utf8');
const result = (name='first') => ({preset_id:name,investigation_id:name,data_kind:'supplied FITS observations',
  frames:[{image_url:`/processing/previews/${name}.png`,observation_id:'epoch-1'}],differences:[],
  grid:{ra_deg:133,dec_deg:-7,fov_arcmin:3,size_px:128},outcome:'insufficient_evidence',
  measurements:[{epoch_id:'epoch-1',status:'ok',ra_deg:133,dec_deg:-7,snr:0}],predictions:[],hotspots:[],
  warnings:['Provisional association'],limitations:[],comparison:{status:'unknown'}});

function setup(fetcher) {
  const win = new Window({url:'http://localhost:8010/processing/',settings:{disableCSSFileLoading:true,disableJavaScriptFileLoading:true}});
  win.document.documentElement.innerHTML = html;
  const context = vm.createContext({document:win.document,window:win,location:win.location,
    fetch:fetcher,FormData:win.FormData,URL,URLSearchParams,Blob,AbortController,setTimeout,clearTimeout,setInterval,clearInterval});
  vm.runInContext(script,context);
  vm.runInContext("document.removeEventListener('DOMContentLoaded',initUI)",context);
  return {win,context,run:code=>vm.runInContext(code,context)};
}
const response = payload => ({ok:true,json:async()=>payload});

test('processing viewer shows live insufficient evidence, zero SNR, and unavailable residuals',async()=>{
  const calls=[];
  const page=setup(async path=>{
    calls.push(path);
    if(path.endsWith('/presets'))return response([{id:'first',title:'First target'}]);
    if(path.includes('/sed?'))return response({spectral_index:null});
    return response(result());
  });
  try {
    await page.run('initUI()');
    const doc=page.win.document;
    assert.equal(doc.getElementById('valOutcome').textContent,'Insufficient evidence');
    assert.equal(doc.getElementById('valSNR').textContent,'0.0');
    assert.equal(doc.getElementById('valVelocity').textContent,'Unavailable arcsec/hr');
    assert.match(doc.getElementById('tableMeasurements').textContent,/Unavailable/);
    assert.equal(doc.getElementById('primaryImage').getAttribute('src'),'/processing/previews/first.png');
    assert.ok(calls.some(path=>path.startsWith('/processing/api/sed?') && path.includes('preset_id=first')));
    assert.equal(doc.getElementById('pinOverlay').children.length,0);
  } finally {await page.win.close();}
});

test('API failures clear earlier images and never display preset success metrics',async()=>{
  let fail=false;
  const page=setup(async path=>{
    if(path.endsWith('/presets'))return response([{id:'first',title:'First target'}]);
    if(path.includes('/sed?'))return response({});
    if(fail)throw new Error('Backend offline');
    return response(result());
  });
  try {
    await page.run('initUI()');fail=true;
    await page.run("loadInvestigation('first')");
    const doc=page.win.document;
    assert.match(doc.getElementById('processingNotice').textContent,/Backend offline/);
    assert.equal(doc.getElementById('primaryImage').getAttribute('src'),null);
    assert.equal(doc.getElementById('valSNR').textContent,'Unavailable');
    assert.equal(doc.getElementById('valOutcome').textContent,'Awaiting evidence');
    assert.equal(doc.getElementById('btnExportJSON').disabled,true);
  } finally {await page.win.close();}
});

test('late preset results cannot overwrite the newer selected target',async()=>{
  let release;
  const page=setup(async(path,options)=>{
    if(path.endsWith('/presets'))return response([{id:'first',title:'First'},{id:'second',title:'Second'}]);
    if(path.includes('/sed?'))return response({});
    const id=options.body.get('preset_id');
    if(id==='slow')return await new Promise(resolve=>{release=()=>resolve(response(result('slow')));});
    return response(result(id));
  });
  try {
    await page.run('initUI()');
    const pending=page.run("loadInvestigation('slow')");
    await page.run("loadInvestigation('second')");
    release();await pending;
    assert.equal(page.win.document.getElementById('primaryImage').getAttribute('src'),'/processing/previews/second.png');
    assert.equal(page.win.document.getElementById('targetTitle').textContent,'Second');
  } finally {await page.win.close();}
});

test('evidence panel can be closed and reopened, and upload dialog restores keyboard focus',async()=>{
  const page=setup(async path=>path.endsWith('/presets')?response([{id:'first',title:'First'}]):path.includes('/sed?')?response({}):response(result()));
  try {
    await page.run('initUI()');
    const doc=page.win.document;
    doc.getElementById('btnCloseDrawer').click();
    assert.equal(doc.getElementById('btnOpenDrawer').getAttribute('aria-expanded'),'false');
    assert.ok(doc.getElementById('viewerMain').classList.contains('details-closed'));
    doc.getElementById('btnOpenDrawer').click();
    assert.equal(doc.getElementById('sideDrawer').classList.contains('closed'),false);
    doc.getElementById('btnUploadModal').focus();doc.getElementById('btnUploadModal').click();
    assert.equal(doc.activeElement.id,'fitsFileInput');
    assert.equal(doc.getElementById('viewerMain').inert,true);
    await page.run('handleCustomUpload()');
    assert.equal(doc.getElementById('uploadError').hidden,false);
    assert.match(doc.getElementById('uploadError').textContent,/Choose FITS files/);
    doc.dispatchEvent(new page.win.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
    assert.equal(doc.getElementById('uploadModal').classList.contains('open'),false);
    assert.equal(doc.activeElement.id,'btnUploadModal');
    assert.equal(doc.getElementById('viewerMain').inert,false);
  } finally {await page.win.close();}
});

test('re-measuring a selected candidate keeps its coordinates and selected dataset',async()=>{
  const calls=[];
  const page=setup(async path=>{
    calls.push(path);
    if(path.endsWith('/presets'))return response([{id:'first',title:'First'}]);
    if(path.includes('/sed?'))return response({});
    return response(result());
  });
  try {
    await page.run('initUI()');
    page.run("selectHotspot({id:'candidate',ra_deg:132.5,dec_deg:-6.5,snr:0})");
    page.win.document.getElementById('btnRefetchSED').click();
    const params=new URL('http://localhost'+calls.at(-1)).searchParams;
    assert.equal(params.get('ra_deg'),'132.5');
    assert.equal(params.get('dec_deg'),'-6.5');
    assert.equal(params.get('preset_id'),'first');
  } finally {await page.win.close();}
});

test('an unreadable server response gives an actionable error and a retry control',async()=>{
  const page=setup(async path=>path.endsWith('/presets')?response([{id:'first',title:'First'}]):{ok:false,json:async()=>{throw new Error('Invalid JSON');}});
  try {
    await page.run('initUI()');
    const doc=page.win.document;
    assert.match(doc.getElementById('processingNotice').textContent,/unreadable response/);
    assert.equal(doc.getElementById('btnRetryProcessing').hidden,false);
    assert.equal(doc.getElementById('apiStatus').dataset.state,'error');
  } finally {await page.win.close();}
});
