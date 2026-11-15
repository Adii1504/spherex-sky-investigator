import React,{lazy,Suspense,useEffect,useRef,useState} from 'react';
import {ARENA,newGame,startGame,togglePause,pulse,stepGame,paintGame} from '../gameEngine.js';

const MODES=[{id:'patrol',name:'Nebula Patrol',tag:'WAVE SHOOTER',description:'Defend the frontier. Break enemy formations, collect upgrades, and face a flagship every fifth wave.',accent:'#a191ff'},
  {id:'asteroids',name:'Asteroid Run',tag:'DEBRIS SURVIVAL',description:'Carve a path through the belt. Dodge drifting rocks and use your laser to clear the way.',accent:'#ffbe83'}];
const readBest=mode=>{try{return Math.max(0,Number(localStorage.getItem('whylab.arcade.'+mode))||0);}catch{return 0;}};
const snapshot=g=>({status:g.status,score:g.score,wave:g.wave,health:g.player.health,pulses:g.pulses,kills:g.kills,rapid:g.player.rapid>0,time:Math.floor(g.time)});
const StarshipMission=lazy(()=>import('./StarshipMission.jsx'));
export default function GameZone(){
  const [mission,setMission]=useState(false);
  return mission?<Suspense fallback={<p role="status">Preparing 3D Starship Intercept…</p>}><StarshipMission onBack={()=>setMission(false)}/></Suspense>:<Arcade onOpenMission={()=>setMission(true)}/>;
}
function Arcade({onOpenMission}){
  const canvas=useRef(null),stage=useRef(null),game=useRef(newGame()),input=useRef({}),audio=useRef(null),soundEnabled=useRef(false);
  const [mode,setMode]=useState('patrol'),[hud,setHud]=useState(snapshot(game.current)),[best,setBest]=useState(readBest('patrol')),[sound,setSound]=useState(false),[notice,setNotice]=useState('');
  const modeInfo=MODES.find(item=>item.id===mode);
  const publish=()=>setHud(snapshot(game.current));
  const save=g=>{const previous=readBest(g.mode);if(g.score>previous){try{localStorage.setItem('whylab.arcade.'+g.mode,String(g.score));}catch{}return g.score;}return previous;};
  const choose=next=>{save(game.current);input.current={};game.current=newGame(next);setMode(next);setBest(readBest(next));publish();setNotice('');};
  const begin=()=>{input.current={};game.current=startGame(newGame(mode));publish();stage.current?.focus({preventScroll:true});canvas.current?.scrollIntoView?.({block:'center',behavior:'smooth'});};
  const pause=()=>{togglePause(game.current);input.current={};publish();if(game.current.status==='playing')stage.current?.focus({preventScroll:true});};
  const usePulse=()=>{if(pulse(game.current)){publish();beep('pulse');}};
  const beep=event=>{
    const context=audio.current;if(!soundEnabled.current||!context||context.state!=='running')return;
    const oscillator=context.createOscillator(),gain=context.createGain();
    oscillator.type=event==='shoot'?'square':'triangle';oscillator.frequency.setValueAtTime(event==='shoot'?560:event==='damage'?80:event==='pulse'?280:140,context.currentTime);
    oscillator.frequency.exponentialRampToValueAtTime(45,context.currentTime+.1);gain.gain.setValueAtTime(.025,context.currentTime);gain.gain.exponentialRampToValueAtTime(.001,context.currentTime+.12);
    oscillator.connect(gain);gain.connect(context.destination);oscillator.start();oscillator.stop(context.currentTime+.13);
  };
  const toggleSound=async()=>{
    if(soundEnabled.current){soundEnabled.current=false;setSound(false);return;}
    try{const Audio=window.AudioContext||window.webkitAudioContext;if(!Audio)throw Error();if(!audio.current)audio.current=new Audio();await audio.current.resume();soundEnabled.current=true;setSound(true);}catch{setNotice('Sound is unavailable in this browser. You can still play.');}
  };
  useEffect(()=>{
    const context=canvas.current.getContext('2d');if(!context){setNotice('This browser cannot draw the game canvas. Try a browser with Canvas 2D support.');return;}
    let frame,last=performance.now(),lastHUD=0;
    const stopForBlur=()=>{input.current={};if(game.current.status==='playing'){game.current.status='paused';setHud(snapshot(game.current));}};
    const hidden=()=>{if(document.hidden)stopForBlur();};
    const release=e=>{const map={ArrowLeft:'left',a:'left',ArrowRight:'right',d:'right',ArrowUp:'up',w:'up',ArrowDown:'down',s:'down',' ':'fire'};const key=map[e.key]||map[e.key.toLowerCase()];if(key)input.current[key]=false;};
    window.addEventListener('blur',stopForBlur);document.addEventListener('visibilitychange',hidden);window.addEventListener('keyup',release);
    const draw=now=>{
      frame=requestAnimationFrame(draw);const dt=(now-last)/1000;last=now;
      if(document.hidden)return;
      const g=game.current,oldStatus=g.status;stepGame(g,dt,input.current);paintGame(context,g);
      if(g.event&&g.status==='playing')beep(g.event);
      if(g.status==='over'&&oldStatus!=='over'){setBest(save(g));setHud(snapshot(g));input.current={};}
      else if(now-lastHUD>150){setHud(snapshot(g));lastHUD=now;}
    };frame=requestAnimationFrame(draw);
    return()=>{cancelAnimationFrame(frame);window.removeEventListener('blur',stopForBlur);document.removeEventListener('visibilitychange',hidden);window.removeEventListener('keyup',release);save(game.current);audio.current?.close().catch(()=>{});};
  },[]);
  const keyDown=event=>{
    if(['BUTTON','SELECT','INPUT'].includes(event.target.tagName))return;
    const key=event.key.toLowerCase(),map={arrowleft:'left',a:'left',arrowright:'right',d:'right',arrowup:'up',w:'up',arrowdown:'down',s:'down',' ':'fire'};
    if(map[key]){event.preventDefault();input.current.pointer=null;input.current[map[key]]=true;}
    else if(['p','escape','q','r'].includes(key)){event.preventDefault();if(event.repeat)return;if(key==='p'||key==='escape')pause();else if(key==='q')usePulse();else if(key==='r')begin();}
  };
  const pointer=event=>{const rect=canvas.current.getBoundingClientRect();input.current.pointer={x:(event.clientX-rect.left)/rect.width*ARENA.width,y:(event.clientY-rect.top)/rect.height*ARENA.height};};
  const hold=(key,value,event)=>{event.preventDefault();input.current.pointer=null;input.current[key]=value;if(value)event.currentTarget.setPointerCapture?.(event.pointerId);};
  return <main className="game-zone" id="game-zone" aria-label="Space arcade Game Zone">
    <header className="arcade-heading"><div><p className="eyebrow">OFF DUTY · INTO THE COSMOS</p><h1>Game <span>Zone</span><i aria-hidden="true">✦</i></h1><p>A little less observation. A little more action.</p></div><div className="arcade-local"><span/>LOCAL ARCADE<small>Play without a backend connection</small></div></header>
    <button className="arcade-feature" onClick={onOpenMission}><div><small>NEW MISSION / REAL-TIME 3D</small><h2>Starship Intercept</h2><p>Pilot a twin-engine fighter. Dodge lasers in a moving starfield. Destroy all three hostiles to complete the mission.</p><strong>ENTER MISSION →</strong></div><svg viewBox="0 0 240 140" aria-hidden="true"><path d="M120 15 143 68 219 82 224 114 142 98 120 121 98 98 16 114 21 82 97 68Z" fill="#6a7b8c" stroke="#9fd4ea" strokeWidth="2"/><path d="M120 22 133 73 120 89 107 73Z" fill="#142838" stroke="#80d3f0"/><path d="M43 88 87 93M153 93 197 88" stroke="#e4a065" strokeWidth="5"/><ellipse cx="97" cy="108" rx="12" ry="10" fill="#253548" stroke="#cbd5df" strokeWidth="4"/><ellipse cx="143" cy="108" rx="12" ry="10" fill="#253548" stroke="#cbd5df" strokeWidth="4"/><path d="M97 113 97 135M143 113 143 135" stroke="#6deaff" strokeWidth="8"/></svg></button>
    <div className="arcade-mode-grid">{MODES.map(item=><button key={item.id} className={`arcade-mode ${mode===item.id?'selected':''}`} style={{'--mode-accent':item.accent}} aria-pressed={mode===item.id} onClick={()=>choose(item.id)}>
      <span className={`arcade-emblem ${item.id}`} aria-hidden="true">{item.id==='patrol'?'✧':'◈'}</span><span><small>{item.tag}</small><strong>{item.name}</strong><span>{item.description}</span></span><b aria-hidden="true">↗</b></button>)}</div>
    <section className="arcade-console" aria-label={modeInfo.name}>
      <div className="arcade-console-bar"><span><i/> {modeInfo.name.toUpperCase()}</span><div><button onClick={toggleSound} aria-pressed={sound}>{sound?'Sound on':'Sound off'}</button><button onClick={pause} disabled={!['playing','paused'].includes(hud.status)}>{hud.status==='paused'?'Resume':'Pause'}</button><button onClick={begin}>Restart</button></div></div>
      <div className="arcade-layout"><div className="arcade-stage" tabIndex={0} ref={stage} role="group" aria-label="Space shooter playfield. Arrow keys or WASD move; Space fires; Q pulse; P pause; R restart." onKeyDown={keyDown} onBlur={event=>{input.current={};if(!event.relatedTarget?.closest?.('.arcade-console')&&game.current.status==='playing'){game.current.status='paused';publish();}}}>
        <canvas ref={canvas} width={ARENA.width} height={ARENA.height} aria-label="Space shooter playfield" onPointerDown={event=>{event.preventDefault();stage.current?.focus({preventScroll:true});event.currentTarget.setPointerCapture?.(event.pointerId);pointer(event);input.current.fire=true;}} onPointerMove={event=>{if(event.buttons||event.pointerType==='touch'&&input.current.fire)pointer(event);}} onPointerUp={()=>{input.current.fire=false;input.current.pointer=null;}} onPointerCancel={()=>{input.current.fire=false;input.current.pointer=null;}}/>
        {hud.status!=='playing'&&<div className="arcade-overlay"><p className="eyebrow">{hud.status==='over'?'MISSION COMPLETE':hud.status==='paused'?'TAKE A BREATHER':'PILOT, YOU ARE CLEARED'}</p><h2>{hud.status==='over'?'Good flight. Go again?':hud.status==='paused'?'Flight paused.':modeInfo.name}</h2><p>{hud.status==='over'?`${hud.score.toLocaleString()} points · ${hud.kills} targets · Wave ${hud.wave}`:hud.status==='paused'?'Your run is right where you left it.':'Move, dodge, and hold fire. The next wave is yours.'}</p><button className="arcade-launch" onClick={hud.status==='paused'?()=>{pause();stage.current?.focus({preventScroll:true});}:begin}>{hud.status==='paused'?'Resume flight':hud.status==='over'?'Fly again':'Launch mission'} <span>→</span></button><small>{hud.status==='ready'?'WASD / arrows · Space to fire · Touch and drag on mobile':'P to pause · R to restart'}</small></div>}
        <div className="arcade-touch" aria-label="Touch game controls">{[['left','←'],['right','→'],['fire','FIRE']].map(([key,label])=><button key={key} aria-label={key==='fire'?'Hold to fire':`Move ${key}`} onPointerDown={e=>hold(key,true,e)} onPointerUp={e=>hold(key,false,e)} onPointerCancel={e=>hold(key,false,e)} onLostPointerCapture={()=>{input.current[key]=false;}}>{label}</button>)}<button onClick={usePulse} disabled={hud.pulses===0||hud.status!=='playing'}>PULSE</button></div>
      </div><aside className="arcade-dashboard" aria-label="Run statistics"><div className="arcade-score"><small>SCORE</small><strong>{String(hud.score).padStart(6,'0')}</strong></div><div className="arcade-stats"><div><small>PERSONAL BEST</small><b>{Math.max(best,hud.score).toLocaleString()}</b></div><div><small>WAVE</small><b>{String(hud.wave).padStart(2,'0')}</b></div><div><small>HULL</small><b className="arcade-hearts" aria-label={`${hud.health} health remaining`}>{'♥'.repeat(Math.max(0,hud.health))}{'♡'.repeat(3-Math.max(0,hud.health))}</b></div><div><small>PULSES</small><b>{'◆'.repeat(hud.pulses)||'—'}</b></div></div>
        <div className="arcade-brief"><small>FLIGHT MANUAL</small><p><kbd>WASD</kbd> / <kbd>↑↓←→</kbd> Move</p><p><kbd>SPACE</kbd> Hold to fire</p><p><kbd>Q</kbd> Clear nearby threats</p><p><kbd>P</kbd> Pause / resume</p><p><kbd>R</kbd> Restart run</p></div><p className="arcade-tip">{hud.rapid?'RAPID FIRE ACTIVE · Twin lasers online.':mode==='patrol'?'Collect » for twin lasers and + to repair your hull. Save a pulse for the flagship.':'Drag your ship through gaps. Rocks drift sideways; keep a clear escape route.'}</p>
      </aside></div>
    </section>
    {notice&&<p role="status" className="arcade-notice">{notice}</p>}
    <footer className="arcade-footer"><p>Fictional arcade play · Scores stay in this browser · Leaving Game Zone ends the current run</p><p>No astronomy measurements or investigations are used by these games.</p></footer>
  </main>;
}
