import test from 'node:test';
import assert from 'node:assert/strict';
import {missionState,startMission,pauseMission,segmentHit,stepMission} from './starshipMission.js';

test('mission begins with exactly three hostiles and stays within flight bounds',()=>{
  const g=startMission();assert.equal(g.enemies.length,3);assert.equal(g.player.hp,5);
  for(let i=0;i<120;i++)stepMission(g,.05,{right:true,up:true});
  assert.ok(g.player.x<=10&&g.player.y<=4.7);
  const t=g.time;pauseMission(g);stepMission(g,1,{fire:true});assert.equal(g.time,t);
  pauseMission(g);assert.equal(g.status,'playing');assert.equal(missionState().status,'ready');
});
test('swept laser collision detects high-speed shots between frames',()=>{
  assert.equal(segmentHit({x:0,y:0,z:-10},{x:0,y:0,z:10},{x:0,y:0,z:0},1),true);
  assert.equal(segmentHit({x:3,y:0,z:-10},{x:3,y:0,z:10},{x:0,y:0,z:0},1),false);
});
test('all three kills produce victory exactly once, with no respawns',()=>{
  const g=startMission();
  for(const enemy of g.enemies){enemy.hp=1;g.bolts.push({x:enemy.x,y:enemy.y,z:enemy.z+10,vx:0,vy:0,vz:-250});}
  // Freeze the formation phase for each shot at its initial animated coordinates.
  g.enemies.forEach((e,i)=>{e.x=e.baseX+Math.sin(e.phase)*1.6;e.y=(e.id===1?-.5:2)+Math.sin(e.phase)*1.1;g.bolts[i].x=e.x;g.bolts[i].y=e.y;});
  stepMission(g,.05);assert.equal(g.destroyed,3);assert.equal(g.status,'won');
  const score=g.score,time=g.time;stepMission(g,1,{fire:true});assert.equal(g.score,score);assert.equal(g.time,time);assert.equal(g.enemies.length,3);
});
test('enemy fire is aimed, damage has grace time, and a failed mission can restart',()=>{
  const g=startMission();g.enemies[0].fire=0;stepMission(g,0);assert.equal(g.lasers.length,2);assert.ok(g.lasers.every(l=>l.vz>0));
  const strike=()=>{g.lasers=[{x:g.player.x,y:g.player.y,z:0,vx:0,vy:0,vz:200}];stepMission(g,.05);};
  strike();assert.equal(g.player.hp,4);strike();assert.equal(g.player.hp,4);
  for(let i=0;i<4;i++){g.player.invincible=0;strike();}assert.equal(g.status,'lost');
  const fresh=startMission();assert.equal(fresh.player.hp,5);assert.equal(fresh.destroyed,0);assert.ok(fresh.enemies.every(e=>e.hp===32));
});
