/* Correção de uma gravação no próprio trecho, sem reenviar o lote. */
(() => {
 const U=window.SwapUX,$=id=>document.getElementById(id);if(!U)return;
 function mount(){
  if(!U.plan)return;
  document.querySelectorAll('[data-swap-row]').forEach(card=>{
   const row=U.plan.itens.find(r=>r.id===card.dataset.swapRow);
   if(!row?.audio?.raw||card.querySelector('[data-regenerate-one]'))return;
   const area=document.createElement('section');area.className='audio-regenerate';
   area.innerHTML='<button type="button" class="ghost" data-regenerate-one data-swap-lock>Regenerar áudio</button><p class="meta" data-regenerate-result role="status"></p><div class="audio-regenerate-confirm" hidden><strong>Refazer somente esta gravação</strong><p class="meta" data-regenerate-info></p><p class="meta">Pode consumir novos créditos. A gravação anterior fica no histórico. A nova gravação precisará ser ouvida e aprovada; a entrega anterior deve ser atualizada.</p><label class="audio-regenerate-consent"><input type="checkbox" data-regenerate-send> Autorizo enviar esta frase ao serviço e consumir os créditos desta tentativa.</label><label class="audio-regenerate-consent" data-regenerate-clone-label><input type="checkbox" data-regenerate-clone> Tenho autorização para clonar este speaker; ouvi e confirmei a amostra configurada.</label><div class="links"><button type="button" data-regenerate-confirm data-swap-lock>Regenerar esta frase</button><button type="button" class="ghost" data-regenerate-cancel>Cancelar</button></div><p class="meta" data-regenerate-status role="status"></p></div>';
   const originalUpload=card.querySelector('[data-swap-upload]')?.closest('details');
   if(originalUpload)originalUpload.before(area);else card.append(area);
   const q=s=>area.querySelector(s),panel=q('.audio-regenerate-confirm'),status=q('[data-regenerate-status]');
   q('[data-regenerate-one]').disabled=U.busy;
   q('[data-regenerate-one]').onclick=()=>{
    if(U.busy)return;
    panel.hidden=!panel.hidden;if(panel.hidden)return;
    const speaker=card.querySelector('[data-swap-speaker]').value;
    const voice=[...document.querySelectorAll('[data-swap-voice]')].find(i=>i.dataset.swapVoice===speaker)?.value.trim();
    const provider=$('swap-provider').selectedOptions[0]?.textContent||'serviço selecionado',model=$('swap-model').selectedOptions[0]?.textContent||'';
    q('[data-regenerate-info]').textContent=provider+' · '+model+' · Speaker '+speaker+' · '+card.querySelector('[data-swap-text]').value.length+' caracteres. Usa o texto atual e a voz configurada para este speaker.';
    q('[data-regenerate-clone-label]').hidden=!!voice;
    q('[data-regenerate-send]').checked=false;q('[data-regenerate-clone]').checked=false;
    status.textContent='';q('[data-regenerate-send]').focus({preventScroll:true});
   };
   q('[data-regenerate-cancel]').onclick=()=>{panel.hidden=true;};
   q('[data-regenerate-confirm]').onclick=async()=>{
    if(U.busy)return;const button=q('[data-regenerate-confirm]');button.disabled=true;
    status.textContent='Salvando e preparando somente esta frase…';
    try{
     const send=q('[data-regenerate-send]').checked,clone=q('[data-regenerate-clone]').checked;
     if(!send)throw Error('Marque a autorização para regenerar esta frase.');
     await U.regenerateOne(row.id,{autoriza_envio:send,autoriza_clonagem:clone});
     status.textContent='Regenerando esta frase. As demais gravações serão preservadas.';
    }catch(error){status.textContent=error.message;const live=[...document.querySelectorAll('[data-swap-row]')].find(c=>c.dataset.swapRow===row.id)?.querySelector('[data-regenerate-result]');if(live)live.textContent=error.message;}
    finally{button.disabled=U.busy;}
   };
  });
 }
 document.addEventListener('swap:render',mount);
 document.addEventListener('swap:finished',e=>{
  if(e.detail.origin!=='audio-regenerate')return;
  mount();const row=U.plan?.itens.find(r=>r.id===e.detail.rowId);if(!row)return;
  document.querySelector('[data-filter="all"]')?.click();
  [...document.querySelectorAll('[data-ux-row]')].find(b=>b.dataset.uxRow===row.id)?.click();
  const card=[...document.querySelectorAll('[data-swap-row]')].find(c=>c.dataset.swapRow===row.id);
  const result=card?.querySelector('[data-regenerate-result]');if(!result)return;
  const succeeded=e.detail.status==='concluido'&&row.audio?.raw&&row.audio.raw!==e.detail.previousRaw;
  result.textContent=succeeded?'Nova gravação salva. Ouça e aprove este áudio antes de atualizar a entrega.':'A nova gravação não foi concluída. A gravação anterior foi preservada; confira o aviso da geração e tente novamente.';
 });
 mount();
})();
