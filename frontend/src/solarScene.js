export function scenePosition(body, day, step = 1) {
  const samples=body.samples_au;
  const index=Math.max(0,Math.min(samples.length-1,day/step));
  const lower=Math.floor(index),upper=Math.min(samples.length-1,lower+1),fraction=index-lower;
  const xyz=samples[lower].map((v,i)=>v+(samples[upper][i]-v)*fraction);
  return [xyz[0],xyz[2],-xyz[1]]; // right-handed ICRS → Three.js (north is +Y)
}
export function starDirection(target, radius=1500) {
  const ra=target.ra_deg*Math.PI/180,dec=target.dec_deg*Math.PI/180;
  return [radius*Math.cos(dec)*Math.cos(ra),radius*Math.sin(dec),-radius*Math.cos(dec)*Math.sin(ra)];
}
export function stellarBody(target) {
  if(!target)return null;
  const kind=target.object_type || target.type || 'Catalogue object';
  const brown=/brown dwarf/i.test(kind)||['wise-0855','epsilon-indi-b'].includes(target.id);
  return {id:target.id,name:target.name,kind,isCatalogue:true,brown,
    color:brown?'#8f6353':'#ffb968',
    description:`${kind}. ${brown?'A brown-dwarf illustration':'A stellar illustration'} based on the catalogue identity, not an observed surface.`,
    ra_deg:target.ra_deg,dec_deg:target.dec_deg,
    note:target.astrometry_note || 'Catalogue reference coordinates; no measured surface or rotation model is available.'};
}

// An explicitly artistic surface, kept separate from the Solar System image maps.
export function stellarPixels(brown,width=256,height=128) {
  const pixels=new Uint8Array(width*height*4);
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){
    const longitude=x/width*Math.PI*2,latitude=y/height*Math.PI;
    const variation=(Math.sin(longitude*12+Math.sin(latitude*9)*2)+Math.sin(longitude*31-latitude*16)+Math.sin(longitude*63+latitude*37))/6+.5;
    const bands=brown ? .7+.3*Math.sin(latitude*15+Math.sin(longitude*3)) : 1;
    const color=brown?[115,76,65]:[255,153,65];
    const i=(y*width+x)*4;
    color.forEach((value,c)=>{pixels[i+c]=Math.round(value*(.48+.52*variation)*bands);});pixels[i+3]=255;
  }
  return pixels;
}
export const PLANET_STYLE = {
  sun:{radius:.65,spin:25,tilt:7.25},mercury:{radius:.13,spin:58.65,tilt:.03},
  venus:{radius:.18,spin:-243,tilt:2.64},earth:{radius:.19,spin:1,tilt:23.44},
  moon:{radius:.08,spin:27.32,tilt:6.68},mars:{radius:.15,spin:1.026,tilt:25.19},
  jupiter:{radius:.38,spin:.414,tilt:3.13},saturn:{radius:.32,spin:.445,tilt:26.73},
  uranus:{radius:.25,spin:-.718,tilt:82.23},neptune:{radius:.24,spin:.671,tilt:28.32},
};
