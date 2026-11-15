import test from 'node:test';
import assert from 'node:assert/strict';
import {equatorialXYZ, positionedSources, trustedDistance, candidateRecord} from './coordinates.js';

const near = (a,b) => a.forEach((v,i) => assert.ok(Math.abs(v-b[i])<1e-10));
test('ICRS reference axes and known galactic-centre direction use degrees, handedness and radius', () => {
  near(equatorialXYZ(0,0), [1,0,0]); near(equatorialXYZ(90,0), [0,1,0]);
  near(equatorialXYZ(180,0), [-1,0,0]); near(equatorialXYZ(0,90), [0,0,1]);
  near(equatorialXYZ(0,-90,10), [0,0,-10]);
  // Independent reference from Astropy SkyCoord(266.4051,-28.936175,unit='deg').cartesian.
  near(equatorialXYZ(266.4051,-28.936175), [-0.0548739561755396,-0.8734371822248346,-0.48383503143198114]);
  assert.equal(equatorialXYZ(360,0), null); assert.equal(equatorialXYZ(0,NaN), null);
});
test('missing, negative, noisy and unprovenanced distances never produce spatial positions', () => {
  const source={id:'real',ra_deg:12,dec_deg:45,coordinate_frame:'ICRS'};
  assert.equal(positionedSources([source]).length,1);
  assert.deepEqual(positionedSources([source],true),[]);
  for (const distance of [null, {value_pc:5}, {value_pc:-3}, {value_pc:5,uncertainty_pc:4,trustworthy:true,provenance:'x',method:'posterior'}]) {
    assert.equal(trustedDistance({...source,distance}),null);
    assert.deepEqual(positionedSources([{...source,distance}],true),[]);
  }
  const measured={...source,distance:{value_pc:5,uncertainty_pc:.2,trustworthy:true,provenance:'published result',method:'distance posterior'}};
  assert.ok(Math.abs(Math.hypot(...positionedSources([measured],true)[0].xyz)-5)<1e-10);
});
test('candidate records retain source and observation IDs and never assert discovery', () => {
  const c=candidateRecord('source-a','observation-b','personal note','/api/observations/observation-b/quality\nreference');
  assert.equal(c.status,'unverified'); assert.equal(c.target_id,'source-a'); assert.equal(c.observation_id,'observation-b'); assert.equal(c.evidence_references.length,2);
});
