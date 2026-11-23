const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{test}=require('node:test');
const code=fs.readFileSync('plataforma/static/trocas.js','utf8');
const fn=code.slice(code.indexOf('  async function importAudio('),code.indexOf('  function renderSpeakers('));
function fixture(){
 const sent=[],events=[],jobs=[],errors=[];
 const c={folder:'work',plan:{itens:[{id:'one'},{id:'two'}]},busy:false,importing:false,currentJob:null,encodeURIComponent,save:async()=>{},setBusy(v){c.busy=v},fetch:async(url,options)=>{sent.push({url,...options});return {ok:true,json:async()=>({id:'job1'})}},startJob(job,context){jobs.push({job,context});c.currentJob=job.id},CustomEvent:class{constructor(type,options){Object.assign(this,{type,...options})}},document:{dispatchEvent:e=>events.push(e)},action:async f=>{try{await f()}catch(e){errors.push(e.message)}},window:{SwapUX:{flushDraft:async()=>true,hasDraft:()=>false}}};
 vm.createContext(c);vm.runInContext(fn,c);return {c,sent,events,jobs,errors};
}
const audio={name:'take.mp3',size:50,type:'audio/mpeg'};
test('imports exactly the requested phrase, with import context and local file body',async()=>{
 const f=fixture();await f.c.importAudio('two',audio);assert.equal(f.sent.length,1);assert.equal(f.sent[0].headers['X-Row'],'two');assert.equal(f.sent[0].body,audio);assert.equal(f.jobs[0].context.origin,'audio-import');assert.equal(f.jobs[0].context.rowId,'two');assert.equal(f.errors.length,0);
});
test('invalid, empty or oversized files and unsaved drafts never upload',async()=>{
 for(const file of [{name:'video.mp4',size:20},{name:'empty.wav',size:0},{name:'big.wav',size:51*1024*1024}]){const f=fixture();await f.c.importAudio('two',file);assert.equal(f.sent.length,0);assert.equal(f.errors.length,1);assert.equal(f.c.importing,false);}
 const f=fixture();f.c.window.SwapUX.flushDraft=async()=>false;await f.c.importAudio('two',audio);assert.equal(f.sent.length,0);
});
test('concurrent drops upload once, and a failed upload can be retried',async()=>{
 const f=fixture();let resolve;f.c.save=()=>new Promise(r=>resolve=r);const first=f.c.importAudio('two',audio);await Promise.resolve();await Promise.resolve();await f.c.importAudio('one',audio);resolve();await first;assert.equal(f.sent.length,1);
 const g=fixture();g.c.fetch=async()=>({ok:false,json:async()=>({erro:'Falha no áudio'})});await g.c.importAudio('two',audio);assert.equal(g.c.busy,false);assert.equal(g.c.importing,false);assert.match(g.errors[0],/Falha/);g.c.fetch=async()=>({ok:true,json:async()=>({id:'retry'})});await g.c.importAudio('two',audio);assert.equal(g.jobs.length,1);
});
test('changing project while saving cannot upload into another project',async()=>{
 const f=fixture();f.c.save=async()=>{f.c.folder='different'};await f.c.importAudio('two',audio);assert.equal(f.sent.length,0);assert.equal(f.jobs.length,0);
});

test('switching projects during the upload never leaves the interface locked',async()=>{
 const f=fixture();f.c.fetch=async()=>{f.c.folder='another';return {ok:true,json:async()=>({id:'old-project-job'})}};await f.c.importAudio('two',audio);assert.equal(f.c.busy,false);assert.equal(f.jobs.length,0);
});
