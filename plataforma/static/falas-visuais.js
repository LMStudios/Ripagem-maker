/* A evidência visual complementa Falas. Autorizar textos não gera nem aprova vozes. */
(() => {
  const U = window.SwapUX, $ = id => document.getElementById(id), host = $('old-product-panel');
  if (!U || !host) return;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const panel = document.createElement('details');
  panel.className = 'card recovery-falas';
  panel.innerHTML = '<summary><b>Conferência completa das menções</b><span data-recovery-count></span></summary><p class="meta">Confere toda a transcrição e complementa com os achados na imagem. Inclui falas que já existem, mas ficaram fora da seleção. Uma aparição no rótulo não confirma uma menção falada. A conferência local não usa créditos de API.</p><button class="ghost" data-recovery-refresh>Atualizar sugestões</button><p role="status" data-recovery-status></p><div class="links" data-recovery-pages hidden><button class="ghost" data-recovery-prev>← Anterior</button><span class="meta" data-recovery-page></span><button class="ghost" data-recovery-next>Próxima →</button></div><div data-recovery-list></div>';
  const anchor = document.createElement('span'); host.before(anchor, panel);
  const early = document.createElement('div'); early.className = 'ux-toast'; early.hidden = true;
  early.innerHTML = '<p data-recovery-early></p><p data-recovery-coverage class="meta"></p><p class="meta">Autorizar em lote inclui e aprova os textos das menções prováveis. Não gera vozes, não aprova áudios e não muda de etapa. Dúvidas de áudio, speaker, modo de uso ou sobreposição continuam pendentes.</p><div class="links"><button data-recovery-bulk></button><button class="ghost" data-recovery-open>Conferir todas as menções</button></div><p role="status" data-recovery-result></p>';
  $('swap-controls').before(early);
  const status = panel.querySelector('[data-recovery-status]'), list = panel.querySelector('[data-recovery-list]');
  const bulk = early.querySelector('[data-recovery-bulk]'), report = early.querySelector('[data-recovery-result]');
  let scope = '', state = null, pending = false, editing = false, workJob = null, page = 0, visualDirty = false;
  const rows = () => (state?.itens || []).filter(r => r.status === 'pendente');
  const eligible = () => rows().filter(r => r.situacao === 'mencao_provavel' && !r.conflito && !r.forma_pendente && r.speaker !== 'A_CONFIRMAR' && (U.plan?.speakers || []).includes(r.speaker));
  const time = ms => Math.floor(ms / 60000) + ':' + String(Math.floor(ms / 1000) % 60).padStart(2, '0');
  async function post(action, body = {}, work = scope) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 20000);
    try {
      const r = await fetch('/fatiador/trocas/fala-visual-' + action, {method:'POST', headers:{'Content-Type':'application/json'}, signal:controller.signal, body:JSON.stringify({folder:work, ...body})});
      const d = await r.json(); if (!r.ok) throw Error(d.erro || 'Não foi possível conferir.'); return d;
    } catch (e) { if (e.name === 'AbortError') throw Error('A resposta demorou. Atualize as sugestões para conferir o que foi salvo antes de repetir.'); throw e; }
    finally { clearTimeout(timer); }
  }
  function releaseMedia() {
    list.querySelectorAll('video').forEach(v => {v.pause(); v.removeAttribute('src'); v.load(); v.remove();});
  }
  function controls() {
    const count = eligible().length;
    bulk.textContent = `Autorizar todas as menções prováveis (${count})`;
    early.querySelectorAll('button').forEach(b => b.disabled = pending || !!workJob);
    bulk.disabled = pending || !!workJob || !count;
    panel.querySelectorAll('button').forEach(b => b.disabled = pending || !!workJob || b.hasAttribute('data-r-conflict'));
    panel.querySelector('[data-recovery-prev]').disabled ||= page === 0;
    panel.querySelector('[data-recovery-next]').disabled ||= page >= rows().length - 1;
  }
  function render() {
    const coverage = state?.cobertura_mencoes;
    document.dispatchEvent(new CustomEvent('mentions:coverage', {detail:{folder:scope, coverage}}));
    early.querySelector('[data-recovery-coverage]').textContent = coverage && !coverage.ignorado ? `${coverage.itens.length} menção(ões) na transcrição · ${coverage.itens.filter(r => r.status === 'coberta').length} com substituição pronta · ${coverage.pendencias.length} pendente(s). Tempos referentes ao vídeo original; o XML pode ter deslocamentos.` : '';
    const items = rows(); page = Math.max(0, Math.min(page, items.length - 1));
    early.hidden = (!items.length && !report.textContent) || !!state?.somente_valores;
    early.querySelector('[data-recovery-early]').textContent = `${items.length} sugestão(ões) para revisar · ${eligible().length} menção(ões) provável(is) para autorizar em lote.` + ((state?.cobertura_mencoes?.pendencias || []).some(r => r.status === 'fora_da_selecao') ? ' Há falas já identificadas que ficaram fora da seleção da entrega.' : '');
    panel.hidden = !!state?.somente_valores;
    panel.querySelector('[data-recovery-count]').textContent = items.length ? ` · ${items.length} para revisar` : '';
    panel.querySelector('[data-recovery-pages]').hidden = !panel.open || items.length <= 1;
    panel.querySelector('[data-recovery-page]').textContent = items.length ? `${page + 1} de ${items.length}` : '';
    controls();
    if (!panel.open) return;
    releaseMedia();
    const r = items[page];
    if (!r) {list.innerHTML = '<p class="meta">' + esc(state?.aviso || 'Nenhuma nova fala para revisar na conferência visual atual.') + '</p>'; return;}
    list.innerHTML = `<section class="card" data-recovery="${esc(r.id)}"><h3>${time(r.inicio_ms)} – ${time(r.fim_ms)} · ${r.situacao === 'conferir_audio' ? 'Conferir áudio' : 'Menção provável'}</h3><p>${esc(r.motivo)}</p>${r.substitui_id && !r.existing_id ? '<p class="ux-toast">Esta sugestão amplia uma fala existente. Seu áudio precisará ser gerado ou importado novamente; as outras gravações serão preservadas.</p>' : ''}${r.conflito ? '<p role="alert">Há intervalos conflitantes. Ajuste as falas existentes antes de incluir.</p>' : ''}<div data-recovery-player><button class="ghost" data-r-play>Ouvir trecho original</button></div><p class="meta">Tempos do vídeo original. O vídeo só é carregado quando você pede para ouvir.</p><div class="row"><label>Início (segundos)<input data-r-start type="number" min="0" step="0.001" value="${r.inicio_ms / 1000}"></label><label>Fim (segundos)<input data-r-end type="number" min="0" step="0.001" value="${r.fim_ms / 1000}"></label></div><label>Fala original completa<textarea data-r-original>${esc(r.original)}</textarea></label><label>Texto adaptado · revise modo de uso, preços e kits<textarea data-r-new>${esc(r.novo)}</textarea></label><label>Speaker<select data-r-speaker><option value="A_CONFIRMAR">Confirme o speaker</option>${(U.plan?.speakers || []).filter(s => s !== 'A_CONFIRMAR').map(s => `<option value="${esc(s)}" ${s === r.speaker ? 'selected' : ''}>Speaker ${esc(s)}</option>`).join('')}</select></label>${(r.avisos || []).map(s => '<p class="meta">' + esc(s) + '</p>').join('')}<label class="row"><input type="checkbox" data-r-confirm> Ouvi o trecho e confirmei o texto, o speaker e a necessidade de adaptação.</label><div class="links"><button data-r-action="adicionar" ${r.conflito ? 'disabled data-r-conflict' : ''}>${r.existing_id ? 'Selecionar fala existente' : r.substitui_id ? 'Atualizar fala existente' : 'Adicionar às falas para revisão'}</button><button class="ghost" data-r-audio>Conferir este áudio localmente</button><button class="ghost" data-r-action="somente_visual">Não há menção falada · somente visual</button><button class="ghost" data-r-action="descartar">Descartar sugestão</button></div></section>`;
    controls();
  }
  async function refresh(force = false) {
    if (!folder || pending || editing && !force) return;
    const work = folder; scope = work; pending = true; controls();
    try {
      const d = await post('estado', {}, work); if (folder !== work) return;
      state = d; editing = false; render();
      if (d.tarefa && !workJob) {workJob = d.tarefa; poll(d.tarefa, work);}
    } catch (e) {status.textContent = e.message; report.textContent = e.message; early.hidden = false;}
    finally {pending = false; controls();}
  }
  async function ready() {
    if (U.busy) throw Error('Aguarde a tarefa atual terminar.');
    if (await U.flushDraft() === false || U.hasDraft()) throw Error('Salve as alterações de Falas antes de revisar.');
  }
  bulk.onclick = async () => {
    if (pending || workJob || !state) return;
    if (editing) {report.textContent = 'Há uma edição individual em andamento. Adicione essa fala ou atualize as sugestões antes de autorizar o lote.'; return;}
    const work = scope; pending = true; releaseMedia(); controls();
    report.textContent = 'Autorizando os textos em lote…';
    try {
      await ready(); const d = await post('autorizar-todas', {base:state.base, autoriza_lote:true}, work);
      if (folder !== work) return;
      state = d.estado; U.acceptPlan(d.plano); visualDirty = true; page = 0;
      report.textContent = `${d.autorizadas} texto(s) incluído(s) e autorizado(s). Nenhum áudio foi gerado.` + (d.pendencias.length ? ` ${d.pendencias.length} trecho(s) continuam para revisão individual.` : ' Os textos estão autorizados. Gere ou importe os áudios pendentes e confira antes de entregar.');
      status.textContent = ''; render();
    } catch (e) {report.textContent = e.message;}
    finally {pending = false; controls();}
  };
  async function openReview(mention) {
    const work = folder;
    early.after(panel);
    await refresh();
    if (folder !== work) return;
    panel.hidden = false;
    panel.open = true;
    if (!editing) {
      if (mention) {
        const index = rows().findIndex(row => row.inicio_ms <= mention.inicio_ms && row.fim_ms >= mention.fim_ms);
        if (index >= 0) page = index;
      }
      render();
    }
    panel.scrollIntoView({block:'start'});
  }
  early.querySelector('[data-recovery-open]').onclick = () => openReview();
  document.addEventListener('mentions:open-review', event => openReview(event.detail));
  panel.addEventListener('toggle', () => {if (!panel.open) releaseMedia(); else if (!list.childElementCount) render();});
  for (const [selector, delta] of [['[data-recovery-prev]', -1], ['[data-recovery-next]', 1]]) panel.querySelector(selector).onclick = () => {
    if (editing && !window.confirm('Há alterações neste trecho que ainda não foram adicionadas às falas. Trocar de trecho e descartar essas alterações?')) return;
    editing = false; page += delta; render(); panel.scrollIntoView({block:'start'});
  };
  panel.querySelector('[data-recovery-refresh]').onclick = () => {if (!editing || window.confirm('Atualizar as sugestões e descartar a edição individual ainda não salva?')) refresh(true);};
  panel.addEventListener('input', e => {if (!e.target.matches('[data-r-confirm]')) editing = true;});
  list.addEventListener('click', async e => {
    const button = e.target.closest('button'), card = e.target.closest('[data-recovery]');
    if (!button || !card || pending || workJob) return;
    const work = scope, rid = card.dataset.recovery;
    if (button.hasAttribute('data-r-play')) {
      releaseMedia(); const r = rows().find(x => x.id === rid); if (!r) return;
      const v = document.createElement('video'); v.controls = true; v.preload = 'none'; v.style.cssText = 'width:100%;max-height:240px';
      v.src = `/files/${encodeURIComponent(work)}/${encodeURIComponent(state.fonte)}#t=${Math.max(0, r.inicio_ms / 1000 - 1)},${r.fim_ms / 1000 + 1}`;
      button.parentElement.append(v); v.play().catch(() => {status.textContent = 'Use o controle de reprodução para ouvir o trecho.';}); return;
    }
    pending = true; releaseMedia(); controls(); status.textContent = 'Salvando a revisão…';
    try {
      await ready();
      if (button.hasAttribute('data-r-audio')) {const j = await post('audio', {id:rid, base:state.base}, work); workJob = j.id; editing = false; poll(j.id, work); return;}
      const d = await post('revisar', {id:rid, base:state.base, acao:button.dataset.rAction, confirmou_audio:card.querySelector('[data-r-confirm]').checked, original:card.querySelector('[data-r-original]').value, novo:card.querySelector('[data-r-new]').value, speaker:card.querySelector('[data-r-speaker]').value, inicio_ms:Math.round(Number(card.querySelector('[data-r-start]').value) * 1000), fim_ms:Math.round(Number(card.querySelector('[data-r-end]').value) * 1000)}, work);
      if (folder !== work) return;
      editing = false; state = d.estado;
      if (d.plano) {U.acceptPlan(d.plano); visualDirty = true; status.textContent = 'Fala salva para revisão em Falas. Nenhum áudio foi gerado. Selecione o texto quando estiver pronto.';}
      else status.textContent = 'Sugestão classificada. A conferência visual dos takes foi preservada.';
      render();
    } catch (err) {status.textContent = err.message;}
    finally {pending = false; controls();}
  });
  async function poll(id, work) {
    if (folder !== work || workJob !== id) {workJob = null; return;}
    try {
      const response = await fetch('/api/ml/job/' + id); const j = await response.json();
      if (!response.ok) {workJob = null; status.textContent = j.erro || 'Tarefa não disponível. Atualize as sugestões.'; controls(); return;}
      status.textContent = j.step || 'Conferindo áudio…';
      if (['na_fila','executando'].includes(j.status)) {setTimeout(() => poll(id, work), 1500); return;}
      workJob = null; await refresh(true); status.textContent = j.error || 'Áudio conferido. Revise os resultados antes de incluir.';
    } catch (e) {status.textContent = 'Consulta interrompida. Tentando novamente…'; setTimeout(() => poll(id, work), 3000);}
  }
  document.addEventListener('swap:step', () => {
    releaseMedia();
    if (document.querySelector('.wizard-nav [aria-current="step"]')?.dataset.flowStep === '4') {
      anchor.after(panel); if (visualDirty) {visualDirty = false; window.VisualUX?.refresh();}
    }
  });
  document.addEventListener('visual:conferencia-atualizada', () => refresh());
  window.addEventListener('pagehide', releaseMedia);
  const prev = window.loadSwapPlan;
  window.loadSwapPlan = async (...args) => {
    await prev(...args);
    if (scope !== folder) {releaseMedia(); list.innerHTML = ''; editing = false; state = null; page = 0; scope = folder; workJob = null; report.textContent = '';}
    await refresh();
  };
})();
