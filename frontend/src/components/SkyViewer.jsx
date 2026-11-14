import React, { useEffect, useRef, useState } from 'react';
import { resolvePreviewUrl } from '../api.js';
import { formatUtc } from '../search.js';
import { MAX_ZOOM, MIN_ZOOM, clampView, fittedImage, navigatorRectangle, recenterView } from '../viewer.js';

const HOME = { zoom: 1, x: 0, y: 0 };

function PreviewViewport({ frame, fixture, label }) {
  const stageRef = useRef(null);
  const pointers = useRef(new Map());
  const [stage, setStage] = useState({ width: 1, height: 1 });
  const [natural, setNatural] = useState({ width: 1, height: 1 });
  const [view, setView] = useState(HOME);
  const [grid, setGrid] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [imageState, setImageState] = useState({ src: null, status: 'loading' });
  const src = resolvePreviewUrl(frame.preview_url, fixture);
  const status = imageState.src === src && imageState.attempt === attempt ? imageState.status : 'loading';
  const image = fittedImage(stage.width, stage.height, natural.width, natural.height);
  const currentView = clampView(view, stage, image);
  const rectangle = navigatorRectangle(currentView, stage, image);

  useEffect(() => {
    const element = stageRef.current;
    const resize = () => setStage({ width: element.clientWidth, height: element.clientHeight });
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    // Native listener lets wheel zoom prevent page scrolling only over this viewport.
    const element = stageRef.current;
    const wheel = event => {
      event.preventDefault();
      setView(previous => clampView({ ...previous, zoom: previous.zoom * (event.deltaY < 0 ? 1.15 : 1 / 1.15) }, stage, image));
    };
    element.addEventListener('wheel', wheel, { passive: false });
    return () => element.removeEventListener('wheel', wheel);
  }, [stage.width, stage.height, image.width, image.height]);

  const zoom = factor => setView(previous => clampView({ ...previous, zoom: previous.zoom * factor }, stage, image));
  const pan = (x, y) => setView(previous => clampView({ ...previous, x: previous.x + x, y: previous.y + y }, stage, image));
  const keyDown = event => {
    if (event.target !== event.currentTarget) return;
    const actions = {
      '+': () => zoom(1.25), '=': () => zoom(1.25), '-': () => zoom(.8), '0': () => setView(HOME),
      ArrowLeft: () => pan(40, 0), ArrowRight: () => pan(-40, 0), ArrowUp: () => pan(0, 40), ArrowDown: () => pan(0, -40),
    };
    if (actions[event.key]) { event.preventDefault(); actions[event.key](); }
  };
  const pointerDown = event => {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
  };
  const pointerMove = event => {
    const previous = pointers.current.get(event.pointerId);
    if (!previous) return;
    const next = { x: event.clientX, y: event.clientY };
    if (pointers.current.size === 2) {
      const other = [...pointers.current.entries()].find(([id]) => id !== event.pointerId)?.[1];
      const before = Math.hypot(previous.x - other.x, previous.y - other.y);
      const after = Math.hypot(next.x - other.x, next.y - other.y);
      if (before > 0) zoom(after / before);
    } else pan(next.x - previous.x, next.y - previous.y);
    pointers.current.set(event.pointerId, next);
  };

  return <div className="viewport-shell">
    <div className="viewer-toolbar" role="group" aria-label={`${label} image controls`}>
      <button type="button" className="circle-button" aria-label={`Reset ${label} view`} title="Home: reset zoom and pan" onClick={() => setView(HOME)}>⌂</button>
      <button type="button" className="circle-button" aria-label={`Zoom in ${label}`} title="Zoom in" disabled={status !== 'loaded' || currentView.zoom >= MAX_ZOOM} onClick={() => zoom(1.25)}>+</button>
      <button type="button" className="circle-button" aria-label={`Zoom out ${label}`} title="Zoom out" disabled={status !== 'loaded' || currentView.zoom <= MIN_ZOOM} onClick={() => zoom(.8)}>−</button>
      <button type="button" className="circle-button" aria-label={`Toggle display grid for ${label}`} title="Display grid — UI aid, not detected sources" aria-pressed={grid} onClick={() => setGrid(value => !value)}>⊞</button>
    </div>
    <div className="viewport" ref={stageRef} tabIndex="0" role="region" aria-label={`${label} preview. Drag to pan, wheel or pinch to zoom. Arrow keys pan, plus and minus zoom, zero resets.`}
      onKeyDown={keyDown} onPointerDown={pointerDown} onPointerMove={pointerMove}
      onPointerUp={event => pointers.current.delete(event.pointerId)} onPointerCancel={event => pointers.current.delete(event.pointerId)}
      onLostPointerCapture={event => pointers.current.delete(event.pointerId)}
      style={{ touchAction: 'none', overflow: 'hidden', position: 'relative', cursor: currentView.zoom > 1 ? 'grab' : 'default' }}>
      <div className="image-plane" style={{ width: image.width * currentView.zoom, height: image.height * currentView.zoom,
        left: `calc(50% + ${currentView.x}px)`, top: `calc(50% + ${currentView.y}px)`, transform: 'translate(-50%, -50%)', position: 'absolute' }}>
        <img key={`${src}-${attempt}`} className="preview-image" src={src} draggable="false"
          alt={`${fixture ? 'Development fixture, fictional sample' : 'SPHEREx preview'}: ${frame.observation.product_id}`}
          style={{ width: '100%', height: '100%', display: 'block', opacity: status === 'loaded' ? 1 : 0 }}
          onLoad={event => { setNatural({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight }); setImageState({ src, attempt, status: 'loaded' }); }}
          onError={() => setImageState({ src, attempt, status: 'error' })} />
      </div>
      {grid && <div className="viewer-grid" aria-hidden="true" style={{ pointerEvents: 'none' }}><span>Display grid · UI aid only</span></div>}
      {status === 'loading' && <div className="image-status" role="status">Loading preview…</div>}
      {status === 'error' && <div className="image-status image-error" role="alert"><p>This preview could not be loaded. Its observation metadata is preserved.</p><button type="button" onPointerDown={event => event.stopPropagation()} onClick={() => setAttempt(value => value + 1)}>Retry image</button></div>}
    </div>
    {status === 'loaded' && <button type="button" className="viewport-navigator" aria-label={`Recenter ${label} image navigator; PNG view position, not sky coordinates`}
      title="Click to recenter the view within the PNG"
      style={{ aspectRatio: `${natural.width} / ${natural.height}` }}
      onClick={event => {
        // Keyboard activation recenters; pointer activation uses the thumbnail location.
        const bounds = event.currentTarget.getBoundingClientRect();
        const point = event.detail === 0 ? { x: .5, y: .5 } : { x: (event.clientX - bounds.left) / bounds.width, y: (event.clientY - bounds.top) / bounds.height };
        setView(recenterView(currentView, point, stage, image));
      }}>
      <img src={src} alt="" draggable="false" />
      <span className="navigator-window" style={{ left: `${rectangle.left * 100}%`, top: `${rectangle.top * 100}%`, width: `${rectangle.width * 100}%`, height: `${rectangle.height * 100}%` }} />
    </button>}
    <span className="viewer-zoom-label" aria-live="polite">{currentView.zoom.toFixed(1)}×</span>
  </div>;
}

export function SkyViewer({ frames = [], index = 0, playing = false, onPlayingChange, speed = 1,
  mode = 'single', reference = 0, blinkInterval = 800, fixture = false, onDisplayedIndexChange, warnings = [] }) {
  const container = useRef(null);
  const [blinkReference, setBlinkReference] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [fullscreenError, setFullscreenError] = useState('');
  const current = frames[index];
  const other = frames[reference];
  const shownIndex = mode === 'blink' && blinkReference ? reference : index;
  const shown = frames[shownIndex];
  const previewWarnings = mode === 'single' ? shown?.metadata?.warnings || []
    : [...(current?.metadata?.warnings || []), ...(other?.metadata?.warnings || [])];

  useEffect(() => { setBlinkReference(false); }, [mode, index, reference]);
  useEffect(() => {
    if (mode !== 'blink' || !playing || frames.length < 2 || reference === index) return;
    const timer = setInterval(() => setBlinkReference(value => !value), blinkInterval / speed);
    return () => clearInterval(timer);
  }, [mode, playing, frames.length, index, reference, blinkInterval, speed]);

  useEffect(() => { onDisplayedIndexChange?.(shownIndex); }, [shownIndex, onDisplayedIndexChange]);
  useEffect(() => {
    const changed = () => setFullscreen(document.fullscreenElement === container.current);
    document.addEventListener('fullscreenchange', changed);
    return () => document.removeEventListener('fullscreenchange', changed);
  }, []);

  const toggleFullscreen = async () => {
    setFullscreenError('');
    try {
      if (document.fullscreenElement === container.current) await document.exitFullscreen();
      else await container.current.requestFullscreen();
    } catch { setFullscreenError('Fullscreen is unavailable in this browser or window.'); }
  };

  return <section className={`sky-viewer ${fullscreen ? 'is-fullscreen' : ''}`} ref={container} aria-label="Sky image viewer">
    <div className="viewer-heading"><span className="eyebrow">{fixture ? 'DEVELOPMENT FIXTURE · NOT REAL SPHEREX DATA' : 'SPHEREx · DATED INFRARED OBSERVATIONS'}</span>
      <button type="button" className="circle-button" aria-label={fullscreen ? 'Exit fullscreen' : 'Enter fullscreen'} title={fullscreen ? 'Exit fullscreen' : 'Fullscreen'}
        disabled={typeof document !== 'undefined' && !document.fullscreenEnabled} onClick={toggleFullscreen}>⛶</button></div>
    {fullscreenError && <p role="alert" className="notice">{fullscreenError}</p>}
    {!current ? <div className="viewer-empty"><span className="empty-reticle" aria-hidden="true">＋</span><p className="eyebrow">YOUR PATCH OF SKY</p><h2>A question begins<br />with a closer look.</h2><p>Open Sky Regions to search a field.<br />Select observations, then generate a sequence.</p><p className="muted">No astronomical imagery is loaded.</p></div>
      : mode === 'side-by-side' && other ? <><div className="compare-stage">
        <figure className="comparison-frame"><PreviewViewport frame={current} fixture={fixture} label="A" /><figcaption className="comparison-caption">A · {current.observation.product_id}<br />{formatUtc(current.observation.observed_at)}</figcaption></figure>
        <figure className="comparison-frame"><PreviewViewport frame={other} fixture={fixture} label="B" /><figcaption className="comparison-caption">B · {other.observation.product_id}<br />{formatUtc(other.observation.observed_at)}</figcaption></figure>
      </div><p className="viewer-scale-note">Views pan and zoom independently. Shared alignment and wavelength compatibility must be assessed from backend metadata.</p></>
        : <><PreviewViewport frame={shown || current} fixture={fixture} label={mode === 'blink' && blinkReference ? 'B' : 'A'} />
          <p className="comparison-caption">{mode === 'blink' ? `Showing ${blinkReference ? 'B' : 'A'}` : `Observation ${index + 1}`} · {(shown || current).observation.product_id} · {formatUtc((shown || current).observation.observed_at)}{mode === 'blink' && index === reference ? ' · Choose different A/B observations to blink.' : ''}</p>
        </>}
    {current && <p className="viewer-scale-note">Zoom enlarges preview pixels; it adds no scientific detail. Navigator positions are within the PNG, not RA/Dec.</p>}
    {fullscreen && (warnings.length > 0 || previewWarnings.length > 0) && <div className="fullscreen-warnings"><strong>Warnings and limitations</strong><ul className="warning-list">{[...new Set([...warnings, ...previewWarnings])].map((warning, i) => <li key={i}>{warning}</li>)}</ul></div>}
    {fullscreen && <button type="button" className="fullscreen-playback" onClick={() => onPlayingChange?.(!playing)} disabled={frames.length < 2}>{playing ? 'Pause playback' : 'Play / blink'}</button>}
  </section>;
}
