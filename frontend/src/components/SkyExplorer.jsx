import React, { useEffect, useId, useRef, useState } from 'react';
import { createSkyMap, REFERENCE_SURVEY, targetCoordinates } from '../aladin.js';
import { safeProvenanceUrl } from '../search.js';

export function SkyExplorer({ targets = [], selectedTarget = null, onSelectTarget, onSearchTarget,
  observationContent = null, mapFactory = createSkyMap, searchDisabled = false }) {
  const container = useRef(null);
  const detailPanel = useRef(null);
  const map = useRef(null);
  const callbacks = useRef({ onSelectTarget, targets });
  callbacks.current = { onSelectTarget, targets };
  const targetList = useRef(targets);
  targetList.current = targets;
  const selected = useRef(selectedTarget);
  selected.current = selectedTarget;
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState('loading');
  const [mapReady, setMapReady] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');
  const [hoveredId, setHoveredId] = useState(null);
  const [detailsOpen, setDetailsOpen] = useState(true);
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
      onSelect: id => callbacks.current.onSelectTarget?.(id),
      onHover: setHoveredId,
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
      value.setTargets(targetList.current); value.select(selected.current?.id || null);
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
  useEffect(() => {
    map.current?.select(selectedTarget?.id || null);
    if (selectedTarget) setDetailsOpen(true);
  }, [selectedTarget?.id]);
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
    <div className="sky-explorer-heading"><div><p className="eyebrow">THE SKY IS A PLACE TO ASK QUESTIONS</p><h1>Explore a field. Follow the evidence.</h1></div>
      <p>Choose a catalogue target or pan across the reference sky. SPHEREx field coverage and derived observation previews come from the archive workflow.</p>
    </div>
    <div className={`sky-explorer-layout ${detailsOpen && selectedTarget ? 'sky-details-open' : ''}`}>
      <div className="sky-map-column">
        <div className="sky-map-toolbar" role="group" aria-label="Reference sky controls">
          <button type="button" disabled={!mapReady} onClick={() => map.current?.reset()}>Reset / all sky</button>
          <button type="button" aria-label="Zoom in reference sky" disabled={!mapReady} onClick={() => map.current?.zoom(.5)}>+</button>
          <button type="button" aria-label="Zoom out reference sky" disabled={!mapReady} onClick={() => map.current?.zoom(2)}>−</button>
          <button type="button" disabled={!coordinate || !mapReady} onClick={() => map.current?.center(selectedTarget)}>Centre on target</button>
          {selectedTarget && <button type="button" aria-expanded={detailsOpen} aria-controls={detailId} onClick={() => setDetailsOpen(value => !value)}>{detailsOpen ? 'Hide target details' : 'Show target details'}</button>}
        </div>
        <div className="sky-map-stage">
          <div className="sky-map-host" ref={container} aria-label="Aladin Lite reference survey map" />
          {status === 'loading' && <div className="sky-map-state" role="status"><p>Loading Aladin Lite and the reference survey…</p></div>}
          {status === 'error' && <div className="sky-map-state sky-map-error" role="status"><h2>Reference sky unavailable</h2><p>{error}</p><button type="button" onClick={retryMap}>Retry reference sky</button><p>The target list and coordinate-based SPHEREx search remain available.</p></div>}
          {hovered && <div className="sky-marker-tooltip" role="tooltip"><strong>{hovered.name}</strong><span>{hovered.object_type ?? hovered.type ?? 'Type unavailable'}</span></div>}
        </div>
        <p className="sky-survey-credit"><strong>Reference survey: {REFERENCE_SURVEY.name}</strong> · CDS HiPS / Aladin Lite. These survey tiles are not SPHEREx observations. <a href={REFERENCE_SURVEY.url} target="_blank" rel="noreferrer">Survey metadata and credits ↗</a></p>
        {offline && <p className="sky-offline-notice" role="status">Network offline. New reference tiles and live archive searches may be unavailable; previously loaded tiles may remain visible.</p>}
        <section className="sky-target-catalogue" aria-labelledby="sky-targets-title">
          <div className="sky-target-search"><h2 id="sky-targets-title">Five starting points</h2><label htmlFor={`${detailId}-search`}>Find a target by name</label>
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
        <dl className="sky-coordinate-details"><div><dt>Right ascension</dt><dd>{coordinate ? `${coordinate.ra}°` : 'Unverified / unavailable'}</dd></div>
          <div><dt>Declination</dt><dd>{coordinate ? `${coordinate.dec}°` : 'Unverified / unavailable'}</dd></div>
          <div><dt>Coordinate frame</dt><dd>{selectedTarget.coordinate_frame ?? selectedTarget.frame ?? 'Unverified / unavailable'}</dd></div>
          <div><dt>Reference epoch</dt><dd>{selectedTarget.reference_epoch ?? selectedTarget.referenceEpoch ?? 'Unverified / unavailable'}</dd></div>
          <div><dt>Coordinate reference</dt><dd>{selectedTarget.coordinate_reference ?? selectedTarget.coordinateReference ?? 'Unavailable'}</dd></div>
          <div><dt>Astrometry status</dt><dd>{selectedTarget.astrometry_status ?? selectedTarget.astrometryStatus ?? 'Unverified'}</dd></div>
        </dl>
        <p className="sky-astrometry-note">{selectedTarget.astrometry_note ?? selectedTarget.astrometryNote ?? 'Coordinates are not propagated to SPHEREx observation epochs.'}</p>
        {selectedTarget.provisional && <p className="sky-provisional">Provisional for observation matching. Catalogue coordinates do not establish a SPHEREx detection.</p>}
        <div className="sky-target-actions"><button type="button" disabled={!coordinate || !mapReady} onClick={() => map.current?.center(selectedTarget)}>Centre on target</button>
          <button type="button" className="primary" disabled={!coordinate || searchDisabled} onClick={() => onSearchTarget?.(selectedTarget)}>Search SPHEREx field</button></div>
        {!coordinate && <p>Verified coordinates are required before this target can be used for field search.</p>}
        <section className="sky-field-evidence"><h3>Observations covering this sky field</h3><p>Archive coverage is not confirmation that the named target was detected.</p>{observationContent || <p className="muted">Search this field to inspect dates, detectors, wavelengths and products. Generate a sequence for its actual SPHEREx PNG previews.</p>}</section>
        <section className="sky-target-references"><h3>Catalogue references</h3><ul>{references.map((reference, i) => {
          const url = safeProvenanceUrl(reference.url);
          return <li key={`${reference.url}-${i}`}>{url ? <a href={url} target="_blank" rel="noreferrer">{reference.label || 'Catalogue source'} ↗</a> : reference.label || 'Reference unavailable'}</li>;
        })}</ul>{sourceUrl && !references.some(item => item.url === sourceUrl) && <a href={sourceUrl} target="_blank" rel="noreferrer">Catalogue record ↗</a>}</section>
      </aside>}
    </div>
  </section>;
}
