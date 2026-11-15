import test from 'node:test';
import assert from 'node:assert/strict';
import {newGame,startGame,togglePause,pulse,stepGame} from './gameEngine.js';
const run=(mode='patrol')=>startGame(newGame(mode,()=>.5));

test('movement stays within the arena, frame stalls are bounded, and pausing freezes simulation',()=>{
  const game=run();stepGame(game,100,{right:true,up:true,fire:true});
  assert.ok(game.player.x<470);assert.ok(game.player.y>470);assert.equal(game.shots,1);
  const position=[game.player.x,game.player.y],time=game.time;
  togglePause(game);stepGame(game,1,{left:true,fire:true});
  assert.deepEqual([game.player.x,game.player.y],position);assert.equal(game.time,time);
  togglePause(game);assert.equal(game.status,'playing');
  for(let i=0;i<200;i++)stepGame(game,.05,{right:true,down:true});
  assert.ok(game.player.x<=878&&game.player.y<=535);
});

test('a laser destroys only one overlapping target and awards one score',()=>{
  const game=run();game.enemies=[0,1].map(()=>({x:450,y:200,baseX:450,r:18,hp:1,maxHp:1,speed:0,phase:0,fire:50,rock:false}));
  game.bullets=[{x:450,y:200,r:4}];stepGame(game,0);
  assert.equal(game.kills,1);assert.equal(game.score,100);assert.equal(game.hits,1);assert.equal(game.enemies.length,1);
});

test('collision invulnerability prevents repeated instant damage and game over stops input',()=>{
  const game=run();game.enemies=[];
  const strike=()=>{game.hostile=[{x:game.player.x,y:game.player.y,r:5,vx:0,vy:0}];stepGame(game,0);};
  strike();assert.equal(game.player.health,2);strike();assert.equal(game.player.health,2);
  game.player.invincible=0;strike();game.player.invincible=0;strike();assert.equal(game.status,'over');
  const time=game.time;stepGame(game,.05,{fire:true});assert.equal(game.time,time);
  assert.equal(pulse(game),false);assert.equal(newGame().player.health,3);
});

test('wave advancement, boss rounds and asteroid mode are playable distinct rules',()=>{
  const game=run();game.wave=4;game.enemies=[];
  for(let i=0;i<30;i++)stepGame(game,.05);
  assert.equal(game.wave,5);assert.ok(game.enemies.some(enemy=>enemy.boss));
  const asteroids=run('asteroids');assert.ok(asteroids.enemies.every(enemy=>enemy.rock));
  for(let i=0;i<100;i++)stepGame(asteroids,.05);
  assert.equal(asteroids.hostile.length,0);
});

test('pulse stock is limited and shield and rapid pickups apply correctly',()=>{
  const game=run();game.enemies=[{x:200,y:100,r:20,hp:1}];
  assert.equal(pulse(game),true);assert.equal(game.pulses,2);assert.equal(game.kills,1);
  pulse(game);pulse(game);assert.equal(pulse(game),false);
  game.player.health=1;game.enemies=[];game.pickups=[{...game.player,type:'shield'},{...game.player,type:'rapid'}];
  stepGame(game,0);assert.equal(game.player.health,2);assert.equal(game.player.rapid,8);
});
