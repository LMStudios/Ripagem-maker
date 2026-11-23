const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const src=fs.readFileSync('index.html','utf8');
const code=src.slice(src.indexOf('function transcriptionBlocked(){'),src.indexOf('const pick=f=>'));
function fixture(file=null,busy=false){const nodes={'go':{},'wizard-chosen':{},'transcription-file-warning':{}};const c={file,wizardBusy:busy,transcriptionConfirmed:false,document:{querySelectorAll:()=>[]},$:id=>nodes[id]};vm.createContext(c);vm.runInContext(code,c);return {c,nodes};}
test('missing file disables start and explains what is missing',()=>{const {c,nodes}=fixture();c.syncTranscriptionFile();assert.equal(nodes.go.disabled,true);assert.equal(nodes['transcription-file-warning'].hidden,false);assert.match(nodes['wizard-chosen'].textContent,/Nenhum áudio ou vídeo/);});
test('valid file enables start and identifies the selected source',()=>{const {c,nodes}=fixture({name:'VSL.mp4',size:1048576});c.syncTranscriptionFile();assert.equal(nodes.go.disabled,false);assert.equal(nodes['transcription-file-warning'].hidden,true);assert.match(nodes['wizard-chosen'].textContent,/VSL.mp4 · 1.0 MB/);});
test('active operation keeps start disabled even with a selected file',()=>{const {c,nodes}=fixture({name:'VSL.mp4',size:1000},true);c.syncTranscriptionFile();assert.equal(nodes.go.disabled,true);});
test('zero-byte file cannot start transcription',()=>{const {c,nodes}=fixture({name:'empty.mp4',size:0});c.syncTranscriptionFile();assert.equal(nodes.go.disabled,true);});
test('both navigation paths guard missing selection',()=>{assert.match(src,/if\(n===2&&transcriptionBlocked\(\)&&!wizardBusy\)/);assert.match(fs.readFileSync('plataforma/static/fluxo.js','utf8'),/if\(n===2&&transcriptionBlocked\(\)&&!wizardBusy\)/);});
const dropCode=src.slice(src.indexOf('function sourceDropFiles('),src.indexOf('document.addEventListener(\'dragover\''));
test('Finder file drop reads FileList',()=>{const c={wizardCurrent:1,wizardBusy:false,Array};vm.createContext(c);vm.runInContext(dropCode,c);const f={name:'VSL.mp4'};assert.equal(c.sourceDropFiles({files:[f]})[0],f);});
test('drop falls back to file items when FileList is empty',()=>{const c={};vm.createContext(c);vm.runInContext(dropCode,c);const f={name:'VSL.mov'};assert.equal(c.sourceDropFiles({files:[],items:[{kind:'file',getAsFile:()=>f}]})[0],f);assert.equal(c.sourceDropFiles({items:[{kind:'string'}]}).length,0);});
test('drop handling is scoped to source stages and idle state',()=>{const c={wizardCurrent:2,wizardBusy:false};vm.createContext(c);vm.runInContext(dropCode,c);assert.equal(c.sourceDropAllowed(),true);c.wizardCurrent=7;assert.equal(c.sourceDropAllowed(),false);c.wizardCurrent=1;c.wizardBusy=true;assert.equal(c.sourceDropAllowed(),false);});
test('visual refresh retains the selected-file label',()=>assert.match(fs.readFileSync('plataforma/static/studio.js','utf8'),/id="fname" role="status"/));
function dropFixture(){
 const listeners=new Map(),events=[],nodes={};const $=id=>id==='fname'?null:(nodes[id]??={textContent:'',disabled:true,hidden:false,value:'',files:[],classList:{add(){},remove(){},toggle(){}}});
 const c={file:null,wizardReady:false,wizardBusy:false,wizardCurrent:1,$,updateWizard:()=>c.syncTranscriptionFile(),document:{querySelectorAll:()=>[],addEventListener:(name,fn)=>listeners.set(name,fn),dispatchEvent:e=>events.push(e.type)},CustomEvent:class{constructor(type){this.type=type;}}};
 vm.createContext(c);vm.runInContext(src.slice(src.indexOf('function transcriptionBlocked(){'),src.indexOf('const fmt=ms=>')),c);return {c,nodes,listeners,events};
}
test('drop anywhere in source step selects the video and emits one selection event without changing the stage',()=>{const f=dropFixture(),video={name:'Finder VSL.mp4',size:5000};let prevented=false;f.listeners.get('drop')({dataTransfer:{files:[video]},preventDefault(){prevented=true;},stopImmediatePropagation(){}});assert.equal(prevented,true);assert.equal(f.c.file,video);assert.equal(f.c.wizardCurrent,1);assert.equal(f.c.transcriptionConfirmed,false);assert.equal(f.nodes.go.disabled,false);assert.deepEqual(f.events,['ripagem:source-selected']);assert.match(f.nodes['wizard-chosen'].textContent,/Finder VSL/);});
test('empty drop produces an explanation instead of silently ignoring it',()=>{const f=dropFixture();f.listeners.get('drop')({dataTransfer:{files:[]},preventDefault(){},stopImmediatePropagation(){}});assert.equal(f.c.file,null);assert.match(f.nodes['wizard-error'].textContent,/Não recebi um arquivo/);assert.equal(f.events.length,0);});
test('a new drop cannot replace the source during transcription',()=>{const f=dropFixture();f.c.file={name:'active.mp4',size:1000};f.c.wizardBusy=true;f.listeners.get('drop')({dataTransfer:{files:[{name:'new.mp4',size:500}]},preventDefault(){},stopImmediatePropagation(){}});assert.equal(f.c.file.name,'active.mp4');assert.equal(f.events.length,0);});

test('selection event never advances automatically to transcription',()=>{const flow=fs.readFileSync('plataforma/static/fluxo.js','utf8');const handler=flow.match(/document.addEventListener\('ripagem:source-selected',([^\n]+)/)[1];assert.doesNotMatch(handler,/go\(2\)/);assert.match(flow,/n===2&&!transcriptionConfirmed/);});
test('only Continue confirms the selected source for transcription',()=>{assert.match(src,/if\(n===2\)transcriptionConfirmed=true/);assert.match(src,/transcriptionConfirmed=false;wizardReady=false/);});

test('a reopened project with no product mentions still loads its saved plan',()=>{
 const render=src.slice(src.indexOf('function renderFrases('),src.indexOf('const useAlt='));
 const nodes={prod2:{value:'SizeFix'}},calls=[];
 const c={FR:[],window:{loadSwapPlan:rebuild=>calls.push(rebuild)},$:id=>nodes[id]??={classList:{remove(){},toggle(){}}}};
 vm.createContext(c);
 vm.runInContext(render,c);
 c.renderFrases([], '', 'SizeFix', null, null, false);
 assert.deepEqual(calls,[false]);
 assert.match(src,/renderFrases\(s\.frases,[^\n]+s\.metricas,false\)/);
});
