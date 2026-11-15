import React, {useEffect, useRef, useState} from 'react';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {positionedSources} from '../coordinates.js';
import {createRenderer} from '../threeRenderer.js';

export default function Source3D({targets, selectedId, onSelect}) {
  const host = useRef(null), api = useRef(null), callbacks = useRef({selectedId, onSelect});
  callbacks.current = {selectedId, onSelect};
  const [spatial, setSpatial] = useState(false), [error, setError] = useState('');
  const spatialCount = positionedSources(targets, true).length;
  useEffect(() => {
    const element = host.current;
    const sources = positionedSources(targets, spatial);
    let renderer, controls, observer, frame, lost;
    const scene = new THREE.Scene();
    const resources = [];
    try {
      renderer = createRenderer(THREE, {antialias: true, alpha: true});
      setError('');
      renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
      renderer.domElement.setAttribute('aria-label', 'Interactive source positions; select a point or use the target list');
      element.appendChild(renderer.domElement);
      const extent = Math.max(1, ...sources.map(s => Math.hypot(...s.xyz)));
      const camera = new THREE.PerspectiveCamera(48, 1, extent / 10000, extent * 100);
      camera.up.set(0, 0, 1); camera.position.set(extent * 2.5, extent * 2.5, extent * 1.7);
      controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true; controls.minDistance = extent * .05; controls.maxDistance = extent * 12;
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(sources.flatMap(s => s.xyz), 3));
      const material = new THREE.PointsMaterial({color: '#e3bd39', size: 10, sizeAttenuation: false});
      const points = new THREE.Points(geometry, material); scene.add(points); resources.push(geometry, material);
      const highlightGeometry = new THREE.BufferGeometry();
      highlightGeometry.setAttribute('position', new THREE.Float32BufferAttribute([0,0,0], 3));
      const highlightMaterial = new THREE.PointsMaterial({color: '#48c7d0', size: 20, sizeAttenuation: false, depthTest: false});
      const highlight = new THREE.Points(highlightGeometry, highlightMaterial); scene.add(highlight);
      resources.push(highlightGeometry, highlightMaterial);
      const gridGeometry = spatial ? new THREE.BufferGeometry() : new THREE.WireframeGeometry(new THREE.SphereGeometry(1, 24, 12));
      const gridMaterial = new THREE.LineBasicMaterial({color: '#29404e', transparent: true, opacity: .5});
      scene.add(new THREE.LineSegments(gridGeometry, gridMaterial)); resources.push(gridGeometry, gridMaterial);
      const axes = new THREE.AxesHelper(extent * 1.15); scene.add(axes); resources.push(axes.geometry, axes.material);
      const labels = sources.slice(0, 4).map(s => s);
      const selected = sources.find(s => s.target.id === callbacks.current.selectedId);
      if (selected && !labels.includes(selected)) labels.push(selected);
      const labelNodes = labels.map(s => {
        const node = document.createElement('span'); node.className = 'source-3d-label'; node.textContent = s.target.name;
        element.appendChild(node); return {node, source:s};
      });
      const raycaster = new THREE.Raycaster(); raycaster.params.Points.threshold = extent * .035;
      let down;
      const pointerDown = e => {down = [e.clientX, e.clientY];};
      const pick = e => {
        if (!down || Math.hypot(e.clientX-down[0], e.clientY-down[1]) > 5) return;
        const rect = renderer.domElement.getBoundingClientRect();
        raycaster.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1, -(e.clientY-rect.top)/rect.height*2+1), camera);
        const hit = raycaster.intersectObject(points)[0];
        if (hit) callbacks.current.onSelect?.(sources[hit.index].target.id);
      };
      renderer.domElement.addEventListener('pointerdown', pointerDown);
      renderer.domElement.addEventListener('pointerup', pick);
      lost = e => {e.preventDefault(); setError('WebGL context lost. Use the target list or reopen the 3D view.');};
      renderer.domElement.addEventListener('webglcontextlost', lost);
      observer = new ResizeObserver(() => {
        const w = element.clientWidth || 600, h = element.clientHeight || 440;
        renderer.setSize(w, h); camera.aspect = w/h; camera.updateProjectionMatrix();
      }); observer.observe(element);
      const draw = () => {
        frame = requestAnimationFrame(draw);
        // The parent keeps the sky workspace mounted when opening the FITS workflow.
        if (!element.getClientRects().length) return;
        controls.update();
        const source = sources.find(s => s.target.id === callbacks.current.selectedId);
        highlight.visible = !!source;
        if (source) highlight.position.set(...source.xyz);
        renderer.render(scene, camera);
        labelNodes.forEach(({node, source:s}) => {
          const p = new THREE.Vector3(...s.xyz).project(camera);
          node.hidden = p.z < -1 || p.z > 1 || Math.abs(p.x) > 1 || Math.abs(p.y) > 1;
          node.style.left = `${(p.x+1)/2*100}%`; node.style.top = `${(1-p.y)/2*100}%`;
        });
      }; draw();
      api.current = {reset: () => controls.reset(), zoom: factor => {camera.position.sub(controls.target).multiplyScalar(factor).add(controls.target); controls.update();}};
      return () => {
        cancelAnimationFrame(frame); observer.disconnect(); controls.dispose();
        renderer.domElement.removeEventListener('pointerdown', pointerDown);
        renderer.domElement.removeEventListener('pointerup', pick);
        renderer.domElement.removeEventListener('webglcontextlost', lost);
        resources.forEach(r => r.dispose()); renderer.dispose(); renderer.forceContextLoss(); element.replaceChildren(); api.current = null;
      };
    } catch {
      setError('3D rendering is unavailable in this browser. The catalogue list, coordinates and FITS inspection remain usable.');
      cancelAnimationFrame(frame); observer?.disconnect(); controls?.dispose(); resources.forEach(r => r.dispose()); renderer?.dispose(); element.replaceChildren();
    }
  }, [targets, spatial]);
  return <section className="source-3d" aria-label="Three dimensional catalogue view">
    <div className="sky-map-toolbar"><button onClick={() => api.current?.reset()}>Reset 3D view</button>
      <button onClick={() => api.current?.zoom(.8)} aria-label="Zoom in 3D">+</button><button onClick={() => api.current?.zoom(1.25)} aria-label="Zoom out 3D">−</button>
      <label><input type="checkbox" checked={spatial} disabled={!spatialCount} onChange={e => setSpatial(e.target.checked)} />Spatial distances ({spatialCount} eligible)</label></div>
    {error && <p role="status">{error}</p>}<div className="source-3d-host" ref={host} />
    <p className="sky-survey-credit">{spatial ? 'Spatial mode: parsecs, linear scaling; unknown/untrusted distances omitted.' : 'Celestial sphere: unit radius represents directions only, not physical distances.'} ICRS: +X = RA 0°, +Y = RA 90°, +Z = north. Drag to orbit, wheel to zoom. Labels limited to five.</p>
  </section>;
}
