import React from 'react';
import {targetCoordinates} from '../aladin.js';

export function OfflineSky({targets, selectedId, onSelect, onCoordinate}) {
  return <div className="offline-atlas"><p>Bundled catalogue snapshot · SIMBAD / CDS · retrieved 2026-11-14. This coordinate chart has no survey imagery.</p>
    <svg viewBox="0 0 720 360" role="img" aria-label="Offline equatorial coordinate chart" onClick={e => {
      const r=e.currentTarget.getBoundingClientRect();
      if (r.width && r.height) onCoordinate?.({ra:Math.min(359.999999, Math.max(0,(e.clientX-r.left)/r.width*360)), dec:Math.max(-90,Math.min(90,90-(e.clientY-r.top)/r.height*180))});
    }}>
      {[0,60,120,180,240,300,360].map(ra => <g key={ra}><path d={`M${ra*2} 0V360`} /><text x={ra*2+4} y="180">{ra}°</text></g>)}
      {[-60,-30,0,30,60].map(dec => <path key={dec} d={`M0 ${180-dec*2}H720`} />)}
      {targets.map(t => {const c=targetCoordinates(t); return c && <g key={t.id} className="offline-source" role="button" tabIndex="0" aria-label={`Select ${t.name}`} onClick={e => {e.stopPropagation(); onSelect?.(t.id);}} onKeyDown={e => {if (e.key==='Enter' || e.key===' ') {e.preventDefault(); onSelect?.(t.id);}}}>
        <circle cx={c.ra*2} cy={180-c.dec*2} r={selectedId===t.id ? 7:5} fill={selectedId===t.id ? '#48c7d0':'#e3bd39'} /><title>{t.name}</title>
      </g>;})}
    </svg><p>ICRS degrees · RA increases right; north is up. Use the target list for names and details.</p>
  </div>;
}
