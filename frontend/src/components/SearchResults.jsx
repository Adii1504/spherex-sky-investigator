import React from 'react';
import { FIXTURE_LABEL } from '../fixtures/developmentData.js';
import { formatUtc } from '../search.js';
import { MetadataDetails } from './MetadataDetails.jsx';

export function SearchResults({ search, mode, onClear, onRetry, selected = [], onSelectedChange, onGenerate, busy = false, canProcess = false, onClose }) {
  const fixture = mode === 'fixture';
  const searching = search.status === 'loading';
  const observations = search.result?.observations || [];
  const selectedObservations = observations.filter(observation => selected.includes(observation.id));
  const validDates = selectedObservations.filter(observation => observation.observed_at != null && observation.observed_at !== '')
    .map(observation => new Date(observation.observed_at).getTime()).filter(Number.isFinite).sort((a, b) => a - b);
  const span = validDates.length ? `${formatUtc(validDates[0])} — ${formatUtc(validDates[validDates.length - 1])}` : 'Date range unavailable';
  const selectionInvalid = !selected.length || selected.length > 100 || selectedObservations.length !== selected.length;
  function toggle(id, checked) {
    onSelectedChange?.(checked ? [...selected, id] : selected.filter(value => value !== id));
  }
  return <section className="results-panel" id="observations" aria-labelledby="results-title" aria-busy={searching}>
    <div className="section-heading"><div><p className="eyebrow">02 / THE OBSERVATIONAL RECORD</p><h2 id="results-title" tabIndex="-1">Observations</h2></div>{onClose && <button type="button" className="icon-button" onClick={onClose} aria-label="Close observations">×</button>}</div>
    {fixture && <p className="fixture-notice"><strong>{FIXTURE_LABEL}</strong></p>}
    <div role="status" aria-atomic="true">
      {search.status === 'idle' && <p className="muted">Open Sky regions and search to find dated observations.</p>}
      {searching && <p>Searching {fixture ? 'the selected fixture' : 'the archive'}…</p>}
      {search.status === 'empty' && <p><strong>No observations found for this query.</strong> Try different coordinates or a different field size.</p>}
      {search.status === 'success' && <p>{observations.length} observations returned. Choose observations for your sequence.</p>}
    </div>
    {search.query && <p className="query-summary">RA {search.query.ra_deg}° · Dec {search.query.dec_deg}° · FOV {search.query.fov_arcmin} arcmin</p>}
    {search.error && <div className="error-box" role="alert"><h3>Search could not complete</h3><p>{search.error.message}</p>{search.error.code && <p>Error: <code>{search.error.code}</code></p>}
      {search.error.details != null && <details><summary>Backend error details</summary><pre>{JSON.stringify(search.error.details, null, 2)}</pre></details>}
      <p>Your search values are preserved. Retry or edit the query.{!fixture && ' No fixture has been substituted.'}</p><button type="button" onClick={onRetry} disabled={busy}>Retry search</button>
    </div>}
    {!!search.result?.warnings?.length && <details className="search-warnings" open><summary>Search warnings ({search.result.warnings.length})</summary><ul className="warning-list">{search.result.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>}
    {search.result && <details className="coverage"><summary>Coverage summary</summary><pre>{JSON.stringify(search.result.coverage_summary, null, 2)}</pre></details>}
    {!!observations.length && <>
      <div className="selection-summary"><strong>{selected.length} selected</strong><p>{span}</p><div className="actions"><button type="button" disabled={busy || !selected.length} onClick={() => onSelectedChange?.([])}>Clear selection</button><button type="button" className="primary" disabled={busy || selectionInvalid || !canProcess} onClick={onGenerate}>Generate sequence <span aria-hidden="true">→</span></button></div>
        {!canProcess && <p className="muted small">Image preparation is unavailable. Check backend capabilities.</p>}
        {selected.length > 100 && <p className="field-error">Select no more than 100 observations.</p>}
      </div>
      <ul className="observation-list">{observations.map(observation => <li className={`observation-row ${selected.includes(observation.id) ? 'selected' : ''}`} key={observation.id}>
        <label className="observation-choice"><input type="checkbox" disabled={busy} checked={selected.includes(observation.id)} onChange={event => toggle(observation.id, event.target.checked)} /><span><strong>{formatUtc(observation.observed_at)}</strong><small>{observation.product_id}</small></span></label>
        <details><summary>Metadata · Detector {observation.detector ?? 'Unavailable'}</summary><MetadataDetails observation={observation} fixture={fixture} compact /></details>
      </li>)}</ul>
    </>}
    <div className="actions drawer-footer"><button type="button" disabled={search.status === 'idle'} onClick={onClear}>{searching ? 'Cancel search' : 'Start new search'}</button></div>
  </section>;
}
