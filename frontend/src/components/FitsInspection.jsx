import React, {useEffect, useState} from 'react';
import {loadTargetObservations} from '../skyData.js';
import {ObservationProduct} from './TargetProducts.jsx';
import {CandidateNotes} from './CandidateNotes.jsx';
import {request} from '../api.js';

// Dedicated route around the existing FITS preview/quality component and contracts.
export function FitsInspection({targetId, productId}) {
  const [state, setState] = useState({status:'loading'}), [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setState({status:'loading'});
    (targetId ? loadTargetObservations(targetId, controller.signal) : request('/local-products', undefined, controller.signal, {prefix:'/api'})).then(result => {
      const observation = result.observations.find(o => o.product_id === productId);
      if (!observation) throw new Error('This observation is not associated with the selected target.');
      if (!controller.signal.aborted) setState({status:'ready', observation});
    }).catch(error => {if (!controller.signal.aborted) setState({status:'error', message:error.message});});
    return () => controller.abort();
  }, [targetId, productId, attempt]);
  return <main className="fits-inspection"><a href={`?${new URLSearchParams({...(targetId ? {target:targetId} : {}),product:productId})}`}>← Back to selected sky source</a>
    <h1>Inspect observation</h1><p>Target: {targetId || 'Unavailable — no catalogue association'} · Observation: {productId}</p>
    {state.status === 'loading' && <p role="status">Loading approved FITS association…</p>}
    {state.status === 'error' && <div role="alert"><p>{state.message}</p><button onClick={() => setAttempt(v => v+1)}>Retry inspection</button></div>}
    {state.status === 'ready' && <><dl>
      <dt>Observation date (supplied)</dt><dd>{state.observation.observed_at || 'Unavailable'}</dd>
      <dt>Detector</dt><dd>{state.observation.detector ?? 'Unavailable'}</dd>
      <dt>File wavelength range</dt><dd>{state.observation.file_wavelength_um?.map(v => `${v} µm`).join(' – ') || 'Unavailable'}</dd>
      <dt>Position wavelength</dt><dd>{state.observation.position_wavelength_um == null ? 'Unavailable' : `${state.observation.position_wavelength_um} µm`}</dd>
      </dl><ObservationProduct observation={state.observation} /></>}
    <CandidateNotes key={targetId+productId} targetId={targetId} observationId={productId} />
  </main>;
}
