// Presentation only: plot the verified adjusted values without recalculating them.
export function makeEffectChart(data) {
  const svg=document.querySelector('#effectPlot'), tooltip=document.querySelector('#tooltip');
  const brain=document.querySelector('#brainOnly'), show=document.querySelector('#showPoints');
  let group=null;
  const W=1120,H=485,m={left:90,right:25,top:55,bottom:145};
  const bottom=H-m.bottom, width=W-m.left-m.right;
  const x=v=>m.left+(v+.5)*width/data.groups.length;
  const y=v=>m.top+(data.y_max-v)*(bottom-m.top)/(data.y_max-data.y_min);
  const fmt=v=>Number(v).toPrecision(6);
  const color=v=>v>0?'#b2182b':v<0?'#2166ac':'#aab4be';
  const el=(name,attrs={},text)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',name);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;return n;};
  function hide(){tooltip.hidden=true;}
  function pin(title,text){document.querySelector('#selectedTrack').hidden=false;document.querySelector('#selectedTrackTitle').textContent=title;document.querySelector('#selectedTrackText').textContent=text;hide();}
  function bind(n,title,text,action){
    const tip=e=>{tooltip.textContent=title+'\n'+text;tooltip.hidden=false;const r=n.getBoundingClientRect();
      tooltip.style.left=Math.max(8,Math.min((e.clientX||r.right)+12,innerWidth-tooltip.offsetWidth-10))+'px';
      tooltip.style.top=Math.max(8,Math.min((e.clientY||r.top)+12,innerHeight-tooltip.offsetHeight-10))+'px';};
    n.addEventListener('pointermove',tip);n.addEventListener('pointerleave',hide);n.addEventListener('focus',tip);n.addEventListener('blur',hide);
    const select=()=>{pin(title,text);if(action)action();};
    n.addEventListener('click',select);n.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select();}if(e.key==='Escape')hide();});
  }
  function draw(){
    hide();svg.replaceChildren();svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
    const dim=g=>(group&&group!==g.display_group)||(brain.checked&&!g.included_in_brain9);
    for(let j=-2;j<=2;j++){const v=data.y_max*j/2;
      svg.append(el('line',{x1:m.left,x2:W-m.right,y1:y(v),y2:y(v),stroke:j===0?'#758c95':'#e5ecef'}));
      svg.append(el('text',{x:m.left-10,y:y(v)+5,'text-anchor':'end','font-size':14,fill:'#5c7079'},j===0?'0':v.toPrecision(2)));}
    for(const [at,labels] of [[3.5,['Adult brain tissues']],[8,['Embryo']],[9,['Other','tissues']],[10,['Cells','& lines']]])labels.forEach((label,i)=>svg.append(el('text',{x:x(at),y:labels.length===1?30:18+i*20,'text-anchor':'middle','font-size':14,fill:'#5c7079'},label)));
    for(const at of [7.5,8.5,9.5])svg.append(el('line',{x1:x(at),x2:x(at),y1:m.top,y2:bottom,stroke:'#dbe4e8','stroke-dasharray':'4 4'}));
    for(const g of data.groups){
      const text=`Median adjusted RNA score: ${fmt(g.median_effect)}\n${g.n_tracks} assay tracks · ${g.included_in_brain9?'Included in Brain9':'Display only; excluded from Brain9'}`;
      const bw=width/data.groups.length*.72;
      const n=el('rect',{x:x(g.x)-bw/2,y:Math.min(y(0),y(g.median_effect)),width:bw,height:Math.max(.7,Math.abs(y(0)-y(g.median_effect))),fill:color(g.median_effect),class:`bar${dim(g)?' dimmed':''}`,tabindex:0,role:'button','aria-pressed':String(group===g.display_group),'aria-label':g.display_group+'; '+text});
      bind(n,g.display_group,text,()=>{group=group===g.display_group?null:g.display_group;draw();});svg.append(n);
    }
    if(show.checked)for(const p of data.points){
      const text=`Adjusted RNA score: ${fmt(p.effect)}\nCategory: ${p.display_group}\n${p.biosample_type} · ${p.biosample_life_stage||'life stage not recorded'}\n${p.ontology_curie} · ${p.data_source}${p.gtex_tissue?' · '+p.gtex_tissue:''}\nTrack: ${p.track_name}\nRaw score: ${fmt(p.raw_score)} · Null median: ${fmt(p.null_median)} (n=1,000)\n${p.included_in_brain9?'Included in Brain9':'Display only; excluded from Brain9'}\nTrack key: ${p.track_key}`;
      const n=el('circle',{cx:x(p.x),cy:y(p.effect),r:p.group_x<9?4:3.2,fill:color(p.effect),class:`point${dim(p)?' dimmed':''}`,tabindex:0,role:'button','data-track-key':p.track_key,'aria-label':`${p.biosample_name}; adjusted score ${fmt(p.effect)}; ${p.display_group}`});bind(n,p.biosample_name||p.track_name,text);svg.append(n);
    }
    for(const g of data.groups)svg.append(el('text',{x:x(g.x),y:bottom+21,'text-anchor':'end','font-size':14,fill:'#172c35',transform:`rotate(-40 ${x(g.x)} ${bottom+21})`},`${g.label} (${g.n_tracks})`));
    svg.append(el('text',{x:24,y:(m.top+bottom)/2,transform:`rotate(-90 24 ${(m.top+bottom)/2})`,'text-anchor':'middle','font-size':14,fill:'#172c35'},'Adjusted RNA score'));
  }
  brain.checked=false;show.checked=true;
  brain.onchange=draw;show.onchange=draw;
  document.querySelector('#resetChart').onclick=()=>{group=null;brain.checked=false;show.checked=true;document.querySelector('#selectedTrack').hidden=true;draw();};
  document.querySelector('#clearTrack').onclick=()=>{document.querySelector('#selectedTrack').hidden=true;};
  draw();return {draw,hide};
}
