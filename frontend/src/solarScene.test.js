import test from 'node:test';
import assert from 'node:assert/strict';
import {scenePosition,starDirection,stellarBody,stellarPixels,PLANET_STYLE} from './solarScene.js';

test('ephemeris interpolation preserves linear AU spacing and ICRS handedness',()=>{
  const body={samples_au:[[1,2,3],[3,4,5]]};
  assert.deepEqual(scenePosition(body,.5),[2,4,-3]);
  assert.deepEqual(scenePosition(body,100),[3,5,-4]);
  assert.deepEqual(scenePosition(body,-1),[1,3,-2]);
  assert.deepEqual(starDirection({ra_deg:0,dec_deg:0},1),[1,0,-0]);
  assert.ok(Math.abs(starDirection({ra_deg:90,dec_deg:0},1)[2]+1)<1e-12);
  assert.equal(Object.keys(PLANET_STYLE).length,10);
});

test('stellar close-ups preserve catalogue identity and distinguish brown dwarfs without invented measurements',()=>{
  const dwarf=stellarBody({id:'wise-0855',name:'WISE 0855',object_type:'Brown dwarf',ra_deg:134,dec_deg:-7});
  assert.equal(dwarf.id,'wise-0855');assert.equal(dwarf.brown,true);assert.equal(dwarf.isCatalogue,true);
  assert.equal(dwarf.ra_deg,134);assert.equal(dwarf.samples_au,undefined);
  assert.match(dwarf.description,/not an observed surface/);
  assert.equal(stellarBody({id:'star',name:'Example',object_type:'Variable star'}).brown,false);
  assert.equal(stellarBody(null),null);
  const surface=stellarPixels(true,16,8);assert.equal(surface.length,16*8*4);
  assert.notDeepEqual(surface,stellarPixels(false,16,8));
  assert.ok(surface.every((value,i)=>i%4!==3||value===255));
});
