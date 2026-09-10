import {makeEffectChart} from './charts.js';
import {enterLocal,leaveLocal} from './local.js';
import {esc,number,signed,orderedCohort,filterTracks,validateVariant,optionQuery} from './model.js';
const $=s=>document.querySelector(s);
let current=null,key='rbfox1',chart=null,cohort=null,tracks=null,trackPage=0;
let requestId=0;
let feedbackController=null,singleLoading=false;
const state={route:'overview',options:new URLSearchParams()};
function notice(message,error=false){$('#status').textContent=message;$('#status').hidden=!message;$('#status').classList.toggle('error',error);}
async function get(url){const r=await fetch(url);if(!r.ok){let d;try{d=await r.json();}catch{d={detail:'Please try again.'};}throw new Error(typeof d.detail==='string'?d.detail:`Request could not be completed (${r.status}).`);}return r.json();}
function openDialog(title,html){feedbackController?.closeEditor();$('#dialogTitle').textContent=title;$('#dialogContent').innerHTML=html;if(!$('#detailDialog').open)$('#detailDialog').showModal();$('#closeDialog').focus();}
function dl(items){return '<dl>'+items.map(([a,b])=>`<dt>${esc(a)}</dt><dd>${esc(b)}</dd>`).join('')+'</dl>';}
async function loadSingle(nextKey=key){
  const id=++requestId;singleLoading=true;if(state.route==='variant')notice('Loading saved result…');$('#singleView').classList.add('loading');
  if(state.route==='variant')$('#exportButton').disabled=true;
  try{const data=await get('/api/explorer/'+nextKey);if(id!==requestId)return;
    if(key!==nextKey)state.options=new URLSearchParams();key=nextKey;current=data.result;
    const a=current.analysis,v=current.variant;
    $('#geneTitle').innerHTML=esc(v.gene_symbol)+` <span class="badge">${key==='rbfox1'?'Deletion · 16 kb':'Insertion · 1 Mb'}</span>`;
    $('#summary').innerHTML=`<div class="metric"><dl><dt>Brain9 adjusted effect</dt><dd class="${a.real_consensus_delta<0?'negative':'positive'}">${signed(a.real_consensus_delta)}</dd></dl><small>${a.real_consensus_delta<0?'Lower':'Higher'} predicted RNA score</small></div><div class="metric"><dl><dt>Two-sided empirical P</dt><dd>${number(a.empirical_p_two_sided)}</dd></dl><small>Standalone · not FDR-adjusted</small></div><div class="metric"><dl><dt>Matched nulls</dt><dd>1,000</dd></dl><small>Saved analysis · no new inference</small></div>`;
    $('#inputLength').textContent=a.sequence_length.toLocaleString('en-US')+' bp';
    $('#locus').textContent=`GRCh38 · ${v.chrom}:${v.pos1.toLocaleString('en-US')} · ${v.ref} → ${v.alt}`;
    $('#curveImage').src=`/api/explorer/${key}/curve.svg`;
    $('#selectedTrack').hidden=true;chart=makeEffectChart(data.plot);if(state.route==='variant')notice('');
  }catch(e){if(id===requestId){$('#dataset').value=key;if(state.route==='variant')notice(e.message+(current?' The previous result has been retained.':' No saved result has been loaded.')+' Choose a result or reload to retry.',true);}}
  finally{if(id===requestId){singleLoading=false;$('#singleView').classList.remove('loading');if(state.route==='variant')$('#exportButton').disabled=false;}}
}
function dialog(name){
  if(name==='new'){location.hash='local';return;}
  if(name==='feedback'){$('#detailDialog').close();if(location.hash==='#feedback')route();else location.hash='feedback';return;}
  if(name==='about'){openDialog('About AlphaGENIE','<p>AlphaGENome-Integrated Explorer</p><p><strong>Interface v0.21 · source data v0.20</strong></p><p>Explore saved AlphaGenome-derived RNA predictions and export publication figures. Viewing results and changing figure layouts do not submit new AlphaGenome jobs. This local edition supports fresh analyses with your own API key through My analyses. The key is managed locally and is sent to Google DeepMind only for API authentication; AlphaGENIE operators do not collect it.</p><h3>Attribution & use</h3><p>AlphaGenome is developed by Google DeepMind. AlphaGENIE is an independent research interface, not an official Google product and not endorsed by Google DeepMind.</p>'+usageNotice()+'<h3>Modifications</h3><p>AlphaGENIE applies matched-null calibration, tissue grouping, statistical summaries and visualization to AlphaGenome-derived outputs. v0.21 changes presentation, not the frozen v0.20 predictions.</p><p>Scores are model predictions, not measurements, clinical diagnoses or evidence of pathogenicity.</p>');return;}
  if(name==='guide'){openDialog('How to read results','<h3>1. Choose a saved result</h3><p>RBFOX1 uses a 16 kb input; PTCHD1 uses a 1 Mb input. Compare variants opens the separate 17-variant, 1 Mb cohort. Switching results does not run a new analysis.</p><h3>2. Inspect the two views</h3><p>The upper view shows the gene and frontal-cortex prediction. The lower view compares adjusted scores across tissue categories. Hover a point, or select it to keep the source details open. Keyboard users can focus a point and press Enter or Space.</p><h3>3. Review evidence, then export</h3><p>Single-variant results show unadjusted empirical P; cohort results use BH q across 17 variants. Color indicates effect direction, not statistical significance or pathogenicity.</p><p>Export figure combines both single-variant views vertically using your dimensions. The approved cohort PDF retains its fixed manuscript layout.</p><details><summary>Other tools</summary><p>Track library lets you search every source track. My analyses provides local reference checks and explicit fresh API submission with your own key. New runs now use the same manuscript Brain9 classification, with non-brain tissue and cell comparison pools. Their separate Whole brain curve and fresh API numbers are not the saved frontal-cortex inference.</p><button class="text-button" data-dialog="feedback">Feedback →</button></details>');return;}
  if(state.route==='multi'&&['details','groups','methods'].includes(name)){cohortDialog(name);return;}
  if(state.route==='tracks'&&name==='methods'){openDialog('Track classification','<p>Categories use recorded tissue origin, life stage and cell-model metadata. Unknown properties remain unknown; they are not inferred from primary status or donor stage.</p><p>Brain9 includes 14 adult tracks in eight anatomical categories and seven embryo brain tracks. Non-brain tissues (153) and cells/lines (197) are comparison pools only.</p><p>Open a track to inspect its classification evidence, source label and ontology.</p>');return;}
  if(['overview','feedback','local'].includes(state.route)&&name==='methods'){dialog('about');return;}
  if(!current){notice('Please wait for the saved result to load.');return;}
  const a=current.analysis,v=current.variant;
  if(name==='details')openDialog('Analysis details',dl([['Variant',`${v.chrom}:${v.pos1.toLocaleString('en-US')} ${v.ref} → ${v.alt}`],['Target gene',v.target_gene],['Input sequence',`${a.sequence_length.toLocaleString('en-US')} bp · GRCh38`],['Endpoint','Brain9: 8 adult categories + Embryo'],['Brain9 adjusted effect',a.real_consensus_delta],['Two-sided empirical P',a.empirical_p_two_sided],['Multiple testing','None; standalone analysis'],['Matched nulls','1,000']])+`<details><summary>Exploratory direction-selected test</summary><p>Observed-direction P = ${esc(a.empirical_p_observed_direction)}. The direction is selected after observing the result, not a prespecified one-sided hypothesis.</p></details><div class="dialog-actions"><button class="text-button" data-dialog="methods">Methods & provenance →</button><button class="text-button" data-dialog="genome">View genomic locus →</button></div>`);
  if(name==='curve')openDialog('Frontal-cortex prediction','<p>Adult GTEx <strong>Brain_Cortex</strong> · UBERON:0001870 · polyA+ RNA-seq, unstranded. This is not Whole brain or the BA9 track.</p><p>REF and ALT use the same reference-coordinate alignment. The difference curve is ALT − REF at each position; it is not the adjusted GeneMaskLFC score in the bars.</p><p>The input window and plotted gene region are different concepts; the crop does not change the saved analysis.</p>');
  if(name==='groups')openDialog('Tissue group definitions','<p>Brain9 is the median of nine category medians: 14 adult assay tracks in eight categories, plus seven embryo brain-tissue tracks in one category.</p>'+dl(current.groups.map(g=>[`${g.label} (${g.n_tracks})`,g.included_in_brain9?'Included in Brain9':'Display only; excluded from Brain9']))+'<p>Non-brain tissues and cells/lines include all available life stages. Track counts are not biological replicate counts.</p>');
  if(name==='methods')openDialog('Methods & provenance','<p>Adjusted score = raw RNA_SEQ GeneMaskLFC score − the trackwise median of 1,000 matched-null scores. Brain9 is the median of category medians.</p><p>Empirical tests use the recentered null-consensus distribution and the +1/1,001 correction.</p>'+dl([['Interface','v0.21'],['Source data','v0.20 · verified immutable release'],['SDK','0.8.0'],['Scores completed',current.release.completed_at],['Model checkpoint','Not disclosed by the backend'],['Inference on viewing','None']])+usageNotice()+`<details><summary>Full provenance & data files</summary>${Object.entries(current.downloads).filter(([n])=>n.includes('provenance')||n.includes('statistics')||n.includes('scores')).map(([n,url])=>`<p><a href="${esc(url)}">${esc(n.replaceAll('_',' '))}</a></p>`).join('')}</details>`);
  if(name==='curve'){
    const target=$('#dialogContent'),curveKey=key;
    get(current.downloads.frontal_cortex_prediction_status_json).then(s=>{if(!target.isConnected||$('#dialogTitle').textContent!=='Frontal-cortex prediction'||curveKey!==key)return;
      target.insertAdjacentHTML('beforeend',dl([['Curve inference completed',s.inference_provenance.inference_completed_at],['Input interval (0-based, half-open)',`${s.interval.chrom}:[${s.interval.start}, ${s.interval.end})`],['Plotted interval (0-based, half-open)',s.display_interval_0based_halfopen.join(' – ')],['Delta axis',s.delta_scale],['Transcript',s.selected_transcript_name+(s.gene_model_partial?' · partial model in window':'')]]));
    }).catch(()=>{if($('#dialogTitle').textContent==='Frontal-cortex prediction')target.insertAdjacentHTML('beforeend','<p>Additional curve metadata could not be loaded. Please reopen Track details to retry.</p>');});
  }
  if(name==='genome')genomeDialog(v);
}
$('#dataset').addEventListener('change',()=>loadSingle($('#dataset').value));
$('.skip').onclick=e=>{e.preventDefault();$('#workspace').focus();};
$('#closeDialog').onclick=()=>$('#detailDialog').close();
$('#detailDialog').addEventListener('click',e=>{if(feedbackController?.busy)return;if(e.target===$('#detailDialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});
document.addEventListener('click',e=>{const b=e.target.closest('[data-dialog]');if(b)dialog(b.dataset.dialog);});
$('#chartOptionsButton').onclick=()=>{const hidden=!$('#chartOptions').hidden;$('#chartOptions').hidden=hidden;$('#chartOptionsButton').setAttribute('aria-expanded',String(!hidden));};
$('#exportButton').onclick=exportDialog;
$('#newAnalysis').onclick=()=>dialog('new');
function route(){
  const requested=location.hash.slice(1)||'overview';
  state.route=({home:'overview',tissue:'tracks',genome:'variant',guide:'overview',howto:'overview',workspace:'overview'})[requested]||requested;
  if(!['overview','variant','multi','tracks','feedback','local'].includes(state.route))state.route='overview';
  if(state.route!=='local')leaveLocal();
  chart?.hide();notice('');
  document.querySelectorAll('[data-route]').forEach(a=>{if(a.dataset.route===state.route)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  for(const [name,id] of Object.entries({overview:'overviewView',variant:'singleView',multi:'multiView',tracks:'tracksView',feedback:'feedbackView',local:'localView'}))$('#'+id).hidden=state.route!==name;
  $('#pageTitle').textContent={overview:'Overview',variant:'Single variant',multi:'Compare variants',tracks:'Track library',feedback:'Feedback',local:'My analyses'}[state.route];
  $('#pageEyebrow').textContent=['overview','feedback'].includes(state.route)?'ALPHAGENIE':'ANALYSIS WORKSPACE';
  $('#exportButton').hidden=!['variant','multi'].includes(state.route);
  $('#newAnalysis').hidden=!['variant','multi'].includes(state.route);
  $('#exportButton').disabled=state.route==='variant'&&singleLoading;
  document.title=state.route==='overview'?'AlphaGENIE · AlphaGENome-Integrated Explorer':$('#pageTitle').textContent+' · AlphaGENIE v0.21';
  if(state.route==='variant'&&!current&&!singleLoading)loadSingle().then(()=>{if(location.hash==='#genome')dialog('genome');});
  if(state.route==='multi')loadCohort();if(state.route==='tracks')loadTracks();
  if(state.route==='feedback')loadFeedback();
  if(state.route==='local')enterLocal();
  if(['guide','howto'].includes(requested))dialog('guide');
  if(requested==='genome'&&current)dialog('genome');
}
let feedbackLoading=null;
async function loadFeedback(){
  try{
    if(!feedbackLoading)feedbackLoading=import('./feedback.js').then(m=>{
      feedbackController=m.createFeedbackController({openDialog,dialog:$('#detailDialog'),closeButton:$('#closeDialog')});
      return feedbackController;
    }).catch(e=>{feedbackLoading=null;throw e;});
    const controller=await feedbackLoading;if(state.route==='feedback')await controller.enter();
  }catch(e){if(state.route==='feedback'){$('#feedbackStatus').hidden=false;$('#feedbackStatus').textContent='Feedback could not be loaded. Select Refresh to try again.';$('#refreshFeedback').onclick=loadFeedback;}}
}
$('#detailDialog').addEventListener('close',()=>feedbackController?.closeEditor());
$('#detailDialog').addEventListener('cancel',e=>{if(feedbackController?.busy)e.preventDefault();});

function links(entries){return entries.map(([n,url])=>`<a class="file-link" href="${esc(url)}">${esc(n.replaceAll('_',' '))}<span aria-hidden="true">↓</span></a>`).join('');}
function usageNotice(){return '<p class="caption usage-notice">AlphaGenome-derived outputs are subject to the <a href="https://deepmind.google.com/science/alphagenome/output-terms" target="_blank" rel="noopener noreferrer">AlphaGenome Output Terms of Use</a>, including non-commercial use and clinical-use restrictions. AlphaGENIE has modified these outputs through calibration, grouping and visualization. <a href="/static/v021/usage-notice.txt" download>Download accompanying use & modification notice</a>.</p>';}
function dataDownloads(result){
  const entries=Object.entries(result.downloads).filter(([n])=>!n.startsWith('plot_')&&!n.startsWith('figure_'));
  const nulls=entries.filter(([n])=>/null|scores_npz/.test(n));
  const source=entries.filter(([n])=>!nulls.some(([k])=>k===n)&&!/provenance|statistics|qc_summary|validation/.test(n));
  const methods=entries.filter(([n])=>/provenance|statistics|qc_summary|validation/.test(n));
  return `<details><summary>Source tables & curve data (${source.length})</summary><div class="file-list">${links(source)}</div></details><details><summary>Matched-null model files (${nulls.length})</summary><div class="file-list">${links(nulls)}</div></details><details><summary>Methods, statistics & quality checks (${methods.length})</summary><div class="file-list">${links(methods)}</div></details>`;
}
function exportDialog(){
  const multi=state.route==='multi',r=multi?cohort:current;
  const exportKey=key;
  if(!r){notice('Load a saved result before exporting.');return;}
  if(multi){openDialog('Export 17-variant comparison',usageNotice()+'<p>Approved Figure 3D–F · 174 × 68 mm · 17 variants · Brain9</p><a class="button primary" href="'+esc(r.downloads.figure_pdf)+'">Download manuscript PDF</a><a class="button secondary" href="'+esc(r.downloads.figure_svg)+'">SVG</a><a class="button secondary" href="'+esc(r.downloads.figure_png)+'">PNG</a><p class="caption">Fixed manuscript layout. Table sorting in the explorer does not alter the approved figure or its BH17 statistics.</p>'+dataDownloads(r));return;}
  const defaults={figure_width_mm:174,font_size_pt:6.5,top_panel_height_mm:64,effect_panel_height_mm:68};
  const fields=[['figure_width_mm','Width (mm)',90,300,1],['font_size_pt','Font size (pt)',6,14,.1],['top_panel_height_mm','Gene / curve height (mm)',45,200,1],['effect_panel_height_mm','Tissue effects height (mm)',50,200,1]];
  openDialog('Export '+r.variant.gene_symbol,usageNotice()+'<div class="export-layout"><div class="layout-glyph" aria-hidden="true"><span>Gene + RNA</span><span>Tissue effects</span></div><div><h3>Stacked figure</h3><p class="subtle">Gene structure and curves above, bars and all 371 tracks below.</p><p id="exportSize" class="caption"></p></div></div><div id="exportLinks"></div><details id="exportSettings"><summary>Figure dimensions & typography</summary><form id="exportForm"><div class="form-grid">'+fields.map(([n,label,min,max,step])=>`<label>${label}<input name="${n}" type="number" min="${min}" max="${max}" step="${step}" value="${state.options.get(n)||defaults[n]}" required></label>`).join('')+'</div><button class="button secondary" type="submit">Apply export settings</button><p id="exportStatus" class="caption" role="status"></p></form></details><p class="caption">Layout only: scores, P values, categories and nulls stay unchanged. Web highlights and the show-tracks switch are not applied to exported figures. Web typography is optimized separately for reading.</p><details><summary>Original paired manuscript figure</summary><p>The approved manuscript PDF remains unchanged.</p><a class="button secondary" href="'+esc(r.downloads.plot_pdf)+'">Original PDF</a><a class="button secondary" href="'+esc(r.downloads.plot_svg)+'">SVG</a><a class="button secondary" href="'+esc(r.downloads.plot_png)+'">PNG</a></details>'+dataDownloads(r));
  const renderLinks=()=>{const top=Number(state.options.get('top_panel_height_mm')||64),effect=Number(state.options.get('effect_panel_height_mm')||68);
    $('#exportSize').textContent=`${state.options.get('figure_width_mm')||174} × ${top+effect+4} mm · ${state.options.get('font_size_pt')||6.5} pt`;
    $('#exportLinks').innerHTML=['pdf','svg','png'].map(ext=>`<a class="button ${ext==='pdf'?'primary':'secondary'}" href="/api/explorer/${key}/export/${ext}?${esc(state.options)}">${ext==='pdf'?'Download PDF':ext.toUpperCase()}</a>`).join('');};
  renderLinks();
  $('#exportForm').onsubmit=async e=>{e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;const target=$('#exportStatus');target.textContent='Checking label fit…';
    try{const q=optionQuery(Object.fromEntries(new FormData(e.target)));await get(`/api/explorer/${exportKey}/view-options?${q}`);if(target.isConnected&&key===exportKey){state.options=q;renderLinks();target.textContent='Settings applied. Download links now use these dimensions.';}}
    catch(err){if(target.isConnected)target.textContent=err.message+' Previous download settings have been retained.';}
    finally{button.disabled=false;}
  };
}

async function loadCohort(){
  const target=$('#multiView');
  if(cohort){renderCohort();return;}
  target.innerHTML='<div class="figure-card" role="status">Loading the saved 17-variant comparison…</div>';
  try{cohort=(await get('/api/explorer/ccg17')).result;renderCohort();}
  catch(e){target.innerHTML=`<div class="notice error">${esc(e.message)} <button class="text-button" id="retryCohort">Retry</button></div>`;$('#retryCohort').onclick=loadCohort;}
}
function renderCohort(){
  const n=cohort.statistics.filter(r=>r.q_two_sided<=.05).length;
  $('#multiView').innerHTML=`<div class="selection-bar"><div><span class="eyebrow">SAVED COHORT</span><h2>17 CCG variants <span class="badge">1 Mb each</span></h2></div><button class="text-button" data-dialog="details">Analysis details ↗</button></div><div class="summary-row"><div class="metric"><dl><dt>Two-sided BH q ≤ 0.05</dt><dd>${n} <span class="subtle">/ 17 variants</span></dd></dl><small>BH correction across all 17 variants</small></div><div class="metric"><dl><dt>Comparison endpoint</dt><dd>Brain9</dd></dl><small>8 adult categories + Embryo</small></div><div class="metric"><dl><dt>Matched nulls / variant</dt><dd>1,000</dd></dl><small>Saved v0.20 · no new inference</small></div></div><div class="context-row"><span>RBFOX1 reference: 1 Mb, not the standalone 16 kb result</span><button class="text-button" data-dialog="groups">Group definitions ↗</button></div><section class="figure-card"><div class="card-head"><div><span class="panel-index">01</span><h2>Effects, evidence & similarity</h2></div><button class="text-button" id="cohortStats">Numerical results</button></div><p class="subtle figure-subhead">Rows ordered by Brain9 adjusted effect · RGPD1 excluded</p><div class="plot-scroll"><img class="cohort-figure" src="${esc(cohort.downloads.figure_svg)}" alt="17 variants: Brain9 category heatmap, consensus effect with two-sided and exploratory direction-selected FDR, and cosine similarity to RBFOX1"></div><p class="caption">Filled markers: two-sided BH q. Open markers: exploratory direction-selected BH q. Labels follow the approved figure rule; a label alone does not mean two-sided q ≤ 0.05.</p></section><div class="cohort-note"><span>Cosine compares the nine-category score pattern with RBFOX1; it is not a significance test.</span><button class="text-button" data-dialog="methods">How this was calculated ↗</button></div>`;
  $('#cohortStats').onclick=cohortTable;
}
function cohortTable(){
  openDialog('17-variant numerical results','<div class="table-controls"><label>Sort by <select id="cohortSort"><option value="consensus">Figure order</option><option value="q">Two-sided BH q</option><option value="gene">Gene name</option></select></label></div><p class="caption">Sorting changes the table only. All q values retain the original 17-variant correction family.</p><div class="table-scroll"><table><thead><tr><th>Gene</th><th>Brain9 effect</th><th>Two-sided BH q</th><th>Cosine</th></tr></thead><tbody id="cohortRows"></tbody></table></div><p class="caption">Select a gene for exact P/q values and the exploratory direction-selected result.</p>');
  function rows(){const ordered=orderedCohort(cohort,$('#cohortSort').value);$('#cohortRows').innerHTML=ordered.map(r=>`<tr><td><button class="text-button" data-cohort-id="${esc(r.run_id)}">${esc(r.gene_symbol)}</button></td><td>${signed(r.consensus_effect)}</td><td>${number(r.q_two_sided,6)}${r.q_two_sided<=.05?' *':''}</td><td>${number(r.cosine_to_RBFOX1,3)}</td></tr>`).join('');$('#cohortRows').querySelectorAll('[data-cohort-id]').forEach(b=>b.onclick=()=>cohortRow(b.dataset.cohortId));}
  $('#cohortSort').onchange=rows;rows();
}
function cohortRow(id){const r=cohort.statistics.find(r=>r.run_id===id),v=cohort.ranking.find(r=>r.run_id===id);openDialog(r.gene_symbol+' · 1 Mb cohort result',dl([['Variant',`${v.chrom}:${v.pos1} ${v.ref} → ${v.alt}`],['Brain9 adjusted effect',r.consensus_effect],['Two-sided empirical P',r.p_two_sided],['Two-sided BH q (m = 17)',r.q_two_sided],['Cosine to RBFOX1 1 Mb',r.cosine_to_RBFOX1],['Matched nulls',r.n_null]])+`<details><summary>Exploratory direction-selected test</summary>${dl([['Observed direction',r.observed_tail],['Direction-selected P',r.p_observed_direction],['Direction-selected BH q',r.q_observed_direction]])}<p>Post hoc observed direction, not a prespecified one-sided hypothesis.</p></details><details><summary>Null calibration & adult-only sensitivity analysis</summary>${dl([['Null consensus median',r.null_median],['Two-sided tail count',r.tail_two_sided],['Observed-direction tail count',r.tail_observed_direction],['Adult-only consensus',r.adult_only.consensus_effect],['Adult-only two-sided BH q',r.adult_only.q_two_sided]])}<p>Adult-only results are a separate endpoint, corrected separately across the same 17 variants.</p></details><button id="backCohort" class="text-button">← Back to all variants</button>`);$('#backCohort').onclick=cohortTable;}
function cohortDialog(name){
  if(!cohort){notice('Wait for the cohort to load.');return;}
  if(name==='groups'){openDialog('Brain9 groups',dl(cohort.groups.map(g=>[g.label,g.n_tracks+' assay tracks']))+'<p>The median of these nine category medians defines Brain9. Non-brain tissues and cells are not used in this comparison.</p>');return;}
  if(name==='details'){openDialog('17-variant analysis details',dl([['Input window','1,048,576 bp per variant · GRCh38'],['Primary endpoint','Brain9: 8 adult categories + Embryo'],['Nulls','1,000 per variant'],['Primary multiple testing','Two-sided BH q, m = 17'],['Figure row order','Ascending Brain9 consensus effect'],['Excluded','Three RGPD1 variants'],['Cosine reference','RBFOX1 1 Mb; uncentered nine-category vector']])+'<button class="text-button" id="showCohortTable">Open numerical results →</button>');$('#showCohortTable').onclick=cohortTable;return;}
  openDialog('Cohort methods & provenance','<p>Adjusted RNA_SEQ GeneMaskLFC values are centered on each track’s median of 1,000 matched-null scores. Brain9 is the median of nine category medians, not the median of all 21 tracks.</p><p>Empirical tests use recentered null-consensus distributions with a +1/1,001 correction. BH correction is performed across these 17 variants separately for each test. Direction-selected P/q is exploratory.</p><p>Cosine uses the uncentered nine-category vectors relative to the 1 Mb RBFOX1 variant. It measures pattern similarity, not evidence of the same mechanism.</p>'+dl([['Interface / data','v0.21 / frozen v0.20'],['SDK','0.8.0'],['Score inference completed',cohort.release.completed_at],['Backend checkpoint','Not disclosed'],['New inference on viewing','None']])+usageNotice()+dataDownloads(cohort));
}

async function loadTracks(){
  if(tracks){renderTracks();return;}$('#tracksView').innerHTML='<div class="figure-card" role="status">Loading track metadata…</div>';
  try{tracks=await get('/api/explorer/tracks');renderTracks();}catch(e){$('#tracksView').innerHTML=`<div class="notice error">${esc(e.message)} <button class="text-button" id="retryTracks">Retry</button></div>`;$('#retryTracks').onclick=loadTracks;}
}
function renderTracks(){
  $('#tracksView').innerHTML='<div class="library-intro"><h2>Find the data behind each point</h2><p class="subtle">371 RNA-seq assay tracks · 11 display categories · data v0.20</p></div><div class="scope-strip"><div><strong>Adult brain</strong><span>14 tracks · 8 categories</span></div><div><strong>Embryo brain</strong><span>7 tracks · 1 category</span></div><div><strong>Other tissues</strong><span>153 tracks · display only</span></div><div><strong>Cells & lines</strong><span>197 tracks · display only</span></div></div><section class="figure-card"><div class="library-controls"><label class="search-label">Search tracks<input id="trackSearch" type="search" placeholder="Tissue, cell line, ontology or source…"></label><label>Category<select id="trackGroup"><option value="all">All categories</option>'+tracks.visualization_groups.map(g=>`<option value="${esc(g.label)}">${esc(g.label)} (${g.n_unique_tracks})</option>`).join('')+'</select></label></div><p id="trackCount" class="caption" role="status"></p><div class="table-scroll"><table><thead><tr><th>Biosample / track</th><th>Category</th><th>Life stage</th><th>Source</th></tr></thead><tbody id="trackRows"></tbody></table></div><div class="pagination"><button class="button secondary" id="previousTracks">Previous</button><span id="trackPage" class="subtle"></span><button class="button secondary" id="nextTracks">Next</button></div><p class="caption">Track counts do not represent independent biological replicates. Select a biosample to inspect its full metadata.</p></section>';
  trackPage=0;$('#trackSearch').oninput=()=>{trackPage=0;renderTrackRows();};$('#trackGroup').onchange=()=>{trackPage=0;renderTrackRows();};$('#previousTracks').onclick=()=>{trackPage--;renderTrackRows();};$('#nextTracks').onclick=()=>{trackPage++;renderTrackRows();};renderTrackRows();
}
function renderTrackRows(){
  const list=filterTracks(tracks.track_audit,$('#trackSearch').value,$('#trackGroup').value),size=20;
  trackPage=Math.max(0,Math.min(trackPage,Math.ceil(list.length/size)-1));
  $('#trackCount').textContent=`${list.length} of ${tracks.n_tracks} tracks`;
  $('#trackRows').innerHTML=list.length?list.slice(trackPage*size,(trackPage+1)*size).map(r=>`<tr><td><button class="text-button track-name" data-track="${esc(r.track_key)}">${esc(r.biosample_name)}</button><small class="track-assay">${esc(r.track_name)}</small></td><td>${esc(r.display_group)}</td><td>${esc(r.biosample_life_stage||'Not recorded')}</td><td>${esc(r.data_source.toUpperCase())}</td></tr>`).join(''):'<tr><td colspan="4" class="empty-cell">No matching tracks. Try a broader term or choose All categories.</td></tr>';
  $('#trackPage').textContent=list.length?`${trackPage*size+1}–${Math.min((trackPage+1)*size,list.length)} of ${list.length}`:'0 results';
  $('#previousTracks').disabled=trackPage===0;$('#nextTracks').disabled=(trackPage+1)*size>=list.length;
  $('#trackRows').querySelectorAll('[data-track]').forEach(b=>b.onclick=()=>{const r=tracks.track_audit.find(r=>r.track_key===b.dataset.track);openDialog(r.biosample_name,dl([['Track',r.track_name],['Category',r.display_group],['Brain9',r.included_in_brain9?'Included':'Display only'],['Life stage',r.biosample_life_stage||'Not recorded'],['Material',r.biosample_type],['Ontology',r.ontology_curie],['Source',r.data_source],['GTEx tissue',r.gtex_tissue||'Not applicable'],['Mapping rule',r.mapping_rule_id]])+`<details><summary>Classification evidence</summary><p>${esc(r.mapping_notes)}</p><pre>${esc(r.mapping_evidence_urls)}</pre></details><details><summary>All recorded metadata</summary><pre>${esc(JSON.stringify(r,null,2))}</pre></details>`);});
}

function genomeDialog(v){
  openDialog('View genomic locus','<p>Opening UCSC sends the selected assembly and genomic coordinates to UCSC. Nothing is sent until you follow the link.</p><label class="block-label">Flanking region (bp)<input id="genomeFlank" type="number" min="50" max="1000000" step="50" value="5000"></label><p id="genomeLocus" class="caption"></p><a id="genomeLink" class="button primary" target="_blank" rel="noopener noreferrer">Open UCSC Genome Browser ↗</a>');
  const update=()=>{const flank=Number($('#genomeFlank').value),valid=Number.isInteger(flank)&&flank>=50&&flank<=1000000;
    $('#genomeLink').hidden=!valid;if(!valid){$('#genomeLocus').textContent='Enter a flank between 50 and 1,000,000 bp.';return;}
    const position=`${v.chrom}:${Math.max(1,v.pos1-flank)}-${v.pos1+flank}`;$('#genomeLocus').textContent='hg38 · '+position;$('#genomeLink').href='https://genome.ucsc.edu/cgi-bin/hgTracks?'+new URLSearchParams({db:'hg38',position});};
  $('#genomeFlank').oninput=update;update();
}
$('#curveImage').addEventListener('error',()=>notice('The cortex curve could not be loaded. Switch the saved result or reload to retry. Tissue scores are unaffected.',true));
window.addEventListener('hashchange',route);window.addEventListener('scroll',()=>chart?.hide(),{passive:true});
route();
