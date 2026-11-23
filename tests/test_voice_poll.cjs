const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('plataforma/static/trocas.js','utf8');
const functions=src.slice(src.indexOf('  function voiceFailureGroups(rows){'),src.indexOf("  el('swap-cancel').onclick"));
function fixture(fetch){
 const nodes={},timers=new Map();let timerID=0;const session=new Map([['dr.swap.job','job']]);
 const el=id=>nodes[id]??=( {hidden:false,textContent:'',innerHTML:'',classList:{values:new Set(),add(x){this.values.add(x)},remove(x){this.values.delete(x)}}});
 const context={currentJob:'job',folder:'work',poll:null,polling:false,busy:true,jobContext:{},el,status:el('swap-status'),inlineProgress:el('inline'),sessionStorage:{setItem:(k,v)=>session.set(k,v),removeItem:k=>session.delete(k)},setTimeout:(fn,ms)=>{let id=++timerID;timers.set(id,{fn,ms});return id},clearTimeout:id=>timers.delete(id),AbortController,fetch,voiceProgress:()=>{},setBusy:x=>context.busy=x,x:s=>String(s),document:{dispatchEvent(){}},CustomEvent:class{},loads:0};context.window={loadSwapPlan:async()=>context.loads++};vm.createContext(context);vm.runInContext(functions,context);return {c:context,nodes,timers,session};
}
(async()=>{
 let f=fixture(async()=>({ok:true,json:async()=>({status:'concluido',step:'Done',result:{}})}));await f.c.pollJob();assert.equal(f.c.busy,false);assert.equal(f.c.currentJob,null);assert.equal(f.c.loads,1);assert.equal(f.session.has('dr.swap.job'),false);assert(f.nodes['swap-status'].classList.values.has('hidden'));assert.equal(f.timers.size,0);
 f=fixture(async()=>({ok:false,status:404,json:async()=>({erro:'missing'})}));await f.c.pollJob();assert.equal(f.c.busy,false);assert.equal(f.c.currentJob,null);assert.equal(f.timers.size,0);assert.equal(f.nodes['swap-dismiss-status'].hidden,false);
 let resolve;f=fixture(()=>new Promise(r=>resolve=r));let first=f.c.pollJob();await f.c.pollJob();resolve({ok:true,json:async()=>({status:'executando',step:'Working'})});await first;assert.equal([...f.timers.values()].filter(t=>t.ms===2000).length,1);assert.equal(f.timers.size,1);
 f=fixture(async()=>{throw Error('offline')});await f.c.pollJob();assert.equal(f.c.busy,true);assert.equal(f.c.polling,false);assert.equal(f.timers.size,1);assert.equal([...f.timers.values()][0].ms,4000);
 f=fixture(async()=>({ok:true,json:async()=>({status:'concluido',step:'Pendências',result:{resultados:Array.from({length:36},(_,i)=>({id:'row'+i,speaker:'A',erro:'Esta voz exige verificação no ElevenLabs.'}))}})}));await f.c.pollJob();
 assert.equal((f.nodes['swap-job-errors'].innerHTML.match(/Esta voz exige verificação/g)||[]).length,1);
 assert.match(f.nodes['swap-job-errors'].innerHTML,/36 frases pendentes/);
 assert.equal(f.c.busy,false);
 console.log('5 voice-job lifecycle checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
