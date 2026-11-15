import React, {useEffect, useState} from 'react';
import {request} from '../api.js';

export function CatalogSearch({coordinate, onAddTarget}) {
  const [name, setName] = useState(''), [cone, setCone] = useState(null), [state, setState] = useState({status:'idle'});
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!cone && name.trim().length < 2) {setState({status:'idle'}); return;}
    const controller = new AbortController();
    setState({status:'loading'});
    const timer = setTimeout(() => {
      const params = new URLSearchParams(cone ? {ra:cone.ra, dec:cone.dec, radius:.1} : {name:name.trim()});
      request('/catalog/search?' + params, undefined, controller.signal, {prefix:'/api', timeoutMs:15000})
        .then(result => {if (!controller.signal.aborted) setState({status:'ready', result});})
        .catch(error => {if (!controller.signal.aborted) setState({status:'error', message:error.message});});
    }, 450);
    return () => {clearTimeout(timer); controller.abort();};
  }, [name, cone, attempt]);
  return <section className="catalog-lookup" aria-label="Live SIMBAD lookup"><h3>Search SIMBAD</h3>
    <label>Exact catalogue name<input type="search" maxLength={100} value={name} placeholder="e.g. M 31" onChange={e => {setCone(null); setName(e.target.value);}} /></label>
    <button disabled={!coordinate} onClick={() => {setName(''); setCone({...coordinate});}}>Cone search here · 0.1°</button>
    <p>Public SIMBAD / CDS · up to 50 records. Cone uses the last clicked position or selected source. Catalogue matches are not SPHEREx detections.</p>
    {state.status === 'loading' && <p role="status">Searching catalogue…</p>}
    {state.status === 'error' && <div role="alert"><p>{state.message}</p><button onClick={() => setAttempt(v => v+1)}>Retry catalogue lookup</button></div>}
    {state.status === 'ready' && <><p role="status">{state.result.targets.length ? `${state.result.targets.length} catalogue records${state.result.cached ? ' · cached' : ''}` : 'No catalogue results.'}</p>
      <ul>{state.result.targets.map(t => <li key={t.id}><button onClick={() => onAddTarget?.(t)}>{t.name} · {t.object_type || 'Unavailable'}</button></li>)}</ul>
      {state.result.possibly_truncated && <p>Result limit reached; narrow the cone.</p>}</>}
  </section>;
}
