import React,{useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {request} from '../api.js';
import {createRenderer} from '../threeRenderer.js';
import {scenePosition,starDirection,stellarBody,stellarPixels,PLANET_STYLE} from '../solarScene.js';
import {layoutSkyLabels} from '../skyLabels.js';

const EMPTY_TARGETS=[];
export default function SolarSystem3D({selectedId='earth',onSelect,onClose,targets=EMPTY_TARGETS}) {
  const host=useRef(null),dialog=useRef(null),api=useRef(null);
  const [data,setData]=useState(null),[error,setError]=useState(''),[textureError,setTextureError]=useState(false);
  const [overview,setOverview]=useState(false),[playing,setPlaying]=useState(true),[spin,setSpin]=useState(true),[speed,setSpeed]=useState(5),[day,setDay]=useState(0);
  const [inner,setInner]=useState(false);
  const state=useRef({});state.current={selectedId,overview,playing,spin,speed,inner};
  const callbacks=useRef({onSelect});callbacks.current={onSelect};
  useEffect(()=>{
    const previous=document.activeElement,position=[window.scrollX,window.scrollY];dialog.current?.focus({preventScroll:true});
    const overflow=document.body.style.overflow,padding=document.body.style.paddingRight;
    const gutter=Math.max(0,window.innerWidth-document.documentElement.clientWidth);
    document.body.style.paddingRight=`${(parseFloat(window.getComputedStyle(document.body).paddingRight)||0)+gutter}px`;
    document.body.style.overflow='hidden';
    return()=>{document.body.style.overflow=overflow;document.body.style.paddingRight=padding;previous?.focus?.({preventScroll:true});window.scrollTo(...position);};
  },[]);
  useEffect(()=>{
    const controller=new AbortController();
    request('/solar-system/scene',undefined,controller.signal,{prefix:'/api',timeoutMs:30000}).then(value=>{
      if(!Array.isArray(value.bodies) || !value.bodies.every(b=>b.samples_au?.length>1))throw Error('Orbital positions unavailable.');
      if(!controller.signal.aborted)setData(value);
    }).catch(e=>{if(!controller.signal.aborted)setError(e.message);});
    return()=>controller.abort();
  },[]);
  useEffect(()=>{
    if(!data)return;
    const element=host.current,scene=new THREE.Scene(),resources=[],meshes=new Map(),labels=[];
    let renderer,controls,observer,frame,disposed=false,elapsed=0,last=performance.now(),lastUI=0,lastMode='',lastId='',transition=null;
    const camera=new THREE.PerspectiveCamera(45,1,.001,6000);camera.position.set(0,1.3,4);
    const universe=new THREE.Group(),detail=new THREE.Group();scene.add(universe,detail);
    const loader=new THREE.TextureLoader();
    const getMap=id=>{
      const texture=loader.load(`/textures/solar/${id}.jpg`,()=>{if(disposed)texture.dispose();},undefined,()=>{if(!disposed)setTextureError(true);});
      texture.colorSpace=THREE.SRGBColorSpace;resources.push(texture);return texture;
    };
    const surface=(body,radius)=>{
      const group=new THREE.Group(),axis=new THREE.Group();group.add(axis);
      const geometry=new THREE.SphereGeometry(radius,64,40);
      let map;
      if(body.isCatalogue){
        map=new THREE.DataTexture(stellarPixels(body.brown),256,128,THREE.RGBAFormat);
        map.colorSpace=THREE.SRGBColorSpace;map.needsUpdate=true;resources.push(map);
      }else map=getMap(body.id);
      const options={map};
      const material=body.id==='sun'||body.isCatalogue?new THREE.MeshBasicMaterial(options):new THREE.MeshStandardMaterial({...options,roughness:1,metalness:0});
      const mesh=new THREE.Mesh(geometry,material);mesh.userData.bodyId=body.id;axis.add(mesh);resources.push(geometry,material);
      if(body.id==='sun'||body.isCatalogue&&!body.brown){
        material.color.setRGB(1.7,1.35,1.1);
        material.toneMapped=false;
        const canvas=document.createElement('canvas');canvas.width=canvas.height=128;
        const ctx=canvas.getContext('2d'),gradient=ctx.createRadialGradient(64,64,0,64,64,64);
        gradient.addColorStop(0,'rgba(255,225,150,.7)');gradient.addColorStop(.44,'rgba(255,175,70,.5)');gradient.addColorStop(.65,'rgba(255,115,35,.18)');gradient.addColorStop(1,'rgba(255,100,20,0)');
        ctx.fillStyle=gradient;ctx.fillRect(0,0,128,128);
        const texture=new THREE.CanvasTexture(canvas);
        const glowMaterial=new THREE.SpriteMaterial({map:texture,color:'#ffb956',transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false});
        const glow=new THREE.Sprite(glowMaterial);glow.scale.set(radius*3.8,radius*3.8,1);group.add(glow);resources.push(texture,glowMaterial);
      }
      axis.rotation.z=THREE.MathUtils.degToRad(PLANET_STYLE[body.id]?.tilt||0);
      if(body.id==='saturn'){
        const geo=new THREE.RingGeometry(radius*1.35,radius*2.3,128,5),colors=[];
        const positions=geo.attributes.position;
        for(let i=0;i<positions.count;i++){
          const r=Math.hypot(positions.getX(i),positions.getY(i))/radius;
          const color=new THREE.Color(r>1.9&&r<2.02?'#625c4e':r<1.7?'#cbbd99':'#a89472');colors.push(color.r,color.g,color.b);
        }
        geo.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));
        const mat=new THREE.MeshStandardMaterial({vertexColors:true,side:THREE.DoubleSide,transparent:true,opacity:.8,roughness:1});
        const rings=new THREE.Mesh(geo,mat);rings.rotation.x=-Math.PI/2;axis.add(rings);resources.push(geo,mat);
      }
      return {group,mesh};
    };
    const dispose=()=>{
      disposed=true;cancelAnimationFrame(frame);observer?.disconnect();controls?.dispose();
      resources.forEach(resource=>resource.dispose());renderer?.dispose();renderer?.forceContextLoss();element.replaceChildren();api.current=null;
    };
    try{
      renderer=createRenderer(THREE,{antialias:true});renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.75));
      renderer.setClearColor('#02050c');renderer.outputColorSpace=THREE.SRGBColorSpace;
      renderer.domElement.setAttribute('aria-label','3D Solar System; drag to orbit and scroll to zoom');element.append(renderer.domElement);
      controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.minDistance=1.5;controls.maxDistance=180;controls.saveState();
      const ambient=new THREE.AmbientLight('#b8ceff',.35);scene.add(ambient);
      const sunlight=new THREE.PointLight('#fff1d5',3,0,0);universe.add(sunlight);
      const closeLight=new THREE.DirectionalLight('#fff1df',2.6);detail.add(closeLight);
      const leaders=document.createElementNS('http://www.w3.org/2000/svg','svg');leaders.classList.add('planet-orbit-leaders');element.append(leaders);
      for(const body of data.bodies){
        const model=surface(body,PLANET_STYLE[body.id].radius);universe.add(model.group);meshes.set(body.id,model);
        // The Moon's true separation would be hidden by enlarged overview globes.
        model.group.visible=body.id!=='moon';
        if(body.orbit_au.length){
          const geo=new THREE.BufferGeometry().setFromPoints(body.orbit_au.map(p=>new THREE.Vector3(p[0],p[2],-p[1])));
          const mat=new THREE.LineBasicMaterial({color:body.color,transparent:true,opacity:.28});universe.add(new THREE.Line(geo,mat));resources.push(geo,mat);
        }
        const node=document.createElement('button');node.className='planet-3d-label';node.textContent=body.name;
        const line=document.createElementNS(leaders.namespaceURI,'line');line.setAttribute('stroke',body.color);line.setAttribute('stroke-opacity','.6');leaders.append(line);
        node.onclick=()=>{setOverview(false);callbacks.current.onSelect?.(body.id);};element.append(node);labels.push({node,body,line});
      }
      const stars=targets.filter(t=>Number.isFinite(t.ra_deg)&&Number.isFinite(t.dec_deg));
      const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(stars.flatMap(t=>starDirection(t)),3));
      const mat=new THREE.PointsMaterial({color:'#e3bd39',size:4,sizeAttenuation:false,depthTest:false});scene.add(new THREE.Points(geo,mat));resources.push(geo,mat);
      const chooseStar=id=>{setOverview(false);callbacks.current.onSelect?.(id);};
      const starLabels=stars.map(target=>{const node=document.createElement('button');node.type='button';node.className='planet-star-label';node.textContent=target.name;node.setAttribute('aria-label',`Open ${target.name} in 3D`);node.onclick=()=>chooseStar(target.id);element.append(node);return{node,position:new THREE.Vector3(...starDirection(target)),target};});
      let focused;
      const setDetail=id=>{
        if(focused){detail.remove(focused.group);focused.group.traverse(obj=>{if(obj.isMesh)obj.geometry.dispose();if(obj.material){obj.material.map?.dispose();obj.material.dispose();}});}
        const body=data.bodies.find(b=>b.id===id)||stellarBody(targets.find(t=>t.id===id));
        if(!body)throw Error('Unknown 3D body');
        focused=surface(body,1);detail.add(focused.group);
      };
      const resize=()=>{const w=element.clientWidth||900,h=element.clientHeight||500;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();};
      observer=new ResizeObserver(resize);observer.observe(element);resize();
      const down=e=>{api.current.down=[e.clientX,e.clientY];};
      const pick=e=>{
        if(!api.current.down||Math.hypot(e.clientX-api.current.down[0],e.clientY-api.current.down[1])>5)return;
        const rect=renderer.domElement.getBoundingClientRect(),ray=new THREE.Raycaster();
        ray.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1),camera);
        const hit=state.current.overview?ray.intersectObjects([...meshes.values()].map(m=>m.mesh),false)[0]:null;
        if(hit){setOverview(false);callbacks.current.onSelect?.(hit.object.userData.bodyId);return;}
        const star=starLabels.map(item=>{const p=item.position.clone().project(camera);return {...item,p,distance:Math.hypot((p.x+1)*rect.width/2-(e.clientX-rect.left),(1-p.y)*rect.height/2-(e.clientY-rect.top))};}).filter(item=>item.p.z>-1&&item.p.z<1&&item.distance<14).sort((a,b)=>a.distance-b.distance)[0];
        if(star)chooseStar(star.target.id);
      };
      renderer.domElement.addEventListener('pointerdown',down);renderer.domElement.addEventListener('pointerup',pick);
      const lost=e=>{e.preventDefault();setError('3D graphics paused after a WebGL interruption. Close and reopen this view to retry.');};renderer.domElement.addEventListener('webglcontextlost',lost);
      api.current={reset:()=>{lastMode='';},zoom:factor=>camera.position.sub(controls.target).multiplyScalar(factor).add(controls.target),now:()=>{elapsed=0;setDay(0);}};
      const draw=()=>{
        frame=requestAnimationFrame(draw);const now=performance.now(),delta=Math.min(.1,(now-last)/1000);last=now;
        if(document.hidden||!element.getClientRects().length)return;
        const current=state.current;
        if(current.playing)elapsed=(elapsed+delta*current.speed)%data.duration_days;
        if(now-lastUI>200){setDay(elapsed);lastUI=now;}
        universe.visible=current.overview;detail.visible=!current.overview;
        const mode=String(current.overview)+String(current.inner);
        if(lastMode!==mode||lastId!==current.selectedId){
          lastMode=mode;lastId=current.selectedId;
          if(!current.overview)setDetail(current.selectedId);
          const to=current.overview?(current.inner?new THREE.Vector3(0,5,8):new THREE.Vector3(0,60,85)):new THREE.Vector3(0,1.2,current.selectedId==='saturn'?6.5:3.8);
          transition={from:camera.position.clone(),targetFrom:controls.target.clone(),to,start:now};
          controls.minDistance=current.overview ? .4 : 1.5;controls.maxDistance=current.overview?180:30;
        }
        if(transition){const t=Math.min(1,(now-transition.start)/800),ease=t*t*(3-2*t);camera.position.lerpVectors(transition.from,transition.to,ease);controls.target.copy(transition.targetFrom).multiplyScalar(1-ease);if(t===1)transition=null;}
        for(const body of data.bodies){
          const model=meshes.get(body.id);model.group.position.set(...scenePosition(body,elapsed,data.step_days));
          if(current.spin)model.mesh.rotation.y+=delta*.15/Math.max(.25,Math.abs(PLANET_STYLE[body.id].spin))*Math.sign(PLANET_STYLE[body.id].spin);
        }
        const selected=data.bodies.find(b=>b.id===current.selectedId);
        if(focused&&current.spin)focused.mesh.rotation.y+=delta*.2*Math.sign(PLANET_STYLE[current.selectedId]?.spin||1);
        if(selected){const pos=new THREE.Vector3(...scenePosition(selected,elapsed));closeLight.position.copy(pos.length()>0?pos.normalize().multiplyScalar(-5):new THREE.Vector3(3,2,4));}
        controls.update();renderer.render(scene,camera);
        const place=(node,position)=>{const p=position.clone().project(camera);node.hidden=p.z<-1||p.z>1||Math.abs(p.x)>.95||Math.abs(p.y)>.95;node.style.left=`${(p.x+1)*50}%`;node.style.top=`${(1-p.y)*50}%`;};
        leaders.style.display=current.overview?'':'none';
        const points=labels.filter(({body})=>body.id!=='moon').map(({body})=>{
          const p=meshes.get(body.id).group.position.clone().project(camera);
          return {id:body.id,x:(p.x+1)/2*element.clientWidth,y:(1-p.y)/2*element.clientHeight,z:p.z};
        }).filter(p=>p.z>-1&&p.z<1&&p.x>=0&&p.x<=element.clientWidth&&p.y>=0&&p.y<=element.clientHeight);
        const positions=new Map(layoutSkyLabels(points,element.clientWidth,element.clientHeight).map(p=>[p.id,p]));
        labels.forEach(({node,body,line})=>{
          const p=positions.get(body.id);node.hidden=!current.overview||!p;line.style.display=node.hidden?'none':'';
          if(!node.hidden){node.style.left=p.x+'px';node.style.top=p.y+'px';node.style.width=p.width+'px';
            for(const [k,v] of Object.entries({x1:p.anchorX,y1:p.anchorY,x2:p.x+p.width/2,y2:p.y+15}))line.setAttribute(k,String(v));}
        });
        starLabels.forEach(({node,position})=>place(node,position));
      };draw();
      return()=>{renderer.domElement.removeEventListener('pointerdown',down);renderer.domElement.removeEventListener('pointerup',pick);renderer.domElement.removeEventListener('webglcontextlost',lost);dispose();};
    }catch{setError('3D rendering is unavailable. Try a WebGL2-enabled browser; the sky map and body descriptions remain available.');dispose();}
  },[data,targets]);
  const selected=data?.bodies.find(b=>b.id===selectedId)||stellarBody(targets.find(t=>t.id===selectedId));
  const date=data?new Date(Date.parse(data.epoch)+day*86400000).toISOString().replace('T',' ').slice(0,19)+' UTC':'';
  return createPortal(<div className="planet-modal-backdrop"><section className="planet-modal" role="dialog" aria-modal="true" aria-label="Interactive 3D Solar System" tabIndex={-1} ref={dialog} onKeyDown={e=>{
    if(e.key==='Escape'){e.stopPropagation();onClose();}
    if(e.key==='Tab'){const nodes=[...dialog.current.querySelectorAll('button:not(:disabled),select,a[href]')];if(e.shiftKey&&document.activeElement===nodes[0]){e.preventDefault();nodes.at(-1)?.focus();}else if(!e.shiftKey&&document.activeElement===nodes.at(-1)){e.preventDefault();nodes[0]?.focus();}}
  }}>
    <header className="planet-modal-header"><div><p className="eyebrow">EXPLORE IN THREE DIMENSIONS</p><h2>{overview?'The Solar System':selected?.name||selectedId}</h2></div><button onClick={onClose} aria-label="Close 3D Solar System">×</button></header>
    <div className="planet-selection" aria-label="Choose a 3D body">{(data?.bodies||[]).map(body=><button key={body.id} aria-pressed={!overview&&body.id===selectedId} onClick={()=>{setOverview(false);onSelect(body.id);}}>{body.name}</button>)}</div>
    <div className="planet-selection star-selection" aria-label="Choose a catalogue star in 3D"><span>Catalogue stars</span>{targets.map(target=><button key={target.id} aria-pressed={!overview&&target.id===selectedId} onClick={()=>{setOverview(false);onSelect(target.id);}}>{target.name}</button>)}</div>
    <div className="planet-3d-toolbar"><button onClick={()=>{setInner(false);setOverview(true);}}>Solar System overview</button><button onClick={()=>{setInner(true);setOverview(true);}}>Inner planets</button><button onClick={()=>api.current?.reset()}>Reset camera</button><button onClick={()=>api.current?.zoom(.8)} aria-label="Zoom in planet">+</button><button onClick={()=>api.current?.zoom(1.25)} aria-label="Zoom out planet">−</button>
      <button aria-pressed={playing} onClick={()=>setPlaying(v=>!v)}>{playing?'Pause orbits':'Play orbits'}</button><button aria-pressed={spin} onClick={()=>setSpin(v=>!v)}>{spin?'Pause spin':'Rotate bodies'}</button>
      <label>Orbit speed <select value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value={1}>1 day / second</option><option value={5}>5 days / second</option><option value={30}>30 days / second</option></select></label><button onClick={()=>api.current?.now()}>Starting epoch</button></div>
    {!data&&!error&&<p role="status">Calculating planetary paths…</p>}{error&&<p role="alert">{error}</p>}
    <div className="planet-3d-host" ref={host}/>
    <div className="planet-modal-notes"><p><strong>{date}</strong> · Drag to orbit the camera; scroll to zoom. {selected&&!overview&&selected.description}</p>
      {selected?.isCatalogue&&!overview&&<p className="stellar-illustration-note"><strong>Artist’s illustration.</strong> Surface, color, size and spin are not measured for this object. {Number.isFinite(selected.ra_deg)&&Number.isFinite(selected.dec_deg)&&`Catalogue direction: RA ${selected.ra_deg.toFixed(5)}°, Dec ${selected.dec_deg.toFixed(5)}°.`} {selected.note}</p>}
      <p>Sun-centered positions and orbit distances use AU. Overview planet sizes are enlarged; the Moon is available in close-up. Gold points mark catalogue star directions in ICRS, not their distances. Close-ups show a centered globe; they are not an Earth telescope view.</p>
      <p>{data?.note} Playback loops through one year. {textureError&&'Some surface maps could not load.'} Surface maps: <a href="https://www.solarsystemscope.com/textures/" target="_blank" rel="noreferrer">Solar System Scope / INOVE</a>, <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a>; enhanced colors and reconstructed gaps. Rings and surface orientation are illustrative.</p></div>
  </section></div>,document.body);
}
