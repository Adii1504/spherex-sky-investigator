import React from 'react';
import { FIXTURE_LABEL } from '../fixtures/developmentData.js';
import { formatUtc } from '../search.js';
import { MetadataDetails } from './MetadataDetails.jsx';
import {API_BASE} from '../api.js';

export function SearchResults({ search, mode, onClear, onRetry, onSync, onSearchLocal, onSearchLocalField, selected = [], onSelectedChange, onGenerate, busy = false, canProcess = false, onClose }) {
  const fixture = mode === 'fixture';
  const searching = search.status === 'loading';
  const local = search.source === 'local' || search.result?.coverage_summary?.source === 'imported-local';
  const synced = search.result?.coverage_summary?.source === 'local-and-archive';
  const observations = search.result?.observations || [];
  const selectedObservations = observations.filter(observation => selected.includes(observation.id));
  const validDates = selectedObservations.filter(observation => observation.observed_at != null && observation.observed_at !== '')
    .map(observation => new Date(observation.observed_at).getTime()).filter(Number.isFinite).sort((a, b) => a - b);
  const span = validDates.length ? `${formatUtc(validDates[0])} — ${formatUtc(validDates[validDates.length - 1])}` : 'Date range unavailable';
  const selectionInvalid = !selected.length || selected.length > 100 || selectedObservations.length !== selected.length;
  const outage=!fixture&&search.error?.code==='upstream_http_error'&&[500,502,503,504].includes(search.error?.details?.upstream_status);
  function toggle(id, checked) {
    onSelectedChange?.(checked ? [...selected, id] : selected.filter(value => value !== id));
  }
  return <section className="results-panel" id="observations" aria-labelledby="results-title" aria-busy={searching}>
    <div className="section-heading"><div><p className="eyebrow">02 / THE OBSERVATIONAL RECORD</p><h2 id="results-title" tabIndex="-1">Observations</h2></div>{onClose && <button type="button" className="icon-button" onClick={onClose} aria-label="Close observations">×</button>}</div>
    {fixture && <p className="fixture-notice"><strong>{FIXTURE_LABEL}</strong></p>}
    {local && <p className="local-dataset-notice"><strong>Downloaded real observations · {synced?'archive reconciled':'local search'}</strong><br/>{synced?'Local files are retained; matching archive metadata and additional observations are included.':'Your imported files load first. No live archive coverage is assumed.'}</p>}
    {local && search.sync && <div className="archive-sync-status" role="status">
      {search.sync.status==='checking' && <p>Checking IRSA in the background. Your downloaded observations remain usable.</p>}
      {search.sync.status==='unavailable' && <p>IRSA sync is unavailable. Continue with your downloaded data; the app will retry while this page is active.</p>}
      {['ready','partial'].includes(search.sync.status) && <p>{search.result.coverage_summary.archive_matches} local products matched; {search.result.coverage_summary.archive_added} additional archive observations added.{search.sync.status==='partial'&&' Some archive collections remain unavailable.'}</p>}
      {onSync && <button type="button" disabled={search.sync.status==='checking'} onClick={onSync}>Sync with IRSA</button>}
    </div>}
    <div role="status" aria-atomic="true">
      {search.status === 'idle' && <p className="muted">Open Sky regions and search to find dated observations.</p>}
      {searching && <p>Searching {fixture ? 'the selected fixture' : local ? 'downloaded observations' : 'the archive'}…</p>}
      {search.status === 'empty' && local && <p><strong>No downloaded observations cover this position and date range.</strong> Choose a bundled target in the local processing viewer, or retry the live archive later.</p>}
      {search.status === 'empty' && !local && (search.result?.coverage_summary?.collections_failed?.length ? <p><strong>Archive coverage is incomplete.</strong> No observations were returned by the collections that responded. Retry to check unavailable collections.</p> : <p><strong>No observations found for this query.</strong> Try different coordinates or a different field size.</p>)}
      {search.status === 'success' && <p>{observations.length} observations returned. Choose observations for your sequence.</p>}
    </div>
    {search.query && <p className="query-summary">RA {search.query.ra_deg}° · Dec {search.query.dec_deg}° · FOV {search.query.fov_arcmin} arcmin</p>}
    {search.error && <div className="error-box" role="alert"><h3>{outage?'IRSA archive search is temporarily unavailable':'Search could not complete'}</h3><p>{search.error.message}</p>{outage&&<p>The archive returned HTTP {search.error.details.upstream_status}. You do not need to restart the platform. Imported local FITS datasets remain available while the remote service recovers.</p>}{search.error.code && <p>Error: <code>{search.error.code}</code></p>}
      {search.error.details != null && <details><summary>Backend error details</summary><pre>{JSON.stringify(search.error.details, null, 2)}</pre></details>}
      <p>Your search values are preserved. Retry or edit the query.{!fixture && ' No fixture has been substituted.'}</p><button type="button" onClick={onRetry} disabled={busy}>Retry search</button>
      {!fixture && onSearchLocal && <p><button type="button" onClick={onSearchLocal} disabled={busy || searching}>Search downloaded observations</button><small>Search this same position in the real imported FITS files, without contacting IRSA.</small></p>}
      {outage&&<p className="local-dataset-recovery"><a href={`${API_BASE}/processing/`} target="_blank" rel="noreferrer">Open real imported FITS datasets ↗</a><small>Opens the local processing viewer in a new tab. Choose a real target dataset; your archive query stays here.</small></p>}
    </div>}
    {local && !search.error && <div className="actions"><button type="button" onClick={onRetry} disabled={busy || searching}>Refresh downloaded data</button><a href={`${API_BASE}/processing/`} target="_blank" rel="noreferrer">Browse bundled target datasets ↗</a></div>}
    {local && !searching && !!search.result?.coverage_summary?.available_fields?.length && <div className="local-field-choices"><p>Open a supplied target dataset (uses its observation-epoch positions):</p><div className="actions">{search.result.coverage_summary.available_fields.map(field => <button key={field.target_id} disabled={busy} onClick={() => onSearchLocalField?.({ra_deg:field.ra_deg,dec_deg:field.dec_deg,fov_arcmin:field.fov_arcmin},field.target_id)}>{field.label}</button>)}</div></div>}
    {!!search.result?.warnings?.length && <details className="search-warnings" open><summary>Search warnings ({search.result.warnings.length})</summary><ul className="warning-list">{search.result.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>}
    {search.result && <details className="coverage"><summary>Coverage summary</summary><pre>{JSON.stringify(search.result.coverage_summary, null, 2)}</pre></details>}
    {!!observations.length && <>
      <div className="selection-summary"><strong>{selected.length} selected</strong><p>{span}</p><div className="actions"><button type="button" disabled={busy || !selected.length} onClick={() => onSelectedChange?.([])}>Clear selection</button><button type="button" className="primary" disabled={busy || selectionInvalid || !canProcess} onClick={onGenerate}>Generate sequence <span aria-hidden="true">→</span></button></div>
        {!canProcess && <p className="muted small">Image preparation is unavailable. Check backend capabilities.</p>}
        {selected.length > 100 && <p className="field-error">Select no more than 100 observations.</p>}
      </div>
      <ul className="observation-list">{observations.map(observation => <li className={`observation-row ${selected.includes(observation.id) ? 'selected' : ''}`} key={observation.id}>
        <label className="observation-choice"><input type="checkbox" disabled={busy} checked={selected.includes(observation.id)} onChange={event => toggle(observation.id, event.target.checked)} /><span><strong>{formatUtc(observation.observed_at)}</strong><small>{observation.quality?.label || observation.product_id}</small></span></label>
        <details><summary>Metadata · Detector {observation.detector ?? 'Unavailable'}</summary><MetadataDetails observation={observation} fixture={fixture} compact /></details>
      </li>)}</ul>
    </>}
    <div className="actions drawer-footer"><button type="button" disabled={search.status === 'idle'} onClick={onClear}>{searching ? 'Cancel search' : 'Start new search'}</button></div>
  </section>;
}
