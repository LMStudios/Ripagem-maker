/* Avança após ações explícitas confirmadas; navegar nunca gera áudio pago. */
(()=>{
 const U=window.SwapUX,$=id=>document.getElementById(id);if(!U)return;
 const primary=document.createElement('div');primary.className='card';primary.innerHTML='<button id="flow-approve-texts">Aprovar textos e ir para gerar áudios</button><p id="flow-speech-message" role="status" class="meta"></p>';$('speech-texts').closest('nav').after(primary);
 let stage=1,working=false,previous=new Map(),scope='';
 const formPanel=document.querySelector('.product-form');let advancedForm;
 if(formPanel){advancedForm=document.createElement('section');advancedForm.className='practical-form';advancedForm.innerHTML='<header><div><h3>Forma e modo de uso</h3><p id="practical-form-summary" class="meta"></p></div><button class="ghost" id="practical-form-toggle" aria-expanded="false">Configurar adaptação</button></header>';formPanel.before(advancedForm);advancedForm.append(formPanel);formPanel.hidden=true;document.getElementById('practical-form-toggle').onclick=e=>{formPanel.hidden=!formPanel.hidden;e.target.setAttribute('aria-expanded',String(!formPanel.hidden));e.target.textContent=formPanel.hidden?'Configurar adaptação':'Recolher configuração';};}
 const warning=document.createElement('p');warning.id='flow-change-warning';warning.className='meta';warning.setAttribute('role','status');primary.after(warning);
 const message=text=>{$('flow-speech-message').textContent=text;};
 const selected=()=>U.plan?.itens.filter(r=>r.aprovado)||[];
 function state(){
  stage=$('speech-generate').getAttribute('aria-current')==='step'?2:$('speech-listen').getAttribute('aria-current')==='step'?3:1;
  primary.hidden=stage!==1;const b=$('flow-approve-texts');b.disabled=working||U.busy||!U.plan;
  $('swap-approve-all-audio').hidden=stage!==3;
  document.querySelector('[data-w-next="4"]').hidden=true;
  if(advancedForm){advancedForm.hidden=stage!==1;const c=U.plan?.forma,rows=U.plan?.itens||[];document.getElementById('practical-form-summary').textContent=c?.ativo?c.origem+' → '+c.destino+' · '+rows.filter(r=>r.forma_detectada).length+' frases · '+rows.filter(r=>r.forma_pendente&&!r.forma_confirmada).length+' pendentes':'Sem adaptação de forma · configure para trocar patch, gotas, cápsulas ou pó.';}
  document.querySelectorAll('[data-swap-text]').forEach(e=>e.readOnly=stage===3);
  document.querySelectorAll('[data-swap-speaker],[data-swap-approve]').forEach(e=>e.disabled=U.busy||stage===3);
  if(stage===2&&selected().some(r=>!r.audio?.fit)){$('voice-settings').open=true;$('voice-next').hidden=true;}
  const buttons=['swap-all','swap-none'];buttons.forEach(id=>{const b=$(id);if(b){b.classList.add('ghost');b.hidden=stage!==1;}});
 }
 async function texts(){
  if(working||U.busy)return;working=true;state();message('Salvando textos…');
  try{
   if(await U.flushDraft()===false||U.hasDraft())throw Error('Não foi possível salvar. Resolva o aviso de salvamento antes de continuar.');
   const chosen=U.capture().filter(r=>r.aprovado);
   const unresolved=U.plan.itens.filter(r=>r.mencoes_revisar?.length&&!r.mencao_descartada&&!chosen.some(c=>c.id===r.id));
   if(unresolved.length){
    document.querySelector('[data-filter="issues"]')?.click();
    throw Error(`Confira ${unresolved.length} menção(ões) provável(is) em Erros e alertas. Aprove a frase ou descarte a sugestão para continuar.`);
   }
   if(!chosen.length)throw Error('Selecione pelo menos um texto para continuar.');
   if(chosen.some(r=>{const base=U.plan.itens.find(i=>i.id===r.id);return base?.forma_pendente&&!base.forma_confirmada;}))throw Error('Há frases com modo de uso pendente. Informe a orientação correta ou reescreva e confirme cada adaptação.');
   if(chosen.some(r=>!r.novo.trim()||!r.speaker))throw Error('Preencha o texto e o speaker de todas as frases selecionadas.');
   await U.save();U.render();message('Textos salvos. Prepare as vozes e autorize a geração na próxima etapa.');$('speech-generate').click();
  }catch(e){message(e.message);}finally{working=false;state();}
 }
 $('flow-approve-texts').onclick=texts;
 // A aprovação de todos os textos também salva antes de avançar.
 const approveAll=$('swap-all').onclick;
 $('swap-all').onclick=async()=>{approveAll?.();await Promise.resolve();await texts();};
 const manualSave=$('swap-save').onclick;$('swap-save').onclick=async()=>{await manualSave?.();if(!U.hasDraft()&&selected().length&&stage===1)$('speech-generate').click();};
 async function audioDone(){
  const rows=selected();if(U.busy||!rows.length)return;
  if(rows.every(r=>r.audio?.fit&&r.audio.aprovado)){
   if(await U.flushDraft()===false||U.hasDraft())return;
   document.querySelector('[data-flow-step="4"]').click();
  }
 }
 document.addEventListener('swap:audio-approved',audioDone);
 document.addEventListener('swap:finished',e=>{if(e.detail.status==='concluido'&&e.detail.kind==='vozes'&&!['audio-import','audio-regenerate'].includes(e.detail.origin)){if(selected().some(r=>!r.audio?.fit))$('speech-generate').click();else $('speech-listen').click();}});
 document.addEventListener('swap:state',state);document.addEventListener('swap:render',()=>{
  if(scope!==folder){scope=folder;previous=new Map();warning.textContent='';}
  const invalid=(U.plan?.itens||[]).filter(r=>previous.get(r.id)&&!r.audio?.fit);
  if(!invalid.length&&(U.plan?.itens||[]).every(r=>!r.aprovado||r.audio?.fit))warning.textContent='';
  if(invalid.length)warning.textContent=invalid.length+' fala(s) foram alteradas. Os áudios correspondentes precisam ser gerados novamente; a montagem anterior deve ser atualizada. Os outros áudios foram preservados.';
  previous=new Map((U.plan?.itens||[]).map(r=>[r.id,!!r.audio?.fit]));state();
 });
 for(const id of ['speech-texts','speech-generate','speech-listen'])$(id).addEventListener('click',state);
 // Configurações de chave saem do fluxo de geração e ficam centralizadas em Ajustes.
 for(const id of ['swap-key','swap-connect','swap-forget']){const el=$(id);if(el)el.closest(id==='swap-key'?'label':'.links').hidden=true;}
 const keyLink=document.createElement('a');keyLink.href='/#/ajustes';keyLink.textContent='Configurar APIs e testar conexão em Ajustes';$('swap-key-status').after(keyLink);
 const checkKey=async()=>{try{const d=await U.call('chave-status');$('swap-key-status').textContent=d.configurados.includes($('swap-provider').value)?'Chave configurada neste computador. Permanece após fechar o app.':'Chave não configurada. Abra Ajustes → Integrações e APIs.';}catch(e){$('swap-key-status').textContent=e.message;}};
 $('swap-provider').addEventListener('change',checkKey);checkKey();
 state();
})();
