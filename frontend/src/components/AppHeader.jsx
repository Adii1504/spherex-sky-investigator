import React from 'react';

import {API_BASE} from '../api.js';

const capabilities = [
  ['archive_access', 'Archive search'],
  ['image_processing', 'Image preparation'],
  ['motion_verification', 'Motion verification'],
];

export function AppHeader({ health, onRetry, onNavigate, activePanel = 'explore', fixture = false }) {
  const connected = health.status === 'ready';
  const available = connected && health.data.capabilities.archive_access === 'available';
  const connection = health.status === 'checking' ? 'Checking backend' : connected ? 'Backend connected' : 'Backend offline';
  return <header className="topbar">
    <a className="wordmark" href="#explore" onClick={event => { event.preventDefault(); onNavigate?.('explore'); }} aria-label="SPHEREx WhyLab — Explore">
      <svg className="wordmark-icon" viewBox="0 0 36 36" aria-hidden="true"><circle cx="18" cy="18" r="11" /><path d="M18 1v10m0 14v10M1 18h10m14 0h10M10 10l4 4m8 8 4 4" /></svg>
      <span>SPHEREx <strong>WhyLab</strong><small>SPOT A CHANGE. TEST THE EXPLANATION.</small></span>
    </a>
    <nav className="primary-nav" aria-label="Workspace navigation">{[['sky', 'Sky explorer'], ['explore', 'Sequence viewer'], ['observations', 'Observations'], ['investigate', 'Investigate'], ['evidence', 'Evidence'], ['games','Game Zone']].map(([key, label]) =>
      <button type="button" key={key} className={activePanel === key ? 'active' : ''} aria-current={activePanel === key ? 'page' : undefined} onClick={() => onNavigate?.(key)}>{label}</button>
    )}<a href={`${API_BASE}/processing/`}>Processing viewer</a></nav>
    <details className="health-diagnostics">
      <summary><span className={`status-dot ${available ? 'available' : ''}`} aria-hidden="true" /><span>{connection}</span><span aria-hidden="true">⌄</span></summary>
      <div className="diagnostics-content">
        <p className="eyebrow">SERVICE DIAGNOSTICS</p><p role="status">{connection}</p>
        <dl className="capability-list">{capabilities.map(([key, label]) => {
          const value = connected ? health.data.capabilities[key] : health.status === 'checking' ? 'checking' : 'connection error';
          return <div key={key}><dt>{label}</dt><dd>{value}</dd></div>;
        })}</dl>
        {health.error && <p className="notice">{health.error.message} Live actions stay unavailable. Development fixtures require an explicit choice.</p>}
        <button type="button" onClick={onRetry} disabled={health.status === 'checking'}>Retry connection</button>
        <p className="project-note">Independent student/hackathon project. Not an official NASA service.</p>
      </div>
    </details>
    {fixture && <span className="header-fixture">FIXTURE MODE</span>}
  </header>;
}
