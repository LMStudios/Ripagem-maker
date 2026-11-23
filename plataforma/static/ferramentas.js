/* Painel com dois caminhos (fluxo completo e ferramentas avulsas), projetos recentes e ferramentas locais. */
(() => {
 const R = window.RMJob;
 const size = b => b >= 1024 ** 3 ? (b / 1024 ** 3).toFixed(2) + ' GB' : b >= 1024 ** 2 ? (b / 1024 ** 2).toFixed(1) + ' MB' : Math.round((b || 0) / 1024) + ' KB';
 const date = s => { try { return new Date(typeof s === 'number' ? s * 1000 : s).toLocaleDateString('pt-BR'); } catch (e) { return ''; } };
 const deep = (folder, step, tool) => '/fatiador?' + new URLSearchParams({...(folder ? {trabalho: folder} : {}), ...(step ? {etapa: step} : {}), ...(tool ? {ferramenta: tool} : {})});

 function projectRows(list, compact) {
  if (!list.length) return '<div class="empty">Nenhum projeto ainda. Comece pelo fluxo completo ou pela transcrição.</div>';
  return `<div class="rm-project-list"><table class="t rm-project-table"><tr><th></th><th>Projeto</th><th>Produto</th><th>Etapa</th><th>Atualizado</th><th></th></tr>${list.map(p => `<tr>
   <td><button class="ghost btn sm" data-fav="${esc(p.pasta)}" data-on="${p.favorito ? 1 : 0}" aria-pressed="${p.favorito}" title="${p.favorito ? 'Favorito (protegido da limpeza)' : 'Marcar como favorito'}">${p.favorito ? '★' : '☆'}</button></td>
   <td><b>${esc(p.nome)}</b>${compact ? '' : `<div class="small mute mono">${esc(p.caminho)}</div>`}${p.em_uso ? ' <span class="chip run">em processamento</span>' : ''}</td>
   <td>${esc(p.produto || '—')}</td><td class="small">${esc(p.etapa)}</td><td class="small">${date(p.atualizado)}</td>
   <td style="text-align:right;white-space:nowrap"><a class="btn sm pri" href="${deep(p.pasta)}">Continuar</a> <button class="btn sm" data-rm-open="${esc(p.caminho)}">Abrir pasta</button> <button class="btn sm" data-rm-copy="${esc(p.caminho)}">Copiar caminho</button><span role="status" class="small mute"></span></td></tr>`).join('')}</table></div>`;
 }
 document.addEventListener('click', async e => {
  const b = e.target.closest('[data-fav]'); if (!b) return;
  try { const p = await post('/api/projetos/favorito', {pasta: b.dataset.fav, favorito: b.dataset.on !== '1'}); b.dataset.on = p.favorito ? '1' : '0'; b.textContent = p.favorito ? '★' : '☆'; b.setAttribute('aria-pressed', p.favorito); toast(p.favorito ? 'Favorito: protegido da limpeza.' : 'Removido dos favoritos.'); }
  catch (error) { toast(error.message, true); }
 });

 /* ------------------------------------------------------------------ painel */
 routes['/'] = async () => {
  const [data, jobs] = await Promise.all([api('/api/ferramentas'), api('/api/ml/jobs').catch(() => [])]);
  const active = jobs.filter(j => ['na_fila', 'executando'].includes(j.status));
  const interrupted = jobs.filter(j => j.status === 'erro' && j.step === 'Interrompida').slice(0, 3);
  $('#view').innerHTML = `
   <div class="page-h clean-home-heading"><div><p class="clean-eyebrow">SEU ESTÚDIO</p><h1>Vamos editar?</h1><p>Comece uma ripagem ou continue de onde parou.</p></div></div>
   ${interrupted.length ? `<details class="clean-interrupted"><summary><span role="status">${interrupted.length} tarefa(s) interrompida(s) · arquivos salvos preservados</span><span class="small">Ver detalhes</span></summary>${interrupted.map(j => `<p class="small">${esc(j.title)}: ${esc(j.error)}</p>`).join('')}</details>` : ''}
   <section class="card clean-home-start" aria-labelledby="home-start-title">
    <div><span class="clean-eyebrow">TROCA DE POTES</span><h2 id="home-start-title">Do vídeo à entrega.</h2><p>Textos, vozes e takes no mesmo fluxo, com seu trabalho salvo a cada etapa.</p>
     <div class="clean-home-actions"><a class="btn pri" href="/fatiador?inicio=novo">Nova ripagem <span aria-hidden="true">→</span></a><a class="btn ghost" href="/fatiador?inicio=continuar">Continuar projeto</a></div>
    </div>
    <ol class="clean-home-steps" aria-label="Etapas da ripagem"><li><span>01</span> Importar vídeo</li><li><span>02</span> Revisar falas e takes</li><li><span>03</span> Entregar para o Premiere</li></ol>
   </section>
   <a class="clean-tool-shortcut" href="#/ferramentas"><span class="clean-shortcut-icon" aria-hidden="true">▦</span><span><b>Precisa de uma tarefa avulsa?</b><small>Transcrição, áudio, takes e legendas.</small></span><span class="clean-shortcut-link">Ver ferramentas <span aria-hidden="true">→</span></span></a>
   <section id="home-jobs" class="card" ${active.length ? '' : 'hidden'}><h2>Em andamento</h2><div id="home-jobs-list"></div></section>
   <section class="card"><div class="row" style="justify-content:space-between;align-items:baseline"><h2>Projetos recentes</h2><a class="small" href="#/projetos">Ver todos →</a></div>${projectRows(data.projetos.slice(0, 6), true)}</section>
   <nav class="clean-home-utilities" aria-label="Mais recursos"><a href="#/demanda">Microlead’s</a><a href="#/nomes">Nomenclatura VTurb</a><a href="#/ajustes">Ajustes</a></nav>`;
  const list = $('#home-jobs-list');
  active.slice(0, 4).forEach(j => { const box = document.createElement('div'); list.append(box); R.watch(j.id, box, {onDone: () => ''}); });
 };

 routes['/projetos'] = async () => {
  const d = await api('/api/projetos');
  $('#view').innerHTML = `<div class="page-h"><div><h1>Projetos</h1><p>Cada projeto fica numa pasta com nome, produto e data. Favoritos e projetos em processamento ficam protegidos da limpeza.</p></div></div>
   <section class="card"><h2>Onde os novos projetos são criados</h2>${R.pathActions(d.pasta_novos)}<p class="small mute">Para mudar, vá em <a href="#/ajustes">Ajustes → Pasta dos novos projetos</a>. Para levar um projeto existente com os materiais, use “Mover projeto” dentro dele.</p></section>
   <section class="card">${projectRows(d.projetos, false)}</section>`;
 };

 routes['/ferramenta/broll'] = () => {
  const view = $('#view');
  view.innerHTML = `<div class="page-h"><div><h1>Caçar B-rolls</h1><p>Busque por assunto ou cole um link para baixar um trecho do vídeo.</p></div><a class="btn" href="#/ferramentas">← Ferramentas</a></div><div id="broll-library"></div>`;
  window.mountBrollLibrary($('#broll-library', view));
 };

 /* ------------------------------------------------------------------ ferramentas avulsas */
 const toolGroups = [
  {name: 'Texto e transcrição', items: [
   ['transcricao', 'Transcrever arquivo', 'Transforme áudio ou vídeo em texto por pessoa.', 'text'],
   ['mencoes', 'Encontrar menções', 'Localize e revise as falas sobre o produto antigo.', 'search'],
   ['adaptacao', 'Adaptar produto e modo de uso', 'Reescreva as falas para o novo produto.', 'edit'],
  ]},
  {name: 'Voz e áudio', items: [
   ['falas', 'Gerar falas por voz', 'Crie áudios para as frases aprovadas, por pessoa.', 'voice'],
   ['tratamento', 'Limpar áudio', 'Apare o silêncio das bordas e reduza o ruído.', 'audio'],
   ['separacao', 'Separar voz e trilha', 'Extraia voz e música em arquivos separados.', 'split'],
  ]},
  {name: 'Imagem e entrega', items: [
   ['takes', 'Preparar takes', 'Escolha os vídeos que cobrem as falas substituídas.', 'film'],
   ['broll', 'Caçar B-rolls', 'Busque, assista e baixe clipes para seus vídeos.', 'film'],
   ['srt', 'Corrigir legendas SRT', 'Revise as referências ao produto nas legendas.', 'caption'],
   ['premiere', 'Exportar XML para o Premiere', 'Gere a sequência editável para importar.', 'export'],
  ]},
 ];
 const toolIcons = {
  text: '<path d="M5 5h14M5 10h14M5 15h10M5 20h7"/>',
  search: '<circle cx="10.5" cy="10.5" r="5.5"/><path d="m15 15 5 5"/>',
  edit: '<path d="m4 20 4-.8L20 7l-3-3L5 16zm10-13 3 3"/>',
  voice: '<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M6 11v1a6 6 0 0 0 12 0v-1m-6 7v3m-3 0h6"/>',
  audio: '<path d="M3 12h2l2-4 3 9 3-12 3 14 2-7h3"/>',
  split: '<path d="M4 12h5m0 0 6-6h5m-11 6 6 6h5m-3-15 3 3-3 3m0 6 3 3-3 3"/>',
  film: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m10 9 5 3-5 3z"/>',
  caption: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M6 11h7m2 0h3M6 15h3m2 0h7"/>',
  export: '<path d="M12 15V3m-4 4 4-4 4 4M5 13v6a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-6"/>',
 };
 const toolIcon = name => `<span class="rm-catalog-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${toolIcons[name]}</svg></span>`;
 routes['/ferramentas'] = async () => {
  const d = await api('/api/ferramentas');
  if (location.hash.split('?')[0] !== '#/ferramentas') return;
  const catalog = new Map(d.ferramentas.map(t => [t.id, t]));
  const labels = new Map(toolGroups.flatMap(g => g.items).map(([id, name]) => [id, name]));
  const options = d.projetos.map(p => `<option value="${esc(p.pasta)}">${esc(p.nome)}${p.produto ? ' · ' + esc(p.produto) : ''} · ${date(p.atualizado)}</option>`).join('');
  $('#view').innerHTML = `<div class="rm-catalog">
   <header class="rm-catalog-header"><span class="rm-catalog-kicker">ÁREA DE EDIÇÃO</span><h1>Ferramentas avulsas</h1>
    <p>Escolha o que você quer fazer agora. Você escolhe o arquivo ou o projeto no próximo passo.</p></header>
   <div class="rm-catalog-groups">${toolGroups.map((g, i) => `
    <section class="rm-catalog-group" aria-labelledby="rm-catalog-group-${i}">
     <h2 id="rm-catalog-group-${i}">${esc(g.name)}</h2>
     <ul>${g.items.filter(([id]) => catalog.has(id)).map(([id, title, summary, icon]) => {
      const t = catalog.get(id);
      return `<li><button type="button" class="ghost rm-catalog-tool" data-tool="${id}" aria-haspopup="dialog">
       ${toolIcon(icon)}<span class="rm-catalog-copy"><strong>${esc(title)}</strong><span>${esc(summary)}</span></span>
       ${t.disponivel === false ? '<span class="rm-catalog-unavailable">Indisponível</span>' : ''}
       <span class="rm-catalog-arrow" aria-hidden="true">›</span>
      </button></li>`;
     }).join('')}</ul>
    </section>`).join('')}</div>
   <p class="rm-catalog-foot">Precisa fazer todas as etapas? <a href="/fatiador">Abrir o fluxo de troca de potes</a></p>
   <dialog class="rm-catalog-dialog" aria-labelledby="rm-tool-title"></dialog>
  </div>`;
  const dialog = $('.rm-catalog-dialog');
  let trigger;
  dialog.addEventListener('close', () => trigger?.focus());
  $$('.rm-catalog-tool').forEach(button => button.onclick = () => {
   const t = catalog.get(button.dataset.tool);
   const isTreatment = t.id === 'tratamento';
   const step = isTreatment ? 3 : t.etapa;
   const needsProject = t.reaproveita && step;
   const unavailable = t.disponivel === false;
   const direct = t.id === 'transcricao' ? ['Transcrever um arquivo', deep('', 1, t.id)]
    : t.avulsa ? [isTreatment ? 'Tratar arquivos avulsos' : t.id === 'broll' ? 'Abrir buscador' : 'Escolher arquivo', '#/ferramenta/' + t.id]
    : null;
   const projectControl = needsProject ? d.projetos.length ? `
    <label class="f" for="rm-tool-project">${isTreatment ? 'Ou use os áudios de um projeto' : 'Escolher projeto'}
     <select id="rm-tool-project"><option value="">Selecione um projeto</option>${options}</select>
    </label><button class="btn ${direct ? 'ghost' : 'pri'}" type="button" data-project-go disabled>Abrir com este projeto</button>`
    : '<p class="rm-catalog-note">Você ainda não tem projetos. <a href="/fatiador?etapa=1&ferramenta=transcricao">Transcreva um arquivo</a> para criar o primeiro.</p>' : '';
   dialog.innerHTML = `
    <form method="dialog"><button class="ghost rm-catalog-close" type="submit" aria-label="Fechar" autofocus>×</button></form>
    <h2 id="rm-tool-title">${esc(labels.get(t.id))}</h2>
    <p>${esc(t.entrega)}</p>
    ${unavailable ? `<p class="rm-catalog-warning">${esc(t.aviso || 'Esta ferramenta não está disponível nesta instalação.')}</p>` : `
     ${direct ? `<a class="btn pri rm-catalog-action" href="${direct[1]}">${direct[0]}</a>` : ''}
     ${projectControl}
     ${t.id === 'srt' && d.projetos.length ? `<p class="rm-catalog-note"><a href="${deep('', 1, 'transcricao')}">Sem projeto? Comece pela transcrição</a></p>` : ''}
    `}
    <details><summary>Requisitos e onde salva</summary><dl>
     <dt>Você precisa de</dt><dd>${esc(t.recebe)}</dd>
     <dt>Salva em</dt><dd>${esc(t.salva)}</dd>
     <dt>Processamento e créditos</dt><dd>${esc(t.custo)}</dd>
    </dl></details>`;
   const select = $('#rm-tool-project', dialog), go = $('[data-project-go]', dialog);
   if (select && go) {
    select.onchange = () => go.disabled = !select.value;
    go.onclick = () => { if (select.value) location.href = deep(select.value, step, t.id); };
   }
   dialog.querySelector('a[href^="#/"]')?.addEventListener('click', () => dialog.close());
   trigger = button;
   dialog.showModal();
  });
 };

 const optionsForm = R.treatForm, readOptions = R.readTreat;
 window.RMTreatmentForm = {html: optionsForm, read: readOptions};

 async function upload(endpoint, file, session, onProgress) {
  return new Promise((resolve, reject) => {
   const x = new XMLHttpRequest(); x.open('POST', endpoint);
   x.setRequestHeader('X-Filename', encodeURIComponent(file.name)); if (session) x.setRequestHeader('X-Sessao', session);
   x.upload.onprogress = e => e.lengthComputable && onProgress(e.loaded / e.total);
   x.onload = () => { let d = {}; try { d = JSON.parse(x.responseText); } catch (e) {} x.status === 200 ? resolve(d) : reject(Error(d.erro || 'Falha no envio (HTTP ' + x.status + ').')); };
   x.onerror = () => reject(Error('O app local não respondeu.'));
   x.send(file);
  });
 }
 const media = (rel, name) => '/ferramentas/arquivo/' + (rel + '/' + name).split('/').map(encodeURIComponent).join('/');

 routes['/ferramenta/tratamento'] = async () => {
  const s = await api('/api/tratamento/padrao');
  $('#view').innerHTML = `<div class="page-h"><div><h1>Tratamento de áudio</h1><p>Recebe áudios avulsos e entrega cópias com o silêncio das bordas aparado e o ruído reduzido. Os originais ficam intactos ao lado.</p></div><a class="btn" href="#/ferramentas">← Ferramentas</a></div>
   <section class="card"><label class="f">Áudios (WAV, MP3, M4A…)<input type="file" id="ta-files" multiple accept="audio/*,video/*"></label>${optionsForm(s)}
   <button class="btn pri" id="ta-go" disabled>Tratar áudios</button><p class="small mute">Salva em Ferramentas/Tratamento de audio/&lt;data&gt; dentro da pasta principal.</p><div id="ta-progress" hidden></div><div id="ta-result"></div></section>`;
  const input = $('#ta-files'), go = $('#ta-go');
  input.onchange = () => go.disabled = !input.files.length;
  go.onclick = async () => {
   go.disabled = true; let session = '', names = [];
   const box = $('#ta-progress'); box.hidden = false;
   try {
    for (const [i, f] of [...input.files].entries()) {
     box.innerHTML = `<div class="rm-progress"><div class="rm-phase">Enviando ${i + 1} de ${input.files.length}: ${esc(f.name)}</div><div class="rm-bar"><i style="width:0"></i></div></div>`;
     const d = await upload('/api/ferramentas/tratamento/enviar', f, session, p => box.querySelector('i').style.width = Math.round(p * 100) + '%');
     session = d.sessao; names.push(d.arquivo);
    }
    const job = await post('/api/ferramentas/tratamento/processar', {sessao: session, arquivos: names, opcoes: readOptions($('#view'))});
    R.watch(job, box, {onDone: r => `${R.pathActions(r.pasta)}${r.arquivos.map(a => `<div class="card" style="margin-top:8px"><b>${esc(a.original)}</b>
       <p class="small">${a.duracao_antes_s.toFixed(2)} s → ${a.duracao_depois_s.toFixed(2)} s · início −${a.removido_inicio_ms} ms · fim −${a.removido_fim_ms} ms${a.ruido_reduzido ? ' · ruído reduzido' : ''}${a.sem_fala_detectada ? ' · <span style="color:var(--warn)">fala não detectada: bordas mantidas</span>' : ''}</p>
       <div class="row" style="gap:12px"><label class="f">Original<audio controls preload="none" src="${media(r.relativo, a.original)}"></audio></label><label class="f">Tratado<audio controls preload="none" src="${media(r.relativo, a.tratado)}"></audio></label></div></div>`).join('')}`, onError: () => go.disabled = false});
   } catch (e) { box.innerHTML = `<p class="rm-err">${esc(e.message)}</p>`; go.disabled = false; }
  };
 };

 routes['/ferramenta/separacao'] = async () => {
  const d = await api('/api/ferramentas'); const t = d.ferramentas.find(x => x.id === 'separacao');
  $('#view').innerHTML = `<div class="page-h"><div><h1>Separação de voz e trilha</h1><p>${esc(t.recebe)} Entrega: ${esc(t.entrega)}</p></div><a class="btn" href="#/ferramentas">← Ferramentas</a></div>
   <section class="card">${t.disponivel ? '' : `<div class="banner warn" style="display:block"><b>Componente não instalado</b><p>${esc(t.aviso)}</p><p class="small">Enquanto isso, se você tiver a trilha em arquivo separado, use “Trilha separada” na etapa Validação e entrega do fluxo completo.</p></div>`}
   <label class="f">Arquivo<input type="file" id="sp-file" accept="audio/*,video/*" ${t.disponivel ? '' : 'disabled'}></label><button class="btn pri" id="sp-go" disabled>Separar</button><div id="sp-progress" hidden></div></section>`;
  const input = $('#sp-file'), go = $('#sp-go'); input.onchange = () => go.disabled = !input.files.length || !t.disponivel;
  go.onclick = async () => {
   go.disabled = true; const box = $('#sp-progress'); box.hidden = false;
   try {
    const f = input.files[0]; box.innerHTML = `<div class="rm-progress"><div class="rm-phase">Enviando ${esc(f.name)}</div><div class="rm-bar"><i></i></div></div>`;
    const up = await upload('/api/ferramentas/separacao/enviar', f, '', p => box.querySelector('i').style.width = Math.round(p * 100) + '%');
    const job = await post('/api/ferramentas/separacao/processar', {sessao: up.sessao, arquivo: up.arquivo});
    R.watch(job, box, {onDone: r => `${R.pathActions(r.pasta)}<div class="row" style="gap:12px"><label class="f">Voz<audio controls src="${media(r.relativo, r.voz)}"></audio></label><label class="f">Trilha<audio controls src="${media(r.relativo, r.trilha)}"></audio></label></div>`, onError: () => go.disabled = false});
   } catch (e) { box.innerHTML = `<p class="rm-err">${esc(e.message)}</p>`; go.disabled = false; }
  };
 };

 const nav = document.querySelector('.nav a[href="/fatiador"]');
 if (nav && !document.querySelector('.nav a[data-r="/ferramentas"]')) {
  nav.insertAdjacentHTML('afterend', '<a href="#/ferramentas" data-r="/ferramentas"><span class="ico" aria-hidden="true">▦</span>Ferramentas avulsas</a><a href="#/projetos" data-r="/projetos"><span class="ico" aria-hidden="true">▤</span>Projetos</a>');
  nav.innerHTML = '<span class="ico" aria-hidden="true">✂</span>Troca de potes';
 }
})();
