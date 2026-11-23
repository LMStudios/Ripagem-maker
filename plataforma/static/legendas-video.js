/* Vídeo com legendas na imagem: preset, estilo recolhido, prévia de 15 s e render completo cancelável. */
(() => {
  const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const anchor=$('subtitles-panel');if(!anchor)return;
  let state=null,scope='',running=null,timer=null;
  const file=p=>'/files/'+encodeURIComponent(scope)+'/'+p.split('/').map(encodeURIComponent).join('/');
  const post=async(action,body={})=>{const r=await fetch('/fatiador/trocas/legendas-video-'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder:scope,...body})});const d=await r.json();if(!r.ok)throw Error(d.erro||'Não foi possível concluir.');return d;};
  const field=(key,label,type='number',extra='')=>`<label>${label}<input data-st="${key}" type="${type}" ${extra}></label>`;
  const card=document.createElement('div');card.className='card';card.id='subtitle-video-panel';
  card.innerHTML=`<h3>Vídeo com legendas na imagem</h3>
  <p class="meta">Renderiza a montagem final (V1, V2, falas novas e margens removidas) com as legendas do SRT acima aplicadas na imagem. Confira a prévia de 15 s antes do vídeo inteiro.</p>
  <p id="sv-block" class="meta" role="status"></p>
  <label>Estilo<select id="sv-preset"></select></label>
  <details id="sv-custom"><summary>Personalizar estilo</summary>
   <h4>Texto</h4><div class="row"><label>Fonte<select data-st="fonte" id="sv-font"></select></label>${field('tamanho','Tamanho (% da altura)','number','min="1" max="20" step="0.1"')}${field('cor','Cor','color')}${field('cor_destaque','Cor do destaque','color')}</div>
   <div class="row"><label style="flex-direction:row;gap:6px"><input data-st="negrito" type="checkbox"> Negrito</label><label style="flex-direction:row;gap:6px"><input data-st="italico" type="checkbox"> Itálico</label><label style="flex-direction:row;gap:6px"><input data-st="maiusculas" type="checkbox"> Maiúsculas</label></div>
   <h4>Contorno, sombra e fundo</h4><div class="row">${field('contorno','Contorno (%)','number','min="0" max="3" step="0.05"')}${field('cor_contorno','Cor do contorno','color')}${field('sombra','Sombra (%)','number','min="0" max="3" step="0.05"')}${field('cor_sombra','Cor da sombra','color')}${field('opacidade_sombra','Opacidade da sombra','number','min="0" max="1" step="0.05"')}</div>
   <div class="row"><label style="flex-direction:row;gap:6px"><input data-st="fundo" type="checkbox"> Caixa de fundo</label>${field('cor_fundo','Cor do fundo','color')}${field('opacidade_fundo','Opacidade do fundo','number','min="0" max="1" step="0.05"')}</div>
   <h4>Posição</h4><div class="row"><label>Posição<select data-st="posicao"><option value="inferior">Inferior</option><option value="meio">Meio</option><option value="superior">Superior</option></select></label><label>Alinhamento<select data-st="alinhamento"><option value="centro">Centro</option><option value="esquerda">Esquerda</option><option value="direita">Direita</option></select></label>${field('margem_vertical','Margem vertical (%)','number','min="0" max="45" step="0.5"')}${field('margem_lateral','Margem lateral (%)','number','min="0" max="30" step="0.5"')}</div>
   <h4>Blocos</h4><div class="row"><label>Exibição<select data-st="exibicao"><option value="frase">Por frase</option><option value="destaque">Frase com a palavra falada em destaque</option><option value="palavras">Poucas palavras por vez</option></select></label>${field('palavras_bloco','Palavras por bloco','number','min="1" max="8"')}${field('caracteres_linha','Caracteres por linha','number','min="12" max="80"')}<label>Linhas<select data-st="linhas"><option>1</option><option>2</option><option>3</option></select></label></div>
   <div class="row"><label>Salvar como preset<input id="sv-preset-name" placeholder="Ex.: VSL vertical amarela"></label><button class="ghost" id="sv-preset-save">Salvar preset</button><button class="ghost" id="sv-preset-delete">Excluir preset selecionado</button></div>
  </details>
  <p id="sv-note" class="meta"></p>
  <div class="row"><label>Início da prévia (vazio = primeira legenda)<input id="sv-start" placeholder="ex.: 36:05"></label><button class="ghost" id="sv-preview">Prévia de 15 s</button><button id="sv-render">Renderizar vídeo completo</button></div>
  <div id="sv-progress" hidden><p id="sv-step" role="status"></p><progress id="sv-bar" max="100" style="width:100%"></progress><button class="ghost" id="sv-cancel">Cancelar · blocos prontos ficam guardados</button></div>
  <p id="sv-error" role="alert" class="err"></p><div id="sv-player"></div><div id="sv-result"></div>`;
  anchor.after(card);
  const inputs=()=>[...card.querySelectorAll('[data-st]')];
  function fill(style){inputs().forEach(e=>{const v=style[e.dataset.st];if(e.type==='checkbox')e.checked=!!v;else if(v!==undefined)e.value=e.type==='color'?String(v).toLowerCase():v;});note();}
  function read(){const s={};inputs().forEach(e=>{const k=e.dataset.st;s[k]=e.type==='checkbox'?e.checked:e.type==='number'?Number(e.value):k.startsWith('cor')?e.value.toUpperCase():e.value;});return s;}
  function note(){const style=read(),msgs=[];if(state?.so_coberturas)msgs.push('Legenda só onde a imagem foi coberta (vídeo original com legendas gravadas), como no SRT.');if(style.exibicao==='destaque'&&state&&!state.palavras_confiaveis)msgs.push('O alinhamento por palavra ficou abaixo de 90%: o destaque será trocado por legenda por frase.');$('sv-note').textContent=msgs.join(' ');}
  function presets(){const p=state.presets,opt=(g,n)=>`<option value="${g}:${esc(n)}">${esc(n)}</option>`;$('sv-preset').innerHTML='<option value="">Estilo atual deste trabalho</option><optgroup label="Padrões">'+Object.keys(p.padrao).map(n=>opt('padrao',n)).join('')+'</optgroup>'+(Object.keys(p.meus).length?'<optgroup label="Meus presets">'+Object.keys(p.meus).map(n=>opt('meus',n)).join('')+'</optgroup>':'');}
  function render(){
    if(!state)return;const fonts=new Set([...(state.fontes||[]),state.estilo.fonte]);$('sv-font').innerHTML=[...fonts].map(f=>`<option>${esc(f)}</option>`).join('');
    presets();fill(state.estilo);$('sv-block').innerHTML=state.bloqueio?'<b>'+esc(state.bloqueio)+'</b>':'';['sv-preview','sv-render'].forEach(id=>$(id).disabled=!!state.bloqueio||!!running);
    const p=state.previa,f=state.final;
    $('sv-player').innerHTML=p?`<video controls preload="metadata" style="max-width:100%;max-height:420px" src="${file(p.arquivo)}"></video><p class="meta">Prévia de 15 s a partir de ${Math.floor(p.inicio/60)}:${String(Math.floor(p.inicio%60)).padStart(2,'0')}${p.atual===false?' · <b>estilo ou montagem mudaram depois desta prévia</b>':''}.</p>`:'';
    $('sv-result').innerHTML=f?`<p>${f.atual===false?'<b>Desatualizado:</b> o estilo ou a montagem mudaram. ':''}Vídeo com legendas: ${Math.floor(f.duracao_s/60)} min ${Math.round(f.duracao_s%60)} s · ${f.blocos} blocos${f.blocos_reaproveitados?` (${f.blocos_reaproveitados} reaproveitados)`:''}.</p><p><a download href="${file(f.arquivo)}?dl=1">Salvar vídeo com legendas</a> · <span class="meta">${esc(f.arquivo.split('/').pop())}</span></p>`:'';
  }
  const lock=v=>card.querySelectorAll('button,input,select').forEach(e=>{if(e.id!=='sv-cancel')e.disabled=v;});
  async function act(fn){$('sv-error').textContent='';lock(true);try{await fn();}catch(e){$('sv-error').textContent=e.message;}finally{if(!running){lock(false);render();}}}
  $('sv-preset').onchange=()=>{const [g,...rest]=$('sv-preset').value.split(':');const n=rest.join(':');if(g&&state.presets[g]?.[n])fill(state.presets[g][n]);};
  card.querySelector('#sv-custom').addEventListener('input',note);
  $('sv-preset-save').onclick=()=>act(async()=>{state.presets=await post('preset-salvar',{nome:$('sv-preset-name').value,estilo:read()});const style=read();presets();fill(style);});
  $('sv-preset-delete').onclick=()=>act(async()=>{const [g,...rest]=$('sv-preset').value.split(':');if(g!=='meus')throw Error('Selecione um preset seu para excluir.');const style=read();state.presets=await post('preset-excluir',{nome:rest.join(':')});presets();fill(style);});
  const seconds=v=>{if(!String(v).trim())return null;const p=String(v).trim().replace(',','.').split(':');if(p.some(x=>!/^\d+(\.\d+)?$/.test(x)))throw Error('Use o início como 36:05.');return p.reverse().reduce((n,x,i)=>n+Number(x)*60**i,0);};
  $('sv-preview').onclick=()=>act(async()=>start(await post('previa',{estilo:read(),inicio:seconds($('sv-start').value)})));
  $('sv-render').onclick=()=>act(async()=>start(await post('render',{estilo:read()})));
  $('sv-cancel').onclick=()=>running&&fetch('/api/ml/job/'+running+'/cancelar',{method:'POST'});
  function start(job){running=job.id;sessionStorage.setItem('dr.sv.job',JSON.stringify({id:job.id,folder:scope}));$('sv-progress').hidden=false;$('sv-bar').removeAttribute('value');lock(true);poll();}
  async function poll(){
    if(!running)return;const id=running,work=scope;
    try{const r=await fetch('/api/ml/job/'+id),j=await r.json();if(!r.ok)throw Error(j.erro);if(work!==scope||id!==running)return;
      $('sv-step').textContent=j.step||'';if(j.status==='na_fila')$('sv-bar').removeAttribute('value');else $('sv-bar').value=Math.round((j.pct||0)*100);
      if(['executando','na_fila'].includes(j.status)){timer=setTimeout(poll,1500);return;}
      running=null;sessionStorage.removeItem('dr.sv.job');$('sv-progress').hidden=true;lock(false);state=await post('estado');render();
      if(j.error)$('sv-error').textContent=j.error;else if(j.status==='cancelado')$('sv-error').textContent='Render cancelado. Os blocos prontos foram guardados e serão reaproveitados.';
    }catch(e){$('sv-step').textContent='Não foi possível consultar: '+e.message;timer=setTimeout(poll,4000);}
  }
  async function refresh(){if(!folder||scope===folder&&state)return;scope=folder;state=null;running=null;clearTimeout(timer);$('sv-progress').hidden=true;$('sv-error').textContent='';try{state=await post('estado');render();const p=JSON.parse(sessionStorage.getItem('dr.sv.job')||'null');if(p?.folder===scope)start(p);}catch(e){$('sv-error').textContent=e.message;}}
  // Depois de gerar o SRT da montagem, o bloco de vídeo é liberado.
  new MutationObserver(()=>{if(scope&&state)post('estado').then(s=>{if(!running){state=s;render();}}).catch(()=>{});}).observe($('sub-result'),{childList:true});
  const previous=window.loadSwapPlan;if(previous)window.loadSwapPlan=async(...args)=>{await previous(...args);await refresh();};
})();
