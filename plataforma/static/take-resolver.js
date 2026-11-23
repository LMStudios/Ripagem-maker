/* Pendências de takes com resolução explícita; nunca infere kit por preço. */
(()=>{
 const V=window.VisualUX,$=id=>document.getElementById(id);if(!V||!$('studio-take-options'))return;
 const options=$('studio-take-options'),mode=$('visual-mode');let scope='',draft=false,lastRender='';
 const label=document.createElement('label');label.innerHTML='Takes para falas sem quantidade<select id="visual-default-kit"><option value="">Sortear todos os takes de produto</option></select>';options.append(label);
 const help=document.createElement('p');help.className='meta';help.textContent='Sem quantidade na fala, sorteia entre os takes de Produto, sem repetir em sequência. Se preferir, limite a um kit. Menções explícitas mantêm o kit correspondente.';options.append(help);
 const modeHelp=document.createElement('p');modeHelp.className='meta';mode.closest('label').after(modeHelp);
 const retry=document.createElement('button');retry.type='button';retry.textContent='Aplicar ajustes e preparar novamente';options.append(retry);
 const status=document.createElement('p');status.className='meta';status.setAttribute('role','status');options.append(status);
 const policyNote=document.createElement('p');policyNote.className='meta';$('visual-summary').before(policyNote);const box=document.createElement('section');box.id='studio-take-issues';box.hidden=true;box.setAttribute('aria-live','polite');$('visual-error').before(box);
 const intervalReview=document.createElement('details');intervalReview.className='card';intervalReview.hidden=true;
 $('visual-summary').after(intervalReview);
 function reviewIntervals(s){
  const rows=s.revisao_intervalos||[];intervalReview.hidden=!rows.length;if(!rows.length)return;
  intervalReview.replaceChildren();
  const summary=document.createElement('summary');summary.textContent='Revisar '+rows.length+' intervalos · vídeos completos';intervalReview.append(summary);
  const help=document.createElement('p');help.className='meta';help.textContent='Tempos da montagem final, com as margens de áudio removidas. Intervalos próximos foram reunidos para manter os vídeos inteiros; os kits indicados nas falas foram respeitados.';intervalReview.append(help);
  const table=document.createElement('table');table.style.width='100%';
  const header=table.insertRow();for(const label of ['Cobertura inicial','Intervalo ajustado','Kit','Situação'])header.insertCell().textContent=label;
  const clock=frame=>{const seconds=frame/s.fps;return Math.floor(seconds/60)+':'+(seconds%60).toFixed(2).padStart(5,'0');};
  for(const r of rows){
   const tr=table.insertRow();const pending=(s.issues||[]).some(i=>i.mention===r.mention);
   for(const value of [clock(r.inicio_original_frame)+' – '+clock(r.fim_original_frame),clock(r.inicio_frame)+' – '+clock(r.fim_frame),r.kit||'Sortido',pending?'Revisar duração':(s.manual_markers||[]).some(m=>m.id===r.mention)?'Ajuste manual autorizado':'Preparado'])tr.insertCell().textContent=value;
   if(pending)tr.style.color='var(--err)';
  }
  intervalReview.append(table);
 }
 const select=$('visual-default-kit');
 function changed(){draft=true;$('visual-max').dispatchEvent(new Event('input'));status.textContent='Sorteio alterado. Clique em Aplicar ajustes e preparar novamente.';}
 select.onchange=changed;
 async function prepare(){if(V.busy)return;status.textContent='Aplicando as escolhas…';try{await V.automatic();}catch(e){status.textContent=e.message;}}
 retry.onclick=prepare;
 function detail(){$('visual-extend').closest('label').hidden=mode.value!=='inteiro';modeHelp.textContent=mode.value==='encaixar'?'Mantém os arquivos originais inteiros no disco e ajusta a duração do último take somente na timeline. Vídeos continuam em movimento e na velocidade natural.':mode.value==='inteiro'?'Usa cada take do início ao fim. Ao permitir o ajuste, reúne intervalos compatíveis e antecipa ou estende a cobertura após a primeira menção. Confira os tempos em Revisar intervalos.':'Compatibilidade: permite recortes preparados e imagens estáticas.';}
 mode.addEventListener('change',detail);detail();
 function code(issue){return issue.code||(issue.error?.includes('genérico')?'generico':issue.error?.includes('combinação de vídeos completos')?'duracao':'outros');}
 function time(ms){const n=Math.max(0,Math.round((ms||0)/1000));return Math.floor(n/60)+':'+String(n%60).padStart(2,'0');}
 function openSettings(){document.getElementById('practical-take-config')?.setAttribute('open','');options.open=true;options.scrollIntoView({block:'center',behavior:'smooth'});select.focus({preventScroll:true});}
 function render(){
  const s=V.state;if(!s)return;reviewIntervals(s);const renderKey=JSON.stringify([folder,V.busy,draft,select.value,s.issues,s.manual_markers,s.fallbacks,s.kit_sem_quantidade,s.modo_takes,s.prepared?.signature,s.coverage_policy,s.assets.map(a=>[a.id,a.kit,a.uso,a.kind])]);if(renderKey===lastRender)return;lastRender=renderKey;policyNote.textContent=!s.cobrir_falas?'':s.coverage_policy?.escopo==='somente_valores'?'Otimização: takes apenas nos trechos de preços e kits selecionados. O nome e o modo de uso do produto são preservados; não é necessário localizar a primeira menção.':s.coverage_policy?.primeira_mencao_ms==null?'Primeira menção ao produto não localizada: trechos ficam só marcados para adaptação, sem potes automáticos.':'Potes somente a partir de '+time(s.coverage_policy.primeira_mencao_ms)+'. Antes disso, os trechos ficam marcados para adaptar o modo de uso.';if(scope!==folder){scope=folder;draft=false;status.textContent='';}
  const current=draft?select.value:String(s.kit_sem_quantidade||'');const kits=[...new Set(s.assets.filter(a=>a.kind==='video'&&a.kit).map(a=>a.kit))].sort((a,b)=>a-b);
  select.replaceChildren(new Option('Sortear todos os takes de produto',''),...kits.map(k=>new Option('Kit '+k+' pote(s)',String(k))));if(current&&!kits.includes(Number(current)))select.add(new Option('Kit '+current+' · sem vídeo disponível',current));select.value=current;
  if(String(s.kit_sem_quantidade||'')===current)draft=false;select.disabled=V.busy;retry.disabled=V.busy;if(!V.busy&&!draft)status.textContent=s.prepared?'Ajustes aplicados. Takes preparados.':s.issues?.length?'Resolva as pendências abaixo e prepare novamente.':'';detail();
  const issues=s.issues||[];box.hidden=!issues.length&&!s.fallbacks?.length&&!s.manual_markers?.length;document.body.classList.toggle('studio-take-issues-active',!!issues.length);box.replaceChildren();
  const raw=$('visual-error'),text=raw.textContent||'';raw.hidden=!!issues.length&&(text.startsWith('Há menções sem takes suficientes:')||issues.some(i=>text.includes(i.error)));
  if(s.manual_markers?.length){const n=document.createElement('p');n.className='meta';n.textContent=s.manual_markers.length+' ponto(s) ficarão marcados para ajuste manual no Premiere. Os demais takes estão preservados.';box.append(n);}
  if(!issues.length){if(s.fallbacks?.length){const note=document.createElement('p');note.className='meta';note.textContent=s.fallbacks.length+' janela(s) usam potes aleatórios autorizados por você. Confira a quantidade mostrada; a detecção original foi mantida.';box.append(note);}return;}
  const heading=document.createElement('h3');heading.textContent='Ajustes para preparar os takes';box.append(heading);
  const fallback=document.createElement('div');fallback.className='studio-take-issue';
  const warning=document.createElement('p');warning.className='meta';warning.textContent='Não há takes compatíveis para todas as janelas. Você pode autorizar vídeos aleatórios de Produto, de qualquer kit, somente nas pendências. A quantidade exibida pode ser diferente da fala: confira a detecção antes de entregar. Apoio e depoimentos ficam fora do sorteio. Os takes já resolvidos serão preservados.';fallback.append(warning);
  const randomButton=document.createElement('button');randomButton.type='button';randomButton.textContent='Preencher pendências com potes aleatórios';randomButton.disabled=V.busy||s.modo_takes==='recortes'||!s.assets.some(a=>a.kind==='video'&&a.uso==='produto');randomButton.onclick=async()=>{if(V.busy)return;await V.action(async()=>{await V.save();V.start(await V.post('preencher-aleatorio',{autorizado:true,mentions:issues.map(i=>i.mention)}));});};fallback.append(randomButton);
  if(s.modo_takes==='recortes'){const note=document.createElement('p');note.className='meta';note.textContent='Escolha Vídeos originais em Encaixe e compatibilidade para usar este preenchimento.';fallback.append(note);}box.append(fallback);
  const groups=new Map();for(const i of issues){const k=code(i);if(!groups.has(k))groups.set(k,[]);groups.get(k).push(i);}
  for(const [type,items] of groups){
   const card=document.createElement('div');card.className='studio-take-issue';const title=document.createElement('strong'),description=document.createElement('p');description.className='meta';card.append(title,description);
   const button=(text,fn,primary=false)=>{const b=document.createElement('button');b.type='button';b.className=primary?'':'ghost';b.textContent=text;b.disabled=V.busy;b.onclick=fn;card.append(b);};
   if(type==='duracao'){
    title.textContent=items.length+' janela(s) sem encaixe para vídeos inteiros';description.textContent='Você pode usar as mídias originais e ajustar a duração do último take na timeline, ou ampliar a janela para manter o vídeo inteiro.';
    if(!s.ajustar_janela)button('Manter vídeos completos · ampliar intervalos',async()=>{$('visual-extend').checked=true;$('visual-extend').dispatchEvent(new Event('change'));await prepare();},true);
    button('Encaixar na fala · usar mídias originais',async()=>{mode.value='encaixar';mode.dispatchEvent(new Event('change'));await prepare();});
    button('Marcar estes pontos para ajuste manual no Premiere',async()=>{if(!confirm('Estes pontos ficarão sem cobertura automática e serão marcados no XML para você ajustar no Premiere. Os demais takes serão mantidos. Continuar?'))return;await V.action(async()=>{await V.post('marcar-manual',{autorizado:true,mentions:items.map(i=>i.mention)});await V.refresh();});});
    button('Manter vídeo inteiro: ajustar janela',()=>{options.open=true;$('visual-extend').focus();options.scrollIntoView({block:'center'});});
   }else if(type==='generico'){
    title.textContent=items.length+' fala(s) sem quantidade de potes';description.textContent='O sorteio usa vídeos classificados como Produto, de qualquer kit. Classifique os takes corretos como Produto ou escolha um kit específico.';
    button('Configurar sorteio',openSettings,true);button('Conferir associação dos materiais',()=>{const d=$('visual-assets').querySelector('details');if(d)d.open=true;document.getElementById('practical-take-config')?.setAttribute('open','');$('visual-assets').scrollIntoView({block:'start'});});
   }else if(type==='variedade'){
    title.textContent='Falta variedade para completar '+items.length+' janela(s)';description.textContent='Adicione outro vídeo deste kit para preencher o intervalo sem repetir o mesmo material em sequência.';button('Conferir materiais',()=>{$('visual-assets').querySelector('details')?.setAttribute('open','');document.getElementById('practical-take-config')?.setAttribute('open','');$('visual-assets').scrollIntoView({block:'start'});});
   }else{
    title.textContent='Conferir materiais de '+items.length+' janela(s)';description.textContent=items[0].error;button('Conferir materiais e kits',()=>{$('visual-assets').querySelector('details')?.setAttribute('open','');document.getElementById('practical-take-config')?.setAttribute('open','');$('visual-assets').scrollIntoView({block:'start'});});
   }
   const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='Ver janelas afetadas ('+items.length+')';details.append(summary);
   items.forEach(i=>{const row=[...(s.mentions||[]),...(s.coverage_mentions||[])].find(r=>r.id===i.mention);const p=document.createElement('p');p.className='meta';p.textContent=time(i.inicio_ms??row?.start)+'–'+time(i.fim_ms??row?.end)+(i.kit?' · Kit '+i.kit:'');details.append(p);});card.append(details);box.append(card);
  }
 }
 document.addEventListener('visual:render',render);document.addEventListener('visual:state',render);
 new MutationObserver(()=>{const s=V.state,raw=$('visual-error'),text=raw.textContent||'';raw.hidden=!!s?.issues?.length&&(text.startsWith('Há menções sem takes suficientes:')||s.issues.some(i=>text.includes(i.error)));}).observe($('visual-error'),{childList:true,subtree:true,characterData:true});
 render();
})();
