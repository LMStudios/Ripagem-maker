const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{test}=require('node:test');
const naming=fs.readFileSync('plataforma/static/entrega-identidade.js','utf8');
const capture=naming.slice(naming.indexOf(' function capture(){'),naming.indexOf(' function preview(){'));
test('filename pitch accepts underscore and persists normalized form',()=>{
 const scope={config:{numero_vsl:'3',pitch_manual:'52_22'},persist(){},render(){}};vm.createContext(scope);vm.runInContext(capture,scope);
 assert.equal(scope.capture().pitch_manual,'52:22');assert.equal(scope.config.pitch_manual,'52:22');
});
test('invalid pitch still rejects invalid seconds',()=>{
 const scope={config:{numero_vsl:'3',pitch_manual:'52_99'},persist(){},render(){}};vm.createContext(scope);vm.runInContext(capture,scope);
 assert.throws(()=>scope.capture(),/Pitch manual/);
});
test('transcription validation stays in its current step and never uploads',async()=>{
 const html=fs.readFileSync('index.html','utf8');const handler=html.slice(html.indexOf('async function startTranscription('),html.indexOf('let misses=0;'));
 const nodes=new Map();const scope={wizardBusy:false,$:id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',hidden:true,scrollIntoView(){}});return nodes.get(id);},file:{name:'video.mp4'},window:{RipagemNaming:{capture(){throw Error('Pitch manual inválido');}}},wizardStep(){throw Error('Must not jump to first step');},XMLHttpRequest(){throw Error('Must not upload invalid metadata');}};
 vm.createContext(scope);vm.runInContext(handler,scope);await nodes.get('go').onclick();
 assert.equal(nodes.get('transcription-naming-error').hidden,false);assert.match(nodes.get('transcription-naming-error').textContent,/Pitch manual inválido/);assert.equal(nodes.get('transcription-naming-fix').hidden,false);
});

test('a entrada guiada mantém a correção de nomenclatura junto ao botão de início', () => {
 const guided = fs.readFileSync('plataforma/static/fluxo-guiado.js', 'utf8');
 const code = guided.slice(guided.indexOf('  const launch ='), guided.indexOf("  start.textContent ="));
 const added = [];
 const scope = {start: 'início', saveTo: 'destino', advanced: 'opções', byId: id => id,
   block: () => ({append: (...children) => added.push(...children)}), upload: {append() {}}};
 vm.runInNewContext(code, scope);
 assert.deepEqual(added, ['início', 'transcription-naming-error', 'transcription-naming-fix', 'destino']);
});

test('corrigir identificação revela as opções recolhidas e focaliza o campo inválido', async () => {
 const html = fs.readFileSync('index.html', 'utf8');
 const handler = html.slice(html.indexOf('namingFix.onclick = async'), html.indexOf('const OFF='));
 const advanced = {tagName: 'DETAILS', open: false, parentElement: null};
 const naming = {tagName: 'DETAILS', open: false, parentElement: advanced};
 const manual = {tagName: 'DETAILS', open: false, parentElement: naming};
 let focused;
 const field = (id, parentElement) => ({parentElement, focus() { focused = id; }, scrollIntoView() {}});
 const nodes = {'delivery-number-setup': field('vsl', naming), 'delivery-pitch-setup': field('pitch', manual)};
 const scope = {namingError: {textContent: 'Pitch manual inválido'}, namingFix: {}, $: id => nodes[id],
   wizardStep: step => assert.equal(step, 1)};
 vm.runInNewContext(handler, scope);
 await scope.namingFix.onclick();
 assert.equal(focused, 'pitch');
 assert.ok(manual.open && naming.open && advanced.open);
 scope.namingError.textContent = 'Número da VSL: use um valor entre 1 e 999.';
 await scope.namingFix.onclick();
 assert.equal(focused, 'vsl');
});
