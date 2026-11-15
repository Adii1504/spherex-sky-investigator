import React from 'react';
import { exposureConflict } from '../api.js';
import { formatUtc } from '../search.js';
import { MetadataDetails } from './MetadataDetails.jsx';

const sections = [
  ['details', 'Details'], ['compare', 'Compare'], ['investigate', 'Investigate'], ['evidence', 'Evidence'],
];

function Warnings({ title = 'Warnings and limitations', items = [] }) {
  if (!items.length) return null;
  return <section className="panel-section warning-section">
    <h3>{title}</h3>
    <ul className="warning-list">{[...new Set(items)].map((item, index) => <li key={index}>{item}</li>)}</ul>
  </section>;
}

function FrameChoice({ label, value, frames, onChange }) {
  return <label className="context-field">{label}
    <select value={value} onChange={event => onChange(Number(event.target.value))} disabled={!frames.length}>
      {frames.map((frame, index) => <option key={frame.observation.id} value={index}>
        {index + 1} · {formatUtc(frame.observation.observed_at)}
      </option>)}
    </select>
  </label>;
}

function ComparePanel({ frames, index, reference, onIndexChange, onReferenceChange,
  compareMode, onCompareModeChange, blinkInterval, onBlinkIntervalChange }) {
  const pairReady = frames.length > 1 && index !== reference;
  return <>
    <section className="panel-section comparison-controls">
      <h2>Compare observations</h2>
      {!frames.length && <p className="muted">Generate a sequence to choose two dated previews.</p>}
      <FrameChoice label="Observation A" frames={frames} value={index} onChange={onIndexChange} />
      <FrameChoice label="Observation B" frames={frames} value={reference} onChange={onReferenceChange} />
      {frames.length > 0 && index === reference && <p className="muted">Choose different observations for A and B to compare.</p>}
      <div className="comparison-mode-buttons" aria-label="Comparison mode">
        <button type="button" aria-pressed={compareMode === 'single'} onClick={() => onCompareModeChange('single')}>Single</button>
        <button type="button" disabled={!pairReady} aria-pressed={compareMode === 'blink'} onClick={() => onCompareModeChange('blink')}>Blink</button>
        <button type="button" disabled={!pairReady} aria-pressed={compareMode === 'side-by-side'} onClick={() => onCompareModeChange('side-by-side')}>Side by side</button>
      </div>
      {compareMode === 'blink' && <label className="context-field">Blink interval
        <select value={blinkInterval} onChange={event => onBlinkIntervalChange(Number(event.target.value))}>
          <option value={400}>0.4 seconds</option><option value={800}>0.8 seconds</option><option value={1600}>1.6 seconds</option>
        </select>
      </label>}
      <p className="muted">Inspect dates, wavelengths, masking and alignment warnings alongside visual changes.</p>
    </section>
    <section className="panel-section">
      <h3>Scientific difference imagery</h3>
      <button type="button" disabled>Difference unavailable</button>
      <p className="muted">The backend provides no scientific difference-image preview URL.</p>
    </section>
  </>;
}

function InvestigationPanel({ frames, sequence, query, groups, onGroupsChange, onVerify,
  onSave, investigationId, busy, capabilities, fixture }) {
  const observations = frames.map(frame => frame.observation);
  const assigned = observations.filter(observation => ['training', 'reserved'].includes(groups[observation.id]));
  const trainCount = assigned.filter(observation => groups[observation.id] === 'training').length;
  const reservedCount = assigned.filter(observation => groups[observation.id] === 'reserved').length;
  const duplicateIds = new Set(assigned.map(observation => observation.id)).size !== assigned.length;
  const overlap = duplicateIds || exposureConflict(observations, groups);
  const localOnly = assigned.length > 0 && assigned.every(o => o.release === 'imported-local');
  const canVerify = !busy && !fixture && sequence && trainCount >= 3 && reservedCount >= 1
    && !overlap && (localOnly || capabilities?.archive_access === 'available') && capabilities?.motion_verification === 'available';

  return <>
    <section className="panel-section">
      <h2>Test a finding</h2>
      <p>Fit an exploratory motion model using training exposures, then evaluate independent reserved exposures.</p>
      {query ? <dl className="metadata-list search-center">
        <div><dt>Search center / RA</dt><dd>{query.ra_deg}°</dd></div>
        <div><dt>Search center / Dec</dt><dd>{query.dec_deg}°</dd></div>
        <div><dt>Field of view</dt><dd>{query.fov_arcmin} arcmin</dd></div>
      </dl> : <p className="muted">Search a field and generate a sequence to configure an investigation.</p>}
      {query && <p className="muted">The investigation uses this searched field. To choose another center, run a new search.</p>}
      <button type="button" disabled={!!busy || fixture || !sequence || !!investigationId} onClick={onSave}>
        {investigationId ? 'Investigation saved' : 'Save investigation'}
      </button>
      {investigationId && <p className="muted">The processed selection is saved for evidence export.</p>}
    </section>
    {!!frames.length && <section className="panel-section">
      <h3>Independent observation groups</h3>
      <p className="group-summary">{trainCount} training · {reservedCount} reserved</p>
      <div className="role-assignments">{frames.map(frame => {
        const observation = frame.observation;
        return <label key={observation.id} className="role-assignment">
          <span>{formatUtc(observation.observed_at)}<small>{observation.product_id}</small></span>
          <select aria-label={`Role for ${observation.product_id}`} value={groups[observation.id] || 'exclude'} disabled={!!busy}
            onChange={event => onGroupsChange({ ...groups, [observation.id]: event.target.value })}>
            <option value="training">Training</option><option value="reserved">Reserved</option><option value="exclude">Exclude</option>
          </select>
        </label>;
      })}</div>
      {overlap && <p className="inline-error" role="alert">Repeated exposure identities are assigned. Exclude duplicate products within and across the groups.</p>}
      <p className="muted">At least three unique training exposures and one unique reserved exposure are required by the current science adapter.</p>
    </section>}
    <section className="panel-section">
      {fixture && <p className="fixture-notice">Development fixtures exercise the viewer. Motion verification requires live observations.</p>}
      {!fixture && capabilities?.motion_verification !== 'available' && <p className="muted">Motion verification is unavailable. Check backend capabilities.</p>}
      {!fixture && !localOnly && capabilities?.archive_access !== 'available' && <p className="muted">Archive access is required for remote observation verification.</p>}
      <button className="primary" type="button" disabled={!canVerify} onClick={onVerify}>Run exploratory verification</button>
      <p className="muted">Review the returned assumptions and limitations before interpreting any result.</p>
    </section>
  </>;
}

function EvidencePanel({ verification, investigationId, onDownload, busy, fixture }) {
  const outcomeHeadings = { supported: 'Supported', not_supported: 'Not supported', insufficient_evidence: 'Insufficient evidence' };
  return <>
    <section className="panel-section">
      <h2>Evidence record</h2>
      {verification ? <>
        <h3 className="outcome-heading">{outcomeHeadings[verification.outcome] || verification.outcome}</h3>
        <p><code>{verification.outcome}</code></p>
        <p className="muted">Preliminary investigation result.</p>
        {verification.processing_version && <p className="muted">Processing version {verification.processing_version}</p>}
      </> : <p className="muted">Run verification to review the backend outcome, assumptions and limitations.</p>}
    </section>
    {verification && <>
      <Warnings title="Assumptions" items={verification.assumptions} />
      <Warnings title="Limitations" items={verification.limitations} />
      <Warnings title="Verification warnings" items={verification.warnings} />
      <section className="panel-section"><details><summary>Returned measurements</summary>
        <pre>{JSON.stringify(verification.measurements, null, 2)}</pre>
      </details></section>
    </>}
    <section className="panel-section">
      <button type="button" disabled={!!busy || fixture || !investigationId} onClick={onDownload}>Download evidence JSON</button>
      {fixture && <p className="muted">Evidence export requires a live investigation.</p>}
      {!fixture && !investigationId && <p className="muted">Save an investigation in Investigate to enable export.</p>}
      {!verification && investigationId && <p className="muted">Verification is pending. This export includes the saved selection and processing record.</p>}
      {investigationId && <p className="muted">The download preserves the backend's provenance, settings and verification snapshots.</p>}
    </section>
  </>;
}

export function ContextPanel({ tab = 'details', onTabChange, onCollapse, frames = [], index = 0, displayedIndex = index,
  reference = 0, onIndexChange, onReferenceChange, compareMode = 'single', onCompareModeChange,
  blinkInterval = 800, onBlinkIntervalChange, sequence, query, groups = {}, onGroupsChange,
  verification, investigationId, onVerify, onSave, onDownload, busy, capabilities, fixture = false, job }) {
  const frame = frames[displayedIndex];
  const frameWarnings = Array.isArray(frame?.metadata?.warnings) ? frame.metadata.warnings : [];
  return <aside className="context-panel" aria-label="Observation information" id="context-panel" tabIndex={-1}>
    <div className="context-heading">
      <p className="eyebrow">{frames.length ? `Observation ${String(displayedIndex + 1).padStart(2, '0')} / ${String(frames.length).padStart(2, '0')}` : 'Field information'}</p>
      {onCollapse && <button type="button" className="icon-button" onClick={onCollapse} aria-label="Collapse information panel" title="Collapse information panel">›</button>}
    </div>
    <nav className="context-tabs" aria-label="Information sections">{sections.map(([value, label]) =>
      <button key={value} type="button" aria-pressed={tab === value} aria-controls="context-content" onClick={() => onTabChange(value)}>{label}</button>
    )}</nav>
    <div className="context-content" id="context-content">
      {tab === 'details' && <section className="panel-section">
        <h2>{frame?.observation.product_id || 'Explore a sky field'}</h2>
        <MetadataDetails observation={frame?.observation} metadata={frame?.metadata} fixture={fixture} />
        {sequence?.processing_version && <p className="muted">Processing version {sequence.processing_version}</p>}
        {sequence && <details><summary>Processing and shared display settings</summary><pre>{JSON.stringify({processing_settings: sequence.processing_settings, shared_display_settings: sequence.shared_display_settings}, null, 2)}</pre></details>}
      </section>}
      {tab === 'compare' && <ComparePanel frames={frames} index={index} reference={reference} onIndexChange={onIndexChange}
        onReferenceChange={onReferenceChange} compareMode={compareMode} onCompareModeChange={onCompareModeChange}
        blinkInterval={blinkInterval} onBlinkIntervalChange={onBlinkIntervalChange} />}
      {tab === 'investigate' && <InvestigationPanel frames={frames} sequence={sequence} query={query} groups={groups}
        onGroupsChange={onGroupsChange} onVerify={onVerify} onSave={onSave} investigationId={investigationId}
        busy={busy} capabilities={capabilities} fixture={fixture} />}
      {tab === 'evidence' && <EvidencePanel verification={verification} investigationId={investigationId}
        onDownload={onDownload} busy={busy} fixture={fixture} />}
      {busy && job && <p className="context-job" role="status">{job.status === 'queued' ? 'Queued for processing' : job.status === 'running' ? 'Processing observations' : job.status}
        {job.progress?.message && ` · ${job.progress.message}`}
      </p>}
      <Warnings title="Current preview warnings" items={frameWarnings} />
      <Warnings title="Sequence warnings" items={sequence?.warnings} />
    </div>
  </aside>;
}
