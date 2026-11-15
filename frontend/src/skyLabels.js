// Screen-space callouts: celestial anchors stay fixed while labels move apart.
export function layoutSkyLabels(points, width, height, reserved = []) {
  const occupied = [...reserved];
  const intersects = (a,b) => a.x < b.x+b.width+6 && a.x+a.width+6 > b.x && a.y < b.y+b.height+6 && a.y+a.height+6 > b.y;
  return points.map(point => {
    const w = Math.min(112, width-8), h = 30;
    const candidates = [];
    for (const distance of [16,52,88,124,160,196,232,268]) {
      for (const [dx,dy] of [[distance,0],[-distance-w,0],[0,distance],[0,-distance],[distance,distance],[-distance-w,-distance],[distance,-distance],[-distance-w,distance]]) {
        candidates.push({x:Math.max(4,Math.min(width-w-4,point.x+dx)),y:Math.max(42,Math.min(height-h-54,point.y+dy)),width:w,height:h});
      }
    }
    // Scan the viewport when a conjunction needs more than nearby callouts.
    for(let y=42;y<height-h-54;y+=h+8) for(let x=4;x<width-w;x+=w+8) candidates.push({x,y,width:w,height:h});
    const box = candidates.find(candidate => !occupied.some(other => intersects(candidate,other)));
    if (!box) return null; // Small screens still expose every body in the card strip.
    occupied.push(box);
    return {...point,...box,anchorX:point.x,anchorY:point.y};
  }).filter(Boolean);
}

export function createBodyLabels(element, aladin, onSelect) {
  const host=document.createElement('div'); host.className='sky-body-labels';
  element.append(host);
  let bodies=[], targets=[], visible=true, frame=null;
  const project = item => {
    if (!Number.isFinite(item.ra_deg) || !Number.isFinite(item.dec_deg)) return null;
    try {
      const p=aladin.world2pix(item.ra_deg,item.dec_deg);
      return p && Number.isFinite(p[0]) && Number.isFinite(p[1]) ? {...item,x:p[0],y:p[1]} : null;
    } catch {return null;}
  };
  const draw=()=>{
    frame=null;host.replaceChildren(); if(!visible)return;
    const width=element.clientWidth,height=element.clientHeight;
    const inView=p=>p && p.x>=0 && p.x<=width && p.y>=0 && p.y<=height;
    const reserved=targets.map(project).filter(inView).map(p=>({x:p.x-10,y:p.y-14,width:130,height:30}));
    reserved.push({x:width-210,y:height-105,width:210,height:65});
    const labels=layoutSkyLabels(bodies.map(project).filter(inView),width,height,reserved);
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('width','100%');svg.setAttribute('height','100%');host.append(svg);
    for(const p of labels){
      const line=document.createElementNS(svg.namespaceURI,'line');
      for(const [key,value] of Object.entries({x1:p.anchorX,y1:p.anchorY,x2:p.x+p.width/2,y2:p.y+p.height/2,stroke:p.color,'stroke-opacity':'.65'}))line.setAttribute(key,String(value));
      svg.append(line);
      const button=document.createElement('button');button.type='button';button.className='sky-body-callout';
      button.style.left=p.x+'px';button.style.top=p.y+'px';button.style.width=p.width+'px';
      button.setAttribute('aria-label',`About ${p.name}`);button.title=`${p.name} · calculated position`;
      const orb=document.createElement('span');orb.className=`solar-orb solar-${p.id}`;orb.style.setProperty('--body-color',p.color);orb.setAttribute('aria-hidden','true');
      button.append(orb,document.createTextNode(p.name));
      button.addEventListener('click',event=>{event.stopPropagation();onSelect?.(p.id);});host.append(button);
    }
  };
  const update=()=>{if(frame===null)frame=requestAnimationFrame(draw);};
  aladin.on('positionChanged',update);aladin.on('zoomChanged',update);
  const resize=new ResizeObserver(update);resize.observe(element);
  return {
    bodies(value){bodies=value;update();},targets(value){targets=value;update();},
    visible(value){visible=value;update();},
    dispose(){resize.disconnect();if(frame!==null)cancelAnimationFrame(frame);aladin.on('positionChanged',null);aladin.on('zoomChanged',null);host.remove();},
  };
}
