import test from 'node:test';
import assert from 'node:assert/strict';
import {layoutSkyLabels} from './skyLabels.js';

test('conjunction labels separate without moving astronomical anchors or covering star labels',()=>{
  const points=Array.from({length:9},(_,i)=>({id:String(i),x:420,y:220}));
  const reserved=[{x:400,y:205,width:130,height:30}];
  const labels=layoutSkyLabels(points,900,480,reserved);
  assert.equal(labels.length,9);
  const boxes=[...reserved];
  for(const box of labels){
    assert.equal(box.anchorX,420);assert.equal(box.anchorY,220);
    assert.ok(box.x>=0 && box.x+box.width<=900 && box.y>=42 && box.y+box.height<=426);
    for(const other of boxes)assert.ok(box.x>=other.x+other.width || box.x+box.width<=other.x || box.y>=other.y+other.height || box.y+box.height<=other.y);
    boxes.push(box);
  }
});
