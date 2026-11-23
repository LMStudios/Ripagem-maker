/* Ajustes: pasta dos novos projetos, mover projeto, armazenamento e limpeza, limpeza automática e tratamento padrão. */
(() => {
 const R = window.RMJob;
 const size = b => b >= 1024 ** 3 ? (b / 1024 ** 3).toFixed(2) + ' GB' : b >= 1024 ** 2 ? (b / 1024 ** 2).toFixed(1) + ' MB' : Math.round((b || 0) / 1024) + ' KB';
 const date = s => new Date(s * 1000).toLocaleDateString('pt-BR');
 async function chooseFolder() {
  const bridge = window.ripagemDesktop || window.pywebview?.api;
  if (bridge?.choose_folder) { const d = await bridge.choose_folder(); if (!d.ok) throw Error(d.erro); return d.cancelado ? '' : d.pasta; }
  return (prompt('Cole o caminho completo da pasta de destino:') || '').trim();
 }
 window.RMChooseFolder = chooseFolder;

 /* Mover um projeto com os materiais: verifica, confirma e acompanha. Reutilizado dentro do projeto. */
 async function moveProject(folder, box, onDone) {
  const dest = await chooseFolder(); if (!dest) return;
  let check;
  try { check = await post('/api/projetos/verificar-destino', {pasta: folder, destino: dest}); }
  catch (e) { box.innerHTML = `<p class="rm-err" role="alert">${esc(e.message)}</p>`; return; }
  const msg = `Mover o projeto com todos os materiais?\n\nDe: ${check.origem}\nPara: ${check.destino}\nTamanho: ${size(check.bytes)} · livre no destino: ${size(check.livre_bytes)}${check.mesmo_disco ? '' : '\n(outro disco: a cópia pode demorar)'}\n\nO app copia, confere cada arquivo e só então manda a pasta antiga para a Lixeira.` +
   (check.xmls_a_refazer.length ? `\n\nAtenção: ${check.xmls_a_refazer.length} XML(s) já exportado(s) apontam para o local atual e precisarão ser gerados novamente.` : '');
  if (!confirm(msg)) return;
  try {
   const job = await post('/api/projetos/mover', {pasta: folder, destino: dest});
   R.watch(job, box, {onDone: r => { onDone && onDone(r); return `<p>${esc(r.observacao)}</p>${R.pathActions(r.destino)}${r.xmls_a_refazer.length ? `<p class="small" style="color:var(--warn)">XMLs a gerar novamente: ${r.xmls_a_refazer.map(esc).join(', ')}</p>` : ''}`; }});
  } catch (e) { box.innerHTML = `<p class="rm-err" role="alert">${esc(e.message)}</p>`; }
 }
 window.RMMoveProject = moveProject;

 const previous = routes['/ajustes'];
 routes['/ajustes'] = async () => {
  await previous();
  const [cfg, projects, storage] = await Promise.all([api('/api/ajustes'), api('/api/projetos'), api('/api/armazenamento')]);
  // Pasta principal: deixa claro que muda só o destino dos novos projetos.
  const main = [...$$('#view .card')].find(c => /Pasta principal dos arquivos/.test(c.querySelector('h2')?.textContent || ''));
  if (main) {
   main.querySelector('h2').textContent = 'Pasta dos novos projetos';
   const p = main.querySelector('p.small.mute');
   if (p) p.innerHTML = '<b>Muda só onde os próximos projetos serão criados</b> (subpastas Fatiador, Montagens, Biblioteca e Ferramentas). Os projetos existentes continuam onde estão e seguem abríveis. Para levar um projeto com seus materiais, use <b>Mover projeto</b> no cartão abaixo ou dentro do projeto. Se houver uma tarefa em andamento, a mudança pode ser salva assim que ela terminar.';
   main.insertAdjacentHTML('beforeend', `<p class="small"><b>Os novos projetos vão para:</b></p>${R.pathActions(cfg.pastas.fatiador)}`);
  }
  const anchor = main || $('#view .page-h');

  const moveCard = document.createElement('section'); moveCard.className = 'card';
  moveCard.innerHTML = `<h2>Mover um projeto com os materiais</h2><p class="small mute">Copia tudo para a pasta escolhida, confere arquivo por arquivo, atualiza as referências internas e só então manda a pasta antiga para a Lixeira. Se for interrompido, a versão original continua intacta e o app conclui ou desfaz a cópia na próxima abertura.</p>
   ${projects.projetos.length ? `<table class="t"><tr><th>Projeto</th><th>Local atual</th><th></th></tr>${projects.projetos.map(p => `<tr><td><b>${esc(p.nome)}</b><div class="small mute">${esc(p.produto || '')}</div></td><td class="small mono" style="word-break:break-all">${esc(p.caminho)}</td><td style="text-align:right;white-space:nowrap"><button class="btn sm" data-move="${esc(p.pasta)}" ${p.em_uso ? 'disabled title="Em processamento: mova quando a tarefa terminar"' : ''}>Mover…</button> <button class="btn sm" data-rm-open="${esc(p.caminho)}">Abrir pasta</button><span role="status"></span></td></tr>`).join('')}</table>` : '<div class="empty">Nenhum projeto ainda.</div>'}<div id="move-progress" hidden></div>`;
  anchor.after(moveCard);
  moveCard.querySelectorAll('[data-move]').forEach(b => b.onclick = () => moveProject(b.dataset.move, $('#move-progress'), () => setTimeout(render, 2500)));

  // ---------------------------------------------------------------- armazenamento e limpeza
  const card = document.createElement('section'); card.className = 'card'; card.id = 'storage-card';
  card.innerHTML = `<h2>Armazenamento e limpeza</h2><p class="small mute">Veja quanto cada tipo de material ocupa e escolha o que pode ir para a Lixeira. Nada é apagado só por ser antigo: favoritos, projetos abertos nas últimas 24 h, em processamento e arquivos citados por um projeto ou por um XML exportado ficam protegidos. Tudo vai para a Lixeira e pode ser recuperado.</p>
   <div id="st-usage"></div><button class="btn" id="st-measure">Medir espaço ocupado</button><div id="st-measure-progress" hidden></div>
   <h3 style="margin-top:18px">Escolher o que limpar</h3>
   <div class="row" style="gap:14px;flex-wrap:wrap"><label><input type="checkbox" data-cat="temporarios" checked> Temporários (sobras de tarefas interrompidas, uploads antigos)</label><label><input type="checkbox" data-cat="caches" checked> Caches recriáveis</label><label><input type="checkbox" data-cat="previas"> Prévias antigas (a prévia atual de cada projeto fica)</label><label><input type="checkbox" data-cat="projetos_antigos"> Projetos sem uso há <input type="number" id="st-days" min="1" max="3650" value="${storage.regras.dias}" style="width:80px;min-width:0"> dias</label></div>
   <button class="btn pri" id="st-plan" style="margin-top:10px">Conferir o que pode ser limpo</button><div id="st-plan-progress" hidden></div><div id="st-plan-result"></div>
   ${storage.ultimo_relatorio ? `<details style="margin-top:12px"><summary>Último relatório${storage.ultimo_relatorio.automatica ? ' (automático)' : ''} · ${date(storage.ultimo_relatorio.quando)} · ${size(storage.ultimo_relatorio.liberado_bytes)}</summary>${report(storage.ultimo_relatorio)}</details>` : ''}`;
  moveCard.after(card);
  const usage = u => u ? `<p class="small mute">Medido em ${date(u.medido_em)} · ${size(u.livre_bytes)} livres no disco</p><table class="t">${u.categorias.map(c => `<tr><td>${esc(c.nome)}</td><td class="mono" style="text-align:right">${size(c.bytes)}</td></tr>`).join('')}</table>${u.categorias.find(c => c.id === 'recuperacao' && c.bytes) ? '<p class="small mute">A pasta de recuperação guarda itens que a Lixeira do sistema não aceitou. Esvazie-a manualmente quando tiver certeza.</p>' : ''}` : '<p class="small mute">Ainda não medido.</p>';
  $('#st-usage').innerHTML = usage(storage.uso);
  $('#st-measure').onclick = async () => { try { R.watch(await post('/api/armazenamento/medir', {}), $('#st-measure-progress'), {onDone: u => { $('#st-usage').innerHTML = usage(u); return ''; }}); } catch (e) { toast(e.message, true); } };
  let lastPlan = null;
  const plan = async (projetos = []) => {
   const cats = [...card.querySelectorAll('[data-cat]:checked')].map(i => i.dataset.cat);
   if (!cats.length) { toast('Marque pelo menos um tipo de material.', true); return; }
   try { R.watch(await post('/api/armazenamento/conferir', {categorias: cats, dias: Number($('#st-days').value), projetos}), $('#st-plan-progress'), {onDone: p => { lastPlan = p; showPlan(p); return ''; }}); }
   catch (e) { toast(e.message, true); }
  };
  $('#st-plan').onclick = () => plan();
  function showPlan(p) {
   const old = p.projetos_antigos || [];
   $('#st-plan-result').innerHTML = `<p><b>Estimativa: ${size(p.estimado_bytes)}</b> em ${p.itens.length} item(ns) · ${size(p.livre_bytes)} livres hoje.</p>
    ${old.length ? `<h4>Projetos sem uso no período</h4><p class="small mute">Marque os que podem ir para a Lixeira e clique em “Incluir projetos marcados”.</p><table class="t">${old.map(o => `<tr><td><label><input type="checkbox" data-old="${esc(o.pasta)}" ${o.protecao ? 'disabled' : ''} ${p.itens.some(i => i.categoria === 'projetos_antigos' && i.caminho.endsWith(o.pasta)) ? 'checked' : ''}> <b>${esc(o.nome)}</b></label><div class="small mute">${esc(o.produto || '')} · ${esc(o.etapa)} · atualizado em ${date(o.atualizado)}</div></td><td class="mono">${size(o.bytes)}</td><td class="small">${o.protecao ? '🔒 ' + esc(o.protecao) : ''}</td></tr>`).join('')}</table><button class="btn sm" id="st-include">Incluir projetos marcados</button>` : ''}
    ${p.itens.length ? `<h4>Itens que vão para a Lixeira</h4><div style="max-height:320px;overflow:auto"><table class="t">${p.itens.map((i, n) => `<tr><td><label><input type="checkbox" data-item="${n}" checked> <span class="small mono" style="word-break:break-all">${esc(i.caminho)}</span></label><div class="small mute">${esc(i.motivo)}</div></td><td class="mono">${size(i.bytes)}</td></tr>`).join('')}</table></div>
     <button class="btn pri" id="st-run" style="margin-top:10px">Enviar selecionados para a Lixeira</button>` : '<p class="small">Nada para limpar nas categorias escolhidas.</p>'}
    ${p.protegidos.length ? `<details><summary>${p.protegidos.length} item(ns) protegido(s)</summary>${p.protegidos.map(x => `<p class="small">🔒 ${esc(x.motivo)}: <span class="mono">${esc(x.caminho)}</span></p>`).join('')}</details>` : ''}<div id="st-run-progress" hidden></div>`;
   const inc = $('#st-include'); if (inc) inc.onclick = () => plan([...card.querySelectorAll('[data-old]:checked')].map(i => i.dataset.old));
   const run = $('#st-run');
   if (run) run.onclick = async () => {
    const chosen = [...card.querySelectorAll('[data-item]:checked')].map(i => lastPlan.itens[Number(i.dataset.item)]);
    if (!chosen.length) { toast('Marque pelo menos um item.', true); return; }
    const total = chosen.reduce((a, i) => a + i.bytes, 0);
    if (!confirm(`Enviar ${chosen.length} item(ns) (${size(total)}) para a Lixeira?\n\nVocê pode recuperá-los pela Lixeira do sistema enquanto não esvaziá-la.`)) return;
    try { R.watch(await post('/api/armazenamento/limpar', {token: lastPlan.token, itens: chosen.map(i => i.caminho)}), $('#st-run-progress'), {onDone: r => report(r)}); }
    catch (e) { toast(e.message, true); }
   };
  }
  function report(r) {
   return `<p><b>${size(r.liberado_bytes)} liberados</b> · ${r.removidos.length} item(ns) na Lixeira${r.ignorados.length ? ' · ' + r.ignorados.length + ' mantido(s)' : ''}.</p>${r.removidos.slice(0, 40).map(i => `<p class="small mono" style="word-break:break-all">${i.destino === 'recuperacao' ? '↪ pasta de recuperação: ' + esc(i.recuperar_em) : '🗑 ' + esc(i.caminho)}</p>`).join('')}${r.ignorados.map(i => `<p class="small">Mantido: ${esc(i.motivo)} — <span class="mono">${esc(i.caminho)}</span></p>`).join('')}`;
  }

  // ---------------------------------------------------------------- limpeza automática
  const rules = storage.regras, auto = document.createElement('section'); auto.className = 'card';
  auto.innerHTML = `<h2>Limpeza automática</h2><p class="small mute">Começa desligada. Quando ligada, roda no máximo uma vez por dia, ao abrir o app, sem tarefas em andamento, só com as regras abaixo. Tudo vai para a Lixeira e um relatório fica em Armazenamento e limpeza.</p>
   <label><input type="checkbox" data-r="ativa" ${rules.ativa ? 'checked' : ''}> Ativar limpeza automática</label>
   <label><input type="checkbox" data-r="temporarios" ${rules.temporarios ? 'checked' : ''}> Temporários com mais de 1 dia</label>
   <label><input type="checkbox" data-r="caches" ${rules.caches ? 'checked' : ''}> Caches recriáveis</label>
   <label><input type="checkbox" data-r="projetos_antigos" ${rules.projetos_antigos ? 'checked' : ''}> Projetos sem uso há mais de <input type="number" data-r="dias" min="7" max="3650" value="${rules.dias}" style="width:80px;min-width:0"> dias (exceto favoritos, abertos recentemente, em processamento ou citados em XML de outro projeto)</label>
   <button class="btn pri" id="auto-save">Salvar regras</button><p role="status" class="small"></p>`;
  card.after(auto);
  $('#auto-save').onclick = async () => {
   const body = {}; auto.querySelectorAll('[data-r]').forEach(i => body[i.dataset.r] = i.type === 'checkbox' ? i.checked : Number(i.value));
   if (body.ativa && body.projetos_antigos && !confirm(`Com esta regra, projetos sem uso há mais de ${body.dias} dias irão para a Lixeira automaticamente. Continuar?`)) return;
   try { await post('/api/armazenamento/regras', body); auto.querySelector('[role=status]').textContent = body.ativa ? 'Regras salvas. A limpeza automática roda ao abrir o app.' : 'Regras salvas. Limpeza automática desligada.'; }
   catch (e) { auto.querySelector('[role=status]').textContent = e.message; }
  };

  // ---------------------------------------------------------------- tratamento padrão
  const treat = document.createElement('section'); treat.className = 'card';
  treat.innerHTML = `<h2>Tratamento de áudio padrão</h2><p class="small mute">Usado como sugestão ao tratar os áudios gerados e na ferramenta avulsa. O original nunca é alterado e o tratamento pode ser desfeito.</p>${window.RMTreatmentForm.html(cfg.tratamento_audio)}<button class="btn pri" id="treat-save">Salvar padrão</button><p role="status" class="small"></p>`;
  auto.after(treat);
  $('#treat-save').onclick = async () => { try { await post('/api/tratamento/padrao', window.RMTreatmentForm.read(treat)); treat.querySelector('[role=status]').textContent = 'Padrão salvo.'; } catch (e) { treat.querySelector('[role=status]').textContent = e.message; } };
 };
})();
