import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {esc,number,orderedCohort,filterTracks,validateVariant,optionQuery} from '../app/static/v021/model.js';
import {makeEffectChart} from '../app/static/v021/charts.js';
const base=new URL('../data/manuscript_v020_20260909/',import.meta.url);
const read=name=>JSON.parse(fs.readFileSync(new URL(name,base),'utf8'));
const cohort=read('ccg17/payload.json'),tracks=read('tissue_payload.json');

test('cohort order and family remain immutable; all joins are complete',()=>{
  const before=JSON.stringify(cohort),rows=orderedCohort(cohort);
  assert.deepEqual(rows.map(r=>r.run_id),cohort.plot_order_run_ids);
  assert.equal(rows.length,17);assert.equal(rows.filter(r=>r.q_two_sided<=.05).length,6);
  assert.deepEqual(rows.map(r=>r.gene_symbol),['NKX6-2','RNPEPL1','TRAF3IP1','SHISA6','RBFOX1','AUTS2','MSANTD3','PTPRT','HOXC8','FZD7','DNAJC5','BMS1P14','ZZZ3','CNTFR','GSK3B','SPSB4','GPRIN1']);
  assert(!rows.some(r=>r.gene_symbol==='RGPD1'));
  for(const r of rows)assert(cohort.ranking.find(x=>x.run_id===r.run_id));
  const byQ=orderedCohort(cohort,'q');assert(byQ.every((r,i)=>!i||byQ[i-1].q_two_sided<=r.q_two_sided));
  assert.equal(orderedCohort(cohort,'gene')[0].gene_symbol,'AUTS2');
  assert.equal(JSON.stringify(cohort),before);
  assert.equal(rows.find(r=>r.gene_symbol==='RBFOX1').q_two_sided,0.05094905094905095);
});
test('track search/filter covers all 371, cortex4/wholebrain1/embryo7',()=>{
  assert.equal(filterTracks(tracks.track_audit).length,371);
  for(const [group,n] of [['Cerebral cortex',4],['Whole brain',1],['Embryo',7],['Non-brain tissues',153],['Cells & cell lines',197]])assert.equal(filterTracks(tracks.track_audit,'',group).length,n);
  assert(filterTracks(tracks.track_audit,'UBERON:0001870 gtex').some(r=>r.gtex_tissue==='Brain_Cortex'));
  assert(filterTracks(tracks.track_audit,'K562').length>0);
  assert.equal(filterTracks(tracks.track_audit,'HEK293').length,0); // Do not invent an unavailable track.
  assert.equal(filterTracks(tracks.track_audit,'not-a-real-biosample').length,0);
});
test('single and cohort input previews validate syntax only; 17-row source',()=>{
  for(const r of cohort.variant_mapping)assert.deepEqual(validateVariant(r),[]);
  assert.equal(cohort.variant_mapping.length,17);
  const valid={gene_symbol:'RBFOX1',chrom:'chr16',pos1:6018925,ref:'TCCG',alt:'T'};
  assert.deepEqual(validateVariant(valid),[]);
  for(const bad of [{pos1:0},{pos1:1.5},{chrom:'chr23'},{ref:'N'},{alt:'TCCG'},{gene_symbol:''}])assert(validateVariant({...valid,...bad}).length>0);
});
test('escape and print options do not silently coerce unavailable/invalid values',()=>{
  assert.equal(esc('<script>"&\''),'&lt;script&gt;&quot;&amp;&#39;');
  assert.equal(number(null),'Not applicable');assert.equal(number(NaN),'Not applicable');
  const v={figure_width_mm:174,font_size_pt:6.5,top_panel_height_mm:64,effect_panel_height_mm:68};
  assert.equal(optionQuery(v).get('font_size_pt'),'6.5');
  assert.throws(()=>optionQuery({...v,font_size_pt:''}));assert.throws(()=>optionQuery({...v,font_size_pt:'Infinity'}));
});

class FakeNode{
  constructor(name){this.name=name;this.attrs={};this.children=[];this.events={};this.hidden=false;this.checked=false;this.style={};this.textContent='';this.offsetWidth=320;this.offsetHeight=200;}
  setAttribute(k,v){this.attrs[k]=String(v);}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  addEventListener(k,fn){this.events[k]=fn;}
  getBoundingClientRect(){return {top:200,right:400};}
}
test('chart: all values/tracks retained; pointer and keyboard selection; display-only toggles',()=>{
  const selectors=['#effectPlot','#tooltip','#brainOnly','#showPoints','#selectedTrack','#selectedTrackTitle','#selectedTrackText','#resetChart','#clearTrack'];
  const nodes=Object.fromEntries(selectors.map(s=>[s,new FakeNode(s)]));
  globalThis.document={querySelector:s=>nodes[s],createElementNS:(_,name)=>new FakeNode(name)};
  globalThis.innerWidth=1200;globalThis.innerHeight=900;
  const raw=fs.readFileSync(new URL('rbfox1/source_table.tsv',base),'utf8').trimEnd().split('\n');
  const headers=raw.shift().split('\t');const rows=raw.map(l=>Object.fromEntries(l.split('\t').map((v,i)=>[headers[i],v])));
  const result=read('rbfox1/payload.json');
  const groups=result.groups.map((g,x)=>({x,label:g.label,display_group:g.label,n_tracks:g.n_tracks,included_in_brain9:g.included_in_brain9,median_effect:-.01}));
  const points=rows.map(r=>{const i=groups.findIndex(g=>g.display_group===r.display_group);return {...r,group_x:i,x:i,included_in_brain9:i<9,effect:Number(r.effect),raw_score:Number(r.raw_score),null_median:Number(r.null_median)};});
  const data={groups,points,y_min:-.3,y_max:.3},before=JSON.stringify(data);
  makeEffectChart(data);
  const children=()=>nodes['#effectPlot'].children;
  assert.equal(children().filter(n=>n.name==='circle').length,371);
  assert.equal(children().filter(n=>n.name==='rect').length,11);
  const point=children().find(n=>n.name==='circle');
  point.events.pointermove({clientX:1100,clientY:850});assert.equal(nodes['#tooltip'].hidden,false);
  assert(nodes['#tooltip'].textContent.includes('Null median:'));
  point.events.keydown({key:'Enter',preventDefault(){}});assert.equal(nodes['#selectedTrack'].hidden,false);
  assert(nodes['#selectedTrackText'].textContent.includes(points[0].track_key));
  assert.equal(nodes['#tooltip'].hidden,true);
  nodes['#brainOnly'].checked=true;nodes['#brainOnly'].onchange();
  assert.equal(children().filter(n=>n.name==='circle'&&n.attrs.class.includes('dimmed')).length,350);
  const bar=children().find(n=>n.name==='rect');bar.events.click();
  assert(children().some(n=>n.attrs['aria-pressed']==='true'));
  nodes['#showPoints'].checked=false;nodes['#showPoints'].onchange();assert.equal(children().filter(n=>n.name==='circle').length,0);
  nodes['#resetChart'].onclick();assert.equal(children().filter(n=>n.name==='circle').length,371);
  assert.equal(nodes['#selectedTrack'].hidden,true);assert.equal(JSON.stringify(data),before);
  delete globalThis.document;
});

test('progressive disclosure and separate local submission remain in the delivered source',()=>{
  const html=fs.readFileSync(new URL('../app/static/v021/index.html',import.meta.url),'utf8');
  const app=fs.readFileSync(new URL('../app/static/v021/app.js',import.meta.url),'utf8');
  assert(html.includes('<dialog'));assert(html.includes('id="chartOptions" class="chart-options" hidden'));
  assert(!html.includes('v0.20 manuscript presets: Figure 2'));
  for(const s of ['Standalone · not FDR-adjusted','Layout only:','Matched-null model files','Post hoc observed direction','0.05','not the standalone 16 kb'])assert(app.includes(s),s);
  assert(app.includes("location.hash='local'"));assert(!app.includes('temporarily unavailable'));
  assert(!/fetch\([^)]*,\s*\{[^}]*method:\s*['"]POST/.test(app));
});
