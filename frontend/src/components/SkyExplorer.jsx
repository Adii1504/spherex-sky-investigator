import React, { lazy, Suspense, useEffect, useId, useRef, useState } from 'react';
import { createSkyMap, REFERENCE_SURVEY, targetCoordinates } from '../aladin.js';
import { safeProvenanceUrl } from '../search.js';
import { TargetProducts } from './TargetProducts.jsx';
import Starfield from './Starfield.jsx';
import {CatalogSearch} from './CatalogSearch.jsx';
import {CandidateNotes} from './CandidateNotes.jsx';
import {LocalProducts} from './LocalProducts.jsx';
import {OfflineSky} from './OfflineSky.jsx';
import {SolarSystem} from './SolarSystem.jsx';
const Source3D = lazy(() => import('./Source3D.jsx'));
const SolarSystem3D = lazy(() => import('./SolarSystem3D.jsx'));

class RendererBoundary extends React.Component {
  state = {failed: false};
  static getDerivedStateFromError() {return {failed:true};}
  render() {
    return this.state.failed ? <p role="status">The 3D renderer could not load. Use the sky survey or offline snapshot; reload the page to retry 3D.</p> : this.props.children;
  }
}

export function SkyExplorer({ targets = [], selectedTarget = null, onSelectTarget, onSearchTarget,
  observationContent = null, observations = [], onAddTarget, mapFactory = createSkyMap, searchDisabled = false }) {
  const container = useRef(null);
  const detailPanel = useRef(null);
  const map = useRef(null);
  const callbacks = useRef({ onSelectTarget, targets });
  callbacks.current = { onSelectTarget, targets };
  const targetList = useRef(targets);
  targetList.current = targets;
  const selected = useRef(selectedTarget);
  selected.current = selectedTarget;
  const [localProducts, setLocalProducts] = useState([]);
  const [bodies, setBodies] = useState([]);
  const [selectedBody, setSelectedBody] = useState(null);
  const [planetViewOpen, setPlanetViewOpen] = useState(false);
  const selectBody = id => {setSelectedBody(id);setPlanetViewOpen(true);};
  const [viewMode, setViewMode] = useState('sky');
  const [clickedCoordinate, setClickedCoordinate] = useState(null);
  const [layers, setLayers] = useState({sources:true, observations:true, planets:true});
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState('loading');
  const [mapReady, setMapReady] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');
  const [hoveredId, setHoveredId] = useState(null);
  const [detailsOpen, setDetailsOpen] = useState(true);
  const [starsPaused, setStarsPaused] = useState(false);
  const [offline, setOffline] = useState(typeof navigator !== 'undefined' && navigator.onLine === false);
  const detailId = useId().replaceAll(':', '');
  const coordinate = targetCoordinates(selectedTarget);
  const hovered = targets.find(target => target.id === hoveredId);
  const filtered = targets.filter(target => [target.name, ...(target.aliases || [])].join(' ').toLowerCase().includes(filter.trim().toLowerCase()));

  useEffect(() => {
    const controller = new AbortController();
    let instance;
    let timer;
    setStatus('loading'); setError(''); setMapReady(false);
    const ready = mapFactory(container.current, {
      signal: controller.signal,
      onSelect: id => {callbacks.current.onSelectTarget?.(id);setDetailsOpen(true);},
      onHover: setHoveredId,
      onBodySelect: id => {setSelectedBody(id);setPlanetViewOpen(true);},
      onCoordinate: setClickedCoordinate,
      onStatus: (next, message) => {
        if (controller.signal.aborted) return;
        setStatus(next); setError(message || '');
      },
    });
    timer = setTimeout(() => {
      if (!controller.signal.aborted) { setStatus('error'); setError('The reference sky is taking too long to load. Check your network or retry. The catalogue remains usable.'); }
    }, 20000);
    Promise.resolve(ready).then(value => {
      clearTimeout(timer);
      if (controller.signal.aborted) { value?.dispose(); return; }
      instance = value; map.current = value;
      setMapReady(true);
      value.setTargets(targetList.current);
      // Reference tiles can arrive after the Aladin controls become ready.
      setStatus(current => current === 'loading' ? 'ready' : current);
    }).catch(reason => {
      clearTimeout(timer);
      if (!controller.signal.aborted) { setStatus('error'); setError(reason.message || 'The sky survey could not initialize.'); }
    });
    const network = () => setOffline(navigator.onLine === false);
    window.addEventListener('online', network); window.addEventListener('offline', network);
    return () => {
      controller.abort(); clearTimeout(timer); instance?.dispose();
      if (map.current === instance) map.current = null;
      window.removeEventListener('online', network); window.removeEventListener('offline', network);
    };
  }, [attempt, mapFactory]);

  useEffect(() => { map.current?.setTargets(targets); }, [targets]);
  useEffect(() => { map.current?.setBodies?.(bodies); }, [bodies, mapReady]);
  useEffect(() => { map.current?.setFootprints?.([...observations,...localProducts]); }, [observations, localProducts, mapReady]);
  useEffect(() => { map.current?.layers?.(layers); }, [layers, mapReady]);
  useEffect(() => {
    map.current?.select(selectedTarget?.id || null);
    if (selectedTarget) {
      setDetailsOpen(true);
    }
  }, [selectedTarget?.id, mapReady]);
  useEffect(() => {
    if (detailsOpen && selectedTarget && window.matchMedia?.('(max-width: 780px)')?.matches) detailPanel.current?.focus();
  }, [detailsOpen, selectedTarget?.id]);

  const references = selectedTarget?.references || [];
  const sourceUrl = safeProvenanceUrl(selectedTarget?.sourceUrl ?? selectedTarget?.source_url);
  const retryMap = () => {
    if (map.current?.reload) { setStatus('loading'); setError(''); map.current.reload(); }
    else setAttempt(value => value + 1);
  };
  const closeDetails = () => {
    setDetailsOpen(false);
    document.querySelector('.sky-target-list button[aria-pressed="true"]')?.focus();
  };
  return <section className="sky-explorer" id="sky-explorer" aria-label="Astronomy sky explorer" onKeyDown={event => { if (event.key === 'Escape' && detailsOpen) closeDetails(); }}>
    <div className="sky-explorer-heading"><Starfield paused={starsPaused} /><div><p className="eyebrow">THE SKY IS A PLACE TO ASK QUESTIONS</p><h1>Explore a field. Follow the evidence.</h1>
      <p className="starfield-caption">Decorative starfield · simulated, not catalogue objects</p>
      <button type="button" className="starfield-toggle" aria-pressed={starsPaused} onClick={() => setStarsPaused(value => !value)}>{starsPaused ? 'Resume background animation' : 'Pause background animation'}</button></div>
      <p>Choose a catalogue target or pan across the reference sky. SPHEREx field coverage and derived observation previews come from the archive workflow.</p>
    </div>
    <div className={`sky-explorer-layout ${detailsOpen && selectedTarget ? 'sky-details-open' : ''}`}>
      <div className="sky-map-column">
        <div className="sky-map-toolbar" aria-label="Explorer views">
          <button aria-pressed={viewMode === 'sky'} onClick={() => setViewMode('sky')}>Sky survey</button>
          <button aria-pressed={viewMode === '3d'} onClick={() => setViewMode('3d')}>3D sources</button>
          <button aria-pressed={viewMode === 'offline'} onClick={() => setViewMode('offline')}>Offline snapshot</button>
        </div>
        {viewMode === '3d' && <RendererBoundary><Suspense fallback={<p role="status">Loading 3D renderer…</p>}><Source3D targets={targets} selectedId={selectedTarget?.id} onSelect={onSelectTarget} /></Suspense></RendererBoundary>}
        {viewMode === 'offline' && <OfflineSky targets={targets.filter(t => !t.id.startsWith('simbad-'))} selectedId={selectedTarget?.id} onSelect={onSelectTarget} onCoordinate={setClickedCoordinate} />}
        <div hidden={viewMode !== 'sky'}>
        <div className="sky-map-toolbar" role="group" aria-label="Reference sky controls">
          <button type="button" disabled={!mapReady} onClick={() => map.current?.reset()}>Reset view</button>
          <button type="button" disabled={!mapReady} onClick={() => map.current?.allSky?.()}>All-sky overview</button>
          <button type="button" disabled={!mapReady} onClick={() => map.current?.fill?.()}>Fill panel</button>
          <button type="button" aria-label="Pan sky left" disabled={!mapReady} onClick={() => map.current?.pan?.(1, 0)}>←</button>
          <button type="button" aria-label="Pan sky right" disabled={!mapReady} onClick={() => map.current?.pan?.(-1, 0)}>→</button>
          <button type="button" aria-label="Pan sky up" disabled={!mapReady} onClick={() => map.current?.pan?.(0, 1)}>↑</button>
          <button type="button" aria-label="Pan sky down" disabled={!mapReady} onClick={() => map.current?.pan?.(0, -1)}>↓</button>
          <button type="button" aria-label="Zoom in reference sky" disabled={!mapReady} onClick={() => map.current?.zoom(.5)}>+</button>
          <button type="button" aria-label="Zoom out reference sky" disabled={!mapReady} onClick={() => map.current?.zoom(2)}>−</button>
          <button type="button" disabled={!coordinate || !mapReady} onClick={() => map.current?.center(selectedTarget)}>Centre on target</button>
          {selectedTarget && <button type="button" aria-expanded={detailsOpen} aria-controls={detailId} onClick={() => setDetailsOpen(value => !value)}>{detailsOpen ? 'Hide target details' : 'Show target details'}</button>}
        </div>
        <div className="sky-map-toolbar" aria-label="Map layers">
          <label><input type="checkbox" checked={layers.sources} onChange={e => setLayers(v => ({...v,sources:e.target.checked}))} />Catalogue sources (gold)</label>
          <label><input type="checkbox" checked={layers.observations} onChange={e => setLayers(v => ({...v,observations:e.target.checked}))} />Observation footprints (cyan)</label>
          <label><input type="checkbox" checked={layers.planets} onChange={e => setLayers(v => ({...v,planets:e.target.checked}))} />Solar System bodies (coral)</label>
          <span>{[...observations,...localProducts].filter(o => o.footprint_stcs).length} supplied footprints · unavailable geometry is not estimated</span>
        </div>
        <div className="sky-map-stage">
          <div className="sky-map-host" ref={container} tabIndex={0} role="group" aria-label="Aladin Lite reference survey map; arrow keys pan, plus and minus zoom" onKeyDown={event => {
            if (event.target !== event.currentTarget && !['CANVAS', 'DIV'].includes(event.target.tagName)) return;
            const direction = {ArrowLeft: [1, 0], ArrowRight: [-1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1]}[event.key];
            if (direction) {event.preventDefault(); event.stopPropagation(); map.current?.pan?.(...direction);}
            else if (['+', '=', '-'].includes(event.key)) {event.preventDefault(); map.current?.zoom(event.key === '-' ? 2 : .5);}
          }} />
          {status === 'loading' && <div className="sky-map-state" role="status"><p>Loading Aladin Lite and the reference survey…</p></div>}
          {status === 'error' && <div className="sky-map-state sky-map-error" role="status"><h2>Reference sky unavailable</h2><p>{error}</p><button type="button" onClick={retryMap}>Retry reference sky</button><p>The target list and coordinate-based SPHEREx search remain available.</p><button onClick={() => setViewMode('offline')}>Use offline snapshot</button></div>}
          {hovered && <div className="sky-marker-tooltip" role="tooltip"><strong>{hovered.name}</strong><span>{hovered.object_type ?? hovered.type ?? 'Type unavailable'}</span></div>}
          {layers.planets && bodies.some(body => body.id === 'earth') && <button className="sky-earth-observer" onClick={() => selectBody('earth')} aria-label="About Earth, our observing location"><span className="solar-orb solar-earth" style={{'--body-color':'#6abce8'}} aria-hidden="true" /><span>Earth<small>You are viewing from here</small></span></button>}
        </div>
        <p className="sky-navigation-help">Drag to explore, or use the arrow buttons. Scroll or use + / − to zoom. Gold stars open the search and details panel; View in 3D opens their model. Planet labels open their 3D globes. Reset view restores the rectangular overview. Mercator stretches regions near the poles.</p>
        <p className="sky-survey-credit"><strong>Reference survey: {REFERENCE_SURVEY.name}</strong> · CDS HiPS / Aladin Lite. These survey tiles are not SPHEREx observations. <a href={REFERENCE_SURVEY.url} target="_blank" rel="noreferrer">Survey metadata and credits ↗</a></p>
        <SolarSystem onLoad={setBodies} selectedId={selectedBody} onSelect={selectBody} mapReady={mapReady} onVisit={body => {map.current?.layers?.({...layers,planets:true});setLayers(value => ({...value,planets:true}));map.current?.center(body, 15);}} />
        </div>
        <p className="sky-survey-credit" role="status">{clickedCoordinate ? `Last sky position: RA ${clickedCoordinate.ra.toFixed(6)}°, Dec ${clickedCoordinate.dec.toFixed(6)}° · ICRS · coordinate only; no object identified` : 'Click empty sky to read ICRS coordinates. A sky position alone does not identify an object.'}</p>
        {offline && <p className="sky-offline-notice" role="status">Network offline. New reference tiles and live archive searches may be unavailable; previously loaded tiles may remain visible.</p>}
        <p className="sky-survey-credit">Data: SIMBAD / CDS; SPHEREx / NASA-IPAC IRSA; DSS imagery STScI/NASA, coloured by CDS, served by ESA. <a href="/notices/THIRD_PARTY.txt" target="_blank" rel="noreferrer">Software licenses and attribution</a></p>
        <LocalProducts onLoad={setLocalProducts} />
        {onAddTarget && <CatalogSearch coordinate={clickedCoordinate || coordinate} onAddTarget={onAddTarget} />}
        <section className="sky-target-catalogue" aria-labelledby="sky-targets-title">
          <div className="sky-target-search"><h2 id="sky-targets-title">Catalogue starting points</h2><label htmlFor={`${detailId}-search`}>Find a target by name</label>
            <input id={`${detailId}-search`} type="search" value={filter} placeholder="Name or catalogue alias" onChange={event => setFilter(event.target.value)} />
          </div>
          <ul className="sky-target-list">{filtered.map(target => <li key={target.id}><button type="button" aria-pressed={selectedTarget?.id === target.id} onClick={() => onSelectTarget?.(target.id)}>
            <strong>{target.name}</strong><span>{target.object_type ?? target.type ?? 'Type unavailable'}</span><small>{targetCoordinates(target) ? 'Catalogue coordinates · not epoch-propagated' : 'Coordinates pending verification · no sky marker'}</small>
          </button></li>)}</ul>
          {!filtered.length && <p role="status">No catalogue target matches this name.</p>}
        </section>
      </div>
      {detailsOpen && selectedTarget && <aside className="sky-target-details" ref={detailPanel} tabIndex="-1" id={detailId} aria-label={`${selectedTarget.name} target details`}>
        <div className="sky-target-details-heading"><p className="eyebrow">CATALOGUE TARGET</p><button type="button" aria-label="Close target details" onClick={closeDetails}>×</button></div>
        <h2>{selectedTarget.name}</h2><p>{selectedTarget.object_type ?? selectedTarget.type ?? 'Type unavailable'}</p>
        <div className="sky-target-actions"><button type="button" className="primary" disabled={!coordinate || searchDisabled} onClick={() => onSearchTarget?.(selectedTarget)}>Search SPHEREx field</button>
          <button type="button" onClick={() => selectBody(selectedTarget.id)}>View in 3D</button><button type="button" disabled={!coordinate || !mapReady} onClick={() => map.current?.center(selectedTarget)}>Centre on target</button></div>
        <p>Catalog facts · {selectedTarget.source || 'Unavailable'} · {selectedTarget.source_checked_on ? `Bundled snapshot retrieved ${selectedTarget.source_checked_on}` : 'Live catalogue lookup'}</p>
        <dl className="sky-coordinate-details"><div><dt>Catalog identifier</dt><dd>{selectedTarget.source_identifier || 'Unavailable'}</dd></div>
          <div><dt>Distance (measured/catalogued)</dt><dd>{selectedTarget.distance?.value_pc == null ? 'Unavailable' : `${selectedTarget.distance.value_pc} pc`}</dd></div>
          <div><dt>Distance uncertainty</dt><dd>{selectedTarget.distance?.uncertainty_pc == null ? 'Unavailable' : `${selectedTarget.distance.uncertainty_pc} pc`}</dd></div>
          <div><dt>Distance provenance</dt><dd>{selectedTarget.distance?.provenance || 'Unavailable'}</dd></div><div><dt>Right ascension</dt><dd>{coordinate ? `${coordinate.ra}°` : 'Unavailable'}</dd></div>
          <div><dt>Declination</dt><dd>{coordinate ? `${coordinate.dec}°` : 'Unavailable'}</dd></div>
          <div><dt>Coordinate frame</dt><dd>{selectedTarget.coordinate_frame ?? selectedTarget.frame ?? 'Unavailable'}</dd></div>
          <div><dt>Reference epoch</dt><dd>{selectedTarget.reference_epoch ?? selectedTarget.referenceEpoch ?? 'Unavailable'}</dd></div>
          <div><dt>Coordinate reference</dt><dd>{selectedTarget.coordinate_reference ?? selectedTarget.coordinateReference ?? 'Unavailable'}</dd></div>
          <div><dt>Astrometry status</dt><dd>{selectedTarget.astrometry_status ?? selectedTarget.astrometryStatus ?? 'Unverified'}</dd></div>
        </dl>
        <p className="sky-astrometry-note">{selectedTarget.astrometry_note ?? selectedTarget.astrometryNote ?? 'Coordinates are not propagated to SPHEREx observation epochs.'}</p>
        {selectedTarget.provisional && <p className="sky-provisional">Provisional for observation matching. Catalogue coordinates do not establish a SPHEREx detection.</p>}
        {!coordinate && <p>Verified coordinates are required before this target can be used for field search.</p>}
        <section className="sky-field-evidence"><h3>Observations covering this sky field</h3><p>Archive coverage is not confirmation that the named target was detected.</p>{observationContent || <p className="muted">Search this field to inspect dates, detectors, wavelengths and products. Generate a sequence for its actual SPHEREx PNG previews.</p>}</section>
        {selectedTarget.id.startsWith('simbad-') ? <p>Unavailable: no approved local products associated with this catalogue lookup. Search its SPHEREx field separately.</p> : <TargetProducts key={selectedTarget.id} targetId={selectedTarget.id} />}
        <CandidateNotes key={'notes:'+selectedTarget.id} targetId={selectedTarget.id} />
        <section className="sky-target-references"><h3>Catalogue references</h3><ul>{references.map((reference, i) => {
          const url = safeProvenanceUrl(reference.url);
          return <li key={`${reference.url}-${i}`}>{url ? <a href={url} target="_blank" rel="noreferrer">{reference.label || 'Catalogue source'} ↗</a> : reference.label || 'Reference unavailable'}</li>;
        })}</ul>{sourceUrl && !references.some(item => item.url === sourceUrl) && <a href={sourceUrl} target="_blank" rel="noreferrer">Catalogue record ↗</a>}</section>
      </aside>}
    </div>
    {planetViewOpen && <Suspense fallback={<p role="status">Opening 3D planet viewer…</p>}><SolarSystem3D selectedId={selectedBody} targets={targets} onSelect={setSelectedBody} onClose={() => setPlanetViewOpen(false)} /></Suspense>}
  </section>;
}
