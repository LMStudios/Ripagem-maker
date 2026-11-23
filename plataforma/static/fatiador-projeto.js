/* Troca de potes: local do projeto (abrir, copiar, mover), tratamento dos áudios gerados e links diretos das ferramentas avulsas. */
(() => {
 const R = window.RMJob, U = window.SwapUX;
 if (!R) return;
 const esc = R.esc, $ = id => document.getElementById(id);
 const current = () => { try { return folder || ''; } catch (e) { return ''; } };
 const fileUrl = rel => '/files/' + [current(), ...String(rel).split('/')].map(encodeURIComponent).join('/');
 const make = (tag, cls, html) => { const n = document.createElement(tag); n.className = cls; n.innerHTML = html; return n; };

 /* ---------------------------------------------------------------- cartão do projeto */
 const bar = make('section', 'card', '<div class="row" style="justify-content:space-between;align-items:center;gap:8px"><b>Projeto</b><span class="meta" id="proj-name"></span></div><div id="proj-path"></div><div class="row" style="gap:8px"><button class="ghost" id="proj-move">Mover projeto…</button><span class="meta">Os próximos projetos continuam indo para a pasta definida em Ajustes; esta opção leva só este projeto com os materiais.</span></div><div id="proj-move-progress" hidden></div>');
 bar.id = 'project-location'; bar.hidden = true;
 const anchor = document.querySelector('.wizard-nav') || document.querySelector('#guided-fatiador');
 anchor?.after(bar);
 async function refreshLocation() {
  const f = current(); if (!f) { bar.hidden = true; return; }
  try {
   const d = await R.call('/api/projetos/local', {pasta: f});
   bar.hidden = false; $('proj-name').textContent = d.pasta;
   $('proj-path').innerHTML = R.pathActions(d.caminho);
   $('proj-move').disabled = d.em_uso; $('proj-move').title = d.em_uso ? 'Há uma tarefa usando o projeto: mova quando ela terminar.' : '';
  } catch (e) { bar.hidden = true; }
 }
 $('proj-move').onclick = async () => {
  const f = current(), box = $('proj-move-progress');
  const bridge = window.ripagemDesktop || window.pywebview?.api;
  let dest = '';
  try { if (bridge?.choose_folder) { const d = await bridge.choose_folder(); if (!d.ok) throw Error(d.erro); dest = d.cancelado ? '' : d.pasta; } else dest = (prompt('Cole o caminho completo da pasta de destino:') || '').trim(); }
  catch (e) { box.hidden = false; box.innerHTML = `<p class="err">${esc(e.message)}</p>`; return; }
  if (!dest) return;
  try {
   if (U?.flushDraft && await U.flushDraft() === false) throw Error('Salve as alterações antes de mover.');
   const c = await R.call('/api/projetos/verificar-destino', {pasta: f, destino: dest});
   const gb = b => (b / 1024 ** 3).toFixed(2) + ' GB';
   if (!confirm(`Mover este projeto com todos os materiais?\n\nDe: ${c.origem}\nPara: ${c.destino}\n${gb(c.bytes)} · ${gb(c.livre_bytes)} livres no destino\n\nO app copia, confere e só então manda a pasta antiga para a Lixeira.${c.xmls_a_refazer.length ? `\n\n${c.xmls_a_refazer.length} XML(s) já exportado(s) precisarão ser gerados novamente.` : ''}`)) return;
   const job = await R.call('/api/projetos/mover', {pasta: f, destino: dest});
   R.watch(job, box, {onDone: r => { setTimeout(refreshLocation, 300); return `<p>${esc(r.observacao)}</p>`; }});
  } catch (e) { box.hidden = false; box.innerHTML = `<p class="err" role="alert">${esc(e.message)}</p>`; }
 };

 /* ---------------------------------------------------------------- tratamento dos áudios gerados */
 const panel = make('details', 'card', '<summary><b>Tratamento dos áudios gerados</b> <span class="meta">silêncio nas bordas e ruído · opcional</span></summary><p class="meta">Remove o silêncio que sobra no início e no fim e reduz o ruído de fundo. Pausas internas ficam. O áudio original é mantido e você pode desfazer. Depois de tratar, ouça e aprove de novo: a duração muda e a montagem, os takes e o XML passam a usar os novos tempos.</p><div id="treat-form"></div><div class="row" style="gap:8px;margin:8px 0"><button class="ghost" id="treat-all">Marcar todos</button><button id="treat-run">Tratar selecionados</button></div><div id="treat-progress" hidden></div><div id="treat-list"></div>');
 panel.id = 'treat-panel';
 const slot = document.querySelector('[data-w-panel="3"]');
 slot?.append(panel);
 let defaults = null;
 async function renderTreat() {
  const plan = U?.plan; if (!plan || !slot) return;
  if (!defaults) { try { defaults = await R.call('/api/tratamento/padrao'); } catch (e) { defaults = {silencio: true, margem_inicio_ms: 80, margem_fim_ms: 200, ruido: false, intensidade: 35}; } $('treat-form').innerHTML = R.treatForm(defaults); }
  const rows = plan.itens.map((r, i) => [r, i + 1]).filter(([r]) => r.audio?.raw);
  if (!rows.length) { $('treat-list').innerHTML = '<p class="meta">Gere as falas primeiro: o tratamento trabalha sobre os áudios gerados ou importados.</p>'; $('treat-run').disabled = true; return; }
  $('treat-run').disabled = false;
  $('treat-list').innerHTML = rows.map(([r, n]) => {
   const t = r.audio.tratamento;
   return `<div class="card" style="padding:10px;margin:6px 0"><label><input type="checkbox" data-treat="${esc(r.id)}"> <b>${n}.</b> Speaker ${esc(r.speaker)} · ${esc((r.novo || '').slice(0, 90))}</label>
    <p class="meta">${t ? `Tratado: ${t.duracao_antes_s.toFixed(2)} s → ${t.duracao_depois_s.toFixed(2)} s (início −${t.removido_inicio_ms} ms, fim −${t.removido_fim_ms} ms${t.ruido_reduzido ? ', ruído reduzido' : ''})` : `Sem tratamento · ${Number(r.audio.duracao_s || 0).toFixed(2)} s`}${r.audio.aprovado ? ' · aprovado' : ' · <b>ouça e aprove</b>'}</p>
    ${t ? `<div class="row" style="gap:10px"><label>Original<span data-audio-placeholder="${fileUrl(t.origem)}"></span></label><label>Tratado<span data-audio-placeholder="${fileUrl(t.arquivo)}"></span></label><button class="ghost" data-undo="${esc(r.id)}">Desfazer tratamento</button></div>` : ''}</div>`;
  }).join('');
  panel.querySelectorAll('[data-undo]').forEach(b => b.onclick = async () => {
   try { const job = await R.call('/api/tratamento/desfazer', {pasta: current(), id: b.dataset.undo}); R.watch(job, $('treat-progress'), {onDone: r => { reload(); return `<p>${esc(r.observacao)}</p>`; }}); }
   catch (e) { $('treat-progress').hidden = false; $('treat-progress').innerHTML = `<p class="err">${esc(e.message)}</p>`; }
  });
 }
 async function reload() { try { await window.loadSwapPlan?.(); } catch (e) {} renderTreat(); }
 $('treat-all').onclick = () => { const boxes = [...panel.querySelectorAll('[data-treat]')]; const on = boxes.some(b => !b.checked); boxes.forEach(b => b.checked = on); };
 $('treat-run').onclick = async () => {
  const ids = [...panel.querySelectorAll('[data-treat]:checked')].map(b => b.dataset.treat);
  if (!ids.length) { $('treat-progress').hidden = false; $('treat-progress').innerHTML = '<p class="err">Marque pelo menos uma fala.</p>'; return; }
  try {
   if (U?.flushDraft && await U.flushDraft() === false) throw Error('Salve as alterações antes de tratar.');
   const job = await R.call('/api/tratamento/projeto', {pasta: current(), ids, opcoes: R.readTreat(panel)});
   R.watch(job, $('treat-progress'), {onDone: r => { reload(); return `<p>${r.tratados.length} áudio(s) tratado(s)${r.ignorados.length ? ` · ${r.ignorados.length} sem mudança (${[...new Set(r.ignorados.map(i => i.motivo))].map(esc).join(' ')})` : ''}.</p><p class="meta">${esc(r.observacao)}</p>`; }});
  } catch (e) { $('treat-progress').hidden = false; $('treat-progress').innerHTML = `<p class="err" role="alert">${esc(e.message)}</p>`; }
 };
 document.addEventListener('swap:step', () => { refreshLocation(); if (panel.open) renderTreat(); });
 panel.addEventListener('toggle', () => panel.open && renderTreat());

 /* Projeto aberto ou criado: atualiza o cartão de local. */
 const originalShow = window.show;
 if (typeof originalShow === 'function') window.show = function (...args) { const r = originalShow.apply(this, args); setTimeout(refreshLocation, 50); return r; };

 /* ---------------------------------------------------------------- links diretos (?trabalho=…&etapa=…&ferramenta=…) */
 const params = new URLSearchParams(location.search);
 const work = params.get('trabalho'), step = Number(params.get('etapa') || 0), tool = params.get('ferramenta') || '';
 const wait = async (test, ms = 20000) => { const end = Date.now() + ms; while (Date.now() < end) { const v = test(); if (v) return v; await new Promise(r => setTimeout(r, 250)); } return null; };
 async function deepLink() {
  if (!work) { if (tool === 'transcricao') document.querySelector('[data-flow-step="1"]')?.click(); return; }
  const select = $('saved-work'); if (!select) return;
  await wait(() => select.options.length > 1, 4000);
  if (![...select.options].some(o => o.value === work)) { const o = document.createElement('option'); o.value = o.textContent = work; select.append(o); }
  select.value = work; $('reopen')?.click();
  if (!await wait(() => current() === work)) return;
  if (step) {
   const button = await wait(() => { const b = document.querySelector(`[data-flow-step="${step}"]`); return b && !b.disabled && (step < 3 || U?.plan) ? b : null; });
   button?.click();
  }
  if (tool === 'tratamento') { await wait(() => U?.plan, 8000); panel.open = true; renderTreat(); panel.scrollIntoView({block: 'start'}); }
 }
 if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', deepLink); else deepLink();
})();
