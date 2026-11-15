import {targetCoordinates} from './aladin.js';

// Equatorial right-handed axes: X RA=0, Y RA=90, Z north; degrees in, pc out.
export function equatorialXYZ(ra, dec, radius = 1) {
  if (![ra, dec, radius].every(Number.isFinite) || ra < 0 || ra >= 360 || dec < -90 || dec > 90 || radius <= 0) return null;
  const a = ra * Math.PI / 180, d = dec * Math.PI / 180;
  return [radius * Math.cos(d) * Math.cos(a), radius * Math.cos(d) * Math.sin(a), radius * Math.sin(d)];
}

export function trustedDistance(target) {
  const d = target?.distance;
  return d?.trustworthy === true && Number.isFinite(d.value_pc) && d.value_pc > 0
    && Number.isFinite(d.uncertainty_pc) && d.uncertainty_pc >= 0 && d.uncertainty_pc / d.value_pc <= .2
    && typeof d.provenance === 'string' && d.provenance.trim() && typeof d.method === 'string' && d.method.trim()
    ? d : null;
}

export function positionedSources(targets, spatial = false) {
  return targets.flatMap(target => {
    const c = targetCoordinates(target), distance = trustedDistance(target);
    if (!c || (spatial && !distance)) return [];
    return [{target, xyz: equatorialXYZ(c.ra, c.dec, spatial ? distance.value_pc : 1)}];
  });
}

export function candidateRecord(targetId, observationId, notes, evidence) {
  return {schema_version: 1, status: 'unverified', target_id: targetId || null,
    observation_id: observationId || null, notes: notes.slice(0, 4000),
    evidence_references: evidence.split('\n').map(s => s.trim()).filter(Boolean).slice(0, 20),
    saved_at: new Date().toISOString()};
}
