import React, { useEffect, useRef, useState } from 'react';
import { AppHeader } from './components/AppHeader.jsx';
import { SearchPanel } from './components/SearchPanel.jsx';
import { SearchResults } from './components/SearchResults.jsx';
import { SkyViewer } from './components/SkyViewer.jsx';
import { Timeline } from './components/Timeline.jsx';
import { ContextPanel } from './components/ContextPanel.jsx';
import { SkyExplorer } from './components/SkyExplorer.jsx';
import { TargetObservationSummary } from './components/TargetObservationSummary.jsx';
import { targetCatalogue, getCatalogueTarget, hasCatalogueCoordinates, targetIdFromSearch, searchWithTarget } from './data/targetCatalogue.js';
import { useHealth } from './hooks/useHealth.js';
import { INITIAL_INPUTS, searchObservations, validateSearch } from './search.js';
import { FIXTURE_LABEL } from './fixtures/developmentData.js';
import { buildSequence, createRequestOwner, getEvidence, makeSelection, missingPreviewIds, saveInvestigation, verificationIssues, verifyInvestigation } from './workflow.js';

const emptySearch = { status: 'idle', result: null, query: null, error: null };

export default function App() {
  const { health, retry } = useHealth();
  const [inputs, setInputs] = useState({ ...INITIAL_INPUTS });
  const [errors, setErrors] = useState({});
  const [mode, setMode] = useState('live');
  const [scenario, setScenario] = useState('success');
  const [search, setSearch] = useState(emptySearch);
  const [selected, setSelected] = useState([]);
  const [sequence, setSequence] = useState(null);
  const [index, setIndex] = useState(0);
  const [displayedIndex, setDisplayedIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [compareMode, setCompareMode] = useState('single');
  const [reference, setReference] = useState(0);
  const [blinkInterval, setBlinkInterval] = useState(800);
  const [groups, setGroups] = useState({});
  const [investigationId, setInvestigationId] = useState(null);
  const [verification, setVerification] = useState(null);
  const [busy, setBusy] = useState('');
  const [job, setJob] = useState(null);
  const [operationError, setOperationError] = useState(null);
  const [message, setMessage] = useState('');
  const [drawer, setDrawer] = useState(null);
  const [contextOpen, setContextOpen] = useState(true);
  const [tab, setTab] = useState('details');
  const [view, setView] = useState('sky');
  const [targetId, setTargetId] = useState(() => targetIdFromSearch(window.location.search));
  const targetRef = useRef(targetId);
  const owner = useRef(null);
  if (!owner.current) owner.current = createRequestOwner();
  const frames = sequence?.previews || [];
  const fixture = mode === 'fixture';
  const capabilities = health.data?.capabilities;
  const canProcess = fixture || (capabilities?.archive_access === 'available' && capabilities?.image_processing === 'available');
  const target = getCatalogueTarget(targetId);

  useEffect(() => {
    const pop = () => selectTarget(targetIdFromSearch(window.location.search), false);
    window.addEventListener('popstate', pop);
    return () => window.removeEventListener('popstate', pop);
  }, []);

  useEffect(() => () => owner.current.cancel(), []);
  useEffect(() => {
    if (!playing || compareMode === 'blink' || frames.length < 2) return;
    const timer = setInterval(() => setIndex(value => (value + 1) % frames.length), 1200 / speed);
    return () => clearInterval(timer);
  }, [playing, compareMode, frames.length, speed]);
  useEffect(() => {
    if (!drawer) return;
    document.getElementById(drawer === 'search' ? 'search-title' : 'results-title')?.focus();
  }, [drawer]);

  function closeDrawer() {
    const opener = drawer === 'search' ? 'regions-button' : 'observations-button';
    setDrawer(null);
    document.getElementById(opener)?.focus();
  }

  function clearSequence() {
    setPlaying(false); setSequence(null); setIndex(0); setDisplayedIndex(0);
    setReference(0); setCompareMode('single'); setGroups({});
    setInvestigationId(null); setVerification(null); setJob(null);
  }

  function clearResults() {
    owner.current.cancel(); setBusy(''); clearSequence(); setSelected([]);
    setSearch(emptySearch); setOperationError(null); setMessage(''); setDrawer('search');
  }

  function resetWorkspace() {
    clearResults(); setInputs({ ...INITIAL_INPUTS }); setErrors({}); setSpeed(1);
  }

  function changeMode(value) { clearResults(); setErrors({}); setMode(value); }
  function changeScenario(value) { clearResults(); setScenario(value); }

  function changeSelection(ids) {
    owner.current.cancel(); setBusy(''); clearSequence(); setSelected(ids);
    setOperationError(null); setMessage('');
  }

  function changeIndex(value) { setPlaying(false); setIndex(value); setDisplayedIndex(value); }
  function changeCompareMode(value) { setPlaying(false); setCompareMode(value); }

  function selectTarget(id, writeHistory = true) {
    const next = getCatalogueTarget(id);
    if (targetRef.current !== (next?.id || null)) {
      owner.current.cancel(); clearSequence(); setSearch(emptySearch); setSelected([]);
      setBusy(''); setOperationError(null); setMessage(''); setDrawer(null); setErrors({});
      targetRef.current = next?.id || null; setTargetId(next?.id || null);
      if (hasCatalogueCoordinates(next)) setInputs(previous => ({ ...previous, ra_deg: String(next.ra_deg), dec_deg: String(next.dec_deg) }));
      if (writeHistory) window.history.pushState(null, '', window.location.pathname + searchWithTarget(window.location.search, next?.id) + window.location.hash);
    }
    setPlaying(false); setView('sky');
  }

  function searchTarget(next) {
    if (!hasCatalogueCoordinates(next)) return;
    const fields = { ...inputs, ra_deg: String(next.ra_deg), dec_deg: String(next.dec_deg) };
    const validation = validateSearch(fields); setInputs(fields); setErrors(validation.errors);
    setMode('live'); setView('sequence');
    if (!validation.query || capabilities?.archive_access !== 'available') { setDrawer('search'); return; }
    runSearch(validation.query, 'live');
  }

  function navigate(section) {
    setPlaying(false);
    if (section === 'sky') { setView('sky'); setDrawer(null); return; }
    setView('sequence');
    if (section === 'observations') setDrawer('observations');
    else {
      setDrawer(null);
      if (section === 'explore') {
        document.getElementById('explore')?.focus();
      } else {
        setPlaying(false); setContextOpen(true); setTab(section);
        requestAnimationFrame(() => document.getElementById('context-panel')?.focus());
      }
    }
  }

  async function submitSearch(event) {
    event?.preventDefault();
    const validation = validateSearch(inputs); setErrors(validation.errors);
    if (!validation.query) {
      setDrawer('search');
      requestAnimationFrame(() => document.getElementById(Object.keys(validation.errors)[0])?.focus());
      return;
    }
    return runSearch(validation.query);
  }

  async function runSearch(query, requestMode = mode) {
    if (search.status === 'loading' || (requestMode === 'live' && capabilities?.archive_access !== 'available')) return;
    setView('sequence');
    const ticket = owner.current.start();
    clearSequence(); setSelected([]); setBusy(''); setMessage(''); setOperationError(null);
    const linkedTarget = getCatalogueTarget(targetRef.current);
    const fieldTargetId = linkedTarget && query.ra_deg === linkedTarget.ra_deg && query.dec_deg === linkedTarget.dec_deg ? linkedTarget.id : null;
    setSearch({ status: 'loading', result: null, query, error: null, targetId: fieldTargetId });
    try {
      const result = await searchObservations(query, { mode: requestMode, scenario, signal: ticket.signal });
      if (!ticket.isCurrent()) return;
      setSearch({ status: result.observations.length ? 'success' : 'empty', result, query, error: null, targetId: fieldTargetId });
      setDrawer('observations');
    } catch (error) {
      if (!ticket.isCurrent()) return;
      setSearch({ status: 'error', result: null, query, error, targetId: fieldTargetId }); setDrawer('observations');
    }
  }

  async function execute(label, action) {
    if (busy || search.status === 'loading') return;
    const ticket = owner.current.start();
    setBusy(label); setJob(null); setMessage(''); setOperationError(null); setPlaying(false);
    try { await action(ticket); }
    catch (error) {
      if (!ticket.isCurrent()) return;
      setOperationError(error);
      if (error.status === 404) setInvestigationId(null);
    } finally { if (ticket.isCurrent()) setBusy(''); }
  }

  function generate() {
    if (!canProcess) return;
    execute('Preparing sequence', async ticket => {
      const selection = makeSelection(search.result, search.query, selected);
      clearSequence();
      const result = await buildSequence(selection, { mode, scenario, observations: search.result.observations, signal: ticket.signal,
        onStatus: status => { if (ticket.isCurrent()) setJob(status); } });
      if (!ticket.isCurrent()) return;
      setSequence(result); setDrawer(null); setContextOpen(true); setTab('details');
      setReference(result.previews.length > 1 ? 1 : 0);
      setGroups(Object.fromEntries(result.previews.map((frame, i) => [frame.observation.id, i === result.previews.length - 1 ? 'reserved' : 'training'])));
      setMessage(`${result.previews.length} previews ready. Playback loops chronologically.`);
    });
  }

  async function ensureInvestigation(ticket) {
    if (investigationId) return investigationId;
    if (!sequence || fixture) throw new Error('A live processed sequence is required.');
    const id = await saveInvestigation(sequence.selection, sequence.jobId, ticket.signal);
    if (!ticket.isCurrent()) throw new DOMException('Aborted', 'AbortError');
    setInvestigationId(id);
    return id;
  }

  function save() {
    if (fixture || !sequence) return;
    execute('Saving investigation', async ticket => {
      await ensureInvestigation(ticket);
      if (ticket.isCurrent()) setMessage('Investigation saved. Evidence export is available.');
    });
  }

  function verify() {
    if (fixture || !sequence || capabilities?.motion_verification !== 'available' || capabilities?.archive_access !== 'available') return;
    const observations = frames.map(frame => frame.observation);
    const issues = verificationIssues(observations, groups);
    if (issues.length) { setOperationError(new Error(issues.join(' '))); return; }
    execute('Verifying independent exposures', async ticket => {
      setVerification(null);
      const id = await ensureInvestigation(ticket);
      const result = await verifyInvestigation(id, observations, groups, ticket.signal, status => { if (ticket.isCurrent()) setJob(status); });
      if (!ticket.isCurrent()) return;
      setVerification(result); setTab('evidence'); setContextOpen(true);
      setMessage('Verification complete. Review the assumptions and limitations.');
    });
  }

  function download() {
    if (fixture || !investigationId) return;
    execute('Exporting evidence', async ticket => {
      const evidence = await getEvidence(investigationId, ticket.signal);
      if (!ticket.isCurrent()) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify(evidence, null, 2)], { type: 'application/json' }));
      const link = document.createElement('a'); link.href = url; link.download = `whylab-evidence-${investigationId}.json`;
      document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage('Evidence JSON downloaded.');
    });
  }

  const omitted = sequence ? missingPreviewIds(sequence) : [];
  const comparisonWarnings = compareMode === 'single' ? frames[displayedIndex]?.metadata?.warnings || []
    : [...(frames[index]?.metadata?.warnings || []), ...(frames[reference]?.metadata?.warnings || [])];
  const activePanel = view === 'sky' ? 'sky' : drawer === 'observations' ? 'observations' : contextOpen && ['investigate', 'evidence'].includes(tab) ? tab : 'explore';

  return <div className="app-shell" onKeyDown={event => { if (event.key === 'Escape' && drawer) { event.stopPropagation(); closeDrawer(); } }}>
    <a className="skip-link" href={view === 'sky' ? '#sky-explorer' : '#explore'}>Skip to sky workspace</a>
    <AppHeader health={health} onRetry={retry} onNavigate={navigate} activePanel={activePanel} fixture={fixture} />
    {fixture && <div className="fixture-banner" role="status">{FIXTURE_LABEL} · Synthetic calibration charts only</div>}
    <div hidden={view !== 'sky'} className="sky-homepage">
      <div className="sky-home-actions"><button type="button" onClick={() => { navigate('explore'); setDrawer('search'); }}>Search by sky coordinates</button><span>Reference sky for orientation · SPHEREx previews are generated separately</span></div>
      <SkyExplorer targets={targetCatalogue} selectedTarget={target} onSelectTarget={selectTarget} onSearchTarget={searchTarget}
        searchDisabled={capabilities?.archive_access !== 'available' || !!busy || search.status === 'loading'}
        observationContent={target && search.targetId === target.id ? <TargetObservationSummary search={search} sequence={sequence} frame={frames[displayedIndex]}
          fixture={fixture} onOpenSequence={() => navigate('observations')} /> : null} />
    </div>
    <main hidden={view === 'sky'} className={`workspace-layout ${contextOpen ? 'context-open' : 'context-closed'}`}>
      <section className="viewer-column" id="explore" tabIndex="-1" aria-label="Sky exploration workspace">
        <div className="viewer-topbar">
          <button type="button" id="regions-button" aria-expanded={drawer === 'search'} aria-controls="workspace-drawer" onClick={() => setDrawer(drawer === 'search' ? null : 'search')}>Sky regions <span aria-hidden="true">⌄</span></button>
          <button type="button" id="observations-button" aria-expanded={drawer === 'observations'} aria-controls="workspace-drawer" onClick={() => setDrawer(drawer === 'observations' ? null : 'observations')}>Observations {search.result ? `(${search.result.observations.length})` : ''}</button>
          <span className="field-coordinate-label">{search.query ? `RA ${search.query.ra_deg}° / DEC ${search.query.dec_deg}° / ${search.query.fov_arcmin}′` : 'Your next question starts with a sky field'}</span>
          {!contextOpen && <button type="button" onClick={() => setContextOpen(true)} aria-controls="context-panel">Show information</button>}
        </div>
        {drawer && <div className="workspace-drawer" id="workspace-drawer">
          {drawer === 'search' ? <SearchPanel inputs={inputs} onInputsChange={setInputs} errors={errors} onErrorsChange={setErrors}
            mode={mode} onModeChange={changeMode} scenario={scenario} onScenarioChange={changeScenario}
            loading={search.status === 'loading'} health={health} onSubmit={submitSearch} onReset={resetWorkspace} onClose={closeDrawer} />
            : <SearchResults search={search} mode={mode} onClear={clearResults} onRetry={submitSearch} selected={selected}
              onSelectedChange={changeSelection} onGenerate={generate} busy={!!busy || search.status === 'loading'} canProcess={canProcess} onClose={closeDrawer} />}
        </div>}
        <SkyViewer frames={frames} index={index} onIndexChange={changeIndex} playing={playing} onPlayingChange={setPlaying}
          speed={speed} mode={compareMode} reference={reference} blinkInterval={blinkInterval} fixture={fixture} onDisplayedIndexChange={setDisplayedIndex} warnings={sequence?.warnings || []} />
      </section>
      {contextOpen && <ContextPanel tab={tab} onTabChange={setTab} onCollapse={() => setContextOpen(false)} frames={frames}
        index={index} displayedIndex={displayedIndex} onIndexChange={changeIndex} reference={reference}
        onReferenceChange={value => { setPlaying(false); setReference(value); }} compareMode={compareMode} onCompareModeChange={changeCompareMode}
        blinkInterval={blinkInterval} onBlinkIntervalChange={setBlinkInterval} sequence={sequence} query={search.query}
        groups={groups} onGroupsChange={value => { setGroups(value); setVerification(null); }} verification={verification}
        investigationId={investigationId} onVerify={verify} onSave={save} onDownload={download} busy={busy} capabilities={capabilities} fixture={fixture} job={job} />}
      <Timeline frames={frames} index={index} displayedIndex={displayedIndex} onIndexChange={changeIndex} playing={playing}
        onPlayingChange={setPlaying} speed={speed} onSpeedChange={setSpeed} mode={compareMode} disabled={!!busy} />
    </main>
    {view !== 'sky' && sequence && (!contextOpen || compareMode !== 'single') && <div className="comparison-caveat"><p>Visual changes alone do not establish motion. Review the returned compatibility and quality warnings.</p>
      <ul className="warning-list">{sequence.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>
      {!!comparisonWarnings.length && <ul className="warning-list">{[...new Set(comparisonWarnings)].map((warning, i) => <li key={i}>{warning}</li>)}</ul>}
    </div>}
    <div className="workspace-status" role="status" aria-live="polite">
      {busy ? <><span>{busy} · {job?.status || 'Submitting request'}{job?.progress?.message ? ` · ${job.progress.message}` : ''}
        {job?.progress?.completed != null && job?.progress?.total != null ? ` (${job.progress.completed}/${job.progress.total})` : ''}</span>
        <button type="button" onClick={() => { owner.current.cancel(); setBusy(''); setJob(null); setMessage('Stopped waiting. The server job may still be running.'); }}>Stop waiting</button></> : message || 'Search the sky. Keep the evidence.'}
    </div>
    {operationError && <div className="workspace-error" role="alert"><strong>{operationError.code || 'Request error'}</strong><p>{operationError.message}</p>
      {operationError.status === 404 && <p>This session or job may have expired. Search again or regenerate the sequence.</p>}
      {operationError.details != null && <details><summary>Error details</summary><pre>{JSON.stringify(operationError.details, null, 2)}</pre></details>}
      <div className="actions"><button type="button" onClick={() => setOperationError(null)}>Dismiss</button><button type="button" onClick={() => setDrawer('observations')}>Review observations / rebuild</button></div>
    </div>}
    {!!omitted.length && <div className="partial-result"><strong>Partial sequence:</strong> no preview returned for {omitted.join(', ')}. Available frames remain playable.</div>}
    <footer className="app-footer"><span>SPHEREx WhyLab · Spot a change. Test the explanation. Share the evidence.</span><span>Independent student/hackathon project · Not an official NASA service</span></footer>
  </div>;
}
