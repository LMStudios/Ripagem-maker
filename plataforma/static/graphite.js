/* Studio Grafite: orientação contextual e tempo persistido. Não autoriza operações. */
(() => {
 const $=id=>document.getElementById(id), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const request=async(path,body)=>{const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});let d={};try{d=await r.json();}catch{}if(!r.ok)throw Error(d.erro||'Não foi possível acessar o app.');return d;};
 const time=min=>{if(min===null||min===undefined)return 'Não registrado';const n=Math.max(0,Math.round(min));return n>=60?`${Math.floor(n/60)}h${n%60?String(n%60).padStart(2,'0'):''}`:`${n} min`;};
 const make=(tag,cls,html)=>{const n=document.createElement(tag);n.className=cls;n.innerHTML=html;return n;};
 window.GraphiteStudio={formatTime:time};

 // Uma tela independente de preferências; as credenciais continuam nos Ajustes existentes.
 if(typeof routes!=='undefined') {
  routes['/studio']=async()=>{
   const d=await request('/api/studio/preferencias');
   document.querySelector('#view').innerHTML=`<div class="page-h"><div><h1>Experiência Studio</h1><p>Orientações e estimativa de tempo do seu processo.</p></div><a class="btn" href="#/ajustes">Todos os ajustes</a></div><div class="graphite-settings-layout"><section class="card graphite-settings"><h2>Economia de tempo</h2><p>Comparação estimada com a edição manual. O tempo no app é medido por projeto, da seleção do arquivo até salvar o XML, incluindo processamento e revisão.</p><div class="row"><label>Minutos por menção<input id="graphite-rate" type="number" min="0" max="1440" step="0.5" value="${d.minutos_por_mencao}"></label><label>Acréscimo por projeto com modo de uso (min)<input id="graphite-usage" type="number" min="0" max="1440" value="${d.minutos_modo_uso}"></label></div><p class="meta">Padrão: 5 minutos por menção (12 por hora) + 60 minutos quando há adaptação do modo de uso. Projetos anteriores à medição não recebem um percentual inventado.</p><button id="graphite-save">Salvar parâmetros</button><p id="graphite-settings-status" role="status"></p></section><section class="card"><h2>Aprender a usar</h2><p>O guia acompanha as etapas de um trabalho real. Você pode sair a qualquer momento.</p><a class="btn pri" href="/fatiador?guia=1">Abrir troca de potes com tutorial</a></section></div>`;
   $('graphite-save').onclick=async e=>{e.target.disabled=true;try{await request('/api/studio/preferencias',{minutos_por_mencao:Number($('graphite-rate').value),minutos_modo_uso:Number($('graphite-usage').value)});$('graphite-settings-status').textContent='Parâmetros salvos. A comparação usa estes valores.';}catch(error){$('graphite-settings-status').textContent=error.message;}finally{e.target.disabled=false;}};
  };
  const nav=document.querySelector('.nav');if(nav&&!nav.querySelector('[data-r="/studio"]'))nav.append(make('a','','Experiência Studio'));
  const a=nav?.lastElementChild;if(a?.textContent==='Experiência Studio'){a.href='#/studio';a.dataset.r='/studio';}
  if(location.hash==='#/studio')requestAnimationFrame(()=>render());
 }

 document.addEventListener('ripagem:source-selected',()=>{window.RMStudioStarted=Date.now();});
 const U=window.SwapUX;
 if(!U)return;
 const nav=document.querySelector('.wizard-nav');
 const help=make('div','graphite-help','<span class="graphite-time" id="graphite-clock">Tempo do projeto · aguardando arquivo</span><button type="button" class="ghost" id="graphite-pause" hidden>Pausar medição</button><button type="button" class="ghost" id="graphite-help">Como usar</button>');nav.before(help);
 // A localização continua acessível sem ocupar o centro de cada etapa.
 const optimize=$('optimize-card');if(optimize)$('drop').closest('section').after(optimize);
 const locationCard=$('project-location');
 if(locationCard&&!locationCard.querySelector('details')){const details=make('details','','<summary>Pasta e organização do projeto</summary>');details.append(...locationCard.childNodes);locationCard.append(details);}
 let lastRefresh=0;
 let prefs=null,guided=false,dismissed='',tour=null,target=null,lastContext='',timing=null,refreshing=false,summaryStamp='',timerScope='',pendingTimer=null,closed=false;
 const current=()=>{try{return folder||'';}catch{return '';}};
 const context=()=>{
  const step=document.querySelector('[data-flow-step][aria-current=step]')?.dataset.flowStep||'1';
  const sub=step==='3'?($('speech-generate')?.getAttribute('aria-current')==='step'?'gerar':$('speech-listen')?.getAttribute('aria-current')==='step'?'ouvir':'textos'):'';
  return step+(sub?'-'+sub:'');
 };
 const guides={
  '1':['Comece pelo arquivo','Arraste o vídeo ou áudio, confira o nome selecionado e clique em Continuar para transcrição. Seu arquivo só será processado depois da confirmação.','#drop'],
  '2':['Prepare a transcrição','Informe o novo produto e escolha a parte a analisar. A transcrição usa sua integração configurada; confirme antes de iniciar.','#novo'],
  '3-textos':['Confira o que vai mudar','Revise os textos e o modo de uso. Aprovar textos leva à preparação das vozes; ainda não gera áudios automaticamente.','#flow-approve-texts'],
  '3-gerar':['Prepare e gere as vozes','Confira as amostras, os speakers e as autorizações. A geração pode consumir créditos do serviço selecionado.','#ux-voice-stage'],
  '3-ouvir':['Ouça os resultados','Compare os áudios, resolva alertas e aprove os que serão utilizados. Depois, continue para os takes.','#swap-controls'],
  '4':['Escolha os takes','Selecione a pasta dos materiais. O app associa e distribui os takes; confira pendências ou autorize as alternativas disponíveis.','#visual-root'],
  '5':['Confira a montagem','A prévia reúne os trechos alterados. Você também pode usar a entrega rápida, autorizando explicitamente seguir sem assistir.','#flow-preview-generate'],
  '6':['Leve o trabalho ao Premiere','Confirme a entrega, salve o XML e abra a pasta. No Premiere, use Arquivo → Importar e abra a sequência importada.','#flow-delivery-result'],
  '7':['Prepare a legenda quando precisar','Gere o SRT da montagem ou corrija o SRT final e confira texto e tempos.','#srt-file']
 };
 function removeTour(){tour?.remove();tour=null;target?.classList.remove('graphite-tour-target');target=null;}
 function showGuide(){
  const key=context();if(!guided||dismissed===key)return;
  if(tour&&lastContext===key)return;
  removeTour();lastContext=key;
  const g=guides[key]||guides['1'];target=document.querySelector(g[2]);
  if(target&&!target.closest('[hidden]'))target.classList.add('graphite-tour-target');
  tour=make('aside','graphite-tour',`<span class="graphite-tag">Modo guiado · etapa ${esc(key.split('-')[0]==='6'?'7':key.split('-')[0]==='7'?'6':key.split('-')[0])}</span><h3>${esc(g[0])}</h3><p>${esc(g[1])}</p><div class="links"><button type="button" data-tour-next>${key==='6'?'Concluir guia':'Entendi'}</button><button type="button" class="ghost" data-tour-exit>Sair do tutorial</button></div>`);
  tour.setAttribute('aria-label','Orientação da etapa atual');nav.after(tour);
  tour.querySelector('[data-tour-next]').onclick=()=>{dismissed=key;removeTour();if(key==='6')guided=false;};
  tour.querySelector('[data-tour-exit]').onclick=()=>{guided=false;removeTour();};
 }
 async function onboarding(force=false){
  if(document.querySelector('dialog[open]'))return;
  if(!prefs)prefs=await request('/api/studio/preferencias');
  if(!force&&prefs.tutorial!==null)return;
  const dialog=make('dialog','graphite-dialog','<span class="graphite-tag">Bem-vindo ao Studio</span><h2>Como você prefere começar?</h2><p>Conheça a troca de potes enquanto prepara sua primeira ripagem. Você pode reabrir o guia em Como usar.</p><div class="graphite-choice"><button type="button" id="graphite-guided">Quero ser guiado</button><button type="button" class="ghost" id="graphite-direct">Começar direto</button></div><p id="graphite-intro-error" role="status"></p>');document.body.append(dialog);dialog.showModal();
  const choose=async mode=>{const buttons=[...dialog.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);try{prefs=await request('/api/studio/preferencias',{tutorial:mode});guided=mode==='guiado';dismissed='';dialog.close();dialog.remove();if(guided)showGuide();$('graphite-help').focus();}catch(e){dialog.querySelector('[role=status]').textContent=e.message;buttons.forEach(b=>b.disabled=false);}};
  $('graphite-guided').onclick=()=>choose('guiado');$('graphite-direct').onclick=()=>choose('direto');
  dialog.addEventListener('cancel',e=>{e.preventDefault();choose('direto');});
 }
 $('graphite-help').onclick=()=>onboarding(true).catch(e=>{$('graphite-clock').textContent=e.message;});
 request('/api/ajustes').then(d=>{if(d.configuracao_inicial&&d.pasta_disponivel)onboarding(new URLSearchParams(location.search).get('guia')==='1').catch(()=>{});});
 document.addEventListener('ripagem:storage-configured',()=>onboarding().catch(()=>{}));
 const navObserver=new MutationObserver(showGuide);navObserver.observe(nav,{subtree:true,attributes:true,attributeFilter:['aria-current']});
 for(const id of ['speech-texts','speech-generate','speech-listen'])$(id)?.addEventListener('click',showGuide);

 const box=make('section','graphite-delivery','');box.id='graphite-completion';box.hidden=true;$('flow-delivery-result')?.before(box);
 function completion(d){
  if(!d.medicao_encerrada){box.hidden=true;summaryStamp='';return;}
  const stamp=JSON.stringify(d);if(stamp===summaryStamp)return;summaryStamp=stamp;box.hidden=false;
  const positive=d.economia_min>0, has=d.economia_min!==null;
  const heading=has?(d.economia_min===0?'Tempo equivalente à estimativa manual':positive?`${time(d.economia_min)} de economia estimada`:`${time(Math.abs(d.economia_min))} além da estimativa manual`):'Tempo no app não registrado desde o início';
  const ratio=d.manual_min>0&&d.app_min!==null?Math.max(0,Math.min(100,d.app_min/d.manual_min*100)):0;
  box.innerHTML=`<div><h2>Tempo finalizado</h2><p>${esc(U.plan?.produto||'')} → ${esc(U.plan?.produto_novo||'')}</p><p>${d.mencoes} trechos únicos adaptados${d.modo_uso?' · modo de uso adaptado':''}</p><p class="graphite-file">${esc(d.xml_salvo||d.xml)}</p><p class="meta">${d.xml_de_revisao?'XML de revisão salvo. Confira as pendências no Premiere.':'XML salvo para o Premiere. Você pode preparar a legenda depois.'}</p></div><div class="graphite-comparison"><p class="saved">${esc(heading)}</p>${has&&d.percentual!==null?`<p class="percent">${Math.abs(d.percentual).toLocaleString('pt-BR')}% ${positive?'menos':'mais'} tempo</p>`:''}<p>Manual estimado · ${time(d.manual_min)}</p><div class="graphite-track"><i style="width:100%"></i></div><p>Tempo no app${d.completa?'':' · parcial'} · ${time(d.app_min)}</p><div class="graphite-track"><i style="width:${ratio}%"></i></div><details><summary>Como calculamos</summary><p>${d.mencoes} trechos × ${d.parametros.minutos_por_mencao} min${d.modo_uso?' + '+d.parametros.minutos_modo_uso+' min por modo de uso':''}. ${esc(d.referencia)} Não é uma garantia de produtividade.</p><a href="/#/studio">Ajustar parâmetros</a></details></div>`;
 }
 function applyTiming(project,d){
  if(project!==current()||(timerScope===project&&timing?.medicao_encerrada&&!d.medicao_encerrada))return;
  timing=d;timerScope=project;
  $('graphite-clock').textContent=`${d.medicao_encerrada?'Tempo finalizado':'Tempo no app'} · ${time(d.app_min)}${d.completa?'':' · parcial'}${d.pausado&&!d.medicao_encerrada?' · pausado':''}`;
  $('graphite-clock').title=d.referencia;
  $('graphite-pause').hidden=d.medicao_encerrada;$('graphite-pause').textContent=d.pausado?'Retomar medição':'Pausar medição';
  completion(d);
 }
 document.addEventListener('ripagem:studio-saved',event=>applyTiming(event.detail.folder,event.detail.summary));
 async function refresh(paused){
  const f=current();if(!f||refreshing||closed)return;refreshing=true;lastRefresh=Date.now();
  try{
   const d=await U.call('studio-tempo',{...(paused===undefined?{}:{pausado:paused})});
   applyTiming(f,d);
  }catch(e){if(f===current()&&(timerScope!==f||!timing?.medicao_encerrada))$('graphite-clock').textContent='Medição indisponível · '+e.message;}
  finally{refreshing=false;}
 }
 $('graphite-pause').onclick=async e=>{e.target.disabled=true;try{await refresh(!timing?.pausado);}finally{e.target.disabled=false;}};
 function changed(){
  showGuide();if(timerScope!==current()){summaryStamp='';box.hidden=true;}
  clearTimeout(pendingTimer);pendingTimer=setTimeout(()=>{if(timerScope!==current()||Date.now()-lastRefresh>3000)refresh();},350);
 }
 for(const event of ['swap:render','swap:step','swap:finished','visual:state'])document.addEventListener(event,changed);
 // Apenas uma atualização por janela a cada 10 s; o servidor agrega sem duplicar o tempo.
 let interval=setInterval(()=>refresh(),10000), closedAt=0;
 window.addEventListener('pagehide',()=>{closedAt=Date.now();const f=current();if(f)navigator.sendBeacon('/fatiador/trocas/studio-tempo',new Blob([JSON.stringify({folder:f,encerrar:true})],{type:'application/json'}));closed=true;clearInterval(interval);clearTimeout(pendingTimer);navObserver.disconnect();removeTour();});
 window.addEventListener('pageshow',e=>{if(!e.persisted)return;closed=false;if(window.RMStudioStarted&&closedAt)window.RMStudioStarted+=Date.now()-closedAt;clearInterval(interval);interval=setInterval(()=>refresh(),10000);navObserver.observe(nav,{subtree:true,attributes:true,attributeFilter:['aria-current']});refresh();});
 // Uma entrega pode terminar sem renderizar novamente a lista de falas.
 const deliveryObserver=new MutationObserver(()=>{clearTimeout(pendingTimer);pendingTimer=setTimeout(()=>refresh(),150);});
 if($('flow-delivery-result'))deliveryObserver.observe($('flow-delivery-result'),{childList:true});
})();
