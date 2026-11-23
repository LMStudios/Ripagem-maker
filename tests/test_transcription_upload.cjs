const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const src=fs.readFileSync('index.html','utf8');
const code=src.slice(src.indexOf('const OFF='),src.indexOf('$("go").onclick=()=>startTranscription();'));
function fixture(fetch){
 const nodes={},sent=[],events=[];let requests=0;
 const node=id=>nodes[id]??={value:'',checked:false,textContent:'',style:{},className:'',classList:{add(){},remove(){}},scrollIntoView(){}};
 class XHR{constructor(){requests++;this.upload={};}open(){}setRequestHeader(){}send(file){sent.push(file);}}
 const c={file:{name:'large.mp4',size:5958747138},wizardBusy:false,$:node,window:{},document:{getElementById:node,dispatchEvent:e=>events.push(e)},CustomEvent:class{},fetch,XMLHttpRequest:XHR,AbortController,setTimeout,clearTimeout,updateWizard(){},wizardStep(){}};
 vm.createContext(c);vm.runInContext(code,c);return {c,nodes,sent,get requests(){return requests;}};
}
const response=(status,data)=>({ok:status>=200&&status<300,status,json:async()=>data});
test('insufficient space explains the rejection before opening or sending a media request',async()=>{
 const f=fixture(async()=>response(400,{erro:'Espaço insuficiente: vídeo 5,96 GB, livres 3,86 GB.'}));
 await f.c.startTranscription();assert.equal(f.requests,0);assert.equal(f.sent.length,0);assert.equal(f.c.wizardBusy,false);assert.match(f.nodes.step.textContent,/Espaço insuficiente/);assert.doesNotMatch(f.nodes.step.textContent,/conectar/);
});
test('the UI waits for capacity confirmation and ignores duplicate starts',async()=>{
 let release;const f=fixture(()=>new Promise(r=>release=r));const pending=f.c.startTranscription();assert.equal(f.c.wizardBusy,true);assert.equal(f.requests,0);await f.c.startTranscription();release(response(200,{ok:true}));await pending;assert.equal(f.sent.length,1);assert.equal(f.sent[0].name,'large.mp4');
});
test('network failure with live server is described as interrupted file transfer',async()=>{
 const f=fixture(async()=>response(200,{ok:true}));assert.match(await f.c.uploadFailureMessage(f.c.file),/app está aberto.*envio.*interrompida.*Projetos/);
});
test('capacity lost during a transfer reports the actual space error',async()=>{
 const f=fixture(async()=>response(400,{erro:'Espaço insuficiente para receber o arquivo.'}));assert.match(await f.c.uploadFailureMessage(f.c.file),/Espaço insuficiente/);
});
test('unreachable processing service has its own connection message',async()=>{
 const f=fixture(async()=>{throw Error('Failed to fetch');});await f.c.startTranscription();assert.equal(f.requests,0);assert.match(f.nodes.step.textContent,/conectar ao processamento local/);assert.equal(f.c.wizardBusy,false);
});
test('automatic mode gets the same preflight error and never sends the file',async()=>{
 const f=fixture(async()=>response(400,{erro:'Espaço insuficiente'}));await f.c.startTranscription({ativo:true});assert.equal(f.requests,0);assert.equal(f.c.wizardBusy,false);
});
