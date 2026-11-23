/* Sete etapas principais, com automação local e conferências explícitas. */
(() => {
 const U=window.SwapUX,V=window.VisualUX,$=id=>document.getElementById(id),qa=s=>[...document.querySelectorAll(s)],esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 if(!U||!V)return;
 const make=(tag,cls,html)=>{const n=document.createElement(tag);n.className=cls;n.innerHTML=html;return n;};
 const titles=['Arquivo','Transcrição','Falas','Takes','Prévia','Validação e entrega','Legendas'];
 let current=1,changing=0,previewJob=null,quickJob=null,exporting=false,previewStamp='',work='',reviewSignature='',deliveredStamp='',reviewStamp='',quickStarting=false;
 const nav=document.querySelector('.wizard-nav');nav.setAttribute('aria-label','Fluxo completo da ripagem');nav.innerHTML=titles.map((t,i)=>`<button class="ghost" data-flow-step="${i+1}">${i+1}. ${t}</button>`).join('');
 const instructions=document.querySelector('#guided-fatiador > .sub');instructions.textContent='Siga o fluxo: o app prepara os arquivos e destaca o que precisa da sua conferência.';
 const takes=make('section','wizard-panel flow-panel','<h2 id="flow-title-4" tabindex="-1">Etapa 4 de 7 · Preparar os takes dos potes</h2><p class="meta">Escolha a pasta. O app lê os materiais, encontra as menções, sorteia sem repetir em sequência e prepara V2. Confira as escolhas e os tempos antes de continuar.</p><div class="card flow-automation"><b>Preparo automático dos takes</b><p class="meta">Biblioteca → falas e menções → distribuição → vídeos em tela inteira. Todas as falas substituídas recebem cobertura visual: kit correspondente quando identificado e vídeos genéricos classificados como Produto nas demais. A cobertura considera o tempo extra do áudio, sem congelar os takes completos. Se faltar kit ou variedade, o fluxo pausa aqui e explica como resolver.</p><p class="meta" id="flow-visual-margin"></p><button id="flow-auto-takes">Preparar takes automaticamente</button><p id="flow-takes-state" role="status" class="meta"></p></div><div id="flow-takes-content"></div><div class="row"><button class="ghost" id="flow-back-falas">Voltar às falas</button><button id="flow-to-preview">Conferir prévia →</button></div>');takes.dataset.flowPanel='4';takes.hidden=true;
 const preview=make('section','wizard-panel flow-panel','<h2 id="flow-title-5" tabindex="-1">Etapa 5 de 7 · Conferir antes de entregar</h2><p class="meta">Confira as falas e os takes juntos, com contexto. A prévia começa automaticamente quando os áudios selecionados estão aprovados e os takes estão preparados, ou quando você decide seguir sem takes.</p><div class="card"><h3>Conferência da montagem</h3><p id="flow-checklist" class="meta"></p><div id="flow-blockers"></div><button id="flow-preview-generate">Gerar / atualizar prévia</button><div id="flow-preview-progress" hidden><p id="flow-preview-step" role="status"></p><progress id="flow-preview-bar" max="1" style="width:100%"></progress><button class="ghost" id="flow-preview-cancel">Cancelar prévia</button></div><p id="flow-preview-error" role="alert" class="err"></p><div id="flow-preview-player"></div><label><input type="checkbox" id="flow-preview-approved"> Conferi a prévia desta montagem e quero preparar a entrega.</label><p class="meta">A prévia reúne os trechos com 2 segundos de contexto. O XML mantém a VSL inteira; confira também a sequência no Premiere.</p></div><div class="row"><button class="ghost" id="flow-back-takes">Voltar aos takes</button><button id="flow-finish">Aprovar prévia e preparar XML →</button></div>');preview.dataset.flowPanel='5';preview.hidden=true;
 document.querySelector('[data-w-panel="3"]').after(takes,preview);
 const legacyDelivery=make('details','card','<summary>Exportações avulsas e opções avançadas</summary><p class="meta">Para entregas parciais ou edição manual. O fluxo principal reúne as falas e os takes após a conferência da prévia.</p>');
 const deliverySlot=$('wizard-slot-4');legacyDelivery.append(...deliverySlot.children);deliverySlot.append(legacyDelivery);
 const guidedDelivery=make('section','card flow-automation','<h3>Entrega da ripagem</h3><p id="flow-delivery-status" class="meta">Conclua a prévia para preparar o XML automaticamente.</p><button class="ghost" id="flow-review-delivery">Voltar à conferência da prévia</button><div id="flow-delivery-result"></div><div id="flow-review-result" hidden></div>');deliverySlot.prepend(guidedDelivery);$('flow-review-delivery').onclick=()=>go(5);
 const panel=$('visual-panel');panel.open=true;panel.querySelector('summary').hidden=true;$('flow-takes-content').append(panel);panel.classList.add('flow-takes-main');
 panel.querySelector('p').textContent='Imagens e vídeos ocupam a tela inteira em V2, sem o áudio dos materiais. O app mantém a proporção e recorta as bordas quando necessário.';
 const manual=make('details','card','<summary>Ajustes e ações manuais dos takes</summary><p class="meta">Use quando quiser atualizar a biblioteca, refazer a detecção ou distribuir os takes novamente. Refazer a detecção substitui os intervalos visuais ajustados.</p>');
 for(const id of ['visual-scan','visual-detect','visual-shuffle','visual-prepare'])manual.append($(id));
 manual.append($('visual-max').closest('label'));panel.append(manual);
 panel.querySelectorAll('h4').forEach((h,i)=>{h.textContent=i===0?'Pasta dos takes':i===1?'Menções e takes escolhidos':'Configuração da distribuição';if(i===2)h.hidden=true;});
 const autoCard=$('flow-auto-takes').parentElement;autoCard.append($('visual-progress'),$('visual-error'),$('visual-summary'));
 const rootLabel=$('visual-root').closest('label'),rootButtons=$('visual-choose').closest('.row'),rootGuide=rootButtons.nextElementSibling;const folderHelp=make('details','','<summary>Como organizar a pasta dos takes</summary>');folderHelp.append(rootGuide);$('flow-auto-takes').before(rootLabel,rootButtons,folderHelp);panel.querySelector('h4').hidden=true;
 const skip=make('div','card flow-choice','<label><input type="checkbox" id="flow-no-takes"> <span id="flow-no-takes-label">Esta entrega não precisa de takes · manter somente V1</span></label><p class="meta" id="flow-no-takes-help">Para a troca completa, deixe desmarcado e prepare os takes. A escolha fica salva neste trabalho.</p>');autoCard.after(skip);
 const quick=make('section','card flow-automation','<h3>Entrega rápida · sem assistir à prévia</h3><p>Ao clicar, você utiliza os áudios já aprovados e autoriza os takes da montagem. O app prepara os arquivos existentes e gera o XML diretamente.</p><p id="flow-quick-count" class="meta"></p><button id="flow-quick">Preparar entrega sem assistir à prévia</button><p class="meta">Não gera novas vozes nem consome créditos. Falas sem arquivo de áudio continuam como pendência. O relatório registra que a prévia foi dispensada por você.</p><div id="flow-quick-progress" hidden><p id="flow-quick-step" role="status"></p><progress id="flow-quick-bar" max="1" style="width:100%"></progress><button class="ghost" id="flow-quick-cancel">Cancelar entrega</button></div><div id="flow-quick-feedback"><p id="flow-quick-error" class="err" role="alert"></p><div class="links"><button type="button" id="flow-quick-review-xml" hidden>Ir para Entrega com XML de revisão →</button><button type="button" id="flow-quick-review-mention" class="ghost" hidden>Revisar menção em Falas</button></div></div>');skip.after(quick);$('flow-to-preview').textContent='Conferir prévia (opcional)';$('flow-to-preview').classList.add('ghost');
 const takeSummary=make('p','ux-stat','<span id="flow-take-count">Takes: aguardando biblioteca</span>');document.querySelector('.ux-summary').append(takeSummary);
 // Os atalhos agora levam à etapa correspondente, em vez de esconder os takes.
 qa('[data-ux-jump="visual-choose"]').forEach(b=>{b.textContent='Takes · imagens e vídeos';b.onclick=()=>go(4);});
 $('ux-deliver').onclick=()=>go(4);
 const audioContinue=document.querySelector('[data-w-panel="3"] [data-w-next]');audioContinue.textContent='Continuar → Takes';audioContinue.onclick=()=>go(4);
 $('ux-goto-voices').addEventListener('click',()=>{if(current!==3)go(3);});
 const oldPreview=$('ux-preview').closest('details');oldPreview.hidden=true;
 const rawStep=wizardStep;
 function speechReady(){if(U.busy)return false;const p=U.plan,selected=p?.itens.filter(r=>r.aprovado)||[];return selected.length>0&&selected.every(r=>r.audio?.fit&&r.audio.aprovado&&r.audio.texto_hash&&!r.speaker_pendente&&(!r.forma_pendente||r.forma_confirmada));}
 function blockers(){
  const p=U.plan,selected=p?.itens.filter(r=>r.aprovado)||[],missing=selected.filter(r=>!r.audio?.aprovado||!r.audio?.fit),s=V.state;
  const list=[];
  const absent=selected.filter(r=>!r.audio?.raw),duration=selected.filter(r=>r.audio?.raw&&!r.audio?.fit),listen=selected.filter(r=>r.audio?.fit&&!r.audio.aprovado);
  if(!selected.length)list.push({step:3,text:'Selecione e aprove os textos das falas.'});
  if(absent.length)list.push({step:3,filter:'fit',text:`${absent.length} fala(s) ainda sem áudio. Gere ou importe os trechos.`,label:'Gerar áudios faltantes'});
  if(duration.length)list.push({step:3,filter:'fit',text:`${duration.length} áudio(s) precisam do preparo de duração. Use Abrir espaço para falas maiores para reaproveitar os arquivos sem novos créditos.`,label:'Corrigir duração'});
  if(listen.length)list.push({step:3,filter:'listen',text:`${listen.length} áudio(s) já cabem e aguardam sua conferência e aprovação.`,label:'Ouvir e aprovar'});
  if(!$('flow-no-takes').checked&&(!s?.prepared||s?.issues?.length||V.dirty||!s.incluir||!coverageCurrent()))list.push({step:4,text:'Prepare os takes e resolva os kits ou intervalos pendentes.'});
  return list;
 }
 function coverageCurrent(){const s=V.state,rows=(U.plan?.itens||[]).filter(r=>r.aprovado).map(r=>[r.id,r.inicio_ms,r.fim_ms]).sort((a,b)=>a[1]-b[1]||a[2]-b[2]||a[0].localeCompare(b[0]));return !rows.length||(!s?.cobertura_desatualizada&&s?.cobrir_falas&&s.coverage_policy?.versao===3&&s.coverage_policy?.margem_visual_ms===s.margem_visual_atual_ms&&JSON.stringify(rows)===JSON.stringify(s.audio_windows));}
 function stamp(){return JSON.stringify([folder,U.plan?.itens.map(r=>[r.id,r.novo,r.speaker,r.aprovado,r.audio?.fit,r.audio?.aprovado]),V.state?.prepared?.signature,V.state?.incluir,$('flow-no-takes').checked]);}
 async function go(n){
  if(n===2&&!transcriptionConfirmed){$('wizard-error').textContent='Confira o arquivo selecionado e clique em Continuar para transcrição.';return;}
  if(n===2&&transcriptionBlocked()&&!wizardBusy){await go(1);$('wizard-error').textContent='Escolha o áudio ou vídeo no bloco acima antes de continuar. Seu produto novo continua preenchido.';$('drop').focus();return;}
  if(wizardBusy)return;if(quickJob&&n!==4&&n!==6)return;if(n>=3&&!wizardReady)return;
  await U.flushDraft();if(U.hasDraft())return;
  if(n>=4&&(n!==6||!reviewStamp||reviewStamp!==stamp())){const gate=await U.call('workflow');if(!gate.takes_liberados){await go(3);if(gate.estado==='pronto_para_gerar')$('speech-generate').click();else if(gate.estado==='aguardando_conferencia')$('speech-listen').click();else $('speech-texts').click();$('wizard-error').textContent=gate.pendencias.map(p=>(p.frase?'Frase '+p.frase+': ':'')+p.motivo).slice(0,3).join(' · ');return;}}
  const request=++changing;const base=n<=3?n:n===4?3:n===5?4:n===6?4:5;
  await rawStep(base);if(request!==changing)return;
  $('wizard-error').textContent='';current=n;qa('[data-w-panel]').forEach(p=>p.hidden=Number(p.dataset.wPanel)!==base||n===4||n===5);takes.hidden=n!==4;preview.hidden=n!==5;
  qa('[data-flow-step]').forEach(b=>{b.setAttribute('aria-current',Number(b.dataset.flowStep)===n?'step':'false');b.disabled=wizardBusy||(Number(b.dataset.flowStep)===2&&!transcriptionConfirmed)||(Number(b.dataset.flowStep)>=3&&!wizardReady)||(Number(b.dataset.flowStep)>=4&&!speechReady()&&(Number(b.dataset.flowStep)!==6||!reviewStamp||reviewStamp!==stamp()));});
  const heading=n===4?$('flow-title-4'):n===5?$('flow-title-5'):$('wizard-title-'+base);heading.focus({preventScroll:true});heading.scrollIntoView({block:'start',behavior:'smooth'});
  sync();
  if(n===4&&V.state?.cobertura_desatualizada&&$('visual-root').value.trim()&&!V.busy&&!U.busy)await V.automatic();
  if(n===5&&!blockers().length&&!previewJob&&!U.busy&&!V.busy&&previewStamp!==stamp())await generatePreview();
 }
 // Mantém compatibilidade com os controles anteriores (4 = entrega, 5 = SRT).
 wizardStep=n=>go(n<=3?n:n===4?6:7);
 qa('[data-flow-step]').forEach(b=>b.onclick=()=>go(Number(b.dataset.flowStep)));
 $('flow-back-falas').onclick=()=>go(3);$('flow-back-takes').onclick=()=>go(4);$('flow-to-preview').onclick=()=>go(5);
 document.querySelector('[data-w-panel="4"] [data-w-back]').onclick=()=>go(5);
 for(const [base,stage] of [[1,1],[2,2],[3,3],[4,6],[5,7]]){const h=$('wizard-title-'+base);h.textContent=h.textContent.replace(/Etapa \d+ de 5/,`Etapa ${stage} de 7`);}
 $('flow-auto-takes').onclick=async()=>{if(U.busy||V.busy||previewJob)return;$('flow-no-takes').checked=false;await V.automatic();sync();};
 $('flow-no-takes').onchange=async()=>{if(!V.state)return;const want=!$('flow-no-takes').checked;await V.action(async()=>{$('visual-include').checked=want&&!!V.state?.prepared;await V.save();V.render();});sync();};
 function sync(){
  if(work!==folder){work=folder;showQuickError('');previewStamp='';deliveredStamp='';reviewSignature='';$('flow-preview-approved').checked=false;$('flow-preview-player').innerHTML='';$('flow-delivery-result').innerHTML='';clearReviewDelivery();}
  qa('[data-flow-step]').forEach(b=>{b.disabled=wizardBusy||(Number(b.dataset.flowStep)===2&&!transcriptionConfirmed)||(Number(b.dataset.flowStep)>=3&&!wizardReady)||(Number(b.dataset.flowStep)>=4&&!speechReady()&&(Number(b.dataset.flowStep)!==6||!reviewStamp||reviewStamp!==stamp()));b.setAttribute('aria-current',Number(b.dataset.flowStep)===current?'step':'false');});
  qa('[data-flow-take],[data-flow-reroll]').forEach(e=>e.disabled=V.busy||!!previewJob);
  const s=V.state,chosen=s?.mentions.filter(m=>m.selected)||[],usable=!!s?.prepared&&!s?.issues?.length&&!V.dirty&&coverageCurrent();
  if(s&&!V.busy)$('flow-no-takes').checked=!!s.sem_takes;
  $('flow-no-takes-label').textContent=U.plan?.somente_valores?'Manter as imagens atuais · otimizar somente os áudios de preços e kits':'Esta entrega não precisa de takes · manter somente V1';
  $('flow-no-takes-help').textContent=U.plan?.somente_valores?'Marque para gerar o XML sem novos takes. Se mudou a quantidade dos kits, confira e adapte as imagens desses potes no Premiere. Deixe desmarcado para preparar os takes selecionados.':'Para a troca completa, deixe desmarcado e prepare os takes. A escolha fica salva neste trabalho.';
  $('flow-take-count').textContent=s?.sem_takes?'Takes: entrega sem sobreposições':`${s?.assets.length||0} materiais · ${chosen.length} menções · ${usable?s.prepared.segments.length+' takes prontos':(s?.issues?.length||chosen.length)+' menções por preparar'}`;
  const margin=(s?.margem_visual_atual_ms??1500)/1000;
  $('flow-visual-margin').textContent=U.plan?.somente_valores?`Cobertura dos preços e kits selecionados com ${margin.toLocaleString('pt-BR')} s de margem.`:`Margem de ${margin.toLocaleString('pt-BR')} s em cada lado das falas e das aparições aprovadas, dentro do intervalo de cobertura. Ajustável em Ajustes.`;
  $('flow-takes-state').textContent=V.busy?'Preparando takes… acompanhe o progresso abaixo.':s?.cobertura_desatualizada?'O produto ou as falas mudaram. Clique em Preparar takes automaticamente para adaptar a cobertura atual.':usable?`Takes preparados: ${s.prepared.segments.length} takes em V2 e ${s.coverage_markers?.length||0} trechos só marcados para adaptação. Confira ou siga pela entrega rápida.`+(s.modo_takes==='inteiro'?' Vídeos completos referenciados no XML.':s.modo_takes==='encaixar'?' Vídeos originais ajustados às janelas na timeline.':''):'Escolha a pasta e clique em Preparar takes automaticamente.';
  if(reviewStamp&&reviewStamp!==stamp())clearReviewDelivery();
  $('flow-quick-review-xml').disabled=quickStarting||U.busy||V.busy||!!quickJob||!!previewJob;
  $('flow-auto-takes').disabled=!speechReady()||U.busy||V.busy||!!quickJob||!!previewJob||!$('visual-root').value.trim();$('flow-no-takes').disabled=V.busy||!!quickJob||!!previewJob;const selected=U.plan?.itens.filter(r=>r.aprovado)||[];$('flow-quick-count').textContent=selected.length+' falas selecionadas · '+(s?.sem_takes?'sem takes':usable?s.prepared.segments.length+' takes preparados':'os takes serão preparados com a pasta e as regras atuais')+'.';$('flow-quick').disabled=quickStarting||!speechReady()||U.busy||V.busy||!!quickJob||!!previewJob||!selected.length;
  const speech=U.plan?.itens.filter(r=>r.aprovado)||[],readySpeech=speech.length>0&&speech.every(r=>r.audio?.fit&&r.audio.aprovado);
  const stageStates={1:!!folder,2:!!wizardReady,3:readySpeech,4:!!s?.sem_takes||usable,5:!!reviewSignature&&previewStamp===stamp(),6:!!deliveredStamp&&deliveredStamp===stamp()};
  qa('[data-flow-step]').forEach(b=>{const n=Number(b.dataset.flowStep);b.dataset.state=stageStates[n]?'ready':'pending';b.title=stageStates[n]?'Etapa preparada · clique para conferir':'Abrir etapa '+n;});
  $('ux-deliver').textContent=readySpeech?'Continuar → Takes':'Preparar takes e entrega';
  const blocked=blockers();$('flow-checklist').textContent=`${U.plan?.itens.filter(r=>r.aprovado).length||0} falas selecionadas · ${s?.sem_takes?'sem takes':usable?s.prepared.segments.length+' takes em V2':'takes pendentes'}`;
  $('flow-blockers').innerHTML=blocked.map(b=>`<p class="flow-blocker">${esc(b.text)} <button class="ghost" data-flow-fix="${b.step}" data-flow-filter="${b.filter||''}">${b.label||('Resolver na etapa '+b.step)}</button></p>`).join('');
  qa('[data-flow-fix]').forEach(b=>b.onclick=async()=>{await go(Number(b.dataset.flowFix));if(b.dataset.flowFilter==='listen')$('speech-listen').click();else if(b.dataset.flowFilter){$('speech-texts').click();document.querySelector('[data-filter="'+b.dataset.flowFilter+'"]')?.click();}});
  if(previewStamp&&previewStamp!==stamp()){$('flow-preview-approved').checked=false;$('flow-preview-player').innerHTML='<p class="meta">A montagem mudou. Gere a prévia atualizada.</p>';}
  const canReview=!blocked.length&&!previewJob&&previewStamp===stamp()&&!!reviewSignature;$('flow-preview-approved').closest('label').hidden=!canReview;$('flow-preview-approval-help').textContent=canReview?'Reproduza a prévia acima. Depois, marque a conferência para preparar o XML.':previewJob?'Preparando a prévia. A confirmação aparecerá quando o vídeo estiver pronto.':blocked.length?'Resolva as pendências acima. A confirmação aparecerá depois de gerar a prévia.':'Clique em Gerar / atualizar prévia para liberar a conferência.';
  $('flow-preview-cancel').hidden=!previewJob;$('flow-preview-approved').disabled=!!blocked.length||!!previewJob||previewStamp!==stamp();
  $('flow-preview-generate').disabled=!!blocked.length||!!previewJob||U.busy||V.busy;
  $('flow-finish').disabled=!!blocked.length||!!previewJob||exporting||!$('flow-preview-approved').checked||previewStamp!==stamp();
  $('flow-to-preview').disabled=V.busy||U.busy||!!quickJob;
  $('ux-deliver').textContent='Continuar → Takes';$('flow-delivery-status').textContent=deliveredStamp===stamp()?'XML pronto para importar no Premiere.':'Confira a prévia para preparar a entrega completa.';if(deliveredStamp&&deliveredStamp!==stamp()){$('flow-delivery-result').innerHTML='<p class="meta">A montagem mudou após a última entrega. Confira a prévia para gerar um novo XML.</p>';deliveredStamp='';}
 }
 $('visual-root').addEventListener('input',sync);window.addEventListener('dr-folder-selected',sync);
 const approvalHelp=make('p','meta','');approvalHelp.id='flow-preview-approval-help';approvalHelp.setAttribute('role','status');$('flow-preview-approved').closest('label').before(approvalHelp);
 $('flow-preview-approved').onchange=sync;
 async function generatePreview(){
  if(blockers().length||previewJob||U.busy||V.busy)return;
  $('flow-preview-error').textContent='';try{
   await U.save();const job=await U.call('previa-trocas');previewJob=job.id;sessionStorage.setItem('ripagem.preview',JSON.stringify({id:job.id,folder,stamp:stamp()}));$('flow-preview-progress').hidden=false;$('flow-preview-bar').removeAttribute('value');$('flow-preview-step').textContent='Preparando prévia local…';sync();pollPreview();
  }catch(e){$('flow-preview-error').textContent=e.message;}
 }
 async function pollPreview(){
  if(!previewJob)return;const id=previewJob,context=JSON.parse(sessionStorage.getItem('ripagem.preview')||'null');try{
   const r=await fetch('/api/ml/job/'+id),j=await r.json();if(!r.ok)throw Error(j.erro);
   $('flow-preview-step').textContent=j.step;if(j.status==='na_fila')$('flow-preview-bar').removeAttribute('value');else $('flow-preview-bar').value=j.pct||0;
   if(['na_fila','executando'].includes(j.status)){setTimeout(pollPreview,1500);return;}
   previewJob=null;sessionStorage.removeItem('ripagem.preview');
   if(j.status!=='concluido')throw Error(j.error||'Prévia cancelada. Os arquivos anteriores foram preservados.');
   const p=j.result;reviewSignature=p.assinatura;previewStamp=context?.stamp||'';$('flow-preview-approved').checked=false;
   $('flow-preview-player').innerHTML=`<p class="meta">${p.trechos} trechos · ${p.visuais?'com takes em V2':'somente falas'} · com contexto.</p><${p.video?'video':'audio'} controls preload="metadata" src="${url(p.arquivo)}" style="width:100%;max-height:480px"></${p.video?'video':'audio'}>`;sync();
  }catch(e){if(previewJob){$('flow-preview-step').textContent='Retomando consulta do progresso…';setTimeout(pollPreview,4000);}else{$('flow-preview-error').textContent=e.message;sync();}}
 }
 $('flow-preview-generate').onclick=generatePreview;$('flow-preview-cancel').onclick=()=>previewJob&&fetch('/api/ml/job/'+previewJob+'/cancelar',{method:'POST'});
 $('flow-finish').onclick=async()=>{
  if(blockers().length||previewStamp!==stamp()||!$('flow-preview-approved').checked||exporting)return;
  exporting=true;sync();try{await U.save();sessionStorage.setItem('ripagem.final-route.'+folder,JSON.stringify({sem_previa:false,assinatura:reviewSignature}));const result=await U.call('entrega',{assinatura:reviewSignature});await go(6);showDelivery(result);document.dispatchEvent(new CustomEvent('ripagem:xml-ready',{detail:result}));
  }catch(e){$('flow-preview-error').textContent=e.message;}finally{exporting=false;sync();}
 };
 function showDelivery(result){clearReviewDelivery();deliveredStamp=result.xml_existe?stamp():'';$('flow-delivery-result').innerHTML=`<div class="ux-result"><b>${result.sem_previa?'Entrega rápida · prévia dispensada por você':'Entrega pronta · VSL completa'}</b><p>${result.trechos} falas em A3 · ${result.visuais} takes em V2 · cortes originais em A2 desativados.${result.acrescimo_s?' Ajuste de duração da timeline: '+result.acrescimo_s.toFixed(2)+' s, preservando as falas e fechando as margens.':''}</p><div class="links"><a download data-studio-xml="${esc(result.xml)}" href="${url(result.xml)}?dl=1">Salvar uma cópia do XML…</a><a download href="${url(result.json)}?dl=1">Salvar relatório</a><button class="ghost" id="flow-open-delivery">Abrir pasta do XML</button></div><p id="flow-save-status" class="meta" role="status">${result.xml_existe?'Arquivo confirmado: '+esc(result.xml_nome)+' · '+esc(result.xml_absoluto):'Não foi possível confirmar o arquivo no disco. Caminho esperado: '+esc(result.xml_absoluto||result.xml)}</p><p class="meta">Premiere → Arquivo → Importar (Ctrl+I no Windows / ⌘I no Mac) → escolha o XML → abra a sequência com o mesmo nome do XML.</p></div>`;if(!result.xml_existe){$('flow-delivery-result').querySelectorAll('a').forEach(a=>{a.removeAttribute('href');a.setAttribute('aria-disabled','true');});$('flow-delivery-status').textContent='XML não encontrado. Reabra o trabalho correto ou gere a entrega novamente.';} $('flow-open-delivery').onclick=async()=>{const button=$('flow-open-delivery');button.disabled=true;try{const d=await U.call('abrir-entrega',{arquivo:result.xml});$('flow-save-status').textContent='XML salvo em: '+d.arquivo;}catch(e){$('flow-save-status').textContent=e.message;}finally{button.disabled=false;}};}
 document.addEventListener('delivery:renamed',e=>{showDelivery(e.detail);$('flow-delivery-status').textContent='XML atualizado com a identificação da entrega. Mídias e cortes preservados.';});
 function clearReviewDelivery(){
  reviewStamp='';
  const panel=$('flow-review-result');
  panel.hidden=true;
  panel.replaceChildren();
 }
 function showReviewDelivery(result){
  const panel=$('flow-review-result');
  const intervals=new Map();
  for(const item of result.pendencias||[]){
   const key=[item.inicio_timeline_frame??item.inicio_ms,item.fim_timeline_frame??item.fim_ms].join('-');
   if(!intervals.has(key))intervals.set(key,item);
  }
  const pending=[...intervals.values()];
  reviewStamp=result.xml_existe?stamp():'';
  panel.innerHTML=`<div class="ux-result"><h3>XML de revisão · pendências de áudio</h3>
  <p class="err"><strong>${pending.length} trecho(s) para tratar.</strong> O áudio original continua ativo nesses pontos. No Premiere, procure os marcadores <strong>PENDÊNCIA DE ÁUDIO</strong>.</p>
  <ul>${pending.map(item=>`<li><strong>${esc(item.timecode_timeline||fmt(item.inicio_ms))}</strong>${item.timecode_timeline?' na sequência':''} · <button type="button" class="ghost" data-review-speech>Revisar em Falas</button></li>`).join('')}</ul>
  <p class="meta">${result.trechos} falas em A3 · ${result.visuais} takes em V2</p>
  ${result.xml_existe?`<div class="links"><a download data-studio-xml="${esc(result.xml)}" href="${url(result.xml)}?dl=1">Salvar XML de revisão</a><a download href="${url(result.json)}?dl=1">Salvar relatório de revisão</a><button type="button" class="ghost" id="flow-open-review-delivery">Abrir pasta do XML</button></div><p class="meta" role="status" id="flow-review-path">${esc(result.xml_nome)}</p>`:'<p class="err">O XML de revisão não foi encontrado. Gere o arquivo novamente.</p>'}</div>`;
  panel.hidden=false;
  panel.querySelectorAll('[data-review-speech]').forEach((button,index)=>{
   button.onclick=()=>focusMention(pending[index]);
  });
  const open=$('flow-open-review-delivery');
  if(open)open.onclick=async()=>{
   try{
    const file=await U.call('abrir-entrega',{arquivo:result.xml});
    const path=$('flow-review-path');if(path)path.textContent=file.arquivo;
   }catch(error){const path=$('flow-review-path');if(path)path.textContent=error.message;}
  };
 }
 async function focusMention(mention){
  await go(3);
  if(current!==3)return;
  const focus=new CustomEvent('mentions:focus-speech',{detail:mention,cancelable:true});
  if(mention.id_fala&&document.dispatchEvent(focus)===false)return;
  $('speech-texts').click();
  document.dispatchEvent(new CustomEvent('mentions:open-review',{detail:mention}));
 }
 function showQuickError(message, action) {
  $('flow-quick-error').textContent = message;
  const button = $('flow-quick-review-mention');
  const mention = action?.tipo === 'revisar_mencao' ? action.trecho : null;
  button.hidden = !mention;
  $('flow-quick-review-xml').hidden=!mention;
  button.onclick=mention?()=>focusMention(mention):null;
 }
 async function startQuick(revisaoPendencias=false){
  if(quickStarting||quickJob||previewJob||U.busy||V.busy)return;
  const project=folder;
  quickStarting=true;sync();
  try{
   await U.flushDraft();if(U.hasDraft()||folder!==project)return;
   showQuickError('');
   await U.save();await V.save();if(folder!==project)return;
   if(!revisaoPendencias)sessionStorage.setItem('ripagem.final-route.'+folder,JSON.stringify({sem_previa:true}));
   const j=await U.call('entrega-rapida',{autoriza_sem_previa:true,preparar_apenas:false,...(revisaoPendencias?{revisao_pendencias:true}:{})});
   if(folder!==project)return;
   quickJob=j.id;sessionStorage.setItem('ripagem.quick',JSON.stringify({id:j.id,folder}));
   $('flow-quick-progress').hidden=false;$('flow-quick-cancel').hidden=false;
   $('flow-quick-step').textContent=revisaoPendencias?'Marcando pendências de áudio no XML…':'Preparando entrega rápida…';
   $('flow-quick-bar').removeAttribute('value');
   pollQuick();
  }catch(e){if(folder===project)showQuickError(e.message);}
  finally{quickStarting=false;sync();}
 }
 $('flow-quick').onclick=()=>startQuick();
 $('flow-quick-review-xml').onclick=()=>{
  $('flow-quick-feedback').before($('flow-quick-progress'));
  return startQuick(true);
 };
 document.addEventListener('delivery:quick-error',e=>showQuickError(e.detail.error,e.detail.acao_erro));
 async function pollQuick(){
  if(!quickJob)return;
  try{
   const j=await fetch('/api/ml/job/'+quickJob).then(r=>r.json());
   $('flow-quick-step').textContent=j.step;
   if(j.status==='na_fila')$('flow-quick-bar').removeAttribute('value');else $('flow-quick-bar').value=j.pct||0;
   if(['na_fila','executando'].includes(j.status)){setTimeout(pollQuick,1500);return;}
   quickJob=null;sessionStorage.removeItem('ripagem.quick');$('flow-quick-cancel').hidden=true;
   if(j.status!=='concluido'){
    try{await V.refresh();}catch{}
    showQuickError(j.error||'Entrega cancelada. Os arquivos anteriores foram mantidos.',j.acao_erro);
    sync();return;
   }
   await window.loadSwapPlan(false);
   if(j.result.revisao_pendencias){
    showReviewDelivery(j.result);
    await go(6);
    $('flow-review-result').scrollIntoView({block:'nearest'});
   }else{
    await go(6);showDelivery(j.result);
    document.dispatchEvent(new CustomEvent('ripagem:xml-ready',{detail:j.result}));
   }
   sync();
  }catch(e){$('flow-quick-step').textContent='Retomando consulta da entrega…';setTimeout(pollQuick,4000);}
 }
 $('flow-quick-cancel').onclick=()=>quickJob&&fetch('/api/ml/job/'+quickJob+'/cancelar',{method:'POST'});
 document.addEventListener('swap:state',sync);document.addEventListener('visual:state',sync);
 document.addEventListener('visual:render',()=>{renderTakeChoices();sync();});
 function renderTakeChoices(){
  const s=V.state;if(!s)return;qa('.flow-take-options').forEach(e=>e.remove());
  qa('[data-flow-cover-row],[data-flow-mark-row]').forEach(e=>e.remove());
  for(const r of s.coverage_markers||[]){const card=make('div','card',`<b>Modo de uso · somente marcação</b><p class="meta">${fmt(r.start)}–${fmt(r.end)} · Antes da primeira menção ao produto. Sem potes em V2; a área vai marcada no XML para adaptação visual.</p>`);card.dataset.flowMarkRow=r.id;$('visual-mentions').append(card);}
  for(const r of s.coverage_mentions||[]){const issue=(s.issues||[]).find(i=>i.mention===r.id),card=make('div','card',`<b>Fala substituída · cobertura do produto</b><p class="meta">${Math.floor(r.start/60000)}:${String(Math.floor(r.start/1000)%60).padStart(2,'0')}–${Math.floor(r.end/60000)}:${String(Math.ceil(r.end/1000)%60).padStart(2,'0')} · imagem original coberta durante a troca de áudio</p>${issue?'<p class="err">'+esc(issue.error)+'</p>':''}`);card.dataset.flowCoverRow=r.id;$('visual-mentions').append(card);}
  qa('[data-visual-row],[data-flow-cover-row]').forEach(card=>{const segments=(s.segments||[]).map((seg,index)=>({...seg,index})).filter(seg=>seg.mention===(card.dataset.visualRow||card.dataset.flowCoverRow));
   const area=make('details','flow-take-options',`<summary>${segments.length} take(s) · conferir ou alterar escolhas</summary>`);
   window.TakeLazy.mount(area,()=>{for(const seg of segments){const prev=s.segments[seg.index-1]?.asset,next=s.segments[seg.index+1]?.asset,frames=seg.end_frame-seg.start_frame;
    const eligible=s.assets.filter(a=>(seg.sorteio_produto?a.uso==='produto':a.kit===seg.kit)&&a.id!==prev&&a.id!==next&&(s.modo_takes!=='recortes'?a.kind==='video'&&(s.modo_takes==='inteiro'?Math.round(a.duration*s.fps)===frames:Math.round(a.duration*s.fps)>=frames):Math.floor((a.kind==='imagem'?s.max_clip_s:Math.min(s.max_clip_s,a.duration))*s.fps+1e-6)>=frames));
    const selected=s.assets.find(a=>a.id===seg.asset),media='/fatiador/visual-media/'+encodeURIComponent(folder)+'/'+seg.asset;const line=make('div','flow-take-line',`${selected?.kind==='imagem'?`<img src="${media}" loading="lazy" alt="Take selecionado" style="width:140px;height:90px;object-fit:contain">`:`<video src="${media}" controls muted preload="none" style="width:140px;height:90px"></video>`}<label>Take ${seg.index+1} · ${seg.sorteio_produto?'Produto sorteado'+(seg.kit?' · Kit '+seg.kit:''):seg.kit===null?'Produto sem kit específico':'Kit '+seg.kit} · ${(frames/s.fps).toFixed(2)} s<select data-flow-take="${seg.index}" ${V.busy?'disabled':''}>${eligible.map(a=>`<option value="${a.id}" ${a.id===seg.asset?'selected':''}>${esc(a.name)}</option>`).join('')}</select></label><button class="ghost" data-flow-reroll="${seg.index}" ${V.busy?'disabled':''}>Sortear só este take</button>`);area.append(line);
   }
    area.querySelectorAll('[data-flow-take]').forEach(e=>e.onchange=()=>V.replace(Number(e.dataset.flowTake),e.value));area.querySelectorAll('[data-flow-reroll]').forEach(e=>e.onclick=()=>V.replace(Number(e.dataset.flowReroll)));
   });card.append(area);
  });
  qa('[data-flow-take]').forEach(e=>e.onchange=()=>V.replace(Number(e.dataset.flowTake),e.value));qa('[data-flow-reroll]').forEach(e=>e.onclick=()=>V.replace(Number(e.dataset.flowReroll)));
 }
 $('reopen').addEventListener('click',e=>{if(V.busy||previewJob||quickJob){e.stopImmediatePropagation();e.preventDefault();$('wizard-error').textContent='Aguarde ou cancele o preparo atual antes de abrir outro trabalho.';}},true);
 $('go').addEventListener('click',e=>{if(U.busy||V.busy||previewJob||quickJob){e.stopImmediatePropagation();e.preventDefault();$('wizard-error').textContent='Aguarde ou cancele a tarefa atual antes de iniciar outra transcrição.';}else setTimeout(sync,0);},true);
 document.addEventListener('ripagem:source-selected',()=>{if(current===2)go(1);sync();});
 const oldLoad=window.loadSwapPlan;window.loadSwapPlan=async(...args)=>{await oldLoad(...args);const pending=JSON.parse(sessionStorage.getItem('ripagem.preview')||'null');if(pending?.folder===folder&&!previewJob){previewJob=pending.id;$('flow-preview-progress').hidden=false;pollPreview();}const pendingQuick=JSON.parse(sessionStorage.getItem('ripagem.quick')||'null');if(pendingQuick?.folder===folder&&!quickJob){quickJob=pendingQuick.id;$('flow-quick-progress').hidden=false;pollQuick();}renderTakeChoices();sync();try{const saved=await U.call('fluxo-estado');if(saved.entrega_atual||saved.entrega?.xml&&!saved.entrega.xml_existe)showDelivery(saved.entrega);if(saved.entrega_revisao_atual)showReviewDelivery(saved.entrega_revisao);if(saved.previa_atual&&!previewJob){const p=saved.previa;reviewSignature=p.assinatura;previewStamp=stamp();$('flow-preview-player').innerHTML=`<p class="meta">Prévia salva neste trabalho · ${p.trechos} trecho(s).</p><${p.video?'video':'audio'} controls preload="none" src="${url(p.arquivo)}" style="width:100%;max-height:480px"></${p.video?'video':'audio'}>`;}sync();}catch(e){$('flow-preview-error').textContent=e.message;}};
 sync();
})();
