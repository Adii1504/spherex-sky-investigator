// Aladin Lite v3 API: https://cds-astro.github.io/aladin-lite/
// Browser-only lazy import keeps the reference survey separate from SPHEREx PNGs.
export const REFERENCE_SURVEY = { id: 'P/DSS2/color', name: 'DSS2 colour', url: 'https://aladin.cds.unistra.fr/hips/list' };

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

export async function createSkyMap(element, { signal, onSelect, onHover, onStatus } = {}) {
  if (!supportsWebGL2()) throw new Error('This browser cannot provide WebGL2. Use the target list and coordinate search, or try a WebGL2-enabled browser.');
  if (typeof navigator !== 'undefined' && navigator.onLine === false) throw new Error('The reference sky survey is offline. The target catalogue and SPHEREx workspace remain available.');
  const { default: A } = await import('aladin-lite');
  await A.init;
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');

  const aladin = A.aladin(element, {
    // Pinned v3.8.2 accepts an array; start empty and attach our monitored HiPS
    // once below, avoiding a duplicate unmonitored default survey request.
    survey: [], target: '0 +0', fov: 360, projection: 'AIT', cooFrame: 'ICRSd',
    showZoomControl: true, showLayersControl: true, showFullscreenControl: true,
    showCooGridControl: true, showCooGrid: false, showSimbadPointerControl: false,
    showShareControl: false, showStatusBar: true, showFrame: true, showFov: true,
    showCooLocation: true, mode: 'dark', backgroundColor: 'rgb(5,7,11)',
  });
  let disposed = false;
  let catalog;
  let selectedId = null;
  let surveyTimer;
  // HiPS callback means its metadata/layer loaded, not that every tile is cached.
  const loadSurvey = () => {
    clearTimeout(surveyTimer);
    surveyTimer = setTimeout(() => { if (!disposed) onStatus?.('error', 'Reference survey loading timed out. Check the network and retry.'); }, 20000);
    const survey = A.HiPS(REFERENCE_SURVEY.id, {
      successCallback: () => { clearTimeout(surveyTimer); if (!disposed) onStatus?.('ready'); },
      errorCallback: () => {
        clearTimeout(surveyTimer);
        if (!disposed) onStatus?.('error', 'The reference survey could not load. Check the network and retry; SPHEREx searches use the separate backend.');
      },
    });
    // Pinned v3.8.2 returns the HiPS object here, not a Promise.
    aladin.setBaseImageLayer(survey);
  };
  loadSurvey();
  const hovered = source => onHover?.(source?.data?.target_id || null);
  aladin.on('objectHovered', hovered);
  aladin.on('objectHoveredStop', () => onHover?.(null));

  return {
    reload: loadSurvey,
    setTargets(targets) {
      if (catalog) aladin.removeOverlay(catalog);
      catalog = A.catalog({ name: 'WhyLab catalogue targets', shape: 'circle', sourceSize: 14,
        color: '#E3BD39', selectionColor: '#48C7D0', hoverColor: '#FFFFFF',
        displayLabel: true, labelColumn: 'name', labelColor: '#F5F5F5', labelFont: '12px sans-serif',
        onClick: source => { if (source?.data?.target_id) onSelect?.(source.data.target_id); },
      });
      aladin.addCatalog(catalog);
      catalog.addSources(targets.filter(target => targetCoordinates(target)).map(target => {
        const { ra, dec } = targetCoordinates(target);
        return A.source(ra, dec, { target_id: target.id, name: target.name, object_type: target.object_type ?? target.type ?? 'Type unavailable' });
      }));
      if (selectedId) catalog.select(source => source.data.target_id === selectedId);
    },
    select(id) {
      selectedId = id;
      catalog?.deselectAll();
      if (id) catalog?.select(source => source.data.target_id === id);
    },
    center(target) {
      const coordinate = targetCoordinates(target);
      if (!coordinate) return;
      aladin.setProjection('SIN');
      aladin.gotoRaDec(coordinate.ra, coordinate.dec);
      aladin.setFoV(1); // Aladin angular units are DEGREES, not the backend's arcminutes.
    },
    zoom(factor) {
      const current = aladin.getFov()[0];
      aladin.setFoV(Math.max(0.005, Math.min(360, current * factor)));
    },
    reset() {
      aladin.setProjection('AIT'); aladin.gotoRaDec(0, 0); aladin.setFoV(360);
    },
    dispose() {
      disposed = true;
      clearTimeout(surveyTimer);
      // v3.8.2 has on(event, callback) but no public off method.
      aladin.on('objectHovered', null); aladin.on('objectHoveredStop', null);
      if (catalog) aladin.removeOverlay(catalog);
      // Aladin exposes no public instance destroy API. Removing the owned host
      // detaches the view; normal target/view changes never recreate this instance.
      element.replaceChildren();
    },
  };
}
