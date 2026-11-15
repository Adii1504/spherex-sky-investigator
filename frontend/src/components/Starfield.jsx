/** Adapted from the user's supplied Starfield.jsx and standalone HTML reference.
 * Random decorative particles only: no catalogue identity, distances or detections.
 */
import React, {useEffect, useRef} from 'react';
import {createRenderer} from '../threeRenderer.js';

export default function Starfield({starCount = 7000, speed = .0008, paused = false}) {
  const host = useRef(null);
  const pause = useRef(paused);
  pause.current = paused;
  useEffect(() => {
    const container = host.current;
    let disposed = false, cleanup = () => {};
    const motion = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    async function initialize() {
      // A CSS fallback remains visible on devices without WebGL2.
      const probe = document.createElement('canvas');
      const context = probe.getContext('webgl2', {alpha:true,antialias:false,powerPreference:'low-power'});
      if (!context) return;
      const THREE = await import('three');
      if (disposed) { context.getExtension('WEBGL_lose_context')?.loseContext(); return; }
      const scene = new THREE.Scene();
      scene.fog = new THREE.FogExp2(0x020307, .00065);
      const camera = new THREE.PerspectiveCamera(60, 1, .1, 4000);
      camera.position.set(0, 0, 1000);
      const renderer = createRenderer(THREE, {canvas:probe,context,alpha:true,antialias:false,powerPreference:'low-power'});
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
      container.appendChild(renderer.domElement);
      const textureCanvas = document.createElement('canvas');
      textureCanvas.width = textureCanvas.height = 128;
      const ctx = textureCanvas.getContext('2d');
      const glow = ctx.createRadialGradient(64,64,0,64,64,64);
      [[0,'rgba(255,255,255,1)'],[.12,'rgba(240,248,255,.9)'],[.28,'rgba(180,215,255,.45)'],
        [.6,'rgba(80,140,255,.15)'],[1,'rgba(0,0,0,0)']].forEach(([stop,color]) => glow.addColorStop(stop,color));
      ctx.fillStyle=glow; ctx.fillRect(0,0,128,128);
      const texture = new THREE.CanvasTexture(textureCanvas);
      const palette=[0x9bb0ff,0xbbccff,0xfbf8ff,0xfff5ea,0xffecd0,0xffcc8f,0xffa050].map(c => new THREE.Color(c));
      const count = window.innerWidth < 780 ? Math.min(starCount,3000) : starCount;
      const positions=new Float32Array(count*3), colors=new Float32Array(count*3);
      for(let i=0;i<count;i++) {
        const radius=100+Math.random()*2200, theta=Math.random()*Math.PI*2, phi=(Math.random()-.5)*Math.PI*.45;
        positions.set([radius*Math.cos(phi)*Math.cos(theta),radius*Math.sin(phi)*.5,radius*Math.cos(phi)*Math.sin(theta)],i*3);
        const color=palette[Math.floor(Math.random()*palette.length)];
        colors.set([color.r,color.g,color.b],i*3);
      }
      const geometry=new THREE.BufferGeometry();
      geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));
      geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));
      const material=new THREE.PointsMaterial({size:5.5,map:texture,vertexColors:true,transparent:true,
        depthWrite:false,blending:THREE.AdditiveBlending});
      const particles=new THREE.Points(geometry,material);
      scene.add(particles);
      const resize=() => {
        const width=Math.max(1,container.clientWidth), height=Math.max(1,container.clientHeight);
        camera.aspect=width/height; camera.updateProjectionMatrix(); renderer.setSize(width,height);
        renderer.render(scene,camera);
      };
      let mouseX=0,mouseY=0,frame,last=0,visible=true;
      const move=event => {
        const bounds=container.getBoundingClientRect();
        mouseX=((event.clientX-bounds.left)/bounds.width-.5)*60;
        mouseY=((event.clientY-bounds.top)/bounds.height-.5)*30;
      };
      const parent=container.parentElement;
      const animate=time => {
        frame=requestAnimationFrame(animate);
        const dt=Math.min((time-last)/16.667,3); last=time;
        if(!visible || document.hidden || pause.current || motion?.matches) return;
        particles.rotation.y+=speed*dt; particles.rotation.x+=speed*.35*dt;
        camera.position.x+=(mouseX-camera.position.x)*.04;
        camera.position.y+=(-mouseY-camera.position.y)*.04;
        camera.lookAt(0,0,0); renderer.render(scene,camera);
      };
      const observer=typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
      observer?.observe(container);
      const intersection=typeof IntersectionObserver !== 'undefined' ? new IntersectionObserver(entries => {visible=entries[0].isIntersecting;}) : null;
      intersection?.observe(container);
      parent.addEventListener('pointermove',move,{passive:true});
      window.addEventListener('resize',resize);
      resize(); frame=requestAnimationFrame(animate);
      cleanup=() => {
        cancelAnimationFrame(frame); observer?.disconnect(); intersection?.disconnect();
        parent.removeEventListener('pointermove',move); window.removeEventListener('resize',resize);
        geometry.dispose(); material.dispose(); texture.dispose(); renderer.dispose();
        renderer.domElement.remove();
      };
    }
    initialize().catch(() => {cleanup();});
    return () => {disposed=true;cleanup();};
  }, [starCount,speed]);
  return <div className="decorative-starfield" ref={host} aria-hidden="true" />;
}
