/* Camada de fluxo: revisão por pendências, salvamento local e entrega única. */
(() => {
 const U=window.SwapUX,$=id=>document.getElementById(id),all=s=>[...document.querySelectorAll(s)],esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 if(!U)return;
 let active='',filter='pending',search='',version=0,timer=null,dirty=false,saving=false,profiles=[],profileDraft=null,saveFlight=null;
 const create=(tag,cls,html)=>{const e=document.createElement(tag);e.className=cls;e.innerHTML=html;return e;};
 const summary=create('section','ux-summary','<div class="ux-summary-top"><strong id="ux-product">Seu trabalho</strong><span id="ux-saved" class="ux-status" role="status">Salvo neste computador</span></div><div id="ux-stats" class="ux-stats"></div><p id="ux-window" class="meta"></p><div class="links"><button class="ghost" id="ux-pending">Resolver pendências</button><button class="ghost" id="ux-goto-voices">Gerar ou corrigir falas</button><button id="ux-deliver">Preparar para Premiere</button></div>');
 $('wizard-slot-3').prepend(summary);
 const tabs=create('div','ux-tabs','<button class="ghost" data-ux-jump="swap-controls">Frases e áudios</button><button class="ghost" data-ux-jump="swap-voices">Vozes e geração</button><button class="ghost" data-ux-jump="visual-choose">Imagens dos potes</button><button class="ghost" data-ux-jump="pcard">Preços e kits</button>');summary.after(tabs);
 const toolbar=create('div','ux-toolbar','<button class="ghost" data-filter="pending">Só pendências</button><button class="ghost" data-filter="issues">Erros e alertas</button><button class="ghost" data-filter="form">Modo de uso</button><button class="ghost" data-filter="fit">Sem áudio pronto</button><button class="ghost" data-filter="listen">Para ouvir</button><button class="ghost" data-filter="approved">Aprovados</button><button class="ghost" data-filter="all">Todos</button><input id="ux-search" type="search" aria-label="Buscar frase" placeholder="Buscar frase…">');
 const moreFilters=create('details','clean-more-filters','<summary>Mais filtros</summary><div></div>');
 for(const key of ['fit','listen','approved'])moreFilters.lastElementChild.append(toolbar.querySelector('[data-filter="'+key+'"]'));
 toolbar.querySelector('#ux-search').before(moreFilters);
 const workspace=create('div','ux-workspace','<nav class="ux-list" id="ux-list" aria-label="Trechos para conferir"></nav><div id="ux-editor"></div>');
 $('flist').before(toolbar,workspace);$('ux-editor').append($('flist'));
 const list = $('ux-list');
 let listMarkup = '', displayedIds = [], listButtons = new Map(), editors = new Map(), openEditor = null;
 $('swap-controls').querySelector('h3').textContent='Revisar frases e áudios';
 $('swap-controls').querySelector('p').textContent='Selecione um trecho na lista. Alterações de texto, speaker e seleção são salvas automaticamente. Ouça o áudio pronto antes de aprovar.';
 const autoStatus=$('ux-saved');const retrySave=create('button','ghost ux-save-retry','Tentar salvar');retrySave.type='button';retrySave.hidden=true;autoStatus.after(retrySave);retrySave.onclick=()=>flush();
 const newgen=create('div','ux-toast','<strong>Corrigir apenas o que falta</strong><p id="ux-retry-estimate" class="meta"></p><button id="ux-retry" data-swap-lock>Gerar somente pendentes</button><p class="meta">Usa o serviço e as autorizações abaixo. Preserva os áudios que já cabem e suas aprovações.</p>');
 $('swap-voices').querySelector('h3').after(newgen);
 function rows(){
  const byId = new Map(U.plan?.itens.map(row => [row.id, row]));
  return U.capture().map((row, index) => {
   const base = byId.get(row.id);
   const fit = !!base.audio?.fit && base.novo === row.novo && base.speaker === row.speaker;
   return {...row, index, base, fit, ok: fit && !!base.audio.aprovado};
  });
 }
 function hasIssue(r){return (r.base.mencoes_revisar?.length&&!r.aprovado&&!r.base.mencao_descartada)||r.base.speaker_pendente||(r.base.forma_pendente&&!r.base.forma_confirmada)||(r.base.audio?.analise?.arquivo===r.base.audio?.fit&&r.base.audio?.analise?.alertas?.length);}
 function stateName(r){return !r.aprovado?(r.base.mencao_descartada?'Sugestão descartada':r.base.mencoes_revisar?.length?'Menção provável · conferir':'Texto não selecionado'):hasIssue(r)?'Revisar alerta':r.base.forma_detectada&&r.fit&&!r.ok?'Conferir modo de uso':r.ok?'Áudio aprovado':r.fit?'Pronto para ouvir':r.base.audio?.status==='regenerar_longo'?'Preparar duração do áudio':r.base.audio?.status==='regenerar_curto'?'Áudio curto demais':'Precisa de geração';}
 function matches(r){return (filter==='all'||filter==='issues'&&hasIssue(r)||filter==='form'&&r.base.forma_detectada||filter==='pending'&&!r.base.mencao_descartada&&(!r.aprovado||!r.ok)||filter==='fit'&&r.aprovado&&!r.fit||filter==='listen'&&r.aprovado&&r.fit&&!r.ok||filter==='approved'&&r.ok)&&(!search||(r.novo+' '+r.base.original+' '+(r.index+1)).toLowerCase().includes(search));}
 function mountPlayers(root){window.RipagemAudio?.mount(root);}

 function showEditor(){
  const nextEditor = editors.get(active);
  if (openEditor && openEditor !== nextEditor) {
   openEditor.hidden = true;
   window.RipagemAudio?.release(openEditor);
  }
  if (nextEditor) {
   nextEditor.hidden = false;
   if ($('fcard').hidden) window.RipagemAudio?.release(nextEditor);
   else mountPlayers(nextEditor);
  }
  openEditor = nextEditor;
 }
 function selectRow(id){
  const target = listButtons.get(id);
  if (!target || active === id) return;
  listButtons.get(active)?.setAttribute('aria-current', 'false');
  active = id;
  target.setAttribute('aria-current', 'true');
  showEditor();
  return target;
 }
 list.addEventListener('click', event => {
  selectRow(event.target.closest('[data-ux-row]')?.dataset.uxRow);
 });
 function stepRow(event){
  const index = displayedIds.indexOf(active);
  const offset = event.key === 'ArrowDown' ? 1 : -1;
  const nextId = displayedIds[index + offset];
  if (!nextId) return;
  event.preventDefault();
  const focusInList = list.contains(document.activeElement);
  const nextButton = selectRow(nextId);
  if (focusInList) nextButton?.focus();
 }

 function refresh(){
  if(!U.plan)return;const rs=rows(),selected=rs.filter(r=>r.aprovado),missing=selected.filter(r=>!r.fit),duration=missing.filter(r=>r.base.audio?.raw),ungenerated=missing.filter(r=>!r.base.audio?.raw),listen=selected.filter(r=>r.fit&&!r.ok),approved=selected.filter(r=>r.ok);
  $('ux-product').textContent=(U.plan.produto||'Produto original')+' → '+(U.plan.produto_novo||$('novo2').value||'Produto novo');
  $('ux-stats').innerHTML=`<span class="ux-stat">${rs.length} trechos</span><span class="ux-stat">${selected.length} textos selecionados</span><span class="ux-stat ${missing.length?'warning':''}">${ungenerated.length} sem áudio</span>${duration.length?`<span class="ux-stat warning">${duration.length} ajustar duração</span>`:''}<span class="ux-stat">${listen.length} para ouvir</span><span class="ux-stat">${approved.length} áudios aprovados</span>`;
  $('ux-deliver').textContent=selected.length&&approved.length===selected.length?'Tudo pronto · ir ao Premiere':'Preparar para Premiere';
  $('ux-retry-estimate').textContent=`${missing.length} frase(s) · ${missing.reduce((n,r)=>n+r.novo.length,0)} caracteres a enviar. Confira os textos e as amostras antes de gerar.`;
  $('ux-retry').disabled=U.busy||!missing.length;const gate=$('ux-voice-gate');if(gate)gate.textContent=!selected.length?'Primeiro selecione os textos que serão gerados na etapa 3.1.':duration.length?duration.length+' áudio(s) já gerados precisam de ajuste de duração. Para aceitar falas maiores, escolha Abrir espaço e aplique sem novos créditos.':missing.length?selected.length+' texto(s) selecionado(s). Prepare as vozes e gere as falas abaixo.':'Os áudios já cabem. Use a etapa 3.3 para ouvir e aprovar; regenere somente se necessário.';
  all('[data-filter]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.filter===filter?'true':'false'));
  const extraFilter=moreFilters.querySelector('[aria-pressed="true"]');
  moreFilters.querySelector('summary').textContent=extraFilter?'Mais filtros · '+extraFilter.textContent:'Mais filtros';
  moreFilters.classList.toggle('has-active-filter',!!extraFilter);
  const visible = rs.filter(matches).sort((a, b) => Number(!!hasIssue(b)) - Number(!!hasIssue(a)) || a.index - b.index);
  displayedIds = visible.map(row => row.id);
  const previous = active;
  if (!displayedIds.includes(active)) active = displayedIds[0] || '';
  const markup = visible.length ? visible.map(row => `<button type="button" title="Arraste um áudio sobre esta frase para importar a gravação" data-ux-row="${esc(row.id)}" aria-current="false"><b>${String(row.index + 1).padStart(2, '0')} · ${fmt(row.base.inicio_ms)} · Speaker ${esc(row.speaker)}</b><small>${esc(row.novo.slice(0, 85))}${row.novo.length > 85 ? '…' : ''}</small><span class="ux-row-status">${esc(stateName(row))}</span></button>`).join('') : '<p class="ux-empty">Nenhum trecho neste filtro.</p>';
  if (listMarkup !== markup) {
   const focusedId = list.contains(document.activeElement) ? document.activeElement.dataset.uxRow : '';
   listMarkup = markup;
   list.innerHTML = markup;
   listButtons = new Map([...list.querySelectorAll('[data-ux-row]')].map(button => [button.dataset.uxRow, button]));
   if (focusedId) (listButtons.get(focusedId) || listButtons.get(active))?.focus({preventScroll:true});
  } else if (previous !== active) {
   listButtons.get(previous)?.setAttribute('aria-current', 'false');
  }
  listButtons.get(active)?.setAttribute('aria-current', 'true');
  editors = new Map([...$('flist').querySelectorAll('[data-swap-row]')].map(card => [card.dataset.swapRow, card]));
  for (const [id, card] of editors) {
   if (id !== active && !card.hidden) card.hidden = true;
  }
  showEditor();
  let empty=$('ux-empty-editor');if(!empty){empty=create('p','ux-empty','Selecione outro filtro para continuar.');empty.id='ux-empty-editor';$('ux-editor').append(empty);}empty.hidden=!!visible.length;
  const approvalHelp=$('ux-approval-help');if(approvalHelp)approvalHelp.textContent=`${selected.length} de ${rs.length} textos selecionados para geração.`+(selected.length===rs.length&&rs.length?' Todos os textos já estão selecionados.':' A aprovação em lote seleciona as menções exatas; confira as sugestões marcadas.')+(selected.length&&!selected.some(r=>r.fit)?' A aprovação dos áudios será liberada depois da geração e do encaixe.':'');
  const next=selected.length?duration.length?`Próxima ação: preparar a duração de ${duration.length} áudio(s) existentes em 3.2 · sem créditos.`:missing.length?`Próxima ação: gerar ${missing.length} fala(s) em 3.2.`:listen.length?`Próxima ação: ouvir e aprovar ${listen.length} áudio(s).`:'Próxima ação: exportar a montagem em Entrega.':'Selecione os textos que serão trocados.';
  $('ux-product').title=next;const metrics=[...$('troca-metrics').querySelectorAll('strong')];$('ux-window').textContent=next+(metrics.length?' Primeira menção: '+metrics[0].textContent+' · janela até o fim: '+metrics[1].textContent+'.':'');
 }
 function saveStatus(text,error=false){autoStatus.textContent=text;autoStatus.classList.toggle('dirty',error);retrySave.hidden=!(error&&text.startsWith('Não foi salvo'));}
 function flush(){
  clearTimeout(timer);
  if(saveFlight)return saveFlight;
  if(!dirty)return Promise.resolve(true);
  if(U.busy)return Promise.resolve(false);
  saveFlight=(async()=>{
   saving=true;saveStatus('Salvando…');
   try{
    while(dirty&&!U.busy){const snapshot=version;await U.save();if(snapshot===version)dirty=false;}
    if(dirty)return false;
    saveStatus('Salvo neste computador');
    const focused=document.activeElement,card=focused?.closest('[data-swap-row]'),kind=focused?.hasAttribute('data-swap-text')?'[data-swap-text]':focused?.hasAttribute('data-swap-speaker')?'[data-swap-speaker]':null,pos=focused?.selectionStart;
    U.render();
    if(card&&kind){const target=document.querySelector('[data-swap-row="'+card.dataset.swapRow+'"] '+kind);target?.focus({preventScroll:true});if(kind==='[data-swap-text]'&&Number.isInteger(pos))target?.setSelectionRange(pos,pos);}
    return true;
   }catch(e){saveStatus('Não foi salvo · '+e.message,true);$('swap-error').textContent=e.message;return false;}
   finally{saving=false;saveFlight=null;}
  })();
  return saveFlight;
 }

 function changed(){version++;dirty=true;saveStatus('Alterações pendentes…',true);clearTimeout(timer);timer=setTimeout(flush,1000);}
 $('flist').addEventListener('input',e=>{if(e.target.matches('[data-swap-text],[data-swap-speaker],[data-swap-approve]'))changed();});
 $('flist').addEventListener('change',e=>{if(e.target.matches('[data-swap-speaker],[data-swap-approve]'))changed();});
 $('flist').addEventListener('click',async e=>{
  const b=e.target.closest('[data-mention-ignore]');if(!b)return;
  const id=b.dataset.mentionIgnore;b.disabled=true;
  try{
   if(await flush()===false||dirty)throw Error('Salve as alterações antes de revisar a menção.');
   const r=U.plan.itens.find(row=>row.id===id);
   if(r)U.acceptPlan(await U.call('salvar',{itens:[{id,aprovado:false,mencao_descartada:!r.mencao_descartada}]}));
  }catch(error){saveStatus(error.message,true);}finally{b.disabled=false;}
 });
 $('swap-all').addEventListener('click',changed);$('swap-none').addEventListener('click',changed);
 $('swap-save').onclick=async()=>{if(!dirty)changed();await flush();};
 window.addEventListener('beforeunload',e=>{if(dirty||saving){e.preventDefault();e.returnValue='';}});
 all('[data-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;refresh();});$('ux-search').oninput=e=>{search=e.target.value.trim().toLowerCase();refresh();};
 function jump(id){const target=$(id)||$('visual-choose')?.closest('details');if(!target)return;let p=target;while(p){if(p.tagName==='DETAILS')p.open=true;p=p.parentElement;}const sticky=getComputedStyle(summary).position==='sticky'?summary.offsetHeight:0;target.style.scrollMarginTop=(document.querySelector('.wizard-nav').offsetHeight+sticky+24)+'px';target.scrollIntoView({behavior:'smooth',block:'start'});target.focus?.();}
 all('[data-ux-jump]').forEach(b=>b.onclick=()=>jump(b.dataset.uxJump));
 $('ux-pending').onclick=()=>{filter='pending';refresh();jump('swap-controls');};$('ux-goto-voices').onclick=()=>jump('swap-voices');$('ux-deliver').onclick=async()=>{await flush();if(!dirty)wizardStep(4);};
 $('ux-retry').onclick=async()=>{await flush();if(!dirty)U.generate(true);};
 // Fichas mantêm o player pronto em destaque; o bruto fica acessível em detalhes.
 function compact(){all('[data-swap-row]').forEach(card=>{
   const raw=[...card.querySelectorAll('label')].find(l=>l.firstChild?.textContent?.trim()==='Áudio gerado');
   if(raw&&!raw.closest('details')){const d=create('details','ux-collapsed-audio','<summary>Ouvir áudio gerado antes do ajuste</summary>');raw.before(d);d.append(raw);}
 });}
 document.addEventListener('swap:state',refresh);document.addEventListener('swap:render',()=>{compact();refresh();previewResult();if(profileDraft?.vozes)all('[data-swap-voice]').forEach(e=>{if(!e.value)e.value=profileDraft.vozes[e.dataset.swapVoice]||'';});});
 // Navegação entre frases pelo teclado, sem interferir na digitação.
 document.addEventListener('keydown', event => {
  if (!event.altKey || !['ArrowDown','ArrowUp'].includes(event.key) || $('wizard-slot-3').closest('section').hidden || $('fcard').hidden) return;
  stepRow(event);
 });
 // Prévia local, sem aprovar nem fazer chamadas de voz.
 const audition=create('section','card ux-preview','<h3>Conferir as trocas em sequência</h3><p class="meta">Reproduz os áudios prontos, com 2 segundos antes e depois de cada frase. Trechos sem áudio pronto ficam de fora. As imagens V2 entram quando preparadas e incluídas na montagem. A prévia não aprova os áudios.</p><button id="ux-preview" data-swap-lock>Gerar prévia local das trocas</button><div id="ux-preview-result"></div>');
 $('swap-voices').before(audition);const auditionWrap=create('details','card','<summary>Prévia das trocas com contexto</summary>');audition.before(auditionWrap);auditionWrap.append(audition);audition.classList.remove('card');
 $('ux-preview').onclick=async()=>{if(U.busy)return;await flush();if(dirty)return;$('ux-preview').disabled=true;await U.action(async()=>{await U.save();U.startJob(await U.call('previa-trocas'));});if(!U.busy)$('ux-preview').disabled=false;};
 function previewResult(){const p=U.plan?.previa;const node=$('ux-preview-result');if(!p){node.innerHTML='';return;}node.innerHTML=`<p class="meta">${p.trechos} trecho(s) na prévia · ${p.pendentes} sem áudio pronto. ${p.visuais?'Com sobreposições V2.':'Sem sobreposições V2.'}</p>${p.video?'<video controls preload="none" src="'+url(p.arquivo)+'"></video>':'<span data-audio-placeholder="'+url(p.arquivo)+'"></span>'}<p class="meta">${esc(p.observacao)}</p>`;}
 // Entrega: uma escolha clara; os caminhos avançados continuam disponíveis.
 const montage=$('swap-export').closest('.card'),visualExport=$('visual-export').closest('.card'),manual=$('exp-premiere').closest('details');
 const delivery=create('section','card ux-delivery','<h3>O que você quer levar ao Premiere?</h3><label>Tipo de entrega<select id="ux-delivery-type"><option value="audio">Montagem com falas novas · V1 + A1/A2/A3</option><option value="visual">Somente imagens dos potes · V1/V2 + áudio original</option><option value="manual">Somente marcações e cortes para edição manual</option></select></label><p id="ux-delivery-help" class="meta"></p>');
 $('wizard-slot-4').prepend(delivery);delivery.after(montage,visualExport,manual);
 const includeLabel=$('visual-include').closest('label'),includeSave=$('visual-include-save');
 const includeGroup=create('div','ux-toast','<b>Adicionar as imagens dos potes à montagem</b>');includeGroup.append(includeLabel,includeSave);$('swap-export').before(includeGroup);
 const how=montage.querySelector('h4')?.parentElement;if(how){const d=create('details','','<summary>Como importar no Premiere · 4 passos</summary>');how.before(d);d.append(how);}
 $('tutorial-premiere').open=false;
 function deliveryMode(){const type=$('ux-delivery-type').value;montage.hidden=type!=='audio';visualExport.hidden=type!=='visual';manual.hidden=type!=='manual';if(type==='manual')manual.open=true;$('ux-delivery-help').textContent=type==='audio'?'Caminho recomendado: importa as falas aprovadas nos tempos corretos. Você pode incluir os potes em V2 abaixo.':type==='visual'?'Mantém o áudio original e coloca somente os materiais preparados por cima do vídeo.':'Use este caminho se você pretende fazer as substituições à mão no Premiere.';}
 $('ux-delivery-type').onchange=deliveryMode;deliveryMode();
 // Ferramentas de pasta ficam disponíveis sem competir com a ação principal.
 all('[data-swap-path]').forEach(p=>{p.classList.add('ux-path');const card=p.closest('.card');if(!card)return;const details=create('details','card','<summary>Arquivos e pastas deste trabalho</summary>');card.before(details);details.append(card);card.classList.remove('card');});
 // Perfis só guardam escolhas reutilizáveis; jamais chaves ou consentimentos.
 function profilePanel(suffix){const d=create('details','ux-profile',`<summary>Perfil do produto · reutilizar em outras VSLs</summary><div class="row"><label>Perfil salvo<select id="ux-profile-${suffix}"><option value="">Escolha um perfil</option></select></label><button class="ghost" data-profile-apply="${suffix}">Carregar perfil</button></div><div class="row"><label>Nome do perfil<input id="ux-profile-name-${suffix}" maxlength="100" placeholder="Ex.: SizeFix · Inglês"></label><button class="ghost" data-profile-save="${suffix}">Salvar como novo perfil</button></div><p class="meta">Guarda nomes, grafias, preços/kits preenchidos, pasta dos potes e IDs de vozes existentes. Não guarda a chave da API, autorizações, áudios nem aprovações. Confira a associação de speakers em cada VSL.</p><p role="status" id="ux-profile-status-${suffix}"></p>`);return d;}
 $('wizard-slot-2').prepend(profilePanel('setup'));const reviewProfile=profilePanel('review');reviewProfile.id='ux-product-profile';$('fcard').after(reviewProfile);const profileShortcut=create('button','ghost','Perfil do produto');profileShortcut.onclick=()=>jump('ux-product-profile');tabs.append(profileShortcut);
 async function profileList(){profiles=await U.call('perfis');for(const suffix of ['setup','review']){const select=$('ux-profile-'+suffix),old=select.value;select.innerHTML='<option value="">Escolha um perfil</option>'+profiles.map(p=>`<option value="${esc(p.id)}">${esc(p.nome)}</option>`).join('');select.value=old;}}
 const values=selector=>Object.fromEntries(all(selector).filter(e=>e.value.trim()).map(e=>[e.dataset.pv||e.dataset.qv||e.dataset.swapVoice,e.value.trim()]));
 all('[data-profile-save]').forEach(b=>b.onclick=async()=>{const k=b.dataset.profileSave,target=$('ux-profile-status-'+k);try{b.disabled=true;const dados={produto:$('prod2').value||$('prod').value,novo:$('novo2').value||$('novo').value,aliases:$('alias2').value||$('alias').value,pasta:$('visual-root').value,provider:$('swap-provider').value,model:$('swap-model').value,vozes:values('[data-swap-voice]'),precos:values('[data-pv]'),kits:values('[data-qv]')};await U.call('perfil-salvar',{nome:$('ux-profile-name-'+k).value,dados});await profileList();target.textContent='Perfil salvo neste computador.';}catch(e){target.textContent=e.message;}finally{b.disabled=false;}});
 function mapFields(){if(!profileDraft)return;all('[data-pv]').forEach(e=>{if(profileDraft.precos?.[e.dataset.pv]!==undefined)e.value=profileDraft.precos[e.dataset.pv];});all('[data-qv]').forEach(e=>{if(profileDraft.kits?.[e.dataset.qv]!==undefined)e.value=profileDraft.kits[e.dataset.qv];});}
 all('[data-profile-apply]').forEach(b=>b.onclick=async()=>{const k=b.dataset.profileApply,target=$('ux-profile-status-'+k),p=profiles.find(v=>v.id===$('ux-profile-'+k).value);if(!p){target.textContent='Escolha um perfil salvo.';return;}await flush();if(dirty){target.textContent='Salve o texto atual antes de carregar o perfil.';return;}const d=p.dados;profileDraft=d;for(const [ids,key] of [[['prod','prod2'],'produto'],[['novo','novo2'],'novo'],[['alias','alias2'],'aliases']])for(const id of ids)if($(id))$(id).value=d[key]||'';
 if(d.provider){$('swap-provider').value=d.provider;$('swap-provider').dispatchEvent(new Event('change'));if([...$('swap-model').options].some(o=>o.value===d.model))$('swap-model').value=d.model;}
 if(U.plan)U.renderSpeakers();all('[data-swap-voice]').forEach(e=>e.value=d.vozes?.[e.dataset.swapVoice]||'');$('visual-root').value=d.pasta||'';mapFields();
 if(U.plan)$('prod2').closest('details').open=true;target.textContent='Perfil carregado. '+(U.plan?'Clique em “Buscar de novo” para aplicar os nomes às frases. ':'Confira os produtos antes de transcrever. ')+'Leia a pasta para associar os materiais; confira os speakers e preços.';
 });
 new MutationObserver(mapFields).observe($('pdet'),{childList:true,subtree:true});
 profileList().catch(e=>{for(const k of ['setup','review'])$('ux-profile-status-'+k).textContent=e.message;});
 U.call('chave-status').then(s=>{$('swap-key-status').textContent=s.configurados.includes($('swap-provider').value)?'Chave configurada neste computador. Nenhuma geração será feita sem sua autorização.':'Configure a chave em Ajustes → Integrações e APIs.';}).catch(()=>{});
 const guardedStep=wizardStep;wizardStep=async function(n){if(dirty||saving){await flush();if(dirty||saving)return;}return guardedStep(n);};
 $('reopen').addEventListener('click',async e=>{if(U.busy){e.stopImmediatePropagation();e.preventDefault();saveStatus('Aguarde ou cancele a tarefa antes de abrir outro trabalho.',true);return;}if(!dirty&&!saving)return;e.stopImmediatePropagation();e.preventDefault();await flush();if(!dirty&&!saving)$('reopen').click();},true);
 document.addEventListener('swap:step',()=>{if(dirty)flush();});
 const voiceWrap=create('section','card ux-voice-stage','<p class="ux-stage-label">Etapa 3.2 · Vozes e geração</p>');voiceWrap.id='ux-voice-stage';const voiceGate=create('p','ux-toast','');voiceGate.id='ux-voice-gate';voiceGate.setAttribute('role','status');voiceWrap.append(voiceGate);$('fcard').after(voiceWrap);voiceWrap.append($('swap-voices'));$('swap-voices').classList.remove('card');$('swap-voices').querySelector('h3').textContent='Gerar falas por speaker';
 const speechStages=create('nav','ux-speech-stages','<button class="ghost" id="speech-texts"><span>3.1</span> Conferir textos</button><button id="speech-generate"><span>3.2</span> Gerar falas por speaker</button><button class="ghost" id="speech-listen"><span>3.3</span> Ouvir e aprovar áudios</button>');speechStages.setAttribute('aria-label','Etapas de Falas');tabs.after(speechStages);
 let speechStage=1;
 function selectSpeech(stage,scroll=true){
  speechStage=stage;$('fcard').hidden=stage===2;voiceWrap.hidden=stage!==2;
  for(const [id,value] of [['speech-texts',1],['speech-generate',2],['speech-listen',3]]){const b=$(id);b.classList.toggle('ghost',value!==stage);b.setAttribute('aria-current',value===stage?'step':'false');}
  if(stage===1)filter='all';if(stage===3)filter=rows().some(hasIssue)?'issues':'listen';refresh();
  if(scroll){speechStages.scrollIntoView({block:'start',behavior:'smooth'});$(stage===2?'speech-generate':stage===3?'speech-listen':'speech-texts').focus({preventScroll:true});}
 }
 async function switchSpeech(stage){selectSpeech(stage);if(dirty&&!U.busy)flush();}

 $('speech-texts').onclick=()=>switchSpeech(1);$('speech-generate').onclick=()=>switchSpeech(2);$('speech-listen').onclick=()=>switchSpeech(3);
 document.addEventListener('mentions:focus-speech', event => {
  const {id_fala, status} = event.detail;
  if (!U.plan?.itens.some(row => row.id === id_fala)) return;
  selectSpeech(status === 'audio_nao_aprovado' ? 3 : 1, false);
  filter = 'all';
  $('ux-search').value = search = '';
  refresh();
  selectRow(id_fala);
  const button = listButtons.get(id_fala);
  if (!button) return;
  event.preventDefault();
  button.focus({preventScroll:true});
  list.scrollIntoView({block:'start'});
  button.scrollIntoView({block:'nearest'});
 });
 $('ux-goto-voices').onclick=()=>switchSpeech(2);$('ux-pending').onclick=async()=>{await switchSpeech(1);filter='pending';refresh();};
 tabs.hidden=true;newgen.hidden=true;selectSpeech(1,false);

 $('ux-goto-voices').textContent='3.2 · Gerar falas por speaker';
 const voiceHelp=create('p','meta','Confira os textos em 3.1, prepare as vozes e gere aqui. Depois, use 3.3 para ouvir os áudios prontos e aprová-los. Nenhuma fala é enviada ao serviço sem as autorizações abaixo.');$('swap-voices').querySelector('h3').after(voiceHelp);
 $('visual-panel').open=false;
 const metricsBox=create('details','','<summary>Resumo da VSL e lista para copiar</summary>');const fcard=$('fcard'),copyLinks=$('cpAll').closest('.links'),copySummary=$('resumo').closest('details');$('troca-metrics').before(metricsBox);metricsBox.append($('troca-metrics'),copySummary,copyLinks);fcard.querySelector('h2').hidden=true;$('det').hidden=true;
 const searchRow=$('prod2').closest('.row'),searchDetails=create('details','','<summary>Ajustar produto e refazer a busca</summary>');searchRow.before(searchDetails);searchDetails.append(searchRow);const fileDetails=all('[data-swap-path]').map(p=>p.closest('details')).find(d=>d&&$('fcard').contains(d));metricsBox.append($('wizard-coverage'));$('fcard').append(searchDetails,metricsBox);if(fileDetails)$('fcard').append(fileDetails);
 const batch=create('details','','<summary>Ações em lote, seleção de preços e salvar manualmente</summary>');const controls=$('swap-controls'),batchRow=controls.querySelector('.row'),batchLinks=controls.querySelector('.links');const approveAudio=$('swap-approve-all-audio');controls.querySelector('p').after(approveAudio);batch.append(batchRow,batchLinks);$('fcard').append(batch);const batchHelp=[...controls.querySelectorAll('p')].find(p=>p.textContent.startsWith('A aprovação em lote'));if(batchHelp)batch.append(batchHelp);approveAudio.title='Aprova somente os áudios prontos das frases selecionadas. Confira-os antes de aprovar.';
 const approvalActions=create('div','links ux-approval-actions','');controls.querySelector('p').after(approvalActions);approvalActions.append($('swap-all'),$('swap-none'),approveAudio);$('swap-all').classList.remove('ghost');$('swap-all').title='Seleciona os textos da lista e preserva a revisão individual das menções prováveis.';const approvalHelp=create('p','meta','');approvalHelp.id='ux-approval-help';approvalHelp.setAttribute('role','status');approvalActions.after(approvalHelp);
 $('flist').addEventListener('toggle',e=>{if(e.target.tagName==='DETAILS'&&e.target.open)mountPlayers(e.target);},true);
 document.addEventListener('play',e=>{if(e.target.matches('audio,video'))all('audio,video').forEach(a=>{if(a!==e.target&&!a.paused)a.pause();});},true);
 U.flushDraft=flush;U.hasDraft=()=>dirty||saving;
 compact();refresh();
})();
