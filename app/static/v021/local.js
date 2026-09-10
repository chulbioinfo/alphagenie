import {esc} from './model.js';
let initialized=false,timer=null,active=false,token='',busy=false;
const $=s=>document.querySelector(s);
const example='gene_symbol\tchrom\tpos1\tref\talt\nRBFOX1\tchr16\t6018925\tTCCG\tT';
async function request(url,body){
  const response=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-AlphaGENIE-Token':token},body:JSON.stringify(body)});
  let data;try{data=await response.json();}catch{throw new Error('Local server did not return JSON. Check the terminal.');}
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:`Invalid request (${response.status}). Check all fields.`);
  return data;
}
function message(text){$('#localMessage').textContent=text;}
export function leaveLocal(){active=false;clearTimeout(timer);}
export async function enterLocal(){
  active=true;
  if(!initialized){
    $('#localView').innerHTML=`<section class="figure-card"><div class="card-head"><h2>Your environment. Your API key.</h2><span class="badge">Local edition</span></div><p>No API information is collected by AlphaGENIE operators. Your own key is used only for requests from this computer to Google DeepMind's AlphaGenome API.</p><p id="localConfig" role="status">Checking local configuration…</p><details><summary>Set up credentials & references</summary><p>In a terminal at the repository root, run:</p><pre>python -m alphagenie key set
python -m alphagenie configure --fasta /path/to/hg38.fa --gtf /path/to/gencode.v46.annotation.gtf.gz
python -m alphagenie doctor</pre><p>The key is entered privately in the terminal, not this browser. It is stored in an owner-only local file outside the repository (not encrypted). Environment-only credentials are also supported. See docs/PRIVACY.md and docs/INSTALL.md.</p></details></section>
    <section class="figure-card"><h2>New analysis</h2><p class="notice">New runs use the manuscript Brain9 classification: eight adult brain categories + Embryo. Non-brain tissues and Cells &amp; cell lines are separate comparison pools, excluded from Brain9 statistics and cosine.</p><details><summary>Classification &amp; reproducibility</summary><p>The reviewed catalog contains 14 adult, 7 embryonic brain, 153 non-brain tissue and 197 cell tracks. Each null must contain the same tracks; unknown or changed classification metadata stops analysis for review. Single plots show all 11 categories; comparison heatmaps and cosine use Brain9 only. The downloadable matrix retains both comparison pools.</p><p>New runs generate new real/null scores and do not reuse saved predictions. The RNA curve uses the same adult Frontal cortex track as the v0.21 saved explorer: GTEx Brain_Cortex (UBERON:0001870), polyA+ RNA-seq, unstranded. No Whole brain, BA9 or embryonic-tissue fallback is allowed. Matching the classification does not guarantee matching September 2026 numbers.</p></details><p class="caption">Default: 1,000 complete matched nulls per variant.</p>
    <form id="localForm"><label class="block-label">Variants (tab-separated; one row for single, 2–20 for comparison)<textarea name="tsv" rows="6" spellcheck="false" required>${esc(example)}</textarea></label><button type="button" id="localExample" class="text-button">Load saved 17-variant input only</button><div class="form-grid"><label>Dataset name<input name="dataset_name" value="My analysis" maxlength="80" pattern="[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}" required></label><label>Input window<select name="sequence_length"><option value="16384">16,384 bp</option><option value="131072">131,072 bp</option><option value="524288">524,288 bp</option><option value="1048576">1,048,576 bp</option></select></label><label>Nulls per variant<input name="null_depth" type="number" min="10" max="2000" value="1000" required></label></div><p class="caption">1,000 nulls can take substantial time and disk space; requests consume your provider quota. Ten nulls are only an exploratory smoke test. Multi-variant cosine uses the first row as reference; BH is produced only when all requested variants complete.</p><label class="block-label"><input type="checkbox" name="consent" required> I authorize sending these real/null variants and intervals to Google DeepMind with my API key, accept the applicable AlphaGenome API and output terms, and understand this is not for clinical use.</label><p><a href="https://deepmind.google.com/science/alphagenome/terms" target="_blank" rel="noopener noreferrer">Review provider terms ↗</a></p><div class="dialog-actions"><button type="button" id="localValidate" class="button secondary">Check references · no API</button><button type="submit" id="localRun" class="button primary" disabled>Run with my API key</button></div><p id="localMessage" role="status"></p></form></section>
    <section class="figure-card"><div class="card-head"><h2>Local jobs</h2><button id="localRefresh" class="text-button">Refresh</button></div><p class="caption">Inputs, nulls, scores and logs remain in your private local state directory. Stop the server with Ctrl+C to interrupt an active job. Already transmitted requests cannot be recalled.</p><div id="localJobs"></div><div id="localResult"></div></section>`;
    initialized=true;
    const body=()=>{const d=new FormData($('#localForm'));return {tsv:d.get('tsv'),dataset_name:d.get('dataset_name'),sequence_length:Number(d.get('sequence_length')),null_depth:Number(d.get('null_depth')),consent:d.get('consent')==='on'};};
    async function action(run){
      if(busy)return;busy=true;$('#localRun').disabled=true;$('#localValidate').disabled=true;
      message(run?'Validating and submitting a fresh API analysis…':'Checking local FASTA and gene annotation. No API call…');
      try{const d=await request(run?'/api/local/jobs':'/api/local/validate',body());message(run?`Submitted ${d.job_id}. Keep the local server running.`:'Local reference checks passed; no API request made. The server will recheck before execution.');await refresh();}
      catch(e){message(e.message);}finally{busy=false;$('#localValidate').disabled=false;await config();}
    }
    $('#localForm').onsubmit=e=>{e.preventDefault();action(true);};
    $('#localValidate').onclick=()=>action(false);
    $('#localRefresh').onclick=()=>{config();refresh();};
    $('#localExample').onclick=async()=>{try{const d=await request('/api/explorer/ccg17');const fields=['gene_symbol','chrom','pos1','ref','alt'];$('#localForm textarea').value=fields.join('\t')+'\n'+d.result.variant_mapping.map(r=>fields.map(k=>r[k]).join('\t')).join('\n');$('#localForm select').value='1048576';message('Loaded input only. This will be a fresh Brain9 run with new matched nulls; saved scores are not reused.');}catch(e){message(e.message);}};
  }
  await config();await refresh();
}
async function config(){
  try{const s=await request('/api/local/status');token=s.token;
    $('#localConfig').textContent=`API key: ${s.key_configured?'configured (not yet authenticated with provider)':'not configured'} · References: ${s.references_configured?'configured':'not configured'}`;
    $('#localRun').disabled=busy||!s.key_configured||!s.references_configured;
  }catch(e){$('#localConfig').textContent=e.message;$('#localRun').disabled=true;}
}
async function refresh(){
  clearTimeout(timer);
  try{const {jobs}=await request('/api/local/jobs');
    $('#localJobs').innerHTML=jobs.length?jobs.map(j=>`<div class="selected-track"><strong>${esc(j.job_id.slice(0,8))}</strong> · ${esc(j.status)} · ${esc(j.stage)}<p>${esc(j.message)}</p><p class="caption">${esc(j.endpoint)} · ${esc(j.rna_curve)} · ${j.requested_variants} requested variant(s)</p>${Object.keys(j.files).length?`<button class="text-button" data-local-job="${esc(j.job_id)}">View results & downloads →</button>`:''}</div>`).join(''):'<p>No local analyses yet. Saved manuscript results remain available in the other tabs.</p>';
    document.querySelectorAll('[data-local-job]').forEach(b=>b.onclick=()=>result(b.dataset.localJob));
    if(active&&jobs.some(j=>['submitted','running'].includes(j.status)))timer=setTimeout(refresh,5000);
  }catch(e){$('#localJobs').textContent=e.message;}
}
async function result(jid){
  try{const j=await request('/api/local/jobs/'+jid);
    $('#localResult').innerHTML=`<h3>Local v0.20 engine result</h3><p class="notice">${esc(j.endpoint)}. RNA curve: ${esc(j.rna_curve)}. The track library in the sidebar describes the separate saved manuscript data, not this new run.</p>${j.files.plot_png?`<img style="width:100%;height:auto" src="${esc(j.files.plot_png)}" alt="Locally generated v0.20 analysis figure">`:''}<div class="file-grid">${Object.entries(j.files).map(([k,u])=>`<a class="file-link" href="${esc(u)}">${esc(k.replaceAll('_',' '))} ↓</a>`).join('')}</div><p class="caption">All artifacts, including raw real/null scores and provenance sidecars, are also under the private local jobs directory. A cohort is generated only if every requested variant completes. Successful individual outputs remain available after a partial failure.</p>`;
  }catch(e){message(e.message);}
}
