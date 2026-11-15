/* Viewer layout from commit 9c2e3bb, connected to live scientific API results. */
const API_ROOT = location.pathname.startsWith('/processing') ? '/processing' : '';
const byId = id => document.getElementById(id);
const finite = value => typeof value === 'number' && Number.isFinite(value);
const format = (value, digits = 2) => finite(value) ? value.toFixed(digits) : 'Unavailable';
let presets = [], currentInvestigation = null, currentMode = 'composite';
let blinkInterval = null, currentBlinkIndex = 0, currentTourIndex = 0, zoomLevel = 1;
let requestVersion = 0, controller = null, sedVersion = 0, pinsVisible = true;
let lastRequest = null, selectedCoordinate = null, focusBeforeModal = null;

function status(message, state) {
  byId('apiStatus').textContent = message;
  byId('apiStatus').dataset.state = state;
}

function showDrawer(open) {
  byId('sideDrawer').classList.toggle('closed', !open);
  byId('viewerMain').classList.toggle('details-closed', !open);
  byId('btnOpenDrawer').setAttribute('aria-expanded', String(open));
}

function modal(open) {
  byId('uploadModal').classList.toggle('open', open);
  byId('viewerMain').inert = open;
  if (open) {
    focusBeforeModal = document.activeElement;
    byId('uploadError').hidden = true;
    byId('fitsFileInput').focus();
  } else if (focusBeforeModal?.isConnected) focusBeforeModal.focus();
}

function stageMessage(message) {
  byId('stageMessage').textContent = message;
  byId('stageMessage').hidden = !message;
}

async function api(path, options = {}) {
  const response = await fetch(API_ROOT + path, options);
  let payload;
  try { payload = await response.json(); }
  catch { throw new Error('The server returned an unreadable response. Check the connection and retry.'); }
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : `Request failed (${response.status})`);
  return payload;
}

function image(id, url) {
  const element = byId(id);
  element.hidden = !url;
  if (url) element.src = url;
  else element.removeAttribute('src');
}

function stopBlinkLoop() {
  if (blinkInterval) clearInterval(blinkInterval);
  blinkInterval = null;
}

function clearResult(message) {
  stopBlinkLoop(); currentInvestigation = null; selectedCoordinate = null; sedVersion++;
  for (const id of ['primaryImage', 'trajectoryPlot', 'dipolePlot', 'sedPlot']) image(id, null);
  for (const id of ['valCoords','valVelocity','valSNR','valSpectralIndex','truthResidual','valLocationText','valDistanceText','valImageSizeText','valObservatoriesText']) byId(id).textContent = 'Unavailable';
  byId('pinOverlay').replaceChildren(); byId('tableMeasurements').replaceChildren();
  byId('gaiaTruthSection').hidden = true;
  byId('valOutcome').className = 'badge-outcome';
  byId('valOutcome').textContent = 'Awaiting evidence';
  byId('processingNotice').textContent = message;
  byId('btnExportJSON').disabled = true;
  byId('bottomControls').style.display = 'none';
  byId('frameMetadata').textContent = '';
  byId('scientificNotes').hidden = true;
  byId('warningList').replaceChildren();
  byId('btnRetryProcessing').hidden = true;
  stageMessage(message);
}

function showError(error) {
  clearResult(`Processing failed: ${error.message}. Choose a dataset and retry.`);
  status('Processing unavailable', 'error');
  byId('processingNotice').setAttribute('role', 'alert');
  byId('btnRetryProcessing').hidden = false;
}

async function loadInvestigation(presetId, upload = null) {
  lastRequest = {presetId, upload};
  const ticket = ++requestVersion;
  controller?.abort(); controller = new AbortController();
  const signal = controller.signal;
  clearResult('Processing FITS science arrays…');
  byId('processingNotice').setAttribute('role', 'status');
  status('Processing…', 'loading');
  byId('btnCancelProcessing').hidden = false;
  byId('btnRunInvestigation').disabled = true;
  const preset = presets.find(p => p.id === presetId);
  byId('targetTitle').textContent = preset?.title || 'Uploaded FITS investigation';
  byId('targetDescription').textContent = 'Results and limitations will appear after processing.';
  byId('targetSubtitle').textContent = preset?.category || 'User-supplied FITS';
  currentTourIndex = Math.max(0, presets.findIndex(p => p.id === presetId));
  if (presetId) {
    byId('presetSelect').value = presetId; byId('tourStopSelect').value = presetId;
    byId('drawerPageIndicator').textContent = `${currentTourIndex + 1} / ${presets.length}`;
  }
  const requestController = controller;
  const timer = setTimeout(() => requestController.abort(), 90000);
  try {
    const form = upload || new FormData();
    if (!upload) form.append('preset_id', presetId);
    const result = await api('/api/investigate', {method:'POST',body:form,signal});
    if (ticket !== requestVersion) return;
    if (!result.frames?.length) throw new Error('No valid FITS frames were produced');
    result.preset_id = presetId;
    if (presetId === 'nasa_real_6bands') {
      const composite = await api('/api/composite', {method:'POST',body:new FormData(),signal});
      result.composite_url = composite.composite_url;
      result.warnings.push(...(composite.warnings || []));
    }
    if (ticket !== requestVersion) return;
    currentInvestigation = result; currentBlinkIndex = 0;
    renderInvestigation(result);
  } catch (error) {
    if (ticket === requestVersion) showError(error.name === 'AbortError' ? new Error('Request cancelled or timed out') : error);
  } finally {
    clearTimeout(timer);
    if (ticket === requestVersion) {
      byId('btnRunInvestigation').disabled = false;
      byId('btnCancelProcessing').hidden = true;
    }
  }
}

function badge(outcome) {
  const element = byId('valOutcome');
  element.className = 'badge-outcome';
  element.textContent = ({motion_supported:'Motion model supported (exploratory)',
    stationary_plausible:'Stationary model plausible',insufficient_evidence:'Insufficient evidence'})[outcome] || 'Unavailable';
}

function renderInvestigation(inv) {
  showDrawer(true);
  status('Processing complete', 'ready');
  byId('targetSubtitle').textContent = inv.data_kind || 'Supplied FITS observations';
  byId('processingNotice').textContent = `${inv.frames.length} observations aligned. Wavelength comparison: ${inv.comparison?.status || 'unknown'}. Results are exploratory.`;
  const notes = [...new Set([...(inv.warnings || []),...(inv.limitations || [])])];
  byId('scientificNotes').hidden = !notes.length;
  byId('warningSummary').textContent = `Assumptions and processing notes (${notes.length})`;
  byId('warningList').replaceChildren();
  for (const note of notes) {
    const item = document.createElement('li'); item.textContent = note; byId('warningList').append(item);
  }
  byId('targetDescription').textContent = 'Images are aligned on a common celestial grid. Differences and centroid tracks are exploratory evidence; source identity is unconfirmed.';
  byId('valLocationText').textContent = inv.grid ? `ICRS RA ${format(inv.grid.ra_deg,5)}°, Dec ${format(inv.grid.dec_deg,5)}°` : 'Unavailable';
  byId('valDistanceText').textContent = 'Unavailable';
  byId('valImageSizeText').textContent = inv.grid ? `${inv.grid.fov_arcmin} arcminutes; ${inv.grid.size_px} pixels across` : 'Unavailable';
  byId('valObservatoriesText').textContent = inv.data_kind === 'synthetic demonstration' ? 'Synthetic demonstration' : 'Supplied SPHEREx FITS dataset';
  const measurement = inv.measurements?.find(m => m.status === 'ok');
  byId('valCoords').textContent = measurement ? `${format(measurement.ra_deg,5)}°, ${format(measurement.dec_deg,5)}°` : 'Unavailable';
  byId('valVelocity').textContent = `${format(inv.model_comparison?.fitted_speed_arcsec_per_hour,5)} arcsec/hr`;
  byId('valSNR').textContent = format(measurement?.snr,1);
  badge(inv.outcome);
  const truth = inv.gaia_ground_truth;
  byId('gaiaTruthSection').hidden = !truth;
  if (truth) {
    byId('truthSourceId').textContent = `${truth.source_catalogue} ${truth.source_id}`;
    byId('truthRefEpoch').textContent = truth.ref_epoch ?? 'Unavailable';
    byId('truthPM').textContent = `${format(truth.total_proper_motion_arcsec_yr,3)} arcsec/yr (catalogue)`;
    byId('truthResidual').textContent = 'Not independently measured against catalogue';
    byId('truthQuality').textContent = truth.quality_flag || 'Unavailable';
  }
  image('trajectoryPlot', inv.diagnostic_trajectory_url);
  image('dipolePlot', inv.differences?.[0]?.image_url);
  const select = byId('diffPairSelect'); select.replaceChildren();
  (inv.differences || []).forEach((difference,index) => {
    const option = document.createElement('option'); option.value = String(index);
    option.textContent = `${difference.a_observation_id} → ${difference.b_observation_id}`;
    select.append(option);
  });
  byId('tableMeasurements').replaceChildren();
  (inv.measurements || []).forEach((m,index) => {
    const row = document.createElement('tr');
    const prediction = inv.predictions?.find(p => p.epoch_id === m.epoch_id);
    for (const value of [index+1,m.observed_at_utc || 'Unavailable',format(m.ra_deg,5),format(m.dec_deg,5),format(prediction?.residual_arcsec)]) {
      const cell = document.createElement('td'); cell.textContent = String(value); row.append(cell);
    }
    byId('tableMeasurements').append(row);
  });
  renderHotspotPins(inv.hotspots || []);
  byId('btnExportJSON').disabled = false;
  updateStageView();
  const coord = measurement || inv.grid;
  selectedCoordinate = coord;
  if (coord && inv.preset_id) fetchSED(coord.ra_deg,coord.dec_deg);
}

function updateStageView() {
  stopBlinkLoop();
  const inv = currentInvestigation;
  byId('bottomControls').style.display = ['blink','difference'].includes(currentMode) && inv ? 'flex' : 'none';
  byId('blinkControls').style.display = currentMode === 'blink' ? 'flex' : 'none';
  byId('diffControls').style.display = currentMode === 'difference' ? 'flex' : 'none';
  byId('pinOverlay').style.display = currentMode === 'composite' && pinsVisible && !inv?.composite_url ? 'block' : 'none';
  if (!inv) return;
  let url = null;
  if (currentMode === 'composite') url = inv.composite_url || inv.frames[0]?.image_url;
  if (currentMode === 'difference') url = inv.differences?.[Number(byId('diffPairSelect').value)]?.image_url;
  if (currentMode === 'diagnostic') url = inv.diagnostic_trajectory_url;
  if (currentMode !== 'blink') {
    image('primaryImage',url);
    stageMessage(url ? '' : 'This view is unavailable for the current observations. Choose another view.');
    byId('frameMetadata').textContent = currentMode === 'composite' && !inv.composite_url
      ? `Observation 1 / ${inv.frames.length} · ${inv.frames[0]?.observed_at || 'Time unavailable'} · Detector ${inv.frames[0]?.detector ?? 'unavailable'}`
      : currentMode === 'difference' ? 'Signed intensity difference; morphology and wavelength effects require review.' : currentMode === 'diagnostic' ? 'Exploratory trajectory model and residuals.' : 'Three bands aligned to a common sky grid.';
  }
  if (currentMode === 'blink') { displayBlinkFrame(currentBlinkIndex); startBlinkLoop(); }
}

function renderHotspotPins(hotspots) {
  const svg = byId('pinOverlay'), size = currentInvestigation?.grid?.size_px || 128;
  svg.replaceChildren(); svg.setAttribute('viewBox',`0 0 ${size} ${size}`);
  for (const source of hotspots) {
    if (!finite(source.x_px) || !finite(source.y_px)) continue;
    const pin = document.createElementNS('http://www.w3.org/2000/svg','circle');
    pin.setAttribute('cx',source.x_px); pin.setAttribute('cy',size-1-source.y_px);
    pin.setAttribute('r','2'); pin.setAttribute('class','pin-ring hotspot-pin');
    pin.addEventListener('click',() => selectHotspot(source)); svg.append(pin);
  }
}

function selectHotspot(source) {
  showDrawer(true);
  selectedCoordinate = source;
  byId('targetTitle').textContent = `Candidate ${source.id || ''}`;
  byId('targetSubtitle').textContent = `${source.classification || 'Unclassified'} · source identity unconfirmed`;
  byId('valCoords').textContent = `${format(source.ra_deg,5)}°, ${format(source.dec_deg,5)}°`;
  byId('valVelocity').textContent = `${format(source.speed_arcsec_per_hour,5)} arcsec/hr`;
  byId('valSNR').textContent = format(source.snr,1);
  badge(currentInvestigation?.comparison?.status === 'compatible' ? source.verification?.outcome : 'insufficient_evidence');
  fetchSED(source.ra_deg,source.dec_deg);
}

async function fetchSED(ra,dec) {
  const ticket = ++sedVersion, inv = currentInvestigation;
  image('sedPlot',null); byId('valSpectralIndex').textContent = 'Unavailable';
  if (!inv?.preset_id || !finite(ra) || !finite(dec)) return;
  try {
    const params = new URLSearchParams({ra_deg:ra,dec_deg:dec,preset_id:inv.preset_id});
    const result = await api('/api/sed?'+params);
    if (ticket !== sedVersion || inv !== currentInvestigation) return;
    image('sedPlot',result.sed_plot_url);
    byId('valSpectralIndex').textContent = format(result.spectral_index);
  } catch (error) {
    if (ticket === sedVersion) byId('valSpectralIndex').textContent = 'SED unavailable';
  }
}

function displayBlinkFrame(index) {
  const frame = currentInvestigation?.frames?.[index];
  if (frame) {
    image('primaryImage',frame.image_url); stageMessage('');
    byId('epochLabel').textContent = `Epoch ${index+1} / ${currentInvestigation.frames.length}`;
    byId('frameMetadata').textContent = `${frame.observed_at || 'Time unavailable'} · Detector ${frame.detector ?? 'unavailable'}`;
  }
}
function startBlinkLoop() {
  stopBlinkLoop();
  if (!currentInvestigation?.frames?.length) return;
  blinkInterval = setInterval(() => { currentBlinkIndex = (currentBlinkIndex+1)%currentInvestigation.frames.length; displayBlinkFrame(currentBlinkIndex); },1000/Number(byId('blinkSpeed').value));
  byId('btnPlayPause').textContent = 'Pause';
}
function stepEpoch(delta) {
  stopBlinkLoop(); if (!currentInvestigation?.frames?.length) return;
  currentBlinkIndex = (currentBlinkIndex+delta+currentInvestigation.frames.length)%currentInvestigation.frames.length;
  displayBlinkFrame(currentBlinkIndex); byId('btnPlayPause').textContent = 'Play';
}
function stepTourStop(delta) {
  if (presets.length) loadInvestigation(presets[(currentTourIndex+delta+presets.length)%presets.length].id);
}

async function handleCustomUpload() {
  const files = byId('fitsFileInput').files;
  const reject = message => {byId('uploadError').textContent = message; byId('uploadError').hidden = false;};
  if (!files?.length) { reject('Choose FITS files before processing.'); return; }
  if (files.length > 12 || [...files].some(file => file.size > 50_000_000)
      || [...files].reduce((sum,file) => sum+file.size,0) > 100_000_000) {
    reject('Choose up to 12 FITS files, at most 50 MB each and 100 MB combined.'); return;
  }
  const form = new FormData(); for (const file of files) form.append('files',file);
  const ra = byId('inputTargetRA').value, dec = byId('inputTargetDec').value;
  if (Boolean(ra) !== Boolean(dec)) { reject('Provide both RA and Dec, or leave both empty.'); return; }
  if (ra && (!finite(Number(ra)) || !finite(Number(dec)) || Number(ra)<0 || Number(ra)>=360 || Number(dec)<-90 || Number(dec)>90)) {
    reject('RA must be from 0 to below 360 degrees; Dec must be from -90 to 90.'); return;
  }
  if (ra) { form.append('target_ra',ra); form.append('target_dec',dec); }
  modal(false);
  await loadInvestigation(null,form);
}

async function initUI() {
  document.querySelectorAll('.mode-pill').forEach(button => button.addEventListener('click',() => {
    document.querySelectorAll('.mode-pill').forEach(p => p.classList.toggle('active',p===button));
    currentMode=button.dataset.mode; updateStageView();
  }));
  document.querySelectorAll('.drawer-tab').forEach(button => button.addEventListener('click',() => {
    document.querySelectorAll('.drawer-tab').forEach(p => p.classList.toggle('active',p===button));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active',p.id===button.dataset.tab));
  }));
  byId('btnRunInvestigation').addEventListener('click',() => loadInvestigation(byId('presetSelect').value));
  byId('tourStopSelect').addEventListener('change',event => loadInvestigation(event.target.value));
  byId('btnPrevDrawer').addEventListener('click',() => stepTourStop(-1));
  byId('btnNextDrawer').addEventListener('click',() => stepTourStop(1));
  byId('btnCloseDrawer').addEventListener('click',() => {showDrawer(false);byId('btnOpenDrawer').focus();});
  byId('btnOpenDrawer').addEventListener('click',() => showDrawer(byId('sideDrawer').classList.contains('closed')));
  byId('btnRetryProcessing').addEventListener('click',() => {
    if(lastRequest)loadInvestigation(lastRequest.presetId,lastRequest.upload);
  });
  byId('btnCancelProcessing').addEventListener('click',() => controller?.abort());
  for (const [id,delta] of [['btnZoomIn',.25],['btnZoomOut',-.25],['btnResetView',0],['btnFitScreen',0]]) byId(id).addEventListener('click',() => {
    zoomLevel=delta ? Math.min(3,Math.max(.5,zoomLevel+delta)):1;
    byId('imageStage').style.transform=`scale(${zoomLevel})`;
  });
  byId('btnTogglePins').addEventListener('click',() => {pinsVisible=!pinsVisible; updateStageView();});
  byId('btnPlayPause').addEventListener('click',() => {if (blinkInterval) {stopBlinkLoop();byId('btnPlayPause').textContent='Play';} else startBlinkLoop();});
  byId('blinkSpeed').addEventListener('input',event => {byId('speedValue').textContent=event.target.value+' fps';if(blinkInterval)startBlinkLoop();});
  byId('btnPrevEpoch').addEventListener('click',() => stepEpoch(-1));
  byId('btnNextEpoch').addEventListener('click',() => stepEpoch(1));
  byId('diffPairSelect').addEventListener('change',updateStageView);
  byId('btnUploadModal').addEventListener('click',() => modal(true));
  for (const id of ['btnCloseModal','btnCancelUpload']) byId(id).addEventListener('click',() => modal(false));
  byId('uploadModal').addEventListener('click',event => {if(event.target===byId('uploadModal'))modal(false);});
  document.addEventListener('keydown',event => {
    if(!byId('uploadModal').classList.contains('open'))return;
    if(event.key==='Escape') {event.preventDefault();modal(false);}
    if(event.key==='Tab') {
      const fields=[...byId('uploadModal').querySelectorAll('button:not(:disabled),input:not(:disabled)')];
      const first=fields[0],last=fields.at(-1);
      if(event.shiftKey && document.activeElement===first) {event.preventDefault();last.focus();}
      else if(!event.shiftKey && document.activeElement===last) {event.preventDefault();first.focus();}
    }
  });
  byId('btnSubmitUpload').addEventListener('click',handleCustomUpload);
  byId('btnRefetchSED').addEventListener('click',() => {
    const coord=selectedCoordinate;
    if(coord)fetchSED(coord.ra_deg,coord.dec_deg);
  });
  byId('btnExportJSON').addEventListener('click',() => {
    if(!currentInvestigation)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(currentInvestigation,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='SPHEREx-investigation.json';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  for (const id of ['primaryImage','trajectoryPlot','dipolePlot','sedPlot']) byId(id).addEventListener('error',() => {
    byId(id).hidden=true;byId('processingNotice').textContent='A generated image could not load. Retry the investigation to regenerate it.';
    byId('btnRetryProcessing').hidden=false;
    if(id==='primaryImage')stageMessage('Image unavailable. Retry the investigation.');
  });
  try {
    presets=await api('/api/presets');
    for(const id of ['presetSelect','tourStopSelect']) {
      byId(id).replaceChildren();for(const preset of presets) {const option=document.createElement('option');option.value=preset.id;option.textContent=preset.title;byId(id).append(option);}
    }
    if(presets.length)await loadInvestigation(presets[0].id);
  } catch(error) {showError(error);}
}
document.addEventListener('DOMContentLoaded',initUI);
window.addEventListener('pagehide',() => {controller?.abort();stopBlinkLoop();});
