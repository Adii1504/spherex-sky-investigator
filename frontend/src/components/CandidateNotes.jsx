import React, {useState} from 'react';
import {candidateRecord} from '../coordinates.js';

export function CandidateNotes({targetId, observationId = null}) {
  const key = `whylab-candidate:${targetId}:${observationId || 'no-observation'}`;
  const [draft] = useState(() => {try {return JSON.parse(localStorage.getItem(key)) || {};} catch {return {};}});
  const [notes, setNotes] = useState(draft.notes || ''), [evidence, setEvidence] = useState((draft.evidence_references || []).join('\n'));
  const [message, setMessage] = useState('');
  const record = () => candidateRecord(targetId, observationId, notes, evidence);
  const save = () => {try {localStorage.setItem(key, JSON.stringify(record())); setMessage('Unverified candidate saved in this browser.');} catch {setMessage('Browser storage unavailable or full. Export the candidate instead.');}};
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(record(), null, 2)], {type:'application/json'}));
    const anchor = document.createElement('a'); anchor.href=url; anchor.download='unverified-candidate.json'; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <section className="candidate-notes"><h3>User annotations · unverified candidate</h3>
    <p>Source: {targetId || 'Unavailable'} · Observation: {observationId || 'Unavailable'}. Notes are personal annotations, not catalog facts or measured evidence.</p>
    <label>Candidate notes<textarea maxLength={4000} value={notes} onChange={e => setNotes(e.target.value)} /></label>
    <label>Evidence references (one product ID or URL per line)<textarea maxLength={8000} value={evidence} onChange={e => setEvidence(e.target.value)} /></label>
    <button onClick={save}>Mark candidate · unverified</button> <button onClick={download}>Export notes and references</button>
    <p role="status">{message}</p>
  </section>;
}
