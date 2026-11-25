/* Lista aprovada -> vozes -> encaixe -> Premiere -> revisão. Chaves nunca vão ao armazenamento do navegador. */
(() => {
  const el=id=>document.getElementById(id), q=(s,root=document)=>root.querySelector(s), qa=(s,root=document)=>[...root.querySelectorAll(s)];
  const x=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const seconds=n=>n!=null&&Number.isFinite(Number(n))?Number(n).toFixed(2)+' s':'—';
  const call=async(action,data={})=>{const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),45000);try{const r=await fetch('/fatiador/trocas/'+action,{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({folder,product:el('prod2').value,...data})});const d=await r.json();if(!r.ok)throw Error(d.erro||'Não foi possível concluir.');return d;}catch(e){if(e.name==='AbortError')throw Error('A resposta demorou mais que o esperado. Confira o andamento antes de repetir a ação.');throw e;}finally{clearTimeout(timer);}};

  let plan=null,busy=false,voices={},poll=null,currentJob=null,scope='',saveQueue=Promise.resolve(),polling=false,jobContext={},importing=false;
  el('flist').innerHTML='<p class="meta">As frases aprovadas aparecerão aqui.</p>';
  const controls=document.createElement('div');controls.id='swap-controls';controls.innerHTML=`<h3>Lista única de trocas</h3><p class="meta">Confira o texto novo e o speaker, aprove as frases e salve. Só as frases aprovadas serão geradas e montadas.</p><div class="row"><label style="display:flex;flex-direction:row"><input type="checkbox" id="swap-prices"> Incluir também as trocas de preços/kits já preparadas</label><button class="ghost" id="swap-rebuild" data-swap-lock>Atualizar lista</button></div><div class="links"><button class="ghost" id="swap-all" data-swap-lock>Aprovar todos os textos</button><button class="ghost" id="swap-none" data-swap-lock>Desmarcar todos</button><button id="swap-save" data-swap-lock>Salvar aprovação e textos</button><button id="swap-approve-all-audio" data-swap-lock>Aprovar todos os áudios</button></div><p class="meta">A aprovação em lote inclui os áudios prontos das frases selecionadas. Áudios ausentes, desatualizados ou fora da duração continuam pendentes.</p><p id="swap-summary" class="meta"></p><p id="swap-batch-result" class="meta" role="status"></p><p id="swap-error" role="alert" style="color:var(--err)"></p>`;
  el('flist').before(controls);
  const voicesPanel=document.createElement('div');voicesPanel.className='card';voicesPanel.id='swap-voices';voicesPanel.innerHTML=`<h3>Gerar as falas por speaker</h3><p class="meta">Primeiro prepare e ouça as amostras. Você pode usar uma voz autorizada que já existe na conta ou criar um clone para cada speaker. Amostras podem conter ruído/música; confira antes de enviar.</p><button class="ghost" id="swap-samples" data-swap-lock>Preparar amostras locais dos speakers</button><div id="swap-speakers"></div><div class="row"><label>Serviço<select id="swap-provider" data-swap-lock><option value="elevenlabs">ElevenLabs</option><option value="minimax">MiniMax</option></select></label><label>Modelo<select id="swap-model" data-swap-lock></select></label></div><label>Chave da API<input type="password" id="swap-key" autocomplete="off" placeholder="Salva no cofre deste computador" data-swap-lock></label><div class="links"><button class="ghost" id="swap-connect" data-swap-lock>Salvar chave neste computador</button><button class="ghost" id="swap-forget" data-swap-lock>Remover chaves de voz</button></div><p class="meta" id="swap-key-status">Nenhuma chave foi enviada por esta tela.</p><label style="display:flex;flex-direction:row"><input type="checkbox" id="swap-consent" data-swap-lock> Tenho autorização dos speakers para clonar suas vozes; ouvi as amostras e confirmei quem é quem.</label><label style="display:flex;flex-direction:row"><input type="checkbox" id="swap-send" data-swap-lock> Autorizo enviar as frases e, quando houver clonagem, as amostras ao serviço escolhido. A geração/clonagem pode consumir créditos.</label><label style="display:flex;flex-direction:row"><input type="checkbox" id="swap-autofit" checked data-swap-lock> Permitir ajuste de velocidade de até 10% para encaixar; áudios muito curtos ou longos exigem regeneração.</label><label style="display:flex;flex-direction:row"><input type="checkbox" id="swap-delete" data-swap-lock> Excluir permanentemente somente os clones criados por esta geração ao terminar.</label><label style="display:flex;flex-direction:row"><input type="checkbox" id="swap-regenerate" data-swap-lock> Regenerar também os áudios existentes (pode consumir novos créditos).</label><p class="meta" id="swap-estimate"></p><button id="swap-generate" data-swap-lock>Gerar somente as frases aprovadas</button><p class="meta">As frases já geradas com o mesmo texto, speaker e configuração são reutilizadas quando você não marca regenerar. Não há garantia de timbre/duração perfeitos: ouça antes de aprovar.</p>`;
  el('wizard-slot-3').append(voicesPanel);
  const durationPanel=document.createElement('section');durationPanel.id='swap-duration-panel';durationPanel.className='ux-toast';durationPanel.innerHTML='<h4>Duração das falas na timeline</h4><label>Como montar no Premiere<select id="swap-duration-mode" data-swap-lock><option value="expandir">Abrir espaço para falas maiores · velocidade natural</option><option value="fixo">Manter a duração original · ajustar até 10%</option></select></label><p id="swap-duration-info" class="meta"></p><button class="ghost" id="swap-duration-apply" data-swap-lock>Aplicar e preparar áudios já gerados · sem créditos</button><p class="meta">No modo de abrir espaço, o restante de V1, V2 e do áudio avança junto. A imagem final do trecho cobre o tempo extra. Áudios alterados precisam ser conferidos novamente; arquivos antigos são preservados.</p>';voicesPanel.querySelector('h3').after(durationPanel);
  el('swap-duration-apply').onclick=async()=>{if(busy)return;const mode=el('swap-duration-mode').value;setBusy(true);try{await action(async()=>{await save();startJob(await call('duracao',{modo:mode}));});}finally{if(!currentJob)setBusy(false);}};
  const inlineProgress=document.createElement('div');inlineProgress.id='swap-inline-progress';inlineProgress.className='card hidden';inlineProgress.setAttribute('aria-live','polite');inlineProgress.innerHTML='<p id="swap-inline-step" role="status"></p><progress id="swap-inline-bar" max="100" style="width:100%;height:16px"></progress><p id="swap-inline-count" class="meta"></p><p id="swap-inline-error" role="alert"></p><button class="ghost" id="swap-inline-cancel" hidden>Cancelar geração</button>';
  const formNotice=document.createElement('div');formNotice.id='swap-form-notice';formNotice.hidden=true;formNotice.setAttribute('role','alert');formNotice.className='ux-form-notice';formNotice.innerHTML='<p id="swap-form-message"></p><button type="button" class="ghost" id="swap-fix-duration" hidden>Aplicar duração escolhida · sem créditos</button>';el('swap-generate').before(formNotice);
  el('swap-fix-duration').onclick=()=>el('swap-duration-apply').click();
  el('swap-generate').after(inlineProgress);
  function durationPending(){return !!plan&&el('swap-duration-mode').value!==(plan.modo_duracao||'fixo');}
  function durationNotice(){const pending=durationPending();el('swap-fix-duration').hidden=!pending;el('swap-form-notice').hidden=!pending;el('swap-form-message').textContent=pending?'Você mudou a duração da montagem. Aplique esta escolha aos áudios existentes antes de gerar novas falas.':'';const missing=plan?.itens.filter(r=>r.audio?.raw&&!r.audio?.fit).length||0;el('swap-duration-apply').disabled=busy||(!pending&&!missing);el('swap-duration-apply').textContent=pending?'Aplicar nova duração':missing?'Preparar '+missing+' áudios existentes':'Duração já configurada';}
  el('swap-duration-mode').onchange=durationNotice;
  function voiceProgress(j){
    document.dispatchEvent(new CustomEvent('swap:progress',{detail:{...j,...jobContext}}));
    inlineProgress.classList.remove('hidden');const p=j.progresso,active=['na_fila','executando'].includes(j.status);inlineProgress.classList.toggle('working',active);
    el('swap-inline-step').textContent=p?.tipo==='vozes'?p.fase+(p.frase?' · Frase '+p.frase+' · Speaker '+p.speaker:''):(j.step||'Preparando geração…');
    const bar=el('swap-inline-bar');
    if(p?.tipo==='vozes'&&p.total){bar.value=Math.round(p.processadas/p.total*100);el('swap-inline-count').textContent=`${p.processadas} de ${p.total} frases processadas · ${bar.value}% do lote${p.reutilizadas?' · '+p.reutilizadas+' reutilizada(s)':''}${p.erros?' · '+p.erros+' com erro':''}. O percentual conta frases, não o tempo da requisição atual.`;}
    else {bar.removeAttribute('value');el('swap-inline-count').textContent=active?'Aguarde a conclusão desta etapa. Você pode acompanhar ou cancelar o trabalho.':'';}
    if(!active&&!p){if(j.status==='concluido')bar.value=100;else bar.hidden=true;}else bar.hidden=false;
    el('swap-inline-cancel').hidden=!active||!currentJob;
    const errors=voiceFailureGroups(j.result?.resultados||[]);el('swap-inline-error').textContent=j.error||errors.slice(0,3).map(r=>r.message+(r.ids.length>1?' ('+r.ids.length+' frases)':'')).join(' · ')+(errors.length>3?' · Veja os demais avisos nos detalhes.':'');
    if(j.status==='cancelado')el('swap-inline-step').textContent='Geração cancelada. Os áudios já salvos foram preservados.';
  }
  el('swap-inline-cancel').onclick=()=>el('swap-cancel').click();

  const status=document.createElement('div');status.className='card hidden';status.id='swap-status';status.innerHTML='<p id="swap-step" role="status"></p><button class="ghost" id="swap-cancel">Cancelar trabalho</button><div id="swap-job-errors"></div><button class="ghost" id="swap-dismiss-status" hidden>Fechar aviso</button>';
  document.getElementById('guided-fatiador').prepend(status);
  el('swap-dismiss-status').onclick=()=>{if(!currentJob){status.classList.add('hidden');inlineProgress.classList.add('hidden');}};
  const montage=document.createElement('div');montage.className='card';montage.innerHTML=`<h3>Montagem com os áudios aprovados</h3><p class="meta">Gera uma sequência nova do arquivo original, com vídeo preservado e espaço para as falas maiores, o restante do áudio original em A1, os trechos originais separados em A2 (desativados) e cada fala nova correspondente posicionada em A3. Para uma timeline reorganizada, confira o alinhamento antes de aplicar.</p><p id="swap-ready" class="meta"></p><button id="swap-export" data-swap-lock>Gerar montagem pronta para Premiere</button><div id="swap-export-result"></div>`;
  el('wizard-slot-4').prepend(montage);
  const fileTools=document.createElement('div');fileTools.className='card';fileTools.innerHTML=`<h3>Seus arquivos estão salvos neste Mac</h3><p class="meta">Os áudios são salvos automaticamente no trabalho atual. “Salvar cópia” baixa um arquivo para Downloads; abrir a pasta mostra os originais.</p><div class="links"><button class="ghost" data-open-swap="">Abrir pasta do trabalho</button><button class="ghost" data-open-swap="trocas/gerados">Abrir áudios gerados</button><button class="ghost" data-open-swap="trocas/encaixados">Abrir áudios prontos para encaixar</button></div><p class="meta" data-swap-path></p>`;
  el('swap-controls').before(fileTools);
  const fileTools4=fileTools.cloneNode(true);el('wizard-slot-4').prepend(fileTools4);
  const how=document.createElement('div');how.innerHTML=`<h4>Como importar a montagem no Premiere</h4><ol><li>Na etapa 3, ouça e clique em <b>Ouvi e aprovo este áudio</b> em cada fala selecionada.</li><li>Aqui, clique em <b>Gerar montagem pronta para Premiere</b> e depois em <b>Salvar montagem XML em Downloads</b>.</li><li>No Premiere, use <b>Arquivo → Importar (⌘I)</b> e selecione o XML baixado.</li><li>No painel <b>Projeto</b>, expanda a pasta importada e dê dois cliques em <b>sequência com o mesmo nome do XML</b>. A2 guarda os cortes originais desativados e A3 recebe as falas novas correspondentes; confira o resultado antes de exportar.</li></ol><p class="meta">Importe o XML para receber a montagem. O JSON é o relatório das trocas. Não mova os áudios nem o vídeo da pasta do trabalho depois de importar.</p>`;montage.append(how);
  const returnToAudio=document.createElement('button');returnToAudio.className='ghost';returnToAudio.id='swap-back-audio';returnToAudio.textContent='Voltar à etapa 3 para ouvir e aprovar';returnToAudio.onclick=()=>wizardStep(3);el('swap-export').before(returnToAudio);returnToAudio.style.marginRight='8px';
  const manual=el('exp-premiere').parentElement,manualDetails=document.createElement('details');manualDetails.className='card';manualDetails.innerHTML='<summary>Opção alternativa: só marcadores e cortes para edição manual</summary><p class="meta">Estes arquivos não colocam as falas novas na timeline. Para receber os áudios posicionados, use a montagem acima.</p>';manual.before(manualDetails);manualDetails.append(manual);
  qa('[data-open-swap]').forEach(button=>button.onclick=()=>action(async()=>{if(!folder)throw Error('Abra um trabalho primeiro.');const sub=button.dataset.openSwap;const r=await fetch('/open/'+encodeURIComponent(folder)+(sub?'/'+sub.split('/').map(encodeURIComponent).join('/'):''));if(!r.ok)throw Error('Não foi possível abrir a pasta.');}));
  const final=document.createElement('div');final.className='card';final.innerHTML=`<h3>Conferência do áudio final</h3><p class="meta">Mistura as falas aprovadas com o áudio original e transcreve a montagem integral localmente para procurar resquícios do produto antigo. Não envia nada para o serviço de voz. Se você editar essa montagem depois no Premiere, revise também o vídeo exportado.</p><button id="swap-review" data-swap-lock>Montar e conferir o áudio integral</button><div id="swap-review-result"></div>`;
  el('wizard-slot-5').prepend(final);
  function setBusy(value){
    busy = value;
    const approved = new Set(value ? [] : plan?.itens.filter(row => row.audio?.aprovado).map(row => row.id));
    for (const field of qa('[data-swap-lock], [data-swap-text], [data-swap-approve], [data-swap-speaker], [data-swap-upload], [data-swap-audio]')) {
      field.disabled = value || approved.has(field.dataset.swapAudio);
    }
    readiness();
  }
  function capture(){
    if(!plan)return [];
    const cards = new Map(qa('[data-swap-row]', el('flist')).map(card => [card.dataset.swapRow, card]));
    return plan.itens.map(row => {
      const card = cards.get(row.id);
      return card ? {id: row.id, novo: q('[data-swap-text]', card).value,
        speaker: q('[data-swap-speaker]', card).value, aprovado: q('[data-swap-approve]', card).checked,
        ...(q('[data-swap-confirm-voice]', card)?.checked ? {confirmar_speaker: true} : {})}
        : {id: row.id, novo: row.novo, speaker: row.speaker, aprovado: row.aprovado};
    });
  }
  function save(){
    if(!plan)return Promise.reject(Error('Monte a lista primeiro.'));
    const updates=capture(),work=folder;
    const next=saveQueue.catch(()=>{}).then(async()=>{
      if(work!==folder)throw Error('O trabalho mudou. Volte ao anterior para salvar.');
      const before=JSON.stringify(plan.itens),saved=await call('salvar',{itens:updates});
      if(work===folder){plan=saved;if(before!==JSON.stringify(plan.itens)){el('swap-export-result').innerHTML='';renderReview();}}
      return saved;
    });saveQueue=next;return next;
  }
  const canGenerate = row => !(row?.forma_pendente && !row.forma_confirmada);
  const usagePending = document.createElement('p');
  usagePending.className = 'meta';
  usagePending.setAttribute('role','status');
  el('swap-estimate').after(usagePending);
  function readiness(){
    if(!plan)return;
    qa('[data-swap-path]').forEach(e=>e.textContent='Trabalho atual: '+folder);
    const rows = capture().filter(row => row.aprovado);
    const byId = new Map(plan.itens.map(row => [row.id, row]));
    const ready = rows.filter(row => canGenerate(byId.get(row.id)));
    const deferred = rows.length - ready.length;
    usagePending.textContent = deferred ? deferred + ' fala(s) aguardando revisão do modo de uso. A geração inclui apenas as falas prontas.' : '';
    let approvedAudio = 0, pending = 0, canApprove = false;
    for (const row of rows) {
      const base = byId.get(row.id);
      const matchesAudio = base.novo === row.novo && base.speaker === row.speaker;
      if (base.audio?.aprovado && matchesAudio) approvedAudio++;
      if (canGenerate(base) && (!base.audio?.fit || !matchesAudio)) pending++;
      if (base.audio?.fit && (!base.audio.aprovado || !matchesAudio)) canApprove = true;
    }
    el('swap-summary').textContent=`${rows.length} texto(s) aprovado(s) · ${approvedAudio} áudio(s) aprovado(s).`;
    el('swap-ready').textContent=rows.length?`${approvedAudio} de ${rows.length} áudios aprovados. ${approvedAudio<rows.length?'Ouça e aprove os áudios na etapa 3 antes de montar.':'Pronto para gerar a montagem.'}`:'Aprove textos e áudios na etapa 3.';
    el('swap-estimate').textContent=`${ready.length} frase(s) prontas · ${ready.reduce((n,r)=>n+r.novo.length,0)} caracteres · ${new Set(ready.map(r=>r.speaker)).size} speaker(s). Consulte os preços do serviço; clonagem, regenerações e tentativas adicionais podem ser cobradas.`;
    el('swap-approve-all-audio').disabled=busy||!canApprove;
    el('swap-back-audio').hidden=rows.length>0&&rows.length===approvedAudio;
    el('swap-generate').textContent=el('swap-regenerate').checked?'Regenerar '+ready.length+' falas prontas':pending?'Gerar '+pending+' falas prontas':deferred?'Aguardando revisão do modo de uso':'Todos os áudios já estão preparados';el('swap-generate').disabled=busy||!ready.length||(!pending&&!el('swap-regenerate').checked);el('swap-duration-apply').disabled=busy||(!durationPending()&&!plan.itens.some(r=>r.audio?.raw&&!r.audio?.fit));el('swap-autofit').disabled=busy||plan.modo_duracao==='expandir';el('swap-export').disabled=busy||!rows.length||rows.length!==approvedAudio;el('swap-review').disabled=el('swap-export').disabled;document.dispatchEvent(new CustomEvent('swap:state'));
  }
  function render(){
    if(!plan)return;el('swap-duration-mode').value=plan.modo_duracao||'fixo';el('swap-duration-info').textContent=plan.modo_duracao==='expandir'?'Falas maiores são aceitas. A prévia e o XML abrem espaço sem acelerar a voz.':'Este trabalho mantém a duração original. Para aceitar falas maiores, selecione Abrir espaço e aplique aos áudios existentes.';el('swap-autofit').disabled=plan.modo_duracao==='expandir'||busy;
    const statuses={espaco_ampliado:'Fala completa · o restante da timeline será deslocado',preparando_duracao:'Preparando duração localmente',encaixa:'Cabe na duração',silencio_adicionado:'Cabe com silêncio ao final',velocidade_ajustada:'Velocidade ajustada para caber',regenerar_longo:'Longo demais · regenere ou importe outro áudio',regenerar_curto:'Curto demais · confira/regere a frase'};
    el('flist').innerHTML=plan.itens.map((r,i)=>`<div class="card" data-swap-row="${r.id}" style="margin-top:12px"><div class="row"><label style="display:flex;flex-direction:row"><input type="checkbox" data-swap-approve data-approx="${r.mencoes_revisar?.length&&!(r.mencao_descartada&&r.novo_sem_sugestoes)?1:0}" ${r.aprovado?'checked':''}> Aprovar frase ${i+1}</label><span class="meta">${fmt(r.inicio_ms)}–${fmt(r.fim_ms)} · ${seconds(r.duracao_s)} · ${x(r.origem)}</span></div><p><b>Original:</b> ${x(r.original)}</p>${r.mencoes_revisar?.length?`<p class="ux-toast"><b>Menção provável</b> · ${r.mencoes_revisar.map(x).join(', ')}. Ouça o original. Se estiver correta, marque “Aprovar frase”.</p><button type="button" class="ghost" data-mention-ignore="${r.id}">${r.mencao_descartada?'Reconsiderar sugestão':r.novo_sem_sugestoes?'Manter só as menções exatas':'Descartar sugestão'}</button>`:''}${r.original_audio?`<span data-audio-placeholder="${url(r.original_audio)}"></span>`:''}${r.forma_detectada?`<p class="ux-toast"><b>Forma / uso do produto</b><br>${(r.forma_confirmada?['Adaptação de modo de uso aprovada por você.']:(r.forma_avisos||['Confira a adaptação da forma do produto.'])).map(x).join('<br>')}</p>`:''}<label>Frase nova ${i+1}<textarea data-swap-text rows="2">${x(r.novo)}</textarea></label>${r.speaker_pendente?`<p role="alert" style="color:var(--err)">${r.speaker_sugerido?x(r.speaker_aviso)+` Troque o speaker abaixo ou <label style="display:inline-flex;gap:6px;align-items:center"><input type="checkbox" data-swap-confirm-voice> ouvi e é o speaker ${x(r.speaker)} mesmo</label>`:'Confirme o speaker deste trecho. Nenhuma voz será escolhida automaticamente.'}</p>`:''}<label>Speaker da frase ${i+1}<select data-swap-speaker>${[...new Set([r.speaker,...plan.speakers])].map(s=>`<option value="${x(s)}" ${s===r.speaker?'selected':''}>Speaker ${x(s)}</option>`).join('')}</select></label>${r.audio?`<div style="margin-top:10px"><b>${x(statuses[r.audio.status]||r.audio.status)}</b><p class="meta">Gerado: ${seconds(r.audio.duracao_s)} · Janela original: ${seconds(r.audio.alvo_s)} · ${r.audio.modo_duracao==='expandir'?'Espaço adicional':'Diferença'}: ${Number.isFinite(r.audio.diferenca_ms)?r.audio.diferenca_ms+' ms':'—'}</p><div class="links"><a download href="${url(r.audio.raw)}?dl=1">Salvar cópia do áudio gerado</a>${r.audio.fit?`<a download href="${url(r.audio.fit)}?dl=1">Salvar cópia do áudio pronto</a>`:''}</div><label>Áudio gerado<span data-audio-placeholder="${url(r.audio.raw)}"></span></label>${r.audio.fit?`<label>Áudio pronto para encaixar<span data-audio-placeholder="${url(r.audio.fit)}"></span></label><button class="ghost" data-swap-audio="${r.id}" ${r.audio.aprovado?'disabled':''}>${r.audio.aprovado?'Áudio aprovado':'Ouvi e aprovo este áudio'}</button>`:'<p class="meta">O áudio não entrará na montagem até caber no trecho e ser aprovado.</p>'}</div>`:''}<details><summary>Já tenho a gravação desta frase</summary><label>Importar áudio novo ${i+1}<input type="file" accept="audio/*" data-swap-upload="${r.id}"></label><p class="meta">Confere duração localmente, sem créditos. O áudio precisará ser ouvido e aprovado.</p></details></div>`).join('');
    qa('[data-swap-text], [data-swap-approve], [data-swap-speaker]').forEach(e=>e.oninput=readiness);
    qa('[data-swap-confirm-voice]').forEach(e=>e.onchange=()=>save().catch(error=>{el('swap-error').textContent=error.message;}));
    qa('[data-swap-audio]').forEach(b=>b.onclick=()=>action(async()=>{await save();const row=plan.itens.find(r=>r.id===b.dataset.swapAudio);plan=await call('aprovar-audio',{id:row.id,hash:row.audio?.texto_hash});render();document.dispatchEvent(new CustomEvent('swap:audio-approved'));}));
    qa('[data-swap-upload]').forEach(input=>input.onchange=()=>{const file=input.files[0];if(file)importAudio(input.dataset.swapUpload,file);input.value='';});
    renderSpeakers();renderReview();setBusy(busy);durationNotice();document.dispatchEvent(new CustomEvent('swap:render'));
  }
  async function importAudio(rid,file){
    const work=folder,row=plan?.itens.find(r=>r.id===rid);
    if(!row||busy||importing)return;
    importing=true;
    const report=(status,message)=>document.dispatchEvent(new CustomEvent('swap:import-status',{detail:{rowId:rid,folder:work,status,message}}));
    await action(async()=>{
      try{
        if(!file||!file.size||file.size>50*1024*1024)throw Error('Escolha um áudio de até 50 MB.');
        if(!/\.(mp3|wav|m4a|aac|ogg|flac|aiff?|webm)$/i.test(file.name))throw Error('Arquivo inválido. Arraste um áudio MP3, WAV, M4A, AAC, OGG, FLAC, AIFF ou WebM.');
        if(await window.SwapUX.flushDraft?.()===false||window.SwapUX.hasDraft?.())throw Error('Salve as alterações da frase antes de importar.');
        if(folder!==work)throw Error('O projeto mudou. Importe novamente na frase desejada.');
        await save();
        if(folder!==work)throw Error('O projeto mudou. Importe novamente na frase desejada.');
        setBusy(true);report('enviando','Importando '+file.name+' para a frase '+(plan.itens.findIndex(r=>r.id===rid)+1)+'…');
        const response=await fetch('/fatiador/trocas/audio-upload',{method:'POST',headers:{'X-Folder':encodeURIComponent(work),'X-Row':rid,'X-Filename':encodeURIComponent(file.name),'Content-Type':file.type||'application/octet-stream'},body:file});
        const data=await response.json();if(!response.ok)throw Error(data.erro||'Não foi possível importar o áudio.');
        if(folder===work)startJob(data,{origin:'audio-import',rowId:rid});
      }catch(e){if(folder===work)report('erro',e.message);throw e;}
      finally{importing=false;if(!currentJob)setBusy(false);}
    });
  }
  function renderSpeakers(){
    qa('[data-swap-voice]').forEach(i=>voices[i.dataset.swapVoice]=i.value);
    const speakers=[...new Set(plan.itens.map(r=>r.speaker))];
    el('swap-speakers').innerHTML=speakers.map(s=>`<div class="card"><b>Speaker ${x(s)}</b>${plan.samples?.[s]?`<p class="meta">Amostra: ${seconds(plan.samples[s].duracao_s)}</p><span data-audio-placeholder="${url(plan.samples[s].arquivo)}"></span>`:'<p class="meta">Prepare a amostra ou use uma voz já existente.</p>'}${plan.samples?.[s]?.nome?'<p class="meta">Amostra atual: '+x(plan.samples[s].nome)+'</p>':''}<label>Usar outra voz existente · Speaker ${x(s)} (ID do serviço)<input type="text" data-swap-voice="${x(s)}" value="${x(voices[s]||'')}" placeholder="Vazio = clonar a amostra acima" data-swap-lock></label><details><summary>Substituir amostra por outra gravação</summary><p class="meta">Escolha um áudio de até 2 minutos e 50 MB. Ouça a gravação e confirme a autorização deste speaker antes de clonar.</p><label>Importar outra amostra<input type="file" accept="audio/*" data-sample-upload="${x(s)}" data-swap-lock></label></details></div>`).join('');
  }
  function renderReview(){
    const r=plan?.revisao;el('swap-review-result').innerHTML=r?`<p><b>${r.resquicios.length?'Há menções para revisar':'Nenhuma menção antiga encontrada na transcrição da montagem'}</b></p><span data-audio-placeholder="${url(r.audio)}"></span><a href="${url(r.arquivo)}?dl=1">Baixar relatório</a>${r.resquicios.map(h=>`<p>${fmt(h.inicio*1000)} · ${x(h.texto)} · ${x(h.status)}</p>`).join('')}<p class="meta">${x(r.observacao)} A correção do SRT abaixo é uma conferência separada do áudio.</p>`:'';
  }
  async function action(fn){el('swap-error').textContent='';el('swap-form-notice').hidden=true;try{await fn();}catch(e){el('swap-error').textContent=e.message;if(!currentJob){el('swap-status').classList.add('hidden');inlineProgress.classList.add('hidden');el('swap-form-message').textContent=e.message;el('swap-fix-duration').hidden=!durationPending();el('swap-form-notice').hidden=false;}else{el('swap-step').textContent=e.message;}}}
  window.loadSwapPlan=async(rebuild=false)=>{
    if(!folder||!el('prod2').value.trim())return;
    if(scope!==folder){plan=null;voices={};scope=folder;}
    await action(async()=>{plan=await call('plano',{rebuild,precos:el('swap-prices').checked});el('swap-prices').checked=plan.incluir_precos;el('swap-prices').disabled=!!plan.somente_valores;await restoreVoicePreferences();render();const pending=JSON.parse(sessionStorage.getItem('dr.swap.job')||'null');if(pending?.folder===folder&&!currentJob)startJob({id:pending.id},pending.context||{});});
  };
  function voiceOptions(){qa('[data-swap-voice]').forEach(i=>voices[i.dataset.swapVoice]=i.value.trim());voices=Object.fromEntries(Object.entries(voices).filter(([speaker])=>plan?.speakers.includes(speaker)));return {provider:el('swap-provider').value,model:el('swap-model').value,voices,autoriza_envio:el('swap-send').checked,autoriza_clonagem:el('swap-consent').checked,excluir_clones:el('swap-delete').checked,autofit:el('swap-autofit').checked};}
  async function restoreVoicePreferences(){const d=await call('preferencias-voz');if(d.provider){el('swap-provider').value=d.provider;providerChange();}if(d.model)el('swap-model').value=d.model;voices=d.voices||{};qa('[data-swap-voice]').forEach(i=>i.value=voices[i.dataset.swapVoice]||'');for(const [id,key] of [['swap-consent','autoriza_clonagem'],['swap-send','autoriza_envio'],['swap-delete','excluir_clones'],['swap-autofit','autofit']])if(key in d)el(id).checked=!!d[key];}
  function voiceFailureGroups(rows){
    const groups=new Map();
    for(const row of rows){
      if(!row.erro)continue;
      const key=JSON.stringify([row.speaker||'',row.erro]);
      if(!groups.has(key))groups.set(key,{message:row.erro,speaker:row.speaker||'',ids:[]});
      groups.get(key).ids.push(row.id);
    }
    return [...groups.values()];
  }
  function startJob(job,context={}){
    if(currentJob===job.id&&busy)return;
    jobContext=context;clearTimeout(poll);el('swap-dismiss-status').hidden=true;
    el('swap-cancel').hidden=false;currentJob=job.id;sessionStorage.setItem('dr.swap.job',JSON.stringify({id:job.id,folder,context:jobContext}));setBusy(true);el('swap-status').classList.add('working');el('swap-status').classList.remove('hidden');el('swap-job-errors').innerHTML='';voiceProgress({status:'na_fila',step:'Aguardando início do trabalho…'});pollJob();
  }
  async function pollJob(){
    if(!currentJob)return;if(polling){clearTimeout(poll);poll=setTimeout(pollJob,250);return;}
    const id=currentJob,work=folder;polling=true;const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),12000);
    try{
      const r=await fetch('/api/ml/job/'+id,{signal:controller.signal});const j=await r.json();if(id!==currentJob||work!==folder)return;
      if(!r.ok){if(r.status===404){currentJob=null;sessionStorage.removeItem('dr.swap.job');setBusy(false);inlineProgress.classList.add('hidden');el('swap-status').classList.remove('working');el('swap-step').textContent='Esta tarefa não está mais disponível. Seus arquivos salvos foram mantidos; reabra o trabalho para conferir.';el('swap-cancel').hidden=true;el('swap-dismiss-status').hidden=false;return;}throw Error(j.erro||'Não foi possível consultar a tarefa.');}
      voiceProgress(j);el('swap-step').textContent=j.step;
      if(['na_fila','executando'].includes(j.status)){clearTimeout(poll);poll=setTimeout(pollJob,2000);return;}
      el('swap-cancel').hidden=true;sessionStorage.removeItem('dr.swap.job');currentJob=null;el('swap-status').classList.remove('working');setBusy(false);
      const failures=(j.result?.resultados||[]).filter(r=>r.erro);el('swap-job-errors').innerHTML=(j.error?`<p role="alert">${x(j.error)}</p>`:'')+voiceFailureGroups(failures).map(e=>`<p role="alert">${e.speaker?'Speaker '+x(e.speaker)+' · ':''}${x(e.message)}${e.ids.length>1?' · '+e.ids.length+' frases pendentes':''}</p><details><summary>Ver frases afetadas</summary><p>${e.ids.map(x).join(', ')}</p></details>`).join('')+(j.result?.avisos||[]).map(w=>`<p>${x(w)}</p>`).join('');
      if(j.status==='concluido'&&!failures.length){status.classList.add('hidden');inlineProgress.classList.add('hidden');}else el('swap-dismiss-status').hidden=false;
      if(j.kind==='amostras'&&j.result?.speaker){
        voices[j.result.speaker]='';
        qa('[data-swap-voice]').filter(input=>input.dataset.swapVoice===j.result.speaker).forEach(input=>input.value='');
      }
      const finishedContext={...jobContext};await window.loadSwapPlan(false);if(work!==folder)return;document.dispatchEvent(new CustomEvent('swap:finished',{detail:{status:j.status,step:j.step,kind:j.kind,...finishedContext}}));if(!currentJob)jobContext={};
    }catch(e){if(id===currentJob&&work===folder){el('swap-step').textContent='Retomando consulta do andamento…';el('swap-inline-step').textContent=el('swap-step').textContent;clearTimeout(poll);poll=setTimeout(pollJob,4000);}}
    finally{clearTimeout(timeout);polling=false;}
  }
  el('swap-cancel').onclick=()=>currentJob&&fetch('/api/ml/job/'+currentJob+'/cancelar',{method:'POST'});
  el('swap-rebuild').onclick=()=>window.loadSwapPlan(true);
  el('swap-approve-all-audio').onclick=async()=>{
    if(busy)return;setBusy(true);
    try{await action(async()=>{
      await save();
      const selected=plan.itens.filter(r=>r.aprovado),eligible=selected.filter(r=>r.audio?.fit&&!r.audio.aprovado);let count=0;const failed=[];
      for(const row of eligible){
        el('swap-summary').textContent=`Aprovando áudios: ${count+failed.length+1} de ${eligible.length}…`;
        try{plan=await call('aprovar-audio',{id:row.id,hash:row.audio.texto_hash});count++;}catch(e){failed.push(e.message);}
      }
      render();
      const pending=plan.itens.filter(r=>r.aprovado&&!r.audio?.aprovado).map(r=>plan.itens.indexOf(r)+1);
      el('swap-batch-result').textContent=`${count} áudio(s) aprovado(s) agora.`+(pending.length?` Pendentes: frase(s) ${pending.join(', ')}. Confira a duração ou gere/importe o áudio que falta.`:' Tudo pronto para gerar a montagem em Entrega.');
      if(failed.length)el('swap-error').textContent=[...new Set(failed)].join(' · ');
    });}finally{setBusy(false);document.dispatchEvent(new CustomEvent('swap:audio-approved'));}
  };
  el('swap-save').onclick=()=>action(async()=>{await save();render();el('swap-summary').textContent+=' Salvo.';});
  el('swap-all').onclick=()=>{qa('[data-swap-approve]').forEach(i=>{if(i.dataset.approx!=='1')i.checked=true;});readiness();};
  el('swap-none').onclick=()=>{qa('[data-swap-approve]').forEach(i=>i.checked=false);readiness();};
  el('swap-speakers').addEventListener('change',event=>{
    const input=event.target.closest('[data-sample-upload]');
    if(!input)return;
    action(async()=>{
      const file=input.files[0];if(!file||busy)return;
      if(!file.size||file.size>50*1024*1024)throw Error('Escolha um áudio de até 50 MB.');
      if(await window.SwapUX.flushDraft()===false||window.SwapUX.hasDraft())throw Error('Salve os textos antes de substituir a amostra.');
      setBusy(true);
      try{
        const response=await fetch('/fatiador/trocas/amostra-upload',{method:'POST',
          headers:{'X-Folder':encodeURIComponent(folder),'X-Speaker':encodeURIComponent(input.dataset.sampleUpload),
                   'X-Filename':encodeURIComponent(file.name),'Content-Type':file.type||'application/octet-stream'},body:file});
        const result=await response.json();if(!response.ok)throw Error(result.erro);
        el('swap-consent').checked=false;el('swap-send').checked=false;
        startJob(result);
      }finally{if(!currentJob)setBusy(false);}
    });
  });
  el('swap-samples').onclick=()=>action(async()=>{await save();const d=await call('amostras-automaticas');if(d.job)startJob(d.job);else el('swap-key-status').textContent='Amostras locais prontas para ouvir.';});
  const models={elevenlabs:[['eleven_multilingual_v2','Multilingual v2'],['eleven_turbo_v2_5','Turbo v2.5'],['eleven_v3','Eleven v3']],minimax:[['speech-2.8-hd','Speech 2.8 HD'],['speech-2.8-turbo','Speech 2.8 Turbo']]};
  function providerChange(){el('swap-model').innerHTML=models[el('swap-provider').value].map(([id,n])=>`<option value="${id}">${n}</option>`).join('');el('swap-key').value='';el('swap-consent').checked=false;el('swap-send').checked=false;voices={};el('swap-speakers').innerHTML='';el('swap-key-status').textContent='Configure ou substitua a chave em Ajustes → Integrações e APIs.';if(plan)renderSpeakers();}
  el('swap-provider').onchange=providerChange;providerChange();
  el('swap-connect').onclick=()=>action(async()=>{const key=el('swap-key').value;await call('chave',{provider:el('swap-provider').value,key});el('swap-key').value='';el('swap-key-status').textContent='Chave salva no cofre deste computador. Permanecerá após fechar e atualizar o app.';});
  el('swap-forget').onclick=()=>action(async()=>{await call('esquecer-chave');el('swap-key').value='';el('swap-key-status').textContent='Chaves de voz removidas deste computador.';});
  async function generate(pending=false){if(busy)return;if(durationPending()){durationNotice();el('swap-form-notice').scrollIntoView({block:'center',behavior:'smooth'});el('swap-fix-duration').focus({preventScroll:true});return;}setBusy(true);voiceProgress({kind:'vozes',status:'na_fila',step:'Salvando textos e preparando geração…'});await action(async()=>{
    await save();qa('[data-swap-voice]').forEach(i=>voices[i.dataset.swapVoice]=i.value.trim());
    const options={provider:el('swap-provider').value,model:el('swap-model').value,voices,autoriza_envio:el('swap-send').checked,autoriza_clonagem:el('swap-consent').checked,excluir_clones:el('swap-delete').checked,autofit:el('swap-autofit').checked,regenerar:pending?false:el('swap-regenerate').checked,somente_pendentes:pending,adiar_modo_uso:true};
    await call('preferencias-voz',{salvar:true,config:voiceOptions()});const job=await call('gerar',{options});el('swap-cancel').hidden=false;startJob(job);
  });if(!currentJob)setBusy(false);}
  let regeneratingOne=false;
  async function regenerateOne(rowId,authorization={}){
    if(busy||regeneratingOne)throw Error('Aguarde a tarefa atual terminar.');
    regeneratingOne=true;const work=folder;
    try{
      if(await window.SwapUX.flushDraft?.()===false||window.SwapUX.hasDraft?.())throw Error('Salve as alterações da frase antes de regenerar.');
      if(work!==folder)throw Error('O projeto mudou. Confira a frase novamente.');
      await save();
      const row=plan?.itens.find(r=>r.id===rowId);
      if(!row||work!==folder)throw Error('A frase ou o projeto mudou. Atualize a lista.');
      if(!row.aprovado)throw Error('Selecione e aprove o texto desta frase antes de regenerar o áudio.');
      qa('[data-swap-voice]').forEach(i=>voices[i.dataset.swapVoice]=i.value.trim());
      const options={provider:el('swap-provider').value,model:el('swap-model').value,
        voices:{[row.speaker]:voices[row.speaker]||''},autoriza_envio:authorization.autoriza_envio===true,
        autoriza_clonagem:authorization.autoriza_clonagem===true,excluir_clones:el('swap-delete').checked,
        autofit:el('swap-autofit').checked,regenerar:true,somente_pendentes:false,row_ids:[rowId]};
      if(!options.autoriza_envio)throw Error('Confirme o envio e o possível consumo de créditos desta frase.');
      if(!options.voices[row.speaker]&&!options.autoriza_clonagem)throw Error('Confirme a autorização para usar a amostra deste speaker ou configure uma voz existente.');
      jobContext={origin:'audio-regenerate',rowId,previousRaw:row.audio?.raw||''};
      setBusy(true);voiceProgress({kind:'vozes',status:'na_fila',step:'Regenerando somente esta frase…'});
      const job=await call('regenerar-frase',{id:rowId,options});
      startJob(job,{origin:'audio-regenerate',rowId,previousRaw:row.audio?.raw||''});
      return true;
    }catch(error){if(!currentJob){jobContext={};status.classList.add('hidden');inlineProgress.classList.add('hidden');}throw error;}
    finally{regeneratingOne=false;if(!currentJob)setBusy(false);}
  }
  el('swap-regenerate').onchange=readiness;
  el('swap-generate').onclick=()=>generate(!el('swap-regenerate').checked);
  el('swap-export').onclick=()=>action(async()=>{await save();el('swap-export').disabled=true;try{const r=await call('exportar');el('swap-export-result').innerHTML=`<p><b>Montagem salva no trabalho atual.</b> ${r.trechos} troca(s) de áudio e ${r.visuais||0} sobreposição(ões) em V2. Salve uma cópia do XML abaixo para importar no Premiere.</p><div class="links"><a download data-studio-xml="${x(r.xml)}" href="${url(r.xml)}?dl=1">Salvar montagem XML em Downloads</a><a href="${url(r.json)}?dl=1">Salvar relatório JSON</a></div><p class="meta">Premiere → Arquivo → Importar (⌘I) → abra a sequência com o mesmo nome do XML. A1 mantém o restante original; A2 guarda os trechos originais desativados e A3 contém as falas novas correspondentes. Confira os pontos de entrada/saída e o volume antes de exportar.</p>`;}finally{readiness();}});
  el('swap-review').onclick=()=>action(async()=>{await save();el('swap-cancel').hidden=false;startJob(await call('revisar',{aliases:el('alias2').value}));});
  window.SwapUX={acceptPlan(value){const same=JSON.stringify(plan?.itens)===JSON.stringify(value.itens);plan=value;if(same)readiness();else render();return !same;},get plan(){return plan;},get busy(){return busy;},canGenerate,capture,save,render,readiness,generate,call,action,startJob,renderSpeakers,voiceOptions,restoreVoicePreferences,importAudio,regenerateOne};
  const oldStep=wizardStep;
  wizardStep=function(n){if(n>=4&&plan&&!busy){return action(async()=>{await save();oldStep(n);document.dispatchEvent(new CustomEvent('swap:step'));});}else {oldStep(n);document.dispatchEvent(new CustomEvent('swap:step'));}};
})();
