/* One recommended action; settings are optional and work never blocks view tabs. */
(() => {
 const U=window.SwapUX,$=id=>document.getElementById(id);if(!U)return;
 const wrap=$('ux-voice-stage'),voices=$('swap-voices');
 const brief=document.createElement('section');brief.className='voice-brief';brief.innerHTML='<h3 id="voice-main-title">Preparar falas</h3><p id="voice-main-info" class="meta"></p><button type="button" id="voice-next">Continuar</button><p id="voice-last-result" class="meta" role="status"></p>';
 const settings=document.createElement('details');settings.id='voice-settings';settings.innerHTML='<summary id="voice-settings-title">Configurar vozes</summary>';
 voices.before(brief,settings);settings.append(voices);$('ux-voice-gate').hidden=true;
 const advanced=document.createElement('details');advanced.id='voice-advanced';advanced.innerHTML='<summary>Ajustes de duração e regeneração</summary>';advanced.append($('swap-duration-panel'));
 advanced.append($('swap-regenerate').closest('label'),$('swap-autofit').closest('label'));voices.append(advanced);
 const help=document.createElement('details');help.className='voice-help';help.innerHTML='<summary>Como funciona a geração</summary>';
 [...voices.children].filter(n=>n.tagName==='P'&&!n.id).forEach(n=>help.append(n));voices.append(help);
 brief.after($('swap-inline-progress'));let work='',missingBefore=null;
 function state(){
  const p=U.plan;if(!p)return;const selected=p.itens.filter(r=>r.aprovado),missing=selected.filter(r=>!r.audio?.fit),listen=selected.filter(r=>r.audio?.fit&&!r.audio.aprovado);
  if(work!==folder){work=folder;settings.open=missing.length>0;missingBefore=missing.length;$('voice-last-result').textContent='';}
  if(missingBefore>0&&!missing.length&&!U.busy)settings.open=false;missingBefore=missing.length;
  $('voice-main-title').textContent=U.busy?'Trabalho em andamento':!selected.length?'Selecione os textos':missing.length?missing.length+(missing.length===1?' fala para preparar':' falas para preparar'):'Os áudios estão prontos';
  $('voice-main-info').textContent=U.busy?'Você pode alternar entre textos, geração e aprovação. Aguarde para editar.':!selected.length?'Escolha os textos em 3.1 antes de gerar as vozes.':missing.length?'Configure as vozes abaixo. As falas já prontas serão mantidas.':listen.length?listen.length+' áudios aguardam sua aprovação. Você não precisa gerar nem preparar tudo novamente.':'Todos os '+selected.length+' áudios selecionados estão aprovados. Continue para os takes.';
  const b=$('voice-next');b.hidden=U.busy;b.textContent=!selected.length?'Conferir textos':missing.length?'Configurar e gerar falas':listen.length?'Ouvir e aprovar '+listen.length+' áudios':'Continuar para os takes';
  b.onclick=()=>{if(!selected.length)$('speech-texts').click();else if(missing.length){settings.open=true;settings.scrollIntoView({block:'start',behavior:'smooth'});}else if(listen.length)$('speech-listen').click();else document.querySelector('[data-flow-step="4"]').click();};
  $('voice-settings-title').textContent=missing.length?'Vozes e geração':'Opções de voz · gerar novamente';
 }
 document.addEventListener('swap:state',state);document.addEventListener('swap:render',state);
 document.addEventListener('swap:finished',e=>{if(e.detail.status==='concluido'){$('voice-last-result').textContent='Concluído. Seus áudios foram salvos.';state();}});
 // Keep duration actions out of the main path, but reveal the setting if it changed.
 $('swap-duration-mode').addEventListener('change',()=>{advanced.open=true;});
 document.addEventListener('swap:step',state);state();
})();
