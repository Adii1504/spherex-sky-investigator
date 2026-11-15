import * as THREE from 'three';

// Original low-poly craft inspired by the supplied silhouettes, not imported models.
export function makeStarship(enemy,resources){
  const group=new THREE.Group(),engines=[],weapons=[];
  const materials=new Map();
  const material=(color,glow=false)=>{const key=color+glow;if(!materials.has(key)){const mat=new THREE.MeshStandardMaterial({color,metalness:glow?.1:.65,roughness:glow?.35:.4,emissive:glow?color:'#000000',emissiveIntensity:glow?2:0});materials.set(key,mat);resources.push(mat);}return materials.get(key);};
  const part=(geometry,color,position,glow=false)=>{const mesh=new THREE.Mesh(geometry,material(color,glow));mesh.position.set(...position);group.add(mesh);resources.push(geometry);return mesh;};
  const box=(size,color,pos)=>part(new THREE.BoxGeometry(...size),color,pos);
  const tube=(r,length,color,pos,glow=false)=>{const mesh=part(new THREE.CylinderGeometry(r,r,length,20),color,pos,glow);mesh.rotation.x=Math.PI/2;return mesh;};
  const wing=(points,color,y)=>{const shape=new THREE.Shape();points.forEach(([x,z],i)=>i?shape.lineTo(x,-z):shape.moveTo(x,-z));shape.closePath();const geometry=new THREE.ExtrudeGeometry(shape,{depth:.13,bevelEnabled:false});const mesh=part(geometry,color,[0,y,0]);mesh.rotation.x=-Math.PI/2;return mesh;};
  if(!enemy){
    box([1.4,.75,4.5],'#63717c',[0,0,0]);box([.85,.18,2.8],'#b8b9b1',[0,.48,.2]);
    const cockpit=part(new THREE.SphereGeometry(.78,24,16),'#15283a',[0,.55,-.65]);cockpit.scale.set(1,.8,1.3);
    for(const side of [-1,1]){
      wing([[side*.6,-1.5],[side*4.6,-.6],[side*4.9,2.1],[side*1,1.3]],'#7d8790',-.15);
      wing([[side*2,-.1],[side*4.4,.3],[side*4.55,1],[side*2,.65]],'#b6b4a4',.02);
      box([.25,.09,2.1],'#c57843',[side*3,.13,.5]);
      tube(.65,2.4,'#3f4b57',[side*1.7,.2,1]);tube(.45,.25,'#071221',[side*1.7,.2,2.3]);
      const rim=part(new THREE.TorusGeometry(.48,.1,8,24),'#b3c0c7',[side*1.7,.2,2.46]);
      const engine=tube(.32,.15,'#59d9ff',[side*1.7,.2,2.5],true);engines.push(engine);
      const flame=part(new THREE.ConeGeometry(.35,1.4,12),'#52bcff',[side*1.7,.2,3.25],true);flame.rotation.x=Math.PI/2;engines.push(flame);
      box([.12,.8,1.6],'#667583',[side*4.4,.35,1.3]);
      const gun=tube(.105,2.3,'#a7b8bd',[side*.85,-.05,-1.7]);weapons.push(gun);
      box([.12,.1,1.5],'#d9ddd0',[side*3.5,.1,.4]);
    }
    const antenna=part(new THREE.ConeGeometry(.05,1.2,6),'#b2c4cf',[.4,1.1,.25]);antenna.rotation.z=-.2;
  }else{
    const body=part(new THREE.SphereGeometry(1.25,24,16),'#284bbe',[0,.15,0]);body.scale.set(.85,.5,2);
    for(const side of [-1,1]){
      wing([[side*.4,-1.7],[side*6,-.4],[side*4.7,1.9],[side*.6,1.3]],'#345ce0',-.1);
      wing([[side*.65,-1.1],[side*5.4,-.05],[side*4.3,.5],[side*1.2,.15]],'#ef8b33',.07);
      wing([[side*1,-.6],[side*4.8,.1],[side*3.6,.5],[side*1.1,.2]],'#b4d6ec',.1);
      const fin=box([.12,1.1,1.6],'#5478d4',[side*1.5,.55,.8]);fin.rotation.z=side*.35;
      tube(.16,1.6,'#83a2dc',[side*.8,-.05,-1.7]);
      const gun=tube(.12,.22,'#ff3b72',[side*.8,-.05,-2.55],true);weapons.push(gun);
      const engine=tube(.35,.2,'#5ab4ff',[side*1,.15,1.8],true);engines.push(engine);
    }
    const nose=part(new THREE.ConeGeometry(.65,2.3,16),'#5476db',[0,0,-2]);nose.rotation.x=-Math.PI/2;
    const cockpit=part(new THREE.SphereGeometry(.55,20,12),'#8ae4ff',[0,.65,-.55],true);cockpit.scale.set(.7,.45,1.7);
  }
  return {group,engines,weapons};
}
