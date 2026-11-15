export const ARENA={width:900,height:560};
const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
const hit=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y)<a.r+b.r;
export function newGame(mode='patrol',random=Math.random){
  return {mode,status:'ready',random,time:0,score:0,wave:1,kills:0,shots:0,hits:0,
    player:{x:450,y:490,r:16,health:3,invincible:0,rapid:0},pulses:3,
    bullets:[],enemies:[],hostile:[],particles:[],pickups:[],cooldown:0,nextWave:0,spawned:false,event:''};
}
export function startGame(game){game.status='playing';spawnWave(game);return game;}
export function togglePause(game){if(game.status==='playing')game.status='paused';else if(game.status==='paused')game.status='playing';}
function spawnWave(game){
  const random=game.random;game.spawned=true;game.event=`Wave ${game.wave}`;game.hostile=[];game.nextWave=0;
  const count=Math.min(24,7+game.wave*2);
  game.enemies=Array.from({length:count},(_,i)=>{
    const rock=game.mode==='asteroids',x=80+i%6*145;
    return {x,y:-60-Math.floor(i/6)*90,baseX:x,r:rock?20+random()*16:18,
      hp:rock?2:1+Math.floor(game.wave/5),maxHp:rock?2:1+Math.floor(game.wave/5),
      speed:(rock?45:26)+game.wave*5+random()*20,vx:(random()-.5)*55,
      phase:random()*6.28,angle:random()*6.28,fire:1.5+random()*3,rock,boss:false};
  });
  if(game.mode==='patrol'&&game.wave%5===0)game.enemies.push({x:450,y:-110,baseX:450,r:52,hp:35+game.wave*3,maxHp:35+game.wave*3,speed:20,phase:0,angle:0,fire:1,boss:true,rock:false});
}
function burst(game,x,y,color,count=14){
  for(let i=0;i<count;i++){const a=game.random()*Math.PI*2,s=40+game.random()*130;game.particles.push({x,y,vx:Math.cos(a)*s,vy:Math.sin(a)*s,life:.3+game.random()*.45,color});}
  if(game.particles.length>220)game.particles.splice(0,game.particles.length-220);
}
function destroy(game,enemy){
  if(enemy.dead)return;enemy.dead=true;game.kills++;game.score+=enemy.boss?1000:enemy.rock?70:100;
  burst(game,enemy.x,enemy.y,enemy.rock?'#f2b879':'#fa77c3',enemy.boss?35:14);game.event='destroy';
  if(game.random()<.16)game.pickups.push({x:enemy.x,y:enemy.y,r:12,type:game.random()<.4?'shield':'rapid'});
}
function damage(game){
  if(game.player.invincible>0)return;
  game.player.health--;game.player.invincible=1.6;game.event='damage';burst(game,game.player.x,game.player.y,'#73e5fa');
  if(game.player.health<=0){game.status='over';game.event='over';burst(game,game.player.x,game.player.y,'#ffbd70',30);}
}
export function pulse(game){
  if(game.status!=='playing'||game.pulses<1)return false;
  game.pulses--;game.hostile=[];game.event='pulse';
  for(const enemy of game.enemies)if(enemy.y>0){enemy.hp-=5;if(enemy.hp<=0)destroy(game,enemy);else burst(game,enemy.x,enemy.y,'#73e5fa',6);}
  return true;
}
export function stepGame(game,elapsed,input={}){
  if(game.status!=='playing')return;
  const dt=clamp(elapsed,0,.05),p=game.player;game.time+=dt;game.event='';
  p.invincible=Math.max(0,p.invincible-dt);p.rapid=Math.max(0,p.rapid-dt);game.cooldown-=dt;
  if(input.pointer){
    const dx=input.pointer.x-p.x,dy=input.pointer.y-p.y,d=Math.hypot(dx,dy),travel=Math.min(d,430*dt);
    if(d>0){p.x+=dx/d*travel;p.y+=dy/d*travel;}
  }else{
    const dx=(input.right?1:0)-(input.left?1:0),dy=(input.down?1:0)-(input.up?1:0),factor=dx&&dy?Math.SQRT1_2:1;
    p.x+=dx*360*dt*factor;p.y+=dy*360*dt*factor;
  }
  p.x=clamp(p.x,22,878);p.y=clamp(p.y,210,535);
  if(input.fire&&game.cooldown<=0){
    const offsets=p.rapid>0?[-9,9]:[0];for(const offset of offsets)game.bullets.push({x:p.x+offset,y:p.y-22,r:4,dead:false});
    game.shots+=offsets.length;game.cooldown=p.rapid>0?.09:.17;game.event='shoot';
  }
  for(const bullet of game.bullets)bullet.y-=650*dt;
  for(const enemy of game.enemies){
    if(enemy.dead)continue;
    if(enemy.rock){enemy.x+=enemy.vx*dt;enemy.y+=enemy.speed*dt;enemy.angle+=dt*.7;if(enemy.x<-40)enemy.x=940;if(enemy.x>940)enemy.x=-40;}
    else{enemy.x=enemy.baseX+Math.sin(game.time*(enemy.boss?.65:1.2)+enemy.phase)*(enemy.boss?260:45);enemy.y+=enemy.speed*dt;if(enemy.boss&&enemy.y>95)enemy.y=95;
      enemy.fire-=dt;if(enemy.y>20&&enemy.fire<=0){
        for(const vx of enemy.boss?[-90,0,90]:[0])if(game.hostile.length<140)game.hostile.push({x:enemy.x,y:enemy.y+enemy.r,r:5,vx,vy:145+game.wave*6});
        enemy.fire=enemy.boss?.8:Math.max(.65,3-game.wave*.1)+game.random();
      }
    }
    for(const bullet of game.bullets)if(!bullet.dead&&!enemy.dead&&hit(bullet,enemy)){bullet.dead=true;enemy.hp--;game.hits++;burst(game,bullet.x,bullet.y,'#79e9ff',3);if(enemy.hp<=0)destroy(game,enemy);}
    if(!enemy.dead&&hit(p,enemy)){damage(game);if(!enemy.boss)enemy.dead=true;}
  }
  for(const bullet of game.hostile){bullet.y+=bullet.vy*dt;bullet.x+=bullet.vx*dt;if(!bullet.dead&&hit(p,bullet)){bullet.dead=true;damage(game);}}
  for(const item of game.pickups){item.y+=75*dt;if(hit(p,item)){item.dead=true;if(item.type==='shield')p.health=Math.min(3,p.health+1);else p.rapid=8;game.event='pickup';burst(game,p.x,p.y,'#93f5c1',10);}}
  for(const particle of game.particles){particle.x+=particle.vx*dt;particle.y+=particle.vy*dt;particle.life-=dt;}
  game.bullets=game.bullets.filter(b=>!b.dead&&b.y>-15);
  game.hostile=game.hostile.filter(b=>!b.dead&&b.y<580&&b.x>-20&&b.x<920);
  game.enemies=game.enemies.filter(e=>!e.dead&&e.y<610);
  game.pickups=game.pickups.filter(i=>!i.dead&&i.y<580);game.particles=game.particles.filter(p=>p.life>0);
  if(!game.enemies.length&&game.status==='playing'){game.nextWave+=dt;if(game.nextWave>1.4){game.wave++;spawnWave(game);}}
}

export function paintGame(ctx,game){
  const {width:w,height:h}=ARENA,t=game.time;
  const bg=ctx.createLinearGradient(0,0,w,h);bg.addColorStop(0,'#060b20');bg.addColorStop(.55,'#10132f');bg.addColorStop(1,'#021720');ctx.fillStyle=bg;ctx.fillRect(0,0,w,h);
  const nebula=ctx.createRadialGradient(650,160,0,650,160,420);nebula.addColorStop(0,'#6831a026');nebula.addColorStop(1,'#06102000');ctx.fillStyle=nebula;ctx.fillRect(0,0,w,h);
  for(let i=0;i<110;i++){ctx.fillStyle=i%5?'#bccce1':'#8be4ff';ctx.globalAlpha=.25+(i%4)*.18;ctx.fillRect((i*137.51)%w,(i*83.7+t*(15+i%3*12))%h,i%7?1.3:2.5,i%7?1.3:2.5);}ctx.globalAlpha=1;
  for(const enemy of game.enemies){
    ctx.save();ctx.translate(enemy.x,enemy.y);
    if(enemy.rock){ctx.rotate(enemy.angle);ctx.fillStyle='#4b4255';ctx.strokeStyle='#c3a1ad';ctx.lineWidth=2;ctx.beginPath();for(let i=0;i<9;i++){const a=i/9*Math.PI*2,r=enemy.r*(i%2?.85:1);const x=Math.cos(a)*r,y=Math.sin(a)*r;if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y);}ctx.closePath();ctx.fill();ctx.stroke();ctx.fillStyle='#28283c';ctx.beginPath();ctx.arc(-7,0,enemy.r*.25,0,7);ctx.fill();}
    else{const r=enemy.r;ctx.shadowColor=enemy.boss?'#ffb56e':'#ff69bc';ctx.shadowBlur=12;ctx.fillStyle=enemy.boss?'#a34d6e':'#713e83';ctx.strokeStyle=enemy.boss?'#ffbc78':'#ff88d2';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(-r,0);ctx.lineTo(-r*.5,-r*.45);ctx.lineTo(0,-r*.65);ctx.lineTo(r*.5,-r*.45);ctx.lineTo(r,0);ctx.lineTo(r*.5,r*.45);ctx.lineTo(-r*.5,r*.45);ctx.closePath();ctx.fill();ctx.stroke();ctx.shadowBlur=0;ctx.fillStyle='#a9f2ff';ctx.fillRect(-r*.22,-r*.3,r*.44,r*.3);if(enemy.boss){ctx.fillStyle='#ff74ac';ctx.fillRect(-r,-r-12,r*2*enemy.hp/enemy.maxHp,4);}}
    ctx.restore();
  }
  for(const bullet of game.bullets){ctx.fillStyle='#b9f9ff';ctx.shadowColor='#53e3ff';ctx.shadowBlur=12;ctx.fillRect(bullet.x-2,bullet.y-10,4,19);}ctx.shadowBlur=0;
  for(const bullet of game.hostile){ctx.fillStyle='#ff92bb';ctx.beginPath();ctx.arc(bullet.x,bullet.y,bullet.r,0,7);ctx.fill();}
  for(const item of game.pickups){ctx.strokeStyle=item.type==='shield'?'#86ffc3':'#ffd482';ctx.fillStyle='#0a243c';ctx.lineWidth=2;ctx.fillRect(item.x-11,item.y-11,22,22);ctx.strokeRect(item.x-11,item.y-11,22,22);ctx.fillStyle=ctx.strokeStyle;ctx.font='bold 16px monospace';ctx.textAlign='center';ctx.fillText(item.type==='shield'?'+':'»',item.x,item.y+6);}
  for(const particle of game.particles){ctx.globalAlpha=Math.min(1,particle.life*2);ctx.fillStyle=particle.color;ctx.beginPath();ctx.arc(particle.x,particle.y,2.5,0,7);ctx.fill();}ctx.globalAlpha=1;
  const p=game.player;
  if(p.health>0){
    ctx.save();ctx.translate(p.x,p.y);ctx.globalAlpha=p.invincible>0?.5+.5*Math.sin(t*35):1;
    ctx.fillStyle='#fdba77';ctx.shadowColor='#ff883e';ctx.shadowBlur=15;ctx.beginPath();ctx.moveTo(-6,13);ctx.lineTo(0,28+Math.sin(t*50)*7);ctx.lineTo(6,13);ctx.fill();
    ctx.shadowColor='#6ee9ff';ctx.shadowBlur=16;ctx.fillStyle='#74dce8';ctx.strokeStyle='#dbfeff';ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(0,-23);ctx.lineTo(20,17);ctx.lineTo(7,11);ctx.lineTo(0,16);ctx.lineTo(-7,11);ctx.lineTo(-20,17);ctx.closePath();ctx.fill();ctx.stroke();ctx.shadowBlur=0;ctx.fillStyle='#142239';ctx.beginPath();ctx.moveTo(0,-11);ctx.lineTo(5,4);ctx.lineTo(-5,4);ctx.fill();
    if(p.rapid>0){ctx.strokeStyle='#ffd387';ctx.beginPath();ctx.arc(0,0,28,0,7);ctx.stroke();}ctx.restore();
  }
  if(game.nextWave>0){ctx.fillStyle='#b7f7ff';ctx.font='20px monospace';ctx.textAlign='center';ctx.fillText('SECTOR CLEAR · NEXT WAVE INBOUND',w/2,180);}
}
