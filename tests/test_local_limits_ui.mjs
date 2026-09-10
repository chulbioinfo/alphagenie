import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

test('My analyses has a visible no-login warning and uses only the per-process write token',async()=>{
  const source=fs.readFileSync(new URL('../app/static/v021/local.js',import.meta.url),'utf8');
  assert(source.includes('Personal computer only. No login or user isolation; do not run on shared computers or expose this server.'));
  assert(!/bootstrap|localStorage|sessionStorage|document\.cookie|\/api\/local\/(?:session|logout)/.test(source));
  const nodes=new Map(),calls=[];
  globalThis.document={querySelector(selector){
    if(!nodes.has(selector))nodes.set(selector,{textContent:'',innerHTML:'',disabled:false,insertAdjacentHTML(_where,html){this.before=html;}});
    return nodes.get(selector);
  },querySelectorAll(){return [];}};
  const originalFormData=globalThis.FormData;
  globalThis.FormData=class{get(name){return {tsv:'gene_symbol\tchrom\tpos1\tref\talt\nTEST\tchr1\t9000\tTCCG\tT',
    dataset_name:'Fixture',sequence_length:'16384',null_depth:'1000',consent:'on'}[name];}};
  globalThis.fetch=async(url,options)=>{
    calls.push({url,options});
    const data=url==='/api/local/status'?{token:'synthetic-write-token',key_configured:true,references_configured:true}:
      url==='/api/local/jobs'?{jobs:[]}:{api_calls:0};
    return {ok:true,status:200,json:async()=>data};
  };
  try{
    const ui=await import('../app/static/v021/local.js?no-login-limits-test');
    await ui.enterLocal();
    assert.match(nodes.get('#localConfig').before,/No login or user isolation/);
    assert.deepEqual(calls.map(c=>c.url),['/api/local/status','/api/local/jobs']);
    assert.equal(nodes.get('#localRun').disabled,false);
    await nodes.get('#localValidate').onclick();
    const validation=calls.find(c=>c.url==='/api/local/validate');
    assert.equal(validation.options.headers['X-AlphaGENIE-Token'],'synthetic-write-token');
    assert.equal(validation.options.headers['X-AlphaGENIE-CSRF'],undefined);
    assert.equal(validation.options.cache,'no-store');
    ui.leaveLocal();
  }finally{
    delete globalThis.document;delete globalThis.fetch;globalThis.FormData=originalFormData;
  }
});
