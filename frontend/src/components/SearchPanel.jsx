import React from 'react';
import { MAX_FOV_ARCMIN } from '../search.js';
import { targetPresets } from '../data/targetPresets.js';
import { FIXTURE_LABEL } from '../fixtures/developmentData.js';

const fields = [
  { key: 'ra_deg', label: 'Right ascension (RA)', unit: 'degrees', hint: '0 ≤ RA < 360', min: 0 },
  { key: 'dec_deg', label: 'Declination (Dec)', unit: 'degrees', hint: '−90 ≤ Dec ≤ 90', min: -90, max: 90 },
  { key: 'fov_arcmin', label: 'Field of view (FOV)', unit: 'arcminutes', hint: `Greater than 0, up to ${MAX_FOV_ARCMIN} arcminutes`, min: 0, max: MAX_FOV_ARCMIN },
];

export function SearchPanel({ inputs, onInputsChange, errors, onErrorsChange, mode, onModeChange,
  scenario, onScenarioChange, loading, health, onSubmit, onReset, onClose }) {
  const blocked = mode === 'live' && health.status !== 'ready';
  const reason = health.status === 'checking' ? 'Connecting to your observation backend.'
    : health.status === 'error' ? 'The backend is not connected. Retry its connection or explicitly choose development fixtures.'
      : 'The observation backend is unavailable.';

  return <section className="search-panel" id="search" aria-labelledby="search-title">
    <div className="section-heading"><div><p className="eyebrow">01 / CHOOSE YOUR FIELD</p><h2 id="search-title" tabIndex="-1">Sky regions</h2></div>{onClose && <button type="button" className="icon-button" onClick={onClose} aria-label="Close sky regions">×</button>}</div>
    <p className="muted">Search downloaded observations first using ICRS coordinates. IRSA is checked in the background; every observation keeps its provenance.</p>
    <fieldset className="mode-picker"><legend>Data source</legend>
      <label><input type="radio" name="data-mode" value="live" checked={mode === 'live'} onChange={() => onModeChange('live')} /> Real data · downloaded first</label>
      <label><input type="radio" name="data-mode" value="fixture" checked={mode === 'fixture'} onChange={() => onModeChange('fixture')} /> Development fixtures</label>
    </fieldset>
    {mode === 'fixture' && <div className="fixture-notice"><strong>{FIXTURE_LABEL}</strong><p>Fictional responses and sample images for testing the interface.</p>
      <label htmlFor="fixture-scenario">Fixture scenario</label><select id="fixture-scenario" value={scenario} onChange={event => onScenarioChange(event.target.value)}>
        <option value="success">Success with nullable metadata</option><option value="empty">No observations</option><option value="error">Archive error</option><option value="partial">Partial sequence</option><option value="job-error">Sequence job error</option><option value="image-error">Image loading error</option>
      </select></div>}
    <form noValidate onSubmit={onSubmit} aria-busy={loading}>
      <div className="coordinate-fields">{fields.map(field => <div className="form-field" key={field.key}>
        <label htmlFor={field.key}>{field.label} <span className="muted">({field.unit})</span></label>
        <input id={field.key} name={field.key} type="number" step="any" required min={field.min} max={field.max} value={inputs[field.key]} aria-invalid={!!errors[field.key]} aria-describedby={`${field.key}-hint${errors[field.key] ? ` ${field.key}-error` : ''}`}
          onChange={event => { onInputsChange({ ...inputs, [field.key]: event.target.value }); onErrorsChange({ ...errors, [field.key]: undefined }); }} />
        <small id={`${field.key}-hint`}>{field.hint}</small>{errors[field.key] && <p className="field-error" id={`${field.key}-error`}>{errors[field.key]}</p>}
      </div>)}</div>
      {Object.values(errors).some(Boolean) && <p role="alert" className="field-error">Check the highlighted search fields.</p>}
      <div className="actions"><button className="primary" type="submit" disabled={loading || blocked}>{loading ? 'Searching…' : mode === 'fixture' ? 'Search fixture' : 'Search observations'} <span aria-hidden="true">→</span></button><button type="button" onClick={onReset}>Reset workspace</button></div>
      {blocked && <p className="notice">{reason}</p>}
    </form>
    <div className="presets"><h3>Target presets</h3><p id="preset-note" className="muted">Coordinates pending verification</p><div className="preset-buttons">{targetPresets.map(target => <button type="button" key={target.name} disabled aria-describedby="preset-note">{target.name}</button>)}</div></div>
    <p className="small muted">Independent student/hackathon project. Not an official NASA service.</p>
  </section>;
}
