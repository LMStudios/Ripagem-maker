/* Legendas da montagem final: SRT novo no tempo da montagem. O SRT original e o corretor de nomes continuam separados. */
(() => {
  const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const slot=$('wizard-slot-5');if(!slot)return;
  let state=null,scope='',running=null,timer=null;
  const clock=s=>{const t=Math.max(0,Math.round(s*10));return Math.floor(t/600)+':'+String(Math.floor(t/10)%60).padStart(2,'0')+'.'+t%10;};
  const file=p=>'/files/'+encodeURIComponent(scope)+'/'+p.replaceAll('\\','/').split('/').map(encodeURIComponent).join('/');
  const post=async(action,body={})=>{const r=await fetch('/fatiador/trocas/legendas-'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder:scope,...body})});const d=await r.json();if(!r.ok)throw Error(d.erro||'Não foi possível concluir.');return d;};
  const card=document.createElement('div');card.className='card';card.id='subtitles-panel';
  card.innerHTML=`<h3>Legendas da montagem final</h3>
  <p class="meta">Gera um SRT novo no tempo da montagem — com as falas novas, extensões e margens removidas. Reaproveita os tempos já transcritos e alinha só as falas novas. Em Ajustes dos blocos, você pode pedir uma conferência integral do áudio. O SRT original não muda. Para trocar só nomes mantendo os tempos, use o corretor abaixo.</p>
  <label>Onde legendar<select id="sub-mode"><option value="video_inteiro">Vídeo inteiro</option><option value="coberturas">Só onde a imagem foi coberta por takes (V2)</option><option value="auto">Detectar legendas gravadas e limitar às coberturas se encontradas</option></select></label>
  <details><summary>Ajustes dos blocos</summary><div class="row"><label>Caracteres por linha<input id="sub-width" type="number" min="20" max="80"></label><label>Linhas por bloco<select id="sub-lines"><option>1</option><option>2</option><option>3</option></select></label><label>Duração máxima (s)<input id="sub-max" type="number" min="1" max="15" step="0.5"></label></div><label><input type="checkbox" id="sub-full-audit"> Conferir o áudio inteiro novamente (leva mais tempo)</label></details>
  <button id="sub-run">Gerar SRT da montagem</button>
  <div id="sub-progress" hidden><p id="sub-step" role="status"></p><progress id="sub-bar" max="100" style="width:100%"></progress><button class="ghost" id="sub-cancel">Cancelar</button></div>
  <p id="sub-error" role="alert" class="err"></p><div id="sub-result" aria-live="polite"></div>`;
  slot.prepend(card);
  function render(){
    if(!state)return;const c=state.config||{};$('sub-mode').value=c.modo||'video_inteiro';$('sub-width').value=c.caracteres_linha||42;$('sub-lines').value=String(c.linhas||2);$('sub-max').value=c.duracao_max_s||6;$('sub-full-audit').checked=c.conferencia_integral===true;
    const r=state.resultado,g=state.legendas_gravadas;
    if(!r){$('sub-result').innerHTML='<p class="meta">Nenhum SRT da montagem gerado ainda. Requer as falas aprovadas com áudio.</p>';return;}
    const where=r.modo_usado==='coberturas'?`só nas ${r.coberturas} cobertura(s) de V2`:'no vídeo inteiro';
    const burned=g&&!g.indisponivel?(g.detectado?` O vídeo original parece ter legendas gravadas (${g.com_texto_inferior} de ${g.amostras} quadros com texto embaixo).`:' Não encontramos legendas gravadas no vídeo original.'):'';
    $('sub-result').innerHTML=`${state.desatualizado?'<p><b>'+esc(state.desatualizado)+'</b></p>':''}<p>${r.blocos} blocos ${where}. ${r.alinhadas_pct}% das palavras com tempo medido${r.estimadas?`; ${r.estimadas} com tempo estimado entre vizinhas`:''}.${burned}</p>
    <p><a download href="${file(r.arquivo)}?dl=1">Salvar SRT da montagem</a> · <span class="meta">${esc(r.arquivo.replaceAll('\\','/').split('/').pop())}</span></p>
    <p class="meta">No Premiere: Arquivo → Importar o SRT e arraste para a sequência como legenda. O estilo é definido no Premiere; o SRT leva texto e tempos.${r.alinhamento_por_palavra?'':' O alinhamento por palavra ficou abaixo de 90%: use legendas por frase e confira os tempos.'}</p>
    ${r.avisos.length?`<details open><summary><b>${r.avisos.length} aviso(s) para conferir</b></summary>${r.avisos.map(a=>`<p class="meta"><b>${clock(a.inicio)}–${clock(a.fim)}</b> · ${esc(a.motivo)}${a.ouvido!==undefined?`<br>Aprovado: “${esc(a.aprovado)}”<br>Ouvido: “${esc(a.ouvido)}”`:''}</p>`).join('')}</details>`:'<p class="meta">Nenhum alerta na conferência.</p>'}`;
  }
  function lock(v){card.querySelectorAll('button,input,select').forEach(e=>{if(e.id!=='sub-cancel')e.disabled=v;});}
  $('sub-run').onclick=async()=>{$('sub-error').textContent='';lock(true);try{const job=await post('gerar',{config:{modo:$('sub-mode').value,caracteres_linha:Number($('sub-width').value),linhas:Number($('sub-lines').value),duracao_max_s:Number($('sub-max').value),conferencia_integral:$('sub-full-audit').checked}});start(job);}catch(e){$('sub-error').textContent=e.message;lock(false);}};
  $('sub-cancel').onclick=()=>running&&fetch('/api/ml/job/'+running+'/cancelar',{method:'POST'});
  function start(job){running=job.id;sessionStorage.setItem('dr.sub.job',JSON.stringify({id:job.id,folder:scope}));$('sub-progress').hidden=false;$('sub-bar').removeAttribute('value');lock(true);poll();}
  async function poll(){
    if(!running)return;const id=running,work=scope;
    try{const r=await fetch('/api/ml/job/'+id),j=await r.json();if(!r.ok)throw Error(j.erro);if(work!==scope||id!==running)return;
      $('sub-step').textContent=j.step||'';if(j.status==='na_fila')$('sub-bar').removeAttribute('value');else $('sub-bar').value=Math.round((j.pct||0)*100);
      if(['executando','na_fila'].includes(j.status)){timer=setTimeout(poll,1500);return;}
      running=null;sessionStorage.removeItem('dr.sub.job');$('sub-progress').hidden=true;lock(false);state=await post('estado');render();if(j.error)$('sub-error').textContent=j.error;else if(j.status==='cancelado')$('sub-error').textContent='Geração cancelada.';
    }catch(e){$('sub-step').textContent='Não foi possível consultar: '+e.message;timer=setTimeout(poll,4000);}
  }
  async function refresh(){if(!folder||scope===folder&&state)return;scope=folder;state=null;running=null;clearTimeout(timer);$('sub-progress').hidden=true;$('sub-error').textContent='';try{state=await post('estado');render();const p=JSON.parse(sessionStorage.getItem('dr.sub.job')||'null');if(p?.folder===scope)start(p);}catch(e){$('sub-error').textContent=e.message;}}
  document.addEventListener('ripagem:preparar-legendas',async()=>{
    await refresh();
    if(scope===folder&&state&&!running&&(!$('sub-run').disabled)&&(!state.resultado||state.desatualizado))$('sub-run').click();
  });
  document.addEventListener('ripagem:trilha-salva',async()=>{
    if(scope!==folder||running)return;
    const work=scope;
    try{const updated=await post('estado');if(scope===work&&!running){state=updated;render();}}
    catch(e){if(scope===work)$('sub-error').textContent=e.message;}
  });
  const previous=window.loadSwapPlan;if(previous)window.loadSwapPlan=async(...args)=>{await previous(...args);await refresh();};
})();
