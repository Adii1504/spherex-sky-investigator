import React,{useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import {createRenderer} from '../threeRenderer.js';
import {makeStarship} from '../starshipModels.js';
import {missionState,startMission,pauseMission,stepMission} from '../starshipMission.js';

const stats=g=>({status:g.status,time:Math.floor(g.time),hp:g.player.hp,destroyed:g.destroyed,score:g.score,accuracy:g.shots?Math.round(g.hits/g.shots*100):0,enemies:g.enemies.map(e=>({hp:e.hp,max:e.maxHp})),lock:g.lock});
export default function StarshipMission({onBack}){
  const host=useRef(null),field=useRef(null),game=useRef(missionState()),input=useRef({}),api=useRef(null),audio=useRef(null),sound=useRef(false);
  const [hud,setHud]=useState(stats(game.current)),[error,setError]=useState(''),[soundOn,setSoundOn]=useState(false);
  const launch=()=>{game.current=startMission();input.current={};setHud(stats(game.current));field.current?.focus({preventScroll:true});field.current?.scrollIntoView?.({block:'center',behavior:'smooth'});};
  const pause=()=>{pauseMission(game.current);input.current={};setHud(stats(game.current));if(game.current.status==='playing')field.current?.focus({preventScroll:true});};
  const soundToggle=async()=>{if(sound.current){sound.current=false;setSoundOn(false);return;}try{const Audio=window.AudioContext||window.webkitAudioContext;if(!audio.current)audio.current=new Audio();await audio.current.resume();sound.current=true;setSoundOn(true);}catch{sound.current=false;}};
  const beep=event=>{if(!sound.current||!audio.current||!['shoot','damage','destroy','won'].includes(event))return;const c=audio.current,o=c.createOscillator(),gain=c.createGain();o.type=event==='shoot'?'triangle':'sawtooth';o.frequency.setValueAtTime(event==='shoot'?850:event==='won'?650:120,c.currentTime);o.frequency.exponentialRampToValueAtTime(event==='won'?1000:45,c.currentTime+.15);gain.gain.setValueAtTime(.025,c.currentTime);gain.gain.exponentialRampToValueAtTime(.001,c.currentTime+.18);o.connect(gain);gain.connect(c.destination);o.start();o.stop(c.currentTime+.2);};
  useEffect(()=>{
    const element=host.current,resources=[],scene=new THREE.Scene();let renderer,observer,frame,disposed=false;
    const camera=new THREE.PerspectiveCamera(58,1,.1,500);camera.position.set(0,3,25);camera.lookAt(0,0,-25);
    const clean=()=>{disposed=true;cancelAnimationFrame(frame);observer?.disconnect();resources.forEach(r=>r.dispose());renderer?.dispose();renderer?.forceContextLoss();element.replaceChildren();api.current=null;};
    try{
      renderer=createRenderer(THREE,{antialias:true,powerPreference:'high-performance'});renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.5));renderer.setClearColor('#030610');renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.25;element.append(renderer.domElement);
      renderer.domElement.setAttribute('aria-label','3D starship battlefield; move with WASD or arrows, hold Space to fire');
      scene.add(new THREE.HemisphereLight('#a4c5ff','#1b0c2e',2));const key=new THREE.DirectionalLight('#fff1db',3);key.position.set(-12,15,18);scene.add(key);
      const rim=new THREE.DirectionalLight('#556dff',2);rim.position.set(10,-3,-30);scene.add(rim);
      scene.fog=new THREE.FogExp2('#030715',.0023);
      const player=makeStarship(false,resources);scene.add(player.group);
      const enemies=Array.from({length:3},()=>{const model=makeStarship(true,resources);model.group.rotation.y=Math.PI;model.group.scale.setScalar(.75);scene.add(model.group);return model;});
      const starPositions=new Float32Array(1600*3);
      for(let i=0;i<1600;i++){starPositions[i*3]=(Math.random()-.5)*230;starPositions[i*3+1]=(Math.random()-.5)*135;starPositions[i*3+2]=-260+Math.random()*290;}
      const starGeo=new THREE.BufferGeometry();starGeo.setAttribute('position',new THREE.BufferAttribute(starPositions,3));const starMat=new THREE.PointsMaterial({color:'#b8d7ff',size:.2,sizeAttenuation:true});scene.add(new THREE.Points(starGeo,starMat));resources.push(starGeo,starMat);
      const nebulaCanvas=document.createElement('canvas');nebulaCanvas.width=nebulaCanvas.height=256;const ctx=nebulaCanvas.getContext('2d'),gradient=ctx.createRadialGradient(128,128,5,128,128,128);gradient.addColorStop(0,'#46377780');gradient.addColorStop(.5,'#223b573d');gradient.addColorStop(1,'#0a061000');ctx.fillStyle=gradient;ctx.fillRect(0,0,256,256);const nebulaTexture=new THREE.CanvasTexture(nebulaCanvas),nebulaMat=new THREE.SpriteMaterial({map:nebulaTexture,transparent:true,depthWrite:false});const nebula=new THREE.Sprite(nebulaMat);nebula.position.set(-35,18,-190);nebula.scale.set(210,160,1);scene.add(nebula);resources.push(nebulaTexture,nebulaMat);
      const loader=new THREE.TextureLoader(),passing=[];
      for(const [i,id] of ['earth','mars','neptune','sun'].entries()){
        const map=loader.load(`/textures/solar/${id}.jpg`,()=>{if(disposed)map.dispose();});map.colorSpace=THREE.SRGBColorSpace;
        const geometry=new THREE.SphereGeometry(i===3?1.4:2.7,32,24),mat=i===3?new THREE.MeshBasicMaterial({map}):new THREE.MeshStandardMaterial({map,roughness:1});
        const mesh=new THREE.Mesh(geometry,mat);mesh.position.set((i%2?1:-1)*(22+i*2),i%2?11:-10,-80-i*70);scene.add(mesh);passing.push(mesh);resources.push(map,geometry,mat);
      }
      const boltGeo=new THREE.CylinderGeometry(.065,.065,2.8,6);boltGeo.rotateX(Math.PI/2);
      const boltMat=new THREE.MeshBasicMaterial({color:'#8bffff'}),laserMat=new THREE.MeshBasicMaterial({color:'#ff365e'});resources.push(boltGeo,boltMat,laserMat);
      const playerBolts=Array.from({length:130},()=>{const m=new THREE.Mesh(boltGeo,boltMat);m.visible=false;scene.add(m);return m;});
      const enemyLasers=Array.from({length:80},()=>{const m=new THREE.Mesh(boltGeo,laserMat);m.visible=false;scene.add(m);return m;});
      const particleGeo=new THREE.BufferGeometry(),particlePositions=new Float32Array(200*3),particleColors=new Float32Array(200*3);particleGeo.setAttribute('position',new THREE.BufferAttribute(particlePositions,3));particleGeo.setAttribute('color',new THREE.BufferAttribute(particleColors,3));particleGeo.setDrawRange(0,0);const particleMat=new THREE.PointsMaterial({size:.35,vertexColors:true,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending});scene.add(new THREE.Points(particleGeo,particleMat));resources.push(particleGeo,particleMat);
      const targetNodes=enemies.map((_,i)=>{const node=document.createElement('div');node.className='intercept-target';node.innerHTML=`<span>HOSTILE 0${i+1}</span><i></i>`;element.append(node);return node;});
      const project=(node,x,y,z)=>{const p=new THREE.Vector3(x,y,z).project(camera);node.hidden=p.z<0||p.z>1||Math.abs(p.x)>1||Math.abs(p.y)>1;node.style.left=(p.x+1)*50+'%';node.style.top=(1-p.y)*50+'%';};
      const resize=()=>{const w=element.clientWidth||960,h=element.clientHeight||540;renderer.setSize(w,h);camera.aspect=w/h;camera.position.z=8+Math.max(17,13/(Math.tan(THREE.MathUtils.degToRad(29))*camera.aspect));camera.lookAt(0,0,-25);camera.updateProjectionMatrix();};observer=new ResizeObserver(resize);observer.observe(element);resize();
      let previous=performance.now(),hudTime=0,decorTime=0;
      const draw=now=>{
        frame=requestAnimationFrame(draw);const delta=Math.min(.05,(now-previous)/1000);previous=now;if(document.hidden||!element.getClientRects().length)return;
        const g=game.current;stepMission(g,delta,input.current);
        const moving=['ready','playing','won'].includes(g.status)?delta:0;decorTime+=moving;
        for(let i=0;i<1600;i++){const index=i*3+2;starPositions[index]+=moving*38;if(starPositions[index]>30)starPositions[index]=-260;}starGeo.attributes.position.needsUpdate=true;
        passing.forEach((mesh,i)=>{mesh.position.z+=moving*12;mesh.rotation.y+=moving*.08;if(mesh.position.z>34)mesh.position.z=-250;});
        player.group.position.set(g.player.x,g.player.y,g.player.z);player.group.rotation.z=THREE.MathUtils.lerp(player.group.rotation.z,(input.current.left?.18:0)-(input.current.right?.18:0),.1);player.group.rotation.x=THREE.MathUtils.lerp(player.group.rotation.x,(input.current.up?-.06:0)+(input.current.down?.06:0),.1);
        player.group.visible=g.player.hp>0;player.group.traverse(obj=>{if(obj.isMesh)obj.visible=g.player.invincible<=0||Math.sin(g.time*16)>-.3;});
        player.engines.forEach((mesh,i)=>mesh.scale.setScalar(1+Math.sin(decorTime*36+i)*.08));
        enemies.forEach((model,i)=>{const enemy=g.enemies[i];model.group.visible=enemy.hp>0;model.group.position.set(enemy.x,enemy.y,enemy.z);model.group.rotation.z=Math.sin(g.time*.65+enemy.phase)*.09;model.weapons.forEach(mesh=>mesh.material.emissiveIntensity=enemy.fire<.55?6:1.5);const node=targetNodes[i];project(node,enemy.x,enemy.y+2,enemy.z);if(enemy.hp<=0)node.hidden=true;node.classList.toggle('locked',g.lock===enemy.id);node.classList.toggle('charging',enemy.fire<.55);node.querySelector('i').style.setProperty('--target-health',enemy.hp/enemy.maxHp*100+'%');});
        const updateBolts=(pool,bolts)=>pool.forEach((mesh,i)=>{const b=bolts[i];mesh.visible=!!b;if(b){mesh.position.set(b.x,b.y,b.z);mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),new THREE.Vector3(b.vx,b.vy,b.vz).normalize());}});updateBolts(playerBolts,g.bolts);updateBolts(enemyLasers,g.lasers);
        g.particles.forEach((p,i)=>{particlePositions.set([p.x,p.y,p.z],i*3);const color=new THREE.Color(p.color);color.multiplyScalar(Math.min(1,p.life*2));particleColors.set([color.r,color.g,color.b],i*3);});particleGeo.setDrawRange(0,g.particles.length);particleGeo.attributes.position.needsUpdate=true;particleGeo.attributes.color.needsUpdate=true;
        field.current?.classList.toggle('taking-hit',g.player.invincible>1.2);
        renderer.render(scene,camera);
        if(g.status==='playing'||['won','lost'].includes(g.status))g.events.slice(0,3).forEach(beep);g.events=[];
        if(now-hudTime>100){setHud(stats(g));hudTime=now;}
      };frame=requestAnimationFrame(draw);api.current={};
      return clean;
    }catch{setError('This 3D mission requires WebGL2. Try a compatible browser or return to the 2D arcade.');clean();}
  },[]);
  useEffect(()=>{
    const autoPause=()=>{input.current={};if(game.current.status==='playing'){game.current.status='paused';setHud(stats(game.current));}};
    const visibility=()=>{if(document.hidden)autoPause();};
    const release=e=>{const keys={arrowleft:'left',a:'left',arrowright:'right',d:'right',arrowup:'up',w:'up',arrowdown:'down',s:'down',' ':'fire'};const key=keys[e.key.toLowerCase()];if(key)input.current[key]=false;};
    window.addEventListener('blur',autoPause);window.addEventListener('keyup',release);document.addEventListener('visibilitychange',visibility);
    return()=>{window.removeEventListener('blur',autoPause);window.removeEventListener('keyup',release);document.removeEventListener('visibilitychange',visibility);audio.current?.close().catch(()=>{});};
  },[]);
  const keyDown=e=>{if(['BUTTON','SELECT'].includes(e.target.tagName))return;const key=e.key.toLowerCase(),keys={arrowleft:'left',a:'left',arrowright:'right',d:'right',arrowup:'up',w:'up',arrowdown:'down',s:'down',' ':'fire'};
    if(keys[key]){e.preventDefault();input.current.pointer=null;input.current[keys[key]]=true;}else if(['p','escape','r'].includes(key)){e.preventDefault();if(!e.repeat)key==='r'?launch():pause();}};
  const aim=e=>{const rect=host.current.getBoundingClientRect();input.current.pointer={x:((e.clientX-rect.left)/rect.width-.5)*20,y:(.5-(e.clientY-rect.top)/rect.height)*9.4};};
  const touch=(key,value,e)=>{e.preventDefault();input.current.pointer=null;input.current[key]=value;if(value)e.currentTarget.setPointerCapture?.(e.pointerId);};
  const win=hud.status==='won',end=win||hud.status==='lost';
  return <main className="intercept-page" id="game-zone" aria-label="Starship Intercept 3D mission">
    <header className="intercept-heading"><div><p className="eyebrow">GAME ZONE / 3D FLIGHT COMBAT</p><h1>Starship <span>Intercept</span></h1><p>Three hostiles. One fighter. Bring your ship home.</p></div><button onClick={onBack}>← Back to arcade</button></header>
    <div className="intercept-console"><div className="intercept-command"><span>OPERATION: THREE TARGETS <b>MEDIUM</b></span><div><button onClick={soundToggle} aria-pressed={soundOn}>{soundOn?'Sound on':'Sound off'}</button><button onClick={pause} disabled={!['playing','paused'].includes(hud.status)}>{hud.status==='paused'?'Resume':'Pause'}</button><button onClick={launch} disabled={!!error}>Restart</button></div></div>
      <div className="intercept-field" ref={field} tabIndex={0} role="group" aria-label="3D mission controls: WASD or arrows move, Space fires, P pauses, R restarts" onKeyDown={keyDown} onBlur={e=>{input.current={};if(!e.relatedTarget?.closest?.('.intercept-console')&&game.current.status==='playing'){game.current.status='paused';setHud(stats(game.current));}}}>
        <div className="intercept-renderer" ref={host} onPointerDown={e=>{if(e.target.tagName!=='CANVAS')return;e.preventDefault();field.current?.focus({preventScroll:true});e.currentTarget.setPointerCapture?.(e.pointerId);aim(e);input.current.fire=true;}} onPointerMove={e=>{if(input.current.fire&&input.current.pointer)aim(e);}} onPointerUp={()=>{input.current.pointer=null;input.current.fire=false;}} onPointerCancel={()=>{input.current.pointer=null;input.current.fire=false;}}/>
        <div className="intercept-hud"><span>HULL <b>{'▰'.repeat(Math.max(0,hud.hp))}{'▱'.repeat(5-Math.max(0,hud.hp))}</b></span><span>HOSTILES <b>{3-hud.destroyed} / 3</b></span><span>SCORE <b>{String(hud.score).padStart(5,'0')}</b></span></div>
        {hud.status==='playing'&&<div className="intercept-reticle" aria-hidden="true"><i/><span>{hud.lock!==null?'TARGET LOCK':'ALIGN TO LOCK'}</span></div>}
        {(hud.status!=='playing'||error)&&<div className={`intercept-overlay ${win?'victory':''}`}>
          <p className="eyebrow">{error?'GRAPHICS UNAVAILABLE':win?'ALL HOSTILES ELIMINATED':hud.status==='lost'?'FIGHTER LOST':hud.status==='paused'?'FLIGHT PAUSED':'READY FOR INTERCEPT'}</p>
          <h2>{win?<><span>MISSION</span><strong>ACCOMPLISHED</strong></>:hud.status==='lost'?'MISSION FAILED':hud.status==='paused'?'HOLD POSITION':'ENTER THE STARFIELD'}</h2>
          <p>{error|| (win?`3 / 3 SHIPS DESTROYED · ${hud.score} PTS · ${hud.accuracy}% ACCURACY`:hud.status==='lost'?'The fleet is still out there. Repair, rearm, and try again.':hud.status==='paused'?'Your mission is paused. Resume when ready.':'Dodge the red lasers. Align with a target, hold fire, and destroy all three ships.')}</p>
          {win&&<div className="intercept-medals" aria-hidden="true">✦ ✦ ✦</div>}
          <button className="arcade-launch" disabled={!!error} onClick={hud.status==='paused'?pause:launch}>{hud.status==='paused'?'Resume mission':end?'Play again':'Launch operation'} →</button>
          {!error&&<small>WASD / arrows to move · Hold SPACE to fire · Drag and hold on touch screens</small>}
        </div>}
      </div>
      <div className="intercept-touch">{[['left','←'],['up','↑'],['down','↓'],['right','→'],['fire','FIRE']].map(([key,label])=><button key={key} aria-label={key==='fire'?'Hold mission fire':`Fly ${key}`} onPointerDown={e=>touch(key,true,e)} onPointerUp={e=>touch(key,false,e)} onPointerCancel={e=>touch(key,false,e)} onLostPointerCapture={()=>{input.current[key]=false;}}>{label}</button>)}</div>
      <div className="intercept-target-list">{hud.enemies.map((enemy,i)=><div key={i} className={enemy.hp<=0?'defeated':''}><span>{enemy.hp<=0?'✓':'◇'} HOSTILE 0{i+1}</span><div><i style={{width:enemy.hp/enemy.max*100+'%'}}/></div><small>{enemy.hp<=0?'DESTROYED':`${enemy.hp} / ${enemy.max} HULL`}</small></div>)}</div>
    </div>
    <footer className="intercept-notes"><p>Keep moving when enemy weapons glow. Aim assistance engages when you line up with a hostile. Hull damage grants brief protection.</p><p>Original ship models inspired by your references · Fictional starfield and passing planets · P / Escape pauses · R restarts</p></footer>
  </main>;
}
