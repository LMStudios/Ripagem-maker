const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const Draft=require('../plataforma/static/visual-draft.js');
const state={assets:[{id:'asset',kit:1,uso:'produto'}],mentions:[{id:'old',kit:2,start:100,end:500,selected:true}]};
const capture=()=>({root:'/takes',ajustar_janela:true,assets:[{id:'asset',kit:'1',uso:'produto'}],mentions:[{id:'old',kit:'2',start:100,end:500,selected:true}]});
test('plano recalculado não recebe IDs antigos que não foram editados',()=>{const r=Draft.changes(state,capture());assert.equal(r.mentions.length,0);assert.equal(r.assets.length,0);assert.equal(r.ajustar_janela,true)});
test('alterações de associação, tempo e seleção continuam sendo enviadas',()=>{const d=capture();d.assets[0].kit='3';d.mentions[0].end=700;const r=Draft.changes(state,d);assert.equal(r.assets.length,1);assert.equal(r.mentions.length,1);assert.equal(r.mentions[0].end,700)});
test('salvar renova a lista recalculada e preserva a pasta recém-escolhida',async()=>{
 const source=fs.readFileSync('plataforma/static/visuais.js','utf8');const code=source.slice(source.indexOf('  async function save(){'),source.indexOf('  function changed(){'));
 const field={value:'/new/takes'};let renders=0;const c={state:structuredClone(state),capture:()=>({...capture(),root:'/new/takes'}),window:{VisualDraft:Draft},post:async(action,body)=>{assert.equal(body.mentions.length,0);return {assets:state.assets,mentions:[{id:'new'}]}},render:()=>{renders++;field.value='/old/takes'},el:()=>field,ready(){},dirty:true};vm.createContext(c);vm.runInContext(code,c);await c.save();assert.equal(renders,1);assert.equal(field.value,'/new/takes');assert.equal(c.state.mentions[0].id,'new');assert.equal(c.dirty,false)
});
test('erro da entrega atualiza os takes e mantém a mensagem do job',async()=>{
 const source=fs.readFileSync('plataforma/static/fluxo.js','utf8');const code=source.slice(source.indexOf(' async function focusMention('),source.indexOf(" $('flow-quick-cancel').onclick"));const nodes={};let refreshed=0;
 const c={quickJob:'job',fetch:async()=>({json:async()=>({status:'erro',step:'Erro',error:'Vídeo não cabe'})}),$:id=>nodes[id]??={textContent:'',hidden:false,removeAttribute(){}},sessionStorage:{removeItem(){}},V:{refresh:async()=>refreshed++},sync(){},document:{addEventListener(){}},setTimeout(){throw Error('Não deve ficar consultando tarefa concluída')}};vm.createContext(c);vm.runInContext(code,c);await c.pollQuick();assert.equal(refreshed,1);assert.equal(c.quickJob,null);assert.equal(nodes['flow-quick-error'].textContent,'Vídeo não cabe')
});

test('quick XML brings a pending product mention to the exact speech or recovery review',async()=>{
 const source=fs.readFileSync('plataforma/static/fluxo.js','utf8');
 const code=source.slice(source.indexOf(' async function focusMention('),source.indexOf(" $('flow-quick-cancel').onclick"));
 const mention={status:'fora_da_selecao',id_fala:'old-1',inicio_ms:2537000,fim_ms:2537400};
 const nodes={},actions=[];
 const c={
  quickJob:'job',current:4,
  fetch:async()=>({json:async()=>({status:'erro',step:'Erro',error:'Há uma menção pendente.',acao_erro:{tipo:'revisar_mencao',trecho:mention}})}),
  $:id=>nodes[id]??={textContent:'',hidden:false,removeAttribute(){},click(){actions.push(id)}},
  sessionStorage:{removeItem(){}},V:{refresh:async()=>{}},sync(){},
  async go(step){actions.push(step);this.current=step},
  CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail}},
  document:{addEventListener(){},dispatchEvent(event){actions.push(event);return !event.detail.id_fala}},
  setTimeout(){throw Error('Não deve ficar consultando tarefa concluída')}
 };
 vm.createContext(c);vm.runInContext(code,c);vm.runInContext('go=async step=>{current=step}',c);
 await c.pollQuick();
 const button=nodes['flow-quick-review-mention'];
 assert.equal(button.hidden,false);
 assert.equal(nodes['flow-quick-review-xml'].hidden,false);
 await button.onclick();
 assert.equal(c.current,3);
 assert.deepEqual(actions.map(e=>e.type),['mentions:focus-speech']);
 assert.equal(actions[0].detail,mention);
 actions.length=0;
 c.showQuickError('Fala ausente',{tipo:'revisar_mencao',trecho:{...mention,id_fala:null}});
 await button.onclick();
 assert.equal(actions[0],'speech-texts');
 assert.equal(actions[1].type,'mentions:open-review');
 assert.equal(actions[1].detail.inicio_ms,2537000);
 c.showQuickError('Vídeo não cabe');
 assert.equal(button.hidden,true);
 assert.equal(nodes['flow-quick-review-xml'].hidden,true);
 assert.equal(button.onclick,null);
});
