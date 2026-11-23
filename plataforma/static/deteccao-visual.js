/* Produto antigo na imagem: busca e revisão locais dos trechos. */
(() => {
  const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const host=$('flow-takes-content');if(!host)return;
  let state=null,scope='',running=null,timer=null,busy=false,editing=null;
  const clock=ms=>{const t=Math.max(0,Math.round(ms));return Math.floor(t/60000)+':'+String(Math.floor(t/1000)%60).padStart(2,'0')+'.'+String(Math.floor(t%1000/100))};
  const parse=v=>{const p=String(v).trim().replace(',','.').split(':');if(!p.length||p.length>3||p.some(x=>!/^\d+(?:\.\d+)?$/.test(x)))throw Error('Use tempos como 25:10.2');return Math.round(p.reverse().reduce((n,x,i)=>n+Number(x)*60**i,0)*1000);};
  const file=p=>'/files/'+encodeURIComponent(scope)+'/'+p.split('/').map(encodeURIComponent).join('/');
  const post=async(action,body={})=>{const r=await fetch('/fatiador/trocas/deteccao-'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder:scope,...body})});const d=await r.json();if(!r.ok)throw Error(d.erro||'Não foi possível concluir.');return d;};
  const store=(key,value)=>{try{value===undefined?sessionStorage.getItem(key):sessionStorage.setItem(key,value);}catch(e){}};
  const read=key=>{try{return sessionStorage.getItem(key);}catch(e){return null;}};
  const panel=document.createElement('details');panel.className='card';panel.id='old-product-panel';
  panel.innerHTML=`<summary style="cursor:pointer"><b>Produto antigo na imagem</b> <span class="meta" id="op-chip">· procurar aparições sem menção falada</span></summary>
  <p class="meta">Revise as aparições do produto antigo e aprove as que precisam de take por cima. A busca processa rótulos, telas e legendas gravadas neste computador.</p>
  <div class="row"><label>Nome como aparece no rótulo<input id="op-name" autocomplete="off"></label><label>Outras grafias (separe por vírgula)<input id="op-aliases" autocomplete="off"></label></div>
  <div id="op-references"></div>
  <details><summary>Ajustes da análise</summary><label>Trecho analisado<select id="op-window"><option value="apos_mencao">A partir de 2 min antes da 1ª menção (recomendado)</option><option value="video_inteiro">Vídeo inteiro</option></select></label><p class="meta" id="op-window-info"></p><label class="op-auto-choice"><input type="checkbox" id="op-cover-before"> Cobrir também as aparições aprovadas antes da primeira menção</label></details>
  <div class="links"><button id="op-run">Procurar no trecho configurado</button><button class="ghost" id="op-run-full">Varrer o vídeo inteiro</button></div>
  <div id="op-progress" hidden><p id="op-step" role="status"></p><progress id="op-bar" max="100" style="width:100%"></progress><button class="ghost" id="op-cancel">Cancelar · o que já foi lido fica guardado</button></div>
  <p id="op-error" role="alert" class="err"></p><p id="op-summary" class="meta" role="status"></p>
  <div id="op-batch" class="row" hidden><label class="op-filter">Mostrar<select id="op-filter"><option value="">Todas</option><option value="revisar">Para revisar</option><option value="aprovado">Aprovadas</option><option value="descartado">Descartadas</option><option value="referencia">Encontradas pela referência</option><option value="manual">Marcadas pelo editor</option></select></label><button class="ghost" id="op-approve-high">Aprovar todos de confiança alta</button><button class="ghost" id="op-approve-sel">Aprovar selecionados</button><button class="ghost" id="op-discard-sel">Descartar selecionados</button></div>
  <div id="op-list"></div>`;
  const anchor=$('practical-take-config');anchor?host.insertBefore(panel,anchor):host.append(panel);
  // Atalho na etapa Falas: a leitura não depende das vozes e pode correr enquanto elas são geradas.
  const early=document.createElement('div');early.className='card';early.id='old-product-early';
  early.innerHTML='<b>Busca automática do produto antigo na imagem</b><p class="meta">Começa após a transcrição, neste computador e em segundo plano. Continue preparando as falas; confira as sugestões em Takes.</p><label class="op-auto-choice"><input type="checkbox" id="op-auto-early" checked> Buscar automaticamente neste projeto</label><button class="ghost" id="op-run-early">Refazer busca</button><p class="meta" id="op-mini" role="status"></p>';
  $('wizard-slot-3')?.append(early);
  const choice=document.createElement('label');choice.className='op-auto-choice card';choice.innerHTML='<input type="checkbox" id="op-auto-upload" checked> Procurar automaticamente o produto antigo nas imagens após a transcrição <span class="meta">Leitura local em segundo plano. Desmarque apenas se este projeto não precisar da busca visual.</span>'; $('go')?.before(choice);
  $('op-auto-early').onchange=async()=>{const checked=$('op-auto-early').checked;try{const d=await post('automatico',{automatico:checked});state=d.estado;render();if(d.job&&!running)start(d.job,false);}catch(e){$('op-error').textContent=e.message;$('op-auto-early').checked=!checked;}};
  const tone={alta:'var(--ok)',media:'#c98a00',revisar:'var(--err)'},label={alta:'confiança alta',media:'confiança média',revisar:'revisar com atenção'};
  function lock(v){busy=v;panel.querySelectorAll('button,input,select').forEach(e=>{if(e.id!=='op-cancel'&&e.id!=='op-filter'&&!e.closest('#op-references'))e.disabled=v||!!running||(e.id==='op-cover-before'&&!state?.nome);});$('op-run-early').disabled=v||!!running;$('op-auto-early').disabled=v;document.dispatchEvent(new CustomEvent('visual:busca-ocupada',{detail:{busy:v||!!running}}));}
  const chips=it=>(it.motivos||[]).map(m=>`<span class="op-chip">${esc(m)}</span>`).join('');
  function card(it,n){
    const dur=((it.fim_ms-it.inicio_ms)/1000).toFixed(1).replace('.',','),edit=editing===it.id;
    const cover=it.cobertura_inicio_ms!=null&&it.status==='aprovado'?`<br>Takes de ${clock(it.cobertura_inicio_ms)} a ${clock(it.cobertura_fim_ms)}${it.ajustado?' (tempos ajustados, sem margem)':` (aparição com ${((state.margem_visual_ms||0)/1000).toFixed(1).replace('.',',')} s de margem)`}`:'';
    return `<div class="card op-card" data-op="${esc(it.id)}" style="margin-top:10px"><label style="display:flex;flex-direction:row;gap:6px;align-items:center"><input type="checkbox" data-op-select> <b>#${n} · ${clock(it.inicio_ms)} – ${clock(it.fim_ms)}</b> <span class="meta">(${dur} s${it.ajustado?' · ajustado':''})</span></label>
    <div class="op-chips">${chips(it)}</div>
    ${it.fala_sem_troca?'<p><b style="color:var(--err)">Nome falado sem troca?</b> <span class="meta">A legenda gravada mostra o nome e não há fala trocada aqui. Ouça o trecho; se o narrador disser o nome antigo, inclua essa fala na lista de trocas.</span></p>':''}
    <p class="meta"><span style="color:${tone[it.confianca]};font-weight:600">${label[it.confianca]}</span>${it.antes_da_mencao&&!state.cobrir_antes_da_mencao?' · <b>Só marcação</b> · antes da 1ª menção':it.status==='aprovado'?' · recebe takes de Produto em V2':''}<br>${esc(it.motivo)}${cover}</p>${it.status==='sugerido'&&!it.coberto_pela_fala&&it.sem_cobertura_ms>0&&it.sem_cobertura_ms<it.fim_ms-it.inicio_ms?`<p class="meta"><b>Ainda há ${(it.sem_cobertura_ms/1000).toFixed(2).replace('.',',')} s fora da cobertura prevista.</b> Aprove este trecho para incluí-lo no preparo dos takes.</p>`:''}
    <div style="display:flex;gap:6px;flex-wrap:wrap">${(it.miniaturas||[]).map(p=>`<img src="${file(p)}" loading="lazy" alt="" style="height:90px;border-radius:4px">`).join('')}</div>
    <div class="row">${it.status!=='aprovado'?'<button data-op-set="aprovado">Aprovar</button>':''}${it.status!=='descartado'?'<button class="ghost" data-op-set="descartado">Descartar</button>':''}${it.status!=='sugerido'?'<button class="ghost" data-op-set="sugerido">Voltar para revisar</button>':''}<button class="ghost" data-op-side>Lado a lado</button><button class="ghost" data-op-edit>${edit?'Fechar ajuste':'Ajustar tempos'}</button><button class="ghost" data-op-watch>Ver trecho</button></div>
    ${edit?`<div class="row"><label>Início<input data-op-start value="${clock(it.inicio_ms)}"></label><label>Fim<input data-op-end value="${clock(it.fim_ms)}"></label><button data-op-save>Salvar tempos</button></div>`:''}<div data-op-player></div></div>`;
  }
  function showSearchScope(){
    const whole=$('op-window').value==='video_inteiro'||(state&&(state.primeira_mencao_ms==null||state.primeira_mencao_ms<=120000));
    $('op-run-full').hidden=whole;
    $('op-run').textContent=whole?'Procurar no vídeo inteiro':'Procurar no trecho configurado';
  }
  $('op-window').onchange=showSearchScope;
  const pendingOf=items=>items.filter(i=>i.status==='sugerido'&&!i.coberto_pela_fala);
  function filtered(items){
    const f=$('op-filter').value;
    if(f==='revisar')return pendingOf(items);
    if(f==='referencia')return items.filter(i=>(i.evidencias||[]).includes('referencia'));
    if(f==='manual')return items.filter(i=>i.origem==='manual');
    if(f)return items.filter(i=>i.status===f);
    return items;
  }
  function render(){
    if(!state)return;
    // Seleção, grupos abertos e posição da lista sobrevivem a cada atualização.
    const checked=new Set([...panel.querySelectorAll('[data-op-select]:checked')].map(c=>c.closest('[data-op]').dataset.op));
    const closed=new Set([...$('op-list').querySelectorAll('details[data-op-group]')].filter(d=>!d.open).map(d=>d.dataset.opGroup));
    const opened=new Set([...$('op-list').querySelectorAll('details[data-op-group]')].filter(d=>d.open).map(d=>d.dataset.opGroup));
    const y=window.scrollY;
    // Sem vídeo não há imagem para ler: o atalho e o painel saem do caminho.
    early.hidden=panel.hidden=state.tem_video===false;
    if(document.activeElement!==$('op-name'))$('op-name').value=state.nome||'';if(document.activeElement!==$('op-aliases'))$('op-aliases').value=state.aliases||'';$('op-window').value=state.janela||'apos_mencao';
    $('op-cover-before').checked=!!state.cobrir_antes_da_mencao;
    showSearchScope();
    $('op-window-info').textContent=(state.primeira_mencao_ms!=null?`1ª menção falada em ${clock(state.primeira_mencao_ms)}. Trecho analisado: ${clock((state.janela_inicio_s||0)*1000)} até o fim.`:'Sem menção falada encontrada: o vídeo inteiro é analisado.')+(state.origem_primeira_mencao==='legenda'?` A legenda gravada mostra o nome antes, em ${clock(state.primeira_mencao_efetiva_ms)}: essa passa a valer como 1ª menção.`:'');
    $('op-auto-early').checked=state.automatico!==false;
    const items=state.intervalos||[],pend=pendingOf(items),ok=items.filter(i=>i.status==='aprovado'),off=items.filter(i=>i.status==='descartado'),fala=items.filter(i=>i.status==='sugerido'&&i.coberto_pela_fala);
    const loose=(state.falas_sem_troca||[]).length;
    $('op-mini').textContent=state.analise?`Busca feita · ${pend.length} trecho(s) para revisar na etapa Takes${loose?` · ${loose} possível(is) fala(s) com o nome antigo sem troca`:''}.`:state.automatico===false?'Busca automática desativada neste projeto.':state.auto_erro||'Aguardando a busca automática. Continue com as falas.';
    const a=state.analise;$('op-chip').textContent=a?`· ${pend.length} para revisar · ${ok.length} aprovado(s)`:'· procurar aparições sem menção falada';
    $('op-summary').innerHTML=a?`${state.desatualizado?'<b>'+esc(state.desatualizado)+'</b><br>':''}${items.length} trecho(s) com o nome antigo: ${pend.length} para revisar, ${ok.length} aprovado(s), ${off.length} descartado(s), ${fala.length} já coberto(s) pelas falas trocadas. Analisado de ${clock(a.inicio_s*1000)} a ${clock(a.fim_s*1000)} em ${Math.round(a.tempo_s)} s${a.minutos_reaproveitados?` (${a.minutos_reaproveitados} de ${a.minutos} min reaproveitados)`:''}.${loose?`<br><b style="color:var(--err)">${loose} trecho(s) em que a legenda gravada mostra o nome sem fala trocada</b> — o narrador pode estar dizendo o nome antigo. Confira os marcados como “Nome falado sem troca?”.`:''}${state.origem_primeira_mencao==='legenda'?`<br>1ª menção considerada: ${clock(state.primeira_mencao_efetiva_ms)}, pela legenda gravada (a transcrição só encontrou em ${clock(state.primeira_mencao_ms)}).`:''}`:items.length?`${items.length} aparição(ões) marcada(s) pelo editor. Procure no vídeo para encontrar as demais.`:'Nenhuma análise ainda.';
    if(a?.refino)$('op-summary').insertAdjacentHTML('beforeend',`<br>Conferência adicional: ${a.refino.quadros} quadro(s) com leitura detalhada${a.refino.reaproveitado?' · reaproveitada do projeto':''}.`);
    if(a?.aparencia)$('op-summary').insertAdjacentHTML('beforeend',`<br>Referências do editor: ${a.aparencia.com_referencia} quadro(s) parecidos em ${a.aparencia.quadros} comparados${a.aparencia.minutos_reaproveitados?` · ${a.aparencia.minutos_reaproveitados} de ${a.aparencia.minutos} min reaproveitados`:''}.`);
    if(a?.limites)$('op-summary').insertAdjacentHTML('beforeend',`<br>Entrada e saída acompanhadas quadro a quadro em ${a.limites.ajustadas} de ${a.limites.aparicoes} aparição(ões)${a.limites.unidas?` · ${a.limites.unidas} leitura(s) ruim(ns) no mesmo plano unida(s)`:''}${a.limites.descartadas_outro_nome?` · ${a.limites.descartadas_outro_nome} pote(s) com outro nome descartado(s)`:''}.`);
    $('op-batch').hidden=!items.length;let n=0;const order=new Map(items.map(i=>[i.id,++n]));
    const visible=filtered(items);
    const group=(key,title,list,open,hint)=>{list=list.filter(i=>visible.includes(i));if(!list.length)return'';const isOpen=opened.has(key)||(open&&!closed.has(key));return `<details data-op-group="${key}" ${isOpen?'open':''} style="margin-top:12px"><summary><b>${title} (${list.length})</b></summary>${hint?`<p class="meta">${hint}</p>`:''}${list.map(i=>card(i,order.get(i.id))).join('')}</details>`;};
    $('op-list').innerHTML=group('revisar','Para revisar',pend,true,'Confira as miniaturas, compare lado a lado ou veja o trecho completo antes de aprovar.')+group('aprovado','Aprovados',ok,!!$('op-filter').value)+group('fala','Dentro da cobertura prevista pelas falas',fala,false,'Esses trechos recebem takes junto com as falas trocadas ao preparar a montagem atual.')+group('descartado','Descartados',off,!!$('op-filter').value)||(items.length?'<p class="meta">Nenhuma aparição neste filtro.</p>':'');
    $('op-list').querySelectorAll('[data-op]').forEach(box=>{if(checked.has(box.dataset.op))box.querySelector('[data-op-select]').checked=true;});
    if(Math.abs(window.scrollY-y)>2)window.scrollTo(0,y);
    lock(busy);document.dispatchEvent(new CustomEvent('visual:conferencia-atualizada'));
  }
  $('op-filter').onchange=()=>{store('rm.op.filtro.'+scope,$('op-filter').value);render();};
  async function act(fn){if(busy)return;lock(true);$('op-error').textContent='';try{await fn();}catch(e){$('op-error').textContent=e.message;$('op-mini').textContent=e.message;}finally{lock(false);}}
  const set=list=>act(async()=>{state=await post('revisar',{itens:list});render();if(window.VisualUX?.state?.prepared)$('op-summary').insertAdjacentHTML('beforeend','<br><b>Os takes preparados ficaram desatualizados.</b> Clique em “Preparar takes automaticamente” para cobrir os trechos aprovados.');});
  $('op-list').addEventListener('click',e=>{
    const box=e.target.closest('[data-op]');if(!box)return;const id=box.dataset.op,it=state.intervalos.find(i=>i.id===id);
    if(e.target.matches('[data-op-set]'))set([{id,status:e.target.dataset.opSet}]);
    else if(e.target.matches('[data-op-side]'))document.dispatchEvent(new CustomEvent('visual:lado-a-lado',{detail:{id}}));
    else if(e.target.matches('[data-op-edit]')){editing=editing===id?null:id;render();}
    else if(e.target.matches('[data-op-save]'))act(async()=>{state=await post('revisar',{itens:[{id,inicio_ms:parse(box.querySelector('[data-op-start]').value),fim_ms:parse(box.querySelector('[data-op-end]').value)}]});editing=null;render();});
    else if(e.target.matches('[data-op-watch]')){const slot=box.querySelector('[data-op-player]');if(slot.firstChild){slot.innerHTML='';return;}const a=Math.max(0,it.inicio_ms-1000)/1000,b=(it.fim_ms+1000)/1000;slot.innerHTML=`<video controls preload="metadata" style="max-width:100%;max-height:320px" src="${file('_fonte'+(state.extensao||'.mp4'))}#t=${a.toFixed(2)},${b.toFixed(2)}"></video><p class="meta">Começa 1 s antes e termina 1 s depois do trecho, com o áudio original.</p>`;slot.querySelector('video').play().catch(()=>{});}
  });
  const selected=()=>[...panel.querySelectorAll('[data-op-select]:checked')].map(c=>c.closest('[data-op]').dataset.op);
  $('op-approve-high').onclick=()=>set(state.intervalos.filter(i=>i.status==='sugerido'&&!i.coberto_pela_fala&&i.confianca==='alta').map(i=>({id:i.id,status:'aprovado'})));
  $('op-approve-sel').onclick=()=>set(selected().map(id=>({id,status:'aprovado'})));
  $('op-discard-sel').onclick=()=>set(selected().map(id=>({id,status:'descartado'})));
  function analyze(windowMode){
    return act(async()=>{
      const job=await post('analisar',{nome:$('op-name').value,aliases:$('op-aliases').value,janela:windowMode});
      start(job);
    });
  }
  $('op-run').onclick=()=>analyze($('op-window').value);
  $('op-run-full').onclick=()=>analyze('video_inteiro');
  $('op-cover-before').onchange=()=>act(async()=>{
    try{state=await post('config',{cobrir_antes_da_mencao:$('op-cover-before').checked});}
    finally{render();}
    if(window.VisualUX?.state?.prepared)$('op-summary').insertAdjacentHTML('beforeend','<br><b>Prepare os takes novamente para aplicar a cobertura atualizada.</b>');
  });
  $('op-run-early').onclick=()=>act(async()=>{if(!state)state=await post('estado');const job=await post('analisar',{nome:state.nome,aliases:state.aliases,janela:state.janela||'apos_mencao'});start(job);});
  $('op-cancel').onclick=()=>running&&fetch('/api/ml/job/'+running+'/cancelar',{method:'POST'});
  function start(job,foreground=true){running=job.id;store('dr.op.job',JSON.stringify({id:job.id,folder:scope}));$('op-progress').hidden=false;$('op-step').textContent='Aguardando início…';$('op-bar').removeAttribute('value');if(foreground)panel.open=true;lock(busy);poll();}
  async function poll(){
    if(!running)return;const id=running,work=scope;
    try{const r=await fetch('/api/ml/job/'+id),j=await r.json();if(!r.ok)throw Error(j.erro);if(work!==scope||id!==running)return;
      $('op-step').textContent=j.step||'';$('op-mini').textContent=j.step||'';if(j.progresso?.indeterminado||j.status==='na_fila')$('op-bar').removeAttribute('value');else $('op-bar').value=Math.round((j.pct||0)*100);
      if(['executando','na_fila'].includes(j.status)){timer=setTimeout(poll,1000);return;}
      running=null;try{sessionStorage.removeItem('dr.op.job');}catch(e){}$('op-progress').hidden=true;state=await post('estado');render();
      if(j.status==='cancelado')$('op-error').textContent='Busca cancelada. Os minutos já lidos foram guardados e serão reaproveitados.';else if(j.error)$('op-error').textContent=j.error;$('op-mini').textContent=$('op-error').textContent||$('op-mini').textContent;
      document.dispatchEvent(new CustomEvent('visual:busca-concluida',{detail:{status:j.status}}));
    }catch(e){$('op-step').textContent='Não foi possível consultar: '+e.message;timer=setTimeout(poll,3000);}
  }
  async function refresh(force=false){
    if(!folder||scope===folder&&state&&!force)return;const changed=scope!==folder;scope=folder;if(changed){state=null;running=null;clearTimeout(timer);$('op-progress').hidden=true;$('op-error').textContent='';$('op-filter').value=read('rm.op.filtro.'+scope)||'';}
    const work=scope;try{const auto=await post('automatico');if(work!==scope)return;state=auto.estado;render();if(auto.aviso&&!state.desatualizado)$('op-summary').insertAdjacentHTML('afterbegin','<b>'+esc(auto.aviso)+'</b><br>');const pending=JSON.parse(read('dr.op.job')||'null');if(running)return;if(auto.job)start(auto.job,false);else if(state.tarefa)start(state.tarefa,false);else if(pending?.folder===scope)start(pending,false);}catch(e){$('op-summary').textContent='';$('op-error').textContent=e.message;}
  }
  const previous=window.loadSwapPlan;if(previous)window.loadSwapPlan=async(...args)=>{await previous(...args);await refresh();};
  window.OldProductUX={refresh,render,set,post,file,clock,parse,start,act,
    get scope(){return scope;},get state(){return state;},set state(v){state=v;},get busy(){return busy||!!running;},
    analyze:()=>analyze($('op-window').value),open(){panel.open=true;panel.scrollIntoView({block:'start',behavior:'smooth'});},
    filter(value){$('op-filter').value=value;store('rm.op.filtro.'+scope,value);render();}};
})();
