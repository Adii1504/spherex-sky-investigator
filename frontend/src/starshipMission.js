const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
export function missionState(){return {status:'ready',time:0,score:0,destroyed:0,shots:0,hits:0,cooldown:0,
  player:{x:0,y:0,z:8,hp:5,invincible:0},
  enemies:[-7,0,7].map((x,i)=>({id:i,x,y:i===1?-.5:2,z:-43-i*4,baseX:x,hp:32,maxHp:32,fire:1.5+i*.65,phase:i*2.1})),
  bolts:[],lasers:[],particles:[],events:[],lock:null};}
export function startMission(){const game=missionState();game.status='playing';return game;}
export function pauseMission(game){if(game.status==='playing')game.status='paused';else if(game.status==='paused')game.status='playing';}
export function segmentHit(from,to,target,radius){
  const d=[to.x-from.x,to.y-from.y,to.z-from.z],v=[target.x-from.x,target.y-from.y,target.z-from.z];
  const length=d.reduce((s,x)=>s+x*x,0),t=length?clamp(d.reduce((s,x,i)=>s+x*v[i],0)/length,0,1):0;
  return Math.hypot(from.x+d[0]*t-target.x,from.y+d[1]*t-target.y,from.z+d[2]*t-target.z)<radius;
}
function velocity(from,to,speed){const d=[to.x-from.x,to.y-from.y,to.z-from.z],r=Math.hypot(...d)||1;return {vx:d[0]/r*speed,vy:d[1]/r*speed,vz:d[2]/r*speed};}
function explode(game,position,color,count){
  for(let i=0;i<count;i++){const a=i*2.3999,z=1-2*(i+.5)/count,r=Math.sqrt(1-z*z),speed=4+i%7;game.particles.push({...position,vx:Math.cos(a)*r*speed,vy:Math.sin(a)*r*speed,vz:z*speed,life:.6+(i%8)*.08,color});}
  if(game.particles.length>200)game.particles.splice(0,game.particles.length-200);
}
export function stepMission(game,elapsed,input={}){
  if(game.status!=='playing')return;
  const dt=clamp(elapsed,0,.05),p=game.player;game.time+=dt;game.events=[];game.cooldown-=dt;p.invincible=Math.max(0,p.invincible-dt);
  let dx=(input.right?1:0)-(input.left?1:0),dy=(input.up?1:0)-(input.down?1:0);
  if(input.pointer){dx=clamp((input.pointer.x-p.x)*3,-1,1);dy=clamp((input.pointer.y-p.y)*3,-1,1);}
  const factor=Math.hypot(dx,dy)>1?1/Math.hypot(dx,dy):1;
  p.x=clamp(p.x+dx*factor*12*dt,-10,10);p.y=clamp(p.y+dy*factor*9*dt,-4.7,4.7);
  for(const enemy of game.enemies){if(enemy.hp<=0)continue;enemy.x=enemy.baseX+Math.sin(game.time*.65+enemy.phase)*1.6;enemy.y=(enemy.id===1?-.5:2)+Math.sin(game.time*.8+enemy.phase)*1.1;
    enemy.fire-=dt;if(enemy.fire<=0){
      const aim={x:p.x,y:p.y,z:p.z};
      for(const offset of [-.8,.8]){const origin={x:enemy.x+offset,y:enemy.y,z:enemy.z+2};game.lasers.push({...origin,...velocity(origin,aim,27),dead:false});}
      enemy.fire=2.25+enemy.id*.2;game.events.push('incoming');
    }
  }
  const candidates=game.enemies.filter(e=>e.hp>0&&Math.abs(e.x-p.x)<3.1&&Math.abs(e.y-p.y)<3.3).sort((a,b)=>Math.hypot(a.x-p.x,a.y-p.y)-Math.hypot(b.x-p.x,b.y-p.y));
  const lock=candidates[0];game.lock=lock?.id??null;
  if(input.fire&&game.cooldown<=0){
    const aim=lock?{x:lock.x,y:lock.y,z:lock.z}:{x:p.x,y:p.y,z:-100};
    for(const offset of [-.85,.85]){const origin={x:p.x+offset,y:p.y-.05,z:p.z-2.2};game.bolts.push({...origin,...velocity(origin,aim,115),dead:false});game.shots++;}
    game.cooldown=.19;game.events.push('shoot');
  }
  for(const bolt of game.bolts){const before={...bolt};bolt.x+=bolt.vx*dt;bolt.y+=bolt.vy*dt;bolt.z+=bolt.vz*dt;
    for(const enemy of game.enemies){if(!bolt.dead&&enemy.hp>0&&segmentHit(before,bolt,enemy,2.25)){
      bolt.dead=true;enemy.hp--;game.hits++;game.score+=10;game.events.push('hit');explode(game,bolt,'#8cefff',3);
      if(enemy.hp===0){game.destroyed++;game.score+=1000;game.events.push('destroy');explode(game,enemy,'#ffae64',42);}
    }}
  }
  for(const laser of game.lasers){const before={...laser};laser.x+=laser.vx*dt;laser.y+=laser.vy*dt;laser.z+=laser.vz*dt;
    if(!laser.dead&&segmentHit(before,laser,p,.88)){laser.dead=true;if(p.invincible<=0){p.hp--;p.invincible=1.5;game.events.push('damage');explode(game,p,'#ff777f',12);}}
  }
  game.bolts=game.bolts.filter(b=>!b.dead&&b.z>-125).slice(-130);game.lasers=game.lasers.filter(b=>!b.dead&&b.z<25&&Math.abs(b.x)<60&&Math.abs(b.y)<30).slice(-80);
  for(const particle of game.particles){particle.x+=particle.vx*dt;particle.y+=particle.vy*dt;particle.z+=particle.vz*dt;particle.life-=dt;}game.particles=game.particles.filter(p=>p.life>0);
  if(p.hp<=0){game.status='lost';game.events.push('lost');}
  else if(game.destroyed===3){game.status='won';game.events.push('won');game.lasers=[];}
}
