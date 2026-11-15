import React, {useEffect, useState} from 'react';
import {request} from '../api.js';

export function LocalProducts({onLoad}) {
  const [state, setState] = useState({status:'loading'});
  useEffect(() => {
    const controller = new AbortController();
    request('/local-products', undefined, controller.signal, {prefix:'/api'}).then(result => {
      if (!controller.signal.aborted) {setState({status:'ready', observations:result.observations}); onLoad?.(result.observations);}
    }).catch(error => {if (!controller.signal.aborted) setState({status:'error', message:error.message});});
    return () => controller.abort();
  }, [onLoad]);
  return <section className="catalog-lookup"><h3>Local FITS evidence · unassociated</h3>
    {state.status === 'loading' && <p role="status">Loading local product registry…</p>}
    {state.status === 'error' && <p role="status">Local product registry unavailable. {state.message}</p>}
    {state.status === 'ready' && (!state.observations.length ? <p>Unavailable: no unassociated local FITS products registered.</p> : <ul>{state.observations.map(o => <li key={o.product_id}>
      <a href={`?${new URLSearchParams({product:o.product_id,inspect:'1'})}`}>Inspect observation · {o.label || o.product_id}</a><p>{o.observed_at || 'Date: Unavailable'} · No catalogue association established.</p>
    </li>)}</ul>)}
  </section>;
}
