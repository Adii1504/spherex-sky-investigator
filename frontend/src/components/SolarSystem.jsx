import React, {useEffect, useRef, useState} from 'react';
import {request} from '../api.js';

export function SolarSystem({onLoad, onVisit, selectedId, onSelect, mapReady}) {
  const [state, setState] = useState({status:'loading'});
  const [attempt, setAttempt] = useState(0);
  const strip = useRef(null);
  const load = useRef(onLoad); load.current = onLoad;
  useEffect(() => {
    const controller = new AbortController();
    setState({status:'loading'}); load.current([]);
    request('/solar-system', undefined, controller.signal, {prefix:'/api', timeoutMs:15000}).then(data => {
      if (!Array.isArray(data.bodies) || !data.observed_at) throw new Error('Planet positions are unavailable.');
      if (!controller.signal.aborted) {setState({status:'ready', ...data}); load.current(data.bodies);}
    }).catch(error => {if (!controller.signal.aborted) setState({status:'error',message:error.message});});
    return () => controller.abort();
  }, [attempt]);
  useEffect(() => {
    const card=strip.current?.querySelector('[aria-pressed="true"]');
    if(card&&strip.current) strip.current.scrollTo?.({left:card.offsetLeft-strip.current.offsetLeft,behavior:'smooth'});
  }, [selectedId]);
  const body = state.bodies?.find(item => item.id === selectedId);
  const move = direction => {
    const node = strip.current;
    if (node) node.scrollBy({left:direction * node.clientWidth * .75,behavior:'smooth'});
  };
  return <section className="solar-system" aria-label="Solar System explorer">
    <div className="solar-heading"><div><p className="eyebrow">OUR SOLAR SYSTEM</p><h2>Meet our neighbours</h2></div>
      <div className="solar-controls"><button aria-label="Previous Solar System bodies" onClick={() => move(-1)}>←</button><button aria-label="Next Solar System bodies" onClick={() => move(1)}>→</button>
        <button disabled={state.status === 'loading'} onClick={() => setAttempt(value => value + 1)}>Update positions</button></div></div>
    {state.status === 'loading' && <p role="status">Calculating Solar System positions…</p>}
    {state.status === 'error' && <p role="alert">{state.message} Use Update positions to retry.</p>}
    {state.status === 'ready' && <>
      <p className="solar-caption">Click a body or planet label to open its rotating 3D globe and orbital overview. Sky positions at <time dateTime={state.observed_at}>{state.observed_at.replace('T',' ').replace('Z',' UTC')}</time> · Earth-centered view.</p>
      <div className="solar-strip" ref={strip} tabIndex={0} aria-label="Scrollable Solar System bodies">
        {state.bodies.map(item => <button key={item.id} className="solar-card" aria-pressed={selectedId === item.id} onClick={() => onSelect(item.id)}>
          <span className={`solar-orb solar-${item.id}`} style={{'--body-color':item.color}} aria-hidden="true" /><strong>{item.name}</strong><small>{item.kind}</small></button>)}
      </div>
      {body ? <article className="solar-detail" aria-label={`${body.name} overview`}>
        <div><h3>{body.name}</h3><p>{body.description}</p>
          {body.ra_deg !== null && <p className="solar-caption">RA {body.ra_deg.toFixed(3)}° · Dec {body.dec_deg.toFixed(3)}° · Distance from Earth’s center {body.distance_au.toFixed(4)} AU</p>}
        </div>
        <div className="solar-controls">{body.ra_deg !== null && <button disabled={!mapReady} onClick={() => onVisit(body)}>Explore around {body.name}</button>}
          <a href={body.reference_url} target="_blank" rel="noreferrer">About {body.name} · NASA ↗</a></div>
      </article> : <p className="solar-caption">Select a body for a brief introduction, then explore its part of the sky.</p>}
      <p className="solar-caption">{state.note} {state.ephemeris} · {state.frame}. Positions update when you press Update positions; they are not a live telescope feed.</p>
    </>}
  </section>;
}
