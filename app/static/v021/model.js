// Pure presentation helpers. No inference, statistical recalculation, or writes.
export const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const number=(n,digits=4)=>Number.isFinite(n)?n.toFixed(digits):'Not applicable';
export const signed=n=>(n>0?'+':'')+number(n);
export function orderedCohort(data,order='consensus'){
  const rows=[...data.statistics];
  const position=new Map(data.plot_order_run_ids.map((id,i)=>[id,i]));
  if(order==='gene')return rows.sort((a,b)=>a.gene_symbol.localeCompare(b.gene_symbol));
  if(order==='q')return rows.sort((a,b)=>a.q_two_sided-b.q_two_sided);
  return rows.sort((a,b)=>position.get(a.run_id)-position.get(b.run_id));
}
export function filterTracks(rows,query='',group='all'){
  const terms=query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  return rows.filter(r=>(group==='all'||r.display_group===group)&&terms.every(t=>[
    r.biosample_name,r.track_name,r.ontology_curie,r.data_source,r.display_group,
    r.biosample_type,r.biosample_life_stage,r.gtex_tissue,r.cellosaurus_accession,
  ].join(' ').toLowerCase().includes(t)));
}
export function validateVariant(v){
  const errors=[];
  if(!v.gene_symbol?.trim())errors.push('Enter the target gene.');
  if(!/^chr([1-9]|1[0-9]|2[0-2]|X|Y|M)$/.test(v.chrom||''))errors.push('Use a GRCh38 chromosome such as chr16 or chrX.');
  if(!Number.isSafeInteger(Number(v.pos1))||Number(v.pos1)<1)errors.push('Position must be a positive 1-based integer.');
  if(!/^[ACGT]+$/i.test(v.ref||'')||!/^[ACGT]+$/i.test(v.alt||''))errors.push('REF and ALT must contain A, C, G or T; use VCF anchoring for indels.');
  if(v.ref?.toUpperCase()===v.alt?.toUpperCase())errors.push('REF and ALT must differ.');
  return errors;
}
export function optionQuery(values){
  const q=new URLSearchParams();
  for(const k of ['figure_width_mm','font_size_pt','top_panel_height_mm','effect_panel_height_mm']){
    const n=Number(values[k]);if(values[k]===''||!Number.isFinite(n))throw new Error('Enter a finite value for every figure dimension.');q.set(k,String(n));
  }
  return q;
}
