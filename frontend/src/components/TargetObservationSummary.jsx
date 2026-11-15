import React, { useState } from 'react';
import { resolvePreviewUrl } from '../api.js';
import { MetadataDetails } from './MetadataDetails.jsx';

function TargetPreview({ frame, fixture }) {
  const [status, setStatus] = useState('loading');
  const [attempt, setAttempt] = useState(0);
  return <div className="target-observation-preview">
    <p><strong>{fixture ? 'Development fixture preview' : 'Backend-derived SPHEREx PNG'}</strong></p>
    {status === 'loading' && <p role="status">Loading selected observation preview…</p>}
    <img key={attempt} src={resolvePreviewUrl(frame.preview_url, fixture)} alt={`${fixture ? 'Fictional sample' : 'SPHEREx observation'} ${frame.observation.product_id}`}
      onLoad={() => setStatus('loaded')} onError={() => setStatus('error')} hidden={status !== 'loaded'} />
    {status === 'error' && <div role="alert"><p>Preview unavailable. Its product metadata is retained.</p><button type="button" onClick={() => { setStatus('loading'); setAttempt(value => value + 1); }}>Retry selected preview</button></div>}
    <MetadataDetails observation={frame.observation} metadata={frame.metadata} fixture={fixture} compact />
  </div>;
}

export function TargetObservationSummary({ search, sequence, frame, fixture, onOpenSequence }) {
  if (!search?.result) return <p>No archive search is attached to this target yet. Catalogue coordinates are not propagated to observation dates.</p>;
  return <>
    {fixture && <p className="fixture-notice">Development fixture — not real SPHEREx data</p>}
    <p>{search.result.observations.length} observations covering this sky field.</p>
    <details><summary>Returned field coverage</summary><pre>{JSON.stringify(search.result.coverage_summary, null, 2)}</pre></details>
    <ul className="warning-list">{search.result.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
    {frame && <TargetPreview key={frame.observation.id + frame.preview_url} frame={frame} fixture={fixture} />}
    {sequence && <ul className="warning-list">{sequence.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
    <button type="button" onClick={onOpenSequence}>Open observations / sequence</button>
  </>;
}
