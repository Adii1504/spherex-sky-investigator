import React from 'react';
import { formatUtc } from '../search.js';
import { stepFrame } from '../viewer.js';

export function Timeline({ frames = [], index = 0, displayedIndex = index, onIndexChange, playing,
  onPlayingChange, speed = 1, onSpeedChange, disabled = false, mode = 'single' }) {
  const unavailable = disabled || !frames.length;
  const move = value => { onPlayingChange(false); onIndexChange(value); };
  const timestamp = frames[displayedIndex]?.observation.observed_at;
  return <section className="timeline" aria-label="Observation timeline">
    <div className="timeline-controls">
      <button type="button" className="circle-button" aria-label="Previous observation" title="Previous observation"
        disabled={unavailable || frames.length < 2} onClick={() => move(stepFrame(index, -1, frames.length))}>‹</button>
      <button type="button" className="circle-button" aria-label={playing ? 'Pause playback' : mode === 'blink' ? 'Start blink comparison' : 'Play sequence'}
        title={playing ? 'Pause playback' : mode === 'blink' ? 'Start blink comparison' : 'Play sequence'}
        disabled={unavailable || frames.length < 2} onClick={() => onPlayingChange(!playing)}>{playing ? 'Ⅱ' : '▶'}</button>
      <button type="button" className="circle-button" aria-label="Next observation" title="Next observation"
        disabled={unavailable || frames.length < 2} onClick={() => move(stepFrame(index, 1, frames.length))}>›</button>
      <label className="timeline-track"><span className="sr-only">{mode === 'blink' ? 'Observation A frame' : 'Observation frame'}</span>
        <input type="range" min="0" max={Math.max(0, frames.length - 1)} step="1" value={Math.min(index, Math.max(0, frames.length - 1))}
          aria-label={mode === 'blink' ? 'Observation A frame' : 'Observation frame'} aria-valuetext={frames.length ? `${index + 1} of ${frames.length}, ${formatUtc(frames[index]?.observation.observed_at)}` : 'No observations'}
          disabled={unavailable} onChange={event => move(Number(event.target.value))} />
      </label>
      <span className="frame-position">{frames.length ? String(displayedIndex + 1).padStart(2, '0') : '00'} / {String(frames.length).padStart(2, '0')}</span>
      <label className="speed-control">Speed<select aria-label="Playback speed" value={speed} disabled={unavailable} onChange={event => onSpeedChange(Number(event.target.value))}>
        <option value="0.5">0.5×</option><option value="1">1×</option><option value="2">2×</option>
      </select></label>
    </div>
    <div className="timeline-labels"><span>{frames.length ? formatUtc(frames[0].observation.observed_at) : 'No sequence loaded'}</span>
      <span>{frames.length > 1 ? formatUtc(frames[frames.length - 1].observation.observed_at) : ''}</span></div>
    {frames.length > 0 && <p className="timeline-current">{formatUtc(timestamp)} <span className="muted">· {mode === 'blink' ? 'Blink alternates A/B; pause to inspect.' : 'Playback loops in backend observation order.'}</span></p>}
  </section>;
}
