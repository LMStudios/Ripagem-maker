/* IDs internos preservados para compatibilidade de projetos/atalhos: 7=legendas, 6=entrega. */
(() => {
 const U=window.SwapUX,R=window.RMJob,$=id=>document.getElementById(id);
 if(!U||!R)return;
 const nav=document.querySelector('.wizard-nav'),captions=nav.querySelector('[data-flow-step="7"]'),delivery=nav.querySelector('[data-flow-step="6"]');
 nav.insertBefore(captions,delivery);captions.textContent='6. Legendas';delivery.textContent='7. Entrega';
 captions.setAttribute('aria-label','Etapa 6 · Legendas');delivery.setAttribute('aria-label','Etapa 7 · Entrega');
 $('wizard-title-5').textContent='Etapa 6 de 7 · Prepare e confira as legendas';$('wizard-title-4').textContent='Etapa 7 de 7 · Entrega completa';
 const go=n=>nav.querySelector(`[data-flow-step="${n}"]`).click();
 const back=document.querySelector('[data-w-panel="5"] [data-w-back]');if(back)back.onclick=()=>go(5);
 const deliveryBack=document.querySelector('[data-w-panel="4"] [data-w-back]');if(deliveryBack)deliveryBack.onclick=()=>go(4);
 const oldNext=document.querySelector('[data-w-panel="4"] [data-w-next]');if(oldNext)oldNext.hidden=true;
 $('flow-finish').textContent='Aprovar prévia e gerar XML →';
 $('flow-quick').textContent='Gerar XML para o Premiere →';
 const quick=$('flow-quick').closest('section');quick.querySelector('h3').textContent='Gerar XML para o Premiere';quick.querySelector('p').textContent='Gera a montagem com os takes e as falas aprovadas. Você pode gerar a legenda separadamente quando precisar.';
 const music=$('editorial-music');if(music){$('wizard-slot-5').prepend(music);music.style.scrollMarginTop='90px';}
 const old=$('flow-delivery-result').closest('section');old.hidden=true;
 const direct=document.createElement('section');direct.className='card';
 direct.innerHTML='<h2>XML para o Premiere</h2><p>Gere o XML com as falas aprovadas e os takes preparados. O tempo é encerrado ao salvar o arquivo. Você pode cuidar da legenda depois.</p><button id="final-xml">Gerar XML para o Premiere</button><div id="final-xml-progress" hidden></div><p id="final-xml-error" class="err" role="alert"></p>';
 $('wizard-slot-4').prepend(direct);
 direct.after($('flow-review-result'));
 const skipCaption=document.createElement('button');skipCaption.type='button';skipCaption.textContent='Pular legenda e gerar XML →';
 $('wizard-slot-5').prepend(skipCaption);
 skipCaption.onclick=async()=>{await wizardStep(4);if(document.querySelector('[data-flow-step="6"]').getAttribute('aria-current')==='step')$('final-xml').click();};
 $('final-xml').onclick=async()=>{
  if(U.busy||busy)return;
  const button=$('final-xml');button.disabled=true;busy=true;$('final-xml-error').textContent='';
  document.dispatchEvent(new CustomEvent('delivery:quick-error',{detail:{error:''}}));
  const work=folder;
  try{
   if(await U.flushDraft()===false||U.hasDraft())throw Error('Aguarde o salvamento das falas.');
   await U.save();await window.VisualUX.save();
   const job=await U.call('entrega-rapida',{autoriza_sem_previa:true,preparar_apenas:false});
   R.watch(job,$('final-xml-progress'),{
    onDone:result=>{busy=false;if(folder===work){document.dispatchEvent(new CustomEvent('delivery:quick-error',{detail:{error:''}}));document.dispatchEvent(new CustomEvent('ripagem:xml-ready',{detail:result}));window.loadSwapPlan(false);refresh();}button.disabled=false;return '<p>XML gerado. Use os botões abaixo para salvar ou abrir a pasta.</p>';},
    onError:j=>{
     busy=false;button.disabled=false;
     if(folder===work&&j.acao_erro?.tipo==='revisar_mencao'){
      direct.append($('flow-quick-feedback'));
      document.dispatchEvent(new CustomEvent('delivery:quick-error',{detail:{...j,error:''}}));
     }
    }
   });
  }catch(e){busy=false;button.disabled=false;$('final-xml-error').textContent=e.message;}
 };
 document.addEventListener('ripagem:xml-ready',e=>{
  const result=e.detail;if(!result?.xml_existe)return;
  const links=document.createElement('div');links.className='links';
  for(const [key,label] of [['xml','Salvar XML'],['json','Salvar relatório']]){
   if(!result[key])continue;const a=document.createElement('a');a.textContent=label;a.href=url(result[key])+'?dl=1';a.setAttribute('download','');if(key==='xml')a.dataset.studioXml=result.xml;links.append(a);
  }
  const open=document.createElement('button');open.className='ghost';open.textContent='Abrir pasta do XML';
  open.onclick=async()=>{try{await U.call('abrir-entrega',{arquivo:result.xml});}catch(e){$('final-xml-error').textContent=e.message;}};
  const target=document.createElement('p');target.className='meta';target.textContent=result.xml_absoluto||result.xml;
  let output=$('final-xml-files');if(!output){output=document.createElement('div');output.id='final-xml-files';direct.append(output);}
  output.replaceChildren(links,open,target);
 });
 const make=(tag,cls,html)=>{const n=document.createElement(tag);n.className=cls;n.innerHTML=html;return n;};
 const check=make('section','card','<h3>Conferir a legenda antes de entregar</h3><p>Gere o SRT da montagem acima ou envie o SRT final no corretor. A entrega só fica pronta com a legenda atual, conferida e sem resíduos dos nomes antigos informados.</p><label class="op-auto-choice"><input type="checkbox" id="final-caption-check"> Conferi o texto e os tempos da legenda desta montagem</label><button id="final-caption-save">Confirmar legenda e gerar entrega →</button><p id="final-caption-status" role="status" class="meta"></p>');$('wizard-slot-5').append(check);
 const final=make('section','card final-delivery','<h2>Entrega final</h2><p>Confira todos os materiais antes de salvar. Alterações na montagem ou na legenda exigem uma nova conferência.</p><div id="final-checklist" role="status"></div><button type="button" id="final-choose-music" hidden>Escolher trilha →</button><label class="op-auto-choice" id="final-skip-choice"><input type="checkbox" id="final-skip"> Autorizo preparar a entrega sem assistir à prévia</label><div class="links"><button id="final-build">Preparar entrega completa para o Premiere</button><button class="ghost" id="final-caption-back">Conferir legendas</button></div><div id="final-progress" hidden></div><div id="final-files"></div><p id="final-error" role="alert" class="err"></p>');$('wizard-slot-4').prepend(final);
 if($('graphite-completion'))$('flow-review-result').after($('graphite-completion'));
 const complete=document.createElement('details');complete.className='card';complete.innerHTML='<summary>Opcional · entregar também a legenda conferida</summary>';final.before(complete);complete.append(final);
 const file=p=>'/files/'+[folder,...p.replaceAll('\\','/').split('/')].map(encodeURIComponent).join('/');
 let last=null,busy=false,loading=false,queued=null,scope='',interval=null,captionStamp='',filesStamp='',watcher=null;
 function route(){try{return JSON.parse(sessionStorage.getItem('ripagem.final-route.'+folder)||'null');}catch{return null;}}
 function links(result){
  if(!result?.completa||!result.xml_existe||!result.legenda)return;
  const stamp=JSON.stringify(result);if(filesStamp===stamp)return;filesStamp=stamp;
  $('final-files').innerHTML=`<p><b>Materiais confirmados no projeto</b></p><div class="links">${result.pacote?`<a class="btn pri" download data-studio-xml="${R.esc(result.xml)}" href="${file(result.pacote)}?dl=1">Baixar entrega · XML + SRT</a>`:''}<a class="btn ${result.pacote?'':'pri'}" download data-studio-xml="${R.esc(result.xml)}" href="${file(result.xml)}?dl=1">Salvar XML</a><a class="btn" download href="${file(result.legenda_entrega||result.legenda)}?dl=1">Salvar legenda final SRT</a><a class="btn" download href="${file(result.json)}?dl=1">Salvar relatório</a>${result.video?`<a class="btn" download href="${file(result.video)}?dl=1">Salvar vídeo legendado</a>`:""}<button class="ghost" id="final-open">Abrir pasta da entrega</button></div><p class="meta">${R.esc(result.xml_absoluto||result.xml)}</p><p class="meta">Premiere → Arquivo → Importar → selecione o XML e o SRT final. As mídias continuam nas pastas do projeto.</p>`;
  $('final-open').onclick=async()=>{try{await U.call('abrir-entrega',{arquivo:result.xml});}catch(e){$('final-error').textContent=e.message;}};
 }
 async function refresh(){
  if(!folder||loading)return;loading=true;const work=folder;
  try{
   const d=await U.call('finalizacao-estado');if(folder!==work)return;last=d;
   $('final-xml').disabled=busy||U.busy;

   if(scope!==folder){scope=folder;captionStamp='';filesStamp='';busy=false;watcher?.stop();$('final-progress').hidden=true;$('final-skip').checked=false;$('final-caption-check').checked=false;$('final-files').innerHTML='';$('final-error').textContent='';}
   const needsMusic=d.trilha_pendente??(U.plan&&(!U.plan.trilha?.modo||U.plan.trilha.modo==='nao_definida'));
   $('final-choose-music').hidden=!needsMusic;
   if(needsMusic&&music&&captions.getAttribute('aria-current')==='step')music.open=true;
   if(d.xml_atual&&d.entrega?.xml_existe)document.dispatchEvent(new CustomEvent('ripagem:xml-ready',{detail:d.entrega}));
   else $('final-xml-files')?.replaceChildren();
   $('final-caption-check').disabled=!d.legenda||busy||needsMusic;
   if(captionStamp!==(d.legenda?.assinatura||'')){captionStamp=d.legenda?.assinatura||'';$('final-caption-check').checked=d.legenda_conferida;}else if(d.legenda_conferida)$('final-caption-check').checked=true;
   $('final-caption-save').disabled=!d.legenda||busy||needsMusic||!$('final-caption-check').checked;
   $('final-caption-status').textContent=needsMusic?'Escolha e salve a trilha no início desta etapa.':!d.legenda?'Prepare uma legenda atual para liberar a confirmação.':d.legenda_conferida?'Legenda conferida para esta montagem.':`${d.legenda.avisos} aviso(s) na geração. Confira o SRT antes de confirmar.`;
   captions.dataset.state=d.legenda_conferida?'ready':'pending';
   captions.title='Abrir legendas opcionais';delivery.title='Abrir entrega';delivery.dataset.state=d.entrega?.atual?'ready':'pending';
   $('final-checklist').innerHTML=d.pronto?'<p class="rm-ok">✓ Falas, takes, busca visual e legenda conferidos.</p>':'<ul>'+d.pendencias.map(p=>`<li>${R.esc(p)}</li>`).join('')+'</ul>';
   $('final-build').disabled=!d.pronto||busy;
   const r=route();$('final-skip-choice').hidden=!!r&&!r.sem_previa;
   if(d.entrega?.completa&&d.entrega.atual&&d.pronto)links(d.entrega);else {filesStamp='';$('final-files').innerHTML='';}
  }catch(e){$('final-error').textContent=e.message;$('final-build').disabled=true;}
  finally{loading=false;}
 }
 $('final-caption-check').onchange=async()=>{const checked=$('final-caption-check').checked;$('final-caption-save').disabled=!checked;if(!checked&&last?.legenda_conferida){try{await U.call('finalizacao-confirmar',{conferida:false});await refresh();}catch(e){$('final-caption-status').textContent=e.message;}}};
 $('final-caption-save').onclick=async e=>{
  e.target.disabled=true;try{await U.call('finalizacao-confirmar',{conferida:$('final-caption-check').checked});await refresh();go(6);
   const r=route();
   if(r&&last?.pronto&&!last.entrega?.atual){
    if(r.sem_previa)$('final-skip').checked=true;
    $('final-build').click();
   }}catch(error){$('final-caption-status').textContent=error.message;}finally{e.target.disabled=false;}
 };
 $('final-caption-back').onclick=()=>go(7);
 $('final-choose-music').onclick=()=>document.dispatchEvent(new Event('ripagem:escolher-trilha'));
 $('final-build').onclick=async()=>{
  if(busy)return;busy=true;$('final-build').disabled=true;$('final-error').textContent='';
  try{
   if(await U.flushDraft()===false||U.hasDraft())throw Error('Aguarde o salvamento das falas.');
   const r=route();const skip=!r||r.sem_previa;
   if(skip&&!$('final-skip').checked)throw Error('Autorize explicitamente seguir sem prévia ou confira a prévia na etapa 5.');
   const work=folder;const job=await U.call('finalizacao-entregar',{sem_previa:skip,autoriza_sem_previa:skip&&$('final-skip').checked,assinatura:r?.assinatura});
   watcher=R.watch(job,$('final-progress'),{onDone:result=>{busy=false;if(work===folder)links(result);refresh();document.dispatchEvent(new CustomEvent('swap:render'));return '<p>Entrega completa preparada com a legenda conferida.</p>';},onError:()=>{busy=false;refresh();}});
  }catch(e){busy=false;$('final-error').textContent=e.message;await refresh();}
 };
 function schedule(){clearTimeout(queued);queued=setTimeout(refresh,350);}
 new MutationObserver(schedule).observe(nav,{subtree:true,attributes:true,attributeFilter:['aria-current']});
 for(const id of ['sub-result','srt-correction-result'])if($(id))new MutationObserver(schedule).observe($(id),{childList:true,subtree:true});
 for(const event of ['swap:render','swap:finished','visual:state','ripagem:trilha-salva'])document.addEventListener(event,schedule);
 interval=setInterval(()=>{if(delivery.getAttribute('aria-current')==='step'||captions.getAttribute('aria-current')==='step')refresh();},5000);
 window.addEventListener('pageshow',e=>{if(e.persisted){interval=setInterval(refresh,5000);refresh();}});
 window.addEventListener('pagehide',()=>{clearInterval(interval);clearTimeout(queued);});
})();
