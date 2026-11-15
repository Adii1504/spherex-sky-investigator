// Aladin Lite v3 API: https://cds-astro.github.io/aladin-lite/
// Browser-only lazy import keeps the reference survey separate from SPHEREx PNGs.
import { DSS_MIRRORS, createSurveyLoader } from './referenceSurvey.js';
export const REFERENCE_SURVEY = { id: import.meta.env?.VITE_HIPS_URL || DSS_MIRRORS[0], name: 'DSS2 colour', url: DSS_MIRRORS[0] + '/' };
import {createBodyLabels} from './skyLabels.js';

export function targetCoordinates(target) {
  const ra = target?.ra_deg ?? target?.coordinates?.ra_deg;
  const dec = target?.dec_deg ?? target?.coordinates?.dec_deg;
  const frame = target?.coordinate_frame ?? target?.frame;
  if (typeof ra !== 'number' || typeof dec !== 'number' || !Number.isFinite(ra) || !Number.isFinite(dec)
      || ra < 0 || ra >= 360 || dec < -90 || dec > 90
      || (frame && !['ICRS', 'ICRSd', 'J2000', 'j2000'].includes(frame))) return null;
  return { ra, dec };
}

export function supportsWebGL2() {
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl2');
    if (!gl) return false;
    gl.getExtension('WEBGL_lose_context')?.loseContext();
    return true;
  } catch { return false; }
}

export async function createSkyMap(element, { signal, onSelect, onBodySelect, onHover, onStatus, onCoordinate } = {}) {
  if (!supportsWebGL2()) throw new Error('This browser cannot provide WebGL2. Use the target list and coordinate search, or try a WebGL2-enabled browser.');
  if (typeof navigator !== 'undefined' && navigator.onLine === false) throw new Error('The reference sky survey is offline. The target catalogue and SPHEREx workspace remain available.');
  const { default: A } = await import('aladin-lite');
  await A.init;
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');

  const aladin = A.aladin(element, {
    // Pinned v3.8.2 accepts an array; start empty and attach our monitored HiPS
    // once below, avoiding a duplicate unmonitored default survey request.
    // Mercator fills the rectangular canvas and wraps longitude, unlike the
    // bounded Aitoff ellipse. Selection never changes the field or zoom.
    survey: [], target: '0 +5', fov: 360, projection: 'MER', cooFrame: 'ICRSd',
    showZoomControl: true, showLayersControl: true, showFullscreenControl: true,
    showCooGridControl: true, showCooGrid: false, showSimbadPointerControl: false,
    showShareControl: false, showStatusBar: true, showFrame: true, showFov: true,
    showCooLocation: true, mode: 'dark', backgroundColor: 'rgb(5,7,11)',
  });
  let disposed = false;
  let catalog;
  let bodyCatalog;
  let planetsVisible = true;
  let selectedId = null;
  let sourcesVisible = true;
  let clickedSource = false;
  const bodyLabels = createBodyLabels(element, aladin, onBodySelect);
  const footprints = A.graphicOverlay({name: "SPHEREx observation footprints", color: "#48c7d0", lineWidth: 2});
  aladin.addOverlay(footprints);
  aladin.on('objectClicked', source => {
    clickedSource = !!(source?.data?.target_id || source?.data?.body_id);
    if(source?.data?.target_id) onSelect?.(source.data.target_id);
    else if(source?.data?.body_id) onBodySelect?.(source.data.body_id);
  });
  aladin.on("click", event => {
    if (!clickedSource && !event.isDragging && Number.isFinite(event.ra) && Number.isFinite(event.dec)) onCoordinate?.({ra: event.ra, dec: event.dec});
    clickedSource = false;
  });
  // Readiness means metadata/layer loaded, not that every tile is cached.
  const surveyLoader = createSurveyLoader(A, aladin, {
    urls: [REFERENCE_SURVEY.id, ...DSS_MIRRORS], onStatus,
  });
  surveyLoader.load();
  const hovered = source => onHover?.(source?.data?.target_id || null);
  aladin.on('objectHovered', hovered);
  aladin.on('objectHoveredStop', () => onHover?.(null));

  return {
    reload: surveyLoader.load,
    setFootprints(observations) {
      footprints.removeAll();
      for (const o of observations || []) {
        if (typeof o.footprint_stcs !== 'string' || o.footprint_stcs.length > 20000) continue;
        try { footprints.addFootprints(A.footprintsFromSTCS(o.footprint_stcs)); } catch { /* Unsupported provider footprint stays unavailable. */ }
      }
    },
    layers({sources = true, observations = true, planets = true}) {
      sourcesVisible = sources;
      planetsVisible = planets;
      bodyLabels.visible(planets);
      if (catalog) sources ? catalog.show() : catalog.hide();
      if (bodyCatalog) planets ? bodyCatalog.show() : bodyCatalog.hide();
      observations ? footprints.show() : footprints.hide();
    },
    setBodies(bodies) {
      bodyLabels.bodies(bodies);
      if (bodyCatalog) aladin.removeOverlay(bodyCatalog);
      bodyCatalog = A.catalog({name:'Solar System · calculated positions', shape:'circle', sourceSize:5,
        color:'#f39b81', displayLabel:false,
      });
      aladin.addCatalog(bodyCatalog);
      bodyCatalog.addSources(bodies.filter(body => targetCoordinates(body)).map(body =>
        A.source(body.ra_deg,body.dec_deg,{body_id:body.id,name:body.name})));
      if (!planetsVisible) bodyCatalog.hide();
    },
    setTargets(targets) {
      bodyLabels.targets(targets);
      if (catalog) aladin.removeOverlay(catalog);
      catalog = A.catalog({ name: 'WhyLab catalogue targets', shape: 'circle', sourceSize: 14,
        color: '#E3BD39', selectionColor: '#48C7D0', hoverColor: '#FFFFFF',
        displayLabel: true, labelColumn: 'name', labelColor: '#F5F5F5', labelFont: '12px sans-serif',
      });
      aladin.addCatalog(catalog);
      catalog.addSources(targets.filter(target => targetCoordinates(target)).map(target => {
        const { ra, dec } = targetCoordinates(target);
        return A.source(ra, dec, { target_id: target.id, name: target.name, object_type: target.object_type ?? target.type ?? 'Type unavailable' });
      }));
      if (!sourcesVisible) catalog.hide();
      if (selectedId) catalog.select(source => source.data.target_id === selectedId);
    },
    select(id) {
      selectedId = id;
      catalog?.deselectAll();
      if (id) catalog?.select(source => source.data.target_id === id);
    },
    center(target, fov = 1) {
      const coordinate = targetCoordinates(target);
      if (!coordinate) return;
      aladin.setProjection('TAN');
      aladin.gotoRaDec(coordinate.ra, coordinate.dec);
      aladin.setFoV(fov); // Aladin angular units are DEGREES, not the backend's arcminutes.
    },
    zoom(factor) {
      const current = aladin.getFov()[0];
      aladin.setFoV(Math.max(0.005, Math.min(360, current * factor)));
    },
    pan(horizontal, vertical) {
      const [ra, dec] = aladin.getRaDec();
      const [width, height] = aladin.getFov();
      const step = Math.min(30, Math.max(0.001, Math.min(width, height) / 5));
      const longitude = ra + horizontal * step / Math.max(.2, Math.cos(dec * Math.PI / 180));
      aladin.gotoRaDec((longitude % 360 + 360) % 360, Math.max(-89.9, Math.min(89.9, dec + vertical * step)));
    },
    fill() {
      aladin.setProjection('MER'); aladin.setFoV(360);
    },
    reset() {
      aladin.setProjection('MER'); aladin.gotoRaDec(0, 5); aladin.setFoV(360);
    },
    allSky() {
      aladin.setProjection('MER'); aladin.gotoRaDec(0, 5); aladin.setFoV(360);
    },
    dispose() {
      disposed = true;
      bodyLabels.dispose();
      surveyLoader.dispose();
      // v3.8.2 has on(event, callback) but no public off method.
      aladin.on('click', null);
      aladin.on('objectClicked', null);
      aladin.removeOverlay(footprints);
      aladin.on('objectHovered', null); aladin.on('objectHoveredStop', null);
      if (catalog) aladin.removeOverlay(catalog);
      if (bodyCatalog) aladin.removeOverlay(bodyCatalog);
      // Aladin exposes no public instance destroy API. Removing the owned host
      // detaches the view; normal target/view changes never recreate this instance.
      element.replaceChildren();
    },
  };
}
