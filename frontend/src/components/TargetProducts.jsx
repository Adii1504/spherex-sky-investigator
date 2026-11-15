import React, {useEffect, useState} from 'react';
import {loadProduct, loadTargetObservations} from '../skyData.js';
import {formatUtc, safeProvenanceUrl} from '../search.js';
import {CandidateNotes} from './CandidateNotes.jsx';
import {API_BASE} from '../api.js';

function Links({title, items = []}) {
  const links = items.filter(item => safeProvenanceUrl(item.url));
  return <section><h4>{title}</h4>{links.length ? <ul>{links.map((item, i) =>
    <li key={i}><a href={safeProvenanceUrl(item.url)} target="_blank" rel="noreferrer">{item.label}</a></li>)}</ul>
    : <p>{title} unavailable for this observation.</p>}</section>;
}

export function ObservationProduct({observation, productLoader = loadProduct}) {
  const [attempt, setAttempt] = useState(0);
  const [preview, setPreview] = useState({status: 'loading'});
  const [quality, setQuality] = useState({status: 'loading'});
  useEffect(() => {
    const controller = new AbortController();
    let active = true, objectUrl;
    setPreview({status: 'loading'}); setQuality({status: 'loading'});
    if (!observation.available) {
      setPreview({status: 'unavailable'}); setQuality({status: 'unavailable'});
      return () => { active = false; controller.abort(); };
    }
    productLoader(observation.product_id, 'preview', controller.signal).then(blob => {
      if (!active) return;
      objectUrl = URL.createObjectURL(blob);
      setPreview({status: 'ready', url: objectUrl});
    }).catch(error => { if (active) setPreview({status: 'error', message: error.message}); });
    productLoader(observation.product_id, 'quality', controller.signal).then(text => {
      // Keep the JSON text intact: uint64 FLAGS may exceed JavaScript's exact integer range.
      const parsed = JSON.parse(text);
      if (parsed.product_id !== observation.product_id) throw new Error('Quality report belongs to a different product.');
      if (active) setQuality({status: 'ready', text});
    }).catch(error => { if (active) setQuality({status: 'error', message: error.message}); });
    return () => { active = false; controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [observation.product_id, observation.available, attempt, productLoader]);
  const prediction = observation.predicted_position;
  const dataset = observation.dataset;
  const screen = dataset?.detection_screen;
  return <section className="target-product" aria-label={`Product ${observation.product_id}`}>
    <h4>{observation.product_id}</h4>
    <p className="sky-provisional">{observation.provisional ? 'Provisional · ' : ''}{observation.association_status} · {observation.astrometry_status}</p>
    <p>{prediction ? `Supplied observation prediction: RA ${prediction.ra_deg}°, Dec ${prediction.dec_deg}°. Marker is a predicted position only.`
      : 'Observation-specific propagated coordinates unavailable. No catalogue-position marker is substituted.'}</p>
    {dataset && <section aria-label="Supplied dataset evidence">
      <h4>Supplied dataset evidence</h4>
      <p>{dataset.filename}</p>
      <p>Astrometry: {dataset.adopted_astrometry.source_catalogue} · {dataset.adopted_astrometry.source_id} · Reference epoch {dataset.adopted_astrometry.ref_epoch_jyear}</p>
      <p>{dataset.adopted_astrometry.notes}</p>
      <p>{dataset.propagation.rv_status} · {dataset.propagation.time_scale_assumption}. {dataset.propagation.note}</p>
      <p>Coverage: {dataset.coverage.status} · edge clearance {dataset.coverage.edge_distance_px.toFixed(2)} pixels. {dataset.coverage.note}</p>
      {screen && <><p><strong>Detection screen: {screen.verdict}</strong> · Peak SNR {screen.snr_peak ?? 'unavailable'} · Control 99th percentile {screen.control_p99_snr ?? 'unavailable'} · {screen.control_n ?? 0} controls</p>
        <p>{screen.method_note}</p>{screen.note && <p>{screen.note}</p>}</>}
      {observation.file_wavelength && !observation.file_wavelength.unit && <p>Supplied wavelength table extrema: {observation.file_wavelength.min} – {observation.file_wavelength.max}. Unit absent; no conversion to microns is asserted.</p>}
      <p>SHA-256: <code>{observation.sha256}</code></p>
    </section>}
    {observation.fits_url && <a href={`${API_BASE}/api/observations/${encodeURIComponent(observation.product_id)}/fits`} download>Download original FITS</a>}
    <p><strong>Actual FITS-derived SPHEREx preview</strong> · separate from the background reference survey.</p>
    {preview.status === 'ready' ? <img src={preview.url} alt={`FITS preview ${observation.product_id}; predicted marker is not a detection`}
      onError={() => setPreview({status: 'error', message: 'Preview image could not be displayed.'})} />
      : <p role={preview.status === 'error' ? 'alert' : 'status'}>Preview {preview.status}{preview.message ? `: ${preview.message}` : '…'}</p>}
    <h4>Quality report</h4>
    {quality.status === 'ready' ? <details open><summary>Geometry and raw pixel quality — not source detection</summary><pre>{quality.text}</pre></details>
      : <p role={quality.status === 'error' ? 'alert' : 'status'}>Quality {quality.status}{quality.message ? `: ${quality.message}` : '…'}</p>}
    {(preview.status === 'error' || quality.status === 'error') && <button onClick={() => setAttempt(v => v+1)}>Retry product data</button>}
    <Links title="Product references" items={observation.references} />
    <Links title="Evidence" items={observation.evidence} />
    {!!observation.spectra?.length && <Links title="Spectra" items={observation.spectra} />}
  </section>;
}

export function TargetProducts({targetId, observationLoader = loadTargetObservations, productLoader = loadProduct}) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({status: 'loading'});
  const [selected, setSelected] = useState(null);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setState({status: 'loading', targetId}); setSelected(null);
    observationLoader(targetId, controller.signal).then(result => {
      if (result.target_id !== targetId) throw new Error('Mismatched target response.');
      if (!active) return;
      setState({status: 'ready', targetId, result});
      const requested = new URLSearchParams(window.location.search).get('product');
      setSelected(result.observations.find(o => o.product_id === requested)?.product_id || result.observations[0]?.product_id || null);
    }).catch(error => { if (active) setState({status: 'error', targetId, message: error.message}); });
    return () => { active = false; controller.abort(); };
  }, [targetId, attempt, observationLoader]);
  if (state.targetId !== targetId || state.status === 'loading') return <p role="status">Loading target observations…</p>;
  if (state.status === 'error') return <div role="alert"><p>{state.message}</p><button onClick={() => setAttempt(v => v+1)}>Retry target observations</button></div>;
  const observations = state.result.observations;
  const observation = observations.find(o => o.product_id === selected);
  return <section aria-label="Approved target products">
    {(state.result.warnings || []).map((text, i) => <p className="sky-provisional" key={i}>{text}</p>)}
    {!observations.length ? <p>No approved local products are linked to this target. Search the archive separately; field coverage does not identify a source.</p>
      : <><label>Available observations<select aria-label="Select target observation" value={selected || ''} onChange={e => setSelected(e.target.value)}>
        {observations.map(item => <option key={item.product_id} value={item.product_id}>{formatUtc(item.observed_at)} · Detector {item.detector ?? 'Unavailable'} · {item.product_id}</option>)}
      </select></label>
      {observation && <a className="inspect-observation" href={`?${new URLSearchParams({target:targetId,product:selected,inspect:'1'})}`}>Inspect observation ↗</a>}
      {observation && <><dl><div><dt>Date</dt><dd>{formatUtc(observation.observed_at)}</dd></div>
        <div><dt>Detector</dt><dd>{observation.detector ?? 'Unavailable'}</dd></div>
        <div><dt>File wavelength range</dt><dd>{observation.file_wavelength_um?.map(v => `${v} µm`).join(' – ') ?? 'Unavailable'}</dd></div>
        <div><dt>Position wavelength</dt><dd>{observation.position_wavelength_um == null ? 'Unavailable' : `${observation.position_wavelength_um} µm`}</dd></div></dl>
        <p>Measured quality flags: inspect the raw FITS quality report below. Unavailable values remain unavailable.</p>
        <ObservationProduct key={targetId+':'+selected} observation={observation} productLoader={productLoader} />
        <CandidateNotes key={targetId+':notes:'+selected} targetId={targetId} observationId={selected} /></>}
      </>}
  </section>;
}
