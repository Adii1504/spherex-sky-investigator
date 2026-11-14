import React, {useState,useEffect,useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {API_BASE,request,pollJob,defaultSelection,exposureConflict} from './api';
import './style.css';

const time = value => new Date(value).toLocaleString(undefined,{timeZone:'UTC',year:'numeric',month:'short',day:'2-digit',hour:'2-digit',minute:'2-digit'})+' UTC';
const wave = value => value == null ? 'Unknown' : Number(value).toFixed(4)+' ?m';
const number = value => value == null ? '?' : Number(value).toPrecision(4);
function Notice({items=[]}) {return items.length ? <ul className="notices">{[...new Set(items)].map((item,i)=><li key={i}>{item}</li>)}</ul>:null;}
function App() {
 const [health,setHealth]=useState(null),[error,setError]=useState(null),[busy,setBusy]=useState('');
 const [form,setForm]=useState({ra_deg:'127.69444',dec_deg:'-39.17760',fov_arcmin:'2',start_utc:'',end_utc:''});
 const [search,setSearch]=useState(null),[selected,setSelected]=useState([]),[field,setField]=useState(null);
 const [sequence,setSequence]=useState(null),[sequenceJob,setSequenceJob]=useState(null),[job,setJob]=useState(null);
 const [index,setIndex]=useState(0),[reference,setReference]=useState(0),[mode,setMode]=useState('single'),[playing,setPlaying]=useState(false),[blink,setBlink]=useState(false),[opacity,setOpacity]=useState(50);
 const [investigation,setInvestigation]=useState(null),[groups,setGroups]=useState({}),[verification,setVerification]=useState(null);
 const controller=useRef(null);
 useEffect(()=>{request('/health').then(setHealth).catch(e=>setError(e));return ()=>controller.current?.abort();},[]);
 const frames=sequence?.previews || [], current=frames[index], comparison=frames[reference];
 useEffect(()=>{if(!playing || frames.length<2) return;const id=setInterval(()=>{if(mode==='blink')setBlink(b=>!b);else setIndex(i=>(i+1)%frames.length);},800);return ()=>clearInterval(id);},[playing,frames.length,mode]);
 const execute=async(label,fn)=>{
   controller.current?.abort();controller.current=new AbortController();setBusy(label);setError(null);
   try {await fn(controller.current.signal);} catch(e) {if(e.name!=='AbortError')setError(e);} finally {setBusy('');}
 };
 const runSearch=e=>{e.preventDefault();execute('Searching archive',async signal=>{
   setPlaying(false);setSequence(null);setSearch(null);setInvestigation(null);setVerification(null);setJob(null);setSelected([]);
   const query={ra_deg:Number(form.ra_deg),dec_deg:Number(form.dec_deg),fov_arcmin:Number(form.fov_arcmin)};
   for(const key of ['start_utc','end_utc']) if(form[key]) query[key]=new Date(form[key]+'Z').toISOString();
   const result=await request('/observations/search',query,signal);setSearch(result);setField(query);setSelected(defaultSelection(result.observations));
 });};
 const build=()=>execute('Preparing sequence',async signal=>{
   setPlaying(false);setSequence(null);setInvestigation(null);setVerification(null);
   const selection={search_id:search.search_id,observation_ids:selected,ra_deg:field.ra_deg,dec_deg:field.dec_deg,fov_arcmin:field.fov_arcmin};
   const queued=await request('/sequences',selection,signal);setSequenceJob(queued.job_id);
   const result=await pollJob(queued.job_id,setJob,signal);setSequence(result);setIndex(0);setReference(0);setMode('single');
   const ids=result.previews.map(p=>p.observation.id);setGroups(Object.fromEntries(ids.map((id,i)=>[id,i===ids.length-1?'reserved':'training'])));
 });
 const save=async signal=>{
   if(investigation)return investigation;
   const result=await request('/investigations',{search_id:search.search_id,observation_ids:sequence.observation_ids,ra_deg:field.ra_deg,dec_deg:field.dec_deg,fov_arcmin:field.fov_arcmin,sequence_job_id:sequenceJob},signal);
   setInvestigation(result.investigation_id);return result.investigation_id;
 };
 const verify=()=>execute('Evaluating reserved exposures',async signal=>{
   setVerification(null);const id=await save(signal);
   const body={training_observation_ids:[],reserved_observation_ids:[]};
   for(const [key,group] of Object.entries(groups)) if(group!=='exclude')body[group+'_observation_ids'].push(key);
   const queued=await request('/investigations/'+id+'/verify',body,signal);
   setVerification(await pollJob(queued.job_id,setJob,signal));
 });
 const download=()=>execute('Exporting evidence',async signal=>{
   const id=await save(signal);const evidence=await request('/investigations/'+id+'/evidence',undefined,signal);
   const url=URL.createObjectURL(new Blob([JSON.stringify(evidence,null,2)],{type:'application/json'}));
   const a=document.createElement('a');a.href=url;a.download='spherex-whylab-evidence-'+id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 });
 const observations=search?.observations || [];
 const chosen=observations.filter(o=>selected.includes(o.id));
 const sameSelection=sequence && [...selected].sort().join(',')===[...sequence.observation_ids].sort().join(',');
 const conflict=exposureConflict(frames.map(p=>p.observation),groups);
 const trainCount=Object.values(groups).filter(v=>v==='training').length, reserveCount=Object.values(groups).filter(v=>v==='reserved').length;
 const image=p=><img src={API_BASE+p.preview_url} alt={'SPHEREx observation '+p.observation.product_id} />;
 return <div className="app">
  <header className="topbar"><a className="brand" href="#"><span className="brand-mark">?</span><span>SPHEREx <b>WhyLab</b></span></a><span className="project-label">A SKY INVESTIGATION WORKSPACE</span><a href="https://irsa.ipac.caltech.edu/Missions/spherex.html" target="_blank" rel="noreferrer">Archive ?</a></header>
  <main>
   <div className="heading"><div><p className="eyebrow"><span className="small-cross">+</span> REAL OBSERVATIONS. OPEN QUESTIONS.</p><h1>What changes<br/><em>in your patch of sky?</em></h1><p className="intro">Follow infrared observations through time. Compare the evidence,<br className="desktop"/> question the differences, and keep the provenance.</p></div><div className="mission"><span className="orbit"></span><p>01 / INVESTIGATE</p><strong>One field.<br/>Multiple perspectives.</strong><small>NASA Space Apps project<br/>Independent tool ? not a NASA service</small></div></div>
   <div className="capabilities" aria-label="Service capabilities"><span className="connection">SERVICE <i className={health?'dot ready':'dot'}/></span>{['archive_access','image_processing','motion_verification'].map(k=><span key={k}><i className={'dot '+(health?.capabilities[k]==='available'?'ready':'')}/>{k.replaceAll('_',' ')} <b>{health?.capabilities[k] || 'checking'}</b></span>)}</div>
   {error && <div className="error" role="alert"><strong>{error.code || 'Request error'}</strong><p>{error.message}</p>{error.details && <pre>{JSON.stringify(error.details,null,2)}</pre>}</div>}
   <div className="workspace">
    <aside className="panel search-panel"><div className="panel-title"><span className="step">01</span><h2>Choose a sky field</h2></div><p className="muted">ICRS coordinates in decimal degrees.</p>
     <form onSubmit={runSearch}><label>RIGHT ASCENSION <span>degrees</span><input aria-label="Right ascension" required type="number" step="any" min="0" max="359.9999999999" value={form.ra_deg} onChange={e=>setForm({...form,ra_deg:e.target.value})}/></label><label>DECLINATION <span>degrees</span><input aria-label="Declination" required type="number" step="any" min="-90" max="90" value={form.dec_deg} onChange={e=>setForm({...form,dec_deg:e.target.value})}/></label><label>FIELD OF VIEW <span>arcminutes</span><input aria-label="Field of view" required type="number" step="any" min="0.1" max="30" value={form.fov_arcmin} onChange={e=>setForm({...form,fov_arcmin:e.target.value})}/></label><details><summary>Optional date range <span>UTC</span></summary><label>FROM<input aria-label="Start UTC" type="datetime-local" value={form.start_utc} onChange={e=>setForm({...form,start_utc:e.target.value})}/></label><label>TO<input aria-label="End UTC" type="datetime-local" value={form.end_utc} onChange={e=>setForm({...form,end_utc:e.target.value})}/></label></details><button className="primary full" disabled={!!busy || health?.capabilities.archive_access!=='available'}>Search observations <span>?</span></button></form>
     <div className="field-note"><span>?</span><p>The prefilled coordinates are an IRSA example field. Search to retrieve actual coverage; no sample imagery is preloaded.</p></div>
     <div className="sidebar-foot"><span>PROVENANCE FIRST</span><p>Every frame keeps its archive product identity, release, and observation time.</p></div>
    </aside>
    <section className="panel viewer"><div className="viewer-heading"><div className="panel-title"><span className="step">02</span><h2>Explore the sequence</h2></div><span className="badge">{frames.length ? frames.length+' FRAMES' : 'AWAITING A FIELD'}</span></div>
     {frames.length ? <><div className="viewer-tools"><div className="segmented">{['single','compare','blink','overlay'].map(m=><button key={m} aria-pressed={mode===m} onClick={()=>{setMode(m);setPlaying(false);}}>{m}</button>)}</div>{mode!=='single' && <label className="reference">Reference<select aria-label="Reference frame" value={reference} onChange={e=>setReference(Number(e.target.value))}>{frames.map((p,i)=><option key={p.observation.id} value={i}>{i+1} ? {time(p.observation.observed_at)}</option>)}</select></label>}</div>
     <div className={'sky-stage '+(mode==='compare'?'two-up':'')}>
      {mode==='compare'?<><figure>{image(comparison)}<figcaption>REFERENCE / {reference+1}</figcaption></figure><figure>{image(current)}<figcaption>FRAME / {index+1}</figcaption></figure></>:mode==='overlay'?<><div className="overlay-image">{image(comparison)}</div><div className="overlay-image" style={{opacity:opacity/100}}>{image(current)}</div><span className="stage-label">VISUAL OVERLAY ? NOT A DIFFERENCE IMAGE</span></>:<><div className="single-image">{image(mode==='blink' && playing && blink?comparison:current)}</div><span className="stage-label">N ? &nbsp; E ? &nbsp; ? &nbsp; MASKED PIXELS TRANSPARENT</span></>}
     </div>
     {mode==='overlay' && <label className="overlay-control">Frame opacity<input aria-label="Overlay opacity" type="range" min="0" max="100" value={opacity} onChange={e=>setOpacity(Number(e.target.value))}/><span>{opacity}%</span></label>}
     <div className="timeline"><button aria-label={playing?'Pause sequence':'Play sequence'} onClick={()=>setPlaying(!playing)} disabled={frames.length<2}>{playing?'?':'?'}</button><input aria-label="Sequence frame" type="range" min="0" max={Math.max(0,frames.length-1)} value={index} onChange={e=>{setPlaying(false);setIndex(Number(e.target.value));}}/><span>{String(index+1).padStart(2,'0')} / {String(frames.length).padStart(2,'0')}</span></div><div className="frame-meta"><div><span>OBSERVED</span><strong>{time(current.observation.observed_at)}</strong></div><div><span>SELECTED-POSITION WAVELENGTH</span><strong>{wave(current.metadata?.position_wavelength_um)}</strong></div><div><span>VALID COVERAGE</span><strong>{Math.round((current.metadata?.valid_fraction || 0)*100)}%</strong></div></div><div className="product"><a href={current.observation.provenance.source_url} target="_blank" rel="noreferrer">{current.observation.product_id} ?</a></div><Notice items={sequence.warnings}/></>:<div className="empty-stage"><div className="reticle"><span>+</span></div><h3>Your investigation starts here.</h3><p>Search a field, choose observations,<br/>then build a chronological sequence.</p><span className="empty-coordinates">RA {Number(form.ra_deg).toFixed(3)}? &nbsp; / &nbsp; DEC {Number(form.dec_deg).toFixed(3)}?</span></div>}
     {busy && <div className="job-status" role="status"><i className="spinner"/><span>{busy}{job && busy!=='Searching archive'?' ? '+job.status:''}</span></div>}
    </section>
   </div>
   {search && <section className="panel observations"><div className="section-heading"><div><p className="eyebrow">THE OBSERVATIONAL RECORD</p><h2>{observations.length} observations found<span className="muted"> / {selected.length} selected</span></h2></div><button className="primary" disabled={!!busy || !selected.length || health?.capabilities.image_processing!=='available'} onClick={build}>Build sequence <span>?</span></button></div><Notice items={search.warnings}/><div className="table-scroll"><table><thead><tr><th>Select</th><th>Observation / UTC</th><th>Release</th><th>Detector</th><th>File wavelength coverage</th><th>At selected position</th></tr></thead><tbody>{observations.map(o=><tr key={o.id}><td><input aria-label={'Select '+o.product_id} type="checkbox" disabled={!!busy} checked={selected.includes(o.id)} onChange={e=>setSelected(e.target.checked?[...selected,o.id]:selected.filter(id=>id!==o.id))}/></td><td><strong>{time(o.observed_at)}</strong><small>{o.exposure_id}</small></td><td>{o.release}</td><td>D{o.detector || '?'}</td><td>{o.file_wavelength_um?o.file_wavelength_um.map(v=>Number(v).toFixed(3)).join(' ? ')+' ?m':'Unknown'}</td><td>{wave(o.position_wavelength_um)}</td></tr>)}</tbody></table></div>{!observations.length && <p className="no-coverage">No coverage found. Try a wider field or different dates.</p>}{!sameSelection && sequence && <p className="warning">Selection changed. Rebuild the sequence to investigate this selection.</p>}<p className="muted small">The initial selection uses one detector and unique exposures. File coverage is not the wavelength measured at your selected sky position.</p></section>}
   {sequence && <section className="panel investigation"><div className="section-heading"><div><p className="eyebrow">03 / QUESTION THE EVIDENCE</p><h2>Can a simple prediction hold up?</h2></div><button disabled={!!busy} onClick={download}>? Export evidence JSON</button></div><p className="muted">Use training exposures to fit an exploratory straight-line motion model. Keep reserved exposures unused until evaluation. Residuals are measurements, not a detection or confidence score.</p><div className="verification-layout"><div><div className="split-summary"><span><i className="dot ready"/>{trainCount} training</span><span><i className="dot reserved"/>{reserveCount} reserved</span></div>{frames.map(p=><div className="split-row" key={p.observation.id}><span>{time(p.observation.observed_at)} <small>? D{p.observation.detector}</small></span><select aria-label={'Role for '+p.observation.product_id} disabled={!!busy} value={groups[p.observation.id] || 'exclude'} onChange={e=>setGroups({...groups,[p.observation.id]:e.target.value})}><option value="training">Training</option><option value="reserved">Reserved</option><option value="exclude">Exclude</option></select></div>)}{conflict && <p className="warning">Multiple selected products share an exposure. Exclude duplicates before verification.</p>}<button className="primary" disabled={!!busy || conflict || trainCount<3 || reserveCount<1 || health?.capabilities.motion_verification!=='available'} onClick={verify}>Evaluate reserved observations ?</button><p className="muted small">Requires at least 3 training exposures and 1 reserved exposure. A single isolated source must remain near the selected coordinate.</p></div><div className="result-card"><span className="eyebrow">VERIFICATION RESULT</span>{verification?<><h3>{verification.outcome.replaceAll('_',' ')}</h3><Notice items={[...verification.warnings,...verification.limitations]}/>{verification.measurements.fit && <p>East velocity: {number(verification.measurements.fit.east_velocity_arcsec_per_day)} arcsec/day<br/>North velocity: {number(verification.measurements.fit.north_velocity_arcsec_per_day)} arcsec/day</p>}{verification.measurements.reserved?.map(m=><p key={m.observation_id}>Reserved residual: {number(m.residual_arcsec)} arcsec</p>)}<details><summary>Measurements and assumptions</summary><pre>{JSON.stringify(verification,null,2)}</pre></details></>:<><h3>Let unused observations<br/>ask the next question.</h3><p>No motion claim is made before?or automatically after?this exploratory test. Assumptions and limitations travel with your evidence.</p></>}</div></div></section>}
   <footer><span>SPHEREx WhyLab <b> / </b> Follow a question. Keep the evidence.</span><span>Real archive data ? Transparent limitations</span></footer>
  </main>
 </div>;
}
createRoot(document.getElementById('root')).render(<App/>);
