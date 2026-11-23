/* Referências do pote, marcação manual, revisão lado a lado, frestas, próxima pendência e resumo da entrega. */
(() => {
  const D = window.OldProductUX, $ = id => document.getElementById(id);
  if (!D || !$('op-references')) return;
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const clock = ms => D.clock(ms);
  const premiere = s => { const t = Math.max(0, s); return Math.floor(t / 60) + ':' + (t % 60).toFixed(2).padStart(5, '0'); };
  const call = async (action, body = {}) => {
    const r = await fetch('/fatiador/trocas/' + action, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({folder: D.scope || window.folder, ...body})});
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(d.erro || 'Não foi possível concluir.');
    return d;
  };
  const source = () => D.file('_fonte' + (D.state?.extensao || '.mp4'));
  const css = document.createElement('style');
  css.textContent = `
  .op-chips{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}
  .op-chip{font-size:12px;padding:2px 8px;border-radius:999px;border:1px solid var(--line);color:var(--mute);background:color-mix(in srgb,var(--line) 30%,transparent)}
  .ov-refs{display:flex;flex-wrap:wrap;gap:10px;margin:8px 0}
  .ov-ref{border:1px solid var(--line);border-radius:10px;padding:8px;display:flex;flex-direction:column;gap:6px;align-items:flex-start;max-width:180px}
  .ov-ref img{height:96px;max-width:160px;object-fit:contain;border-radius:6px;background:#0002}
  .ov-ref .links{display:flex;flex-direction:row;flex-wrap:wrap;gap:6px}
  .ov-ref .links button{padding:4px 10px;font-size:12px;min-height:0}
  .ov-ref.stale{border-color:var(--err)}
  .ov-player video{width:100%;max-height:360px;background:#000;border-radius:8px}
  .ov-dialog{border:1px solid var(--line);border-radius:14px;padding:0;max-width:min(1100px,96vw);width:96vw;background:var(--card,var(--panel,#fff));color:inherit}
  .ov-dialog::backdrop{background:#0008}
  .ov-dialog .ov-body{padding:16px;display:flex;flex-direction:column;gap:12px}
  .ov-pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  .ov-pair video{width:100%;max-height:52vh;background:#000;border-radius:8px}
  @media (max-width:760px){.ov-pair{grid-template-columns:1fr}}
  .ov-stage{position:relative;display:block;width:fit-content;max-width:100%;cursor:crosshair;user-select:none;touch-action:none}
  .ov-stage img{display:block;max-width:100%;max-height:62vh;width:auto;height:auto}
  .ov-rect{position:absolute;border:2px solid var(--acc);background:color-mix(in srgb,var(--acc) 18%,transparent);pointer-events:none}
  .ov-keys{font-size:12px;color:var(--mute)}
  .ov-banner{display:flex;flex-wrap:wrap;align-items:center;gap:12px;justify-content:space-between}
  .ov-gap{border:1px solid var(--line);border-radius:10px;padding:10px;margin:8px 0}
  .ov-numbers{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px}
  .ov-numbers div{border:1px solid var(--line);border-radius:10px;padding:8px}
  .ov-numbers b{display:block;font-size:20px}`;
  document.head.append(css);

  /* ------------------------------------------------------------ referências e player do original */
  const refs = $('op-references');
  refs.innerHTML = `<details id="ov-ref-box"><summary><b>Referências do pote antigo</b> <span class="meta" id="ov-ref-chip"></span></summary>
   <p class="meta">Pause o vídeo original num quadro em que o pote aparece, clique em <b>Usar este quadro como referência</b> e marque o pote. Adicione ângulos e tamanhos diferentes: longe, de lado, na mão. A busca compara os detalhes da região marcada, como o rótulo e as letras, para não confundir potes parecidos.</p>
   <div class="ov-refs" id="ov-ref-list"></div>
   <div class="links"><button id="ov-ref-search" disabled>Buscar com estas referências</button><button class="ghost" id="ov-open-player">Abrir o vídeo original</button></div>
   <p class="meta" id="ov-ref-status" role="status"></p>
   <div class="ov-player" id="ov-player" hidden><video id="ov-video" controls preload="metadata"></video>
    <div class="links"><button id="ov-use-frame">Usar este quadro como referência</button><button class="ghost" id="ov-mark-in">Marcar início</button><button class="ghost" id="ov-mark-out">Marcar fim</button><button class="ghost" id="ov-send-manual" disabled>Enviar aparição para os takes</button></div>
    <p class="meta" id="ov-manual-info">Aparição que ficou de fora: marque o início e o fim no player e envie. Ela entra aprovada e vai para a preparação dos takes.</p></div></details>`;
  const picker = document.createElement('dialog'); picker.className = 'ov-dialog'; picker.id = 'ov-picker';
  picker.innerHTML = `<div class="ov-body"><b id="ov-picker-title">Marque o pote antigo</b><p class="meta">Arraste um retângulo sobre o pote (inclua o rótulo). Depois confirme.</p><div class="ov-stage" id="ov-stage"><img id="ov-frame" alt="Quadro do vídeo original"><div class="ov-rect" id="ov-rect" hidden></div></div><div class="links"><button id="ov-confirm" disabled>Confirmar seleção</button><button class="ghost" id="ov-picker-cancel">Cancelar</button></div><p class="err" id="ov-picker-error" role="alert"></p></div>`;
  document.body.append(picker);
  let refState = {itens: [], validas: 0, limite: 12}, picking = null, rect = null, manual = {inicio: null, fim: null};
  function renderRefs() {
    const items = refState.itens || [];
    $('ov-ref-chip').textContent = items.length ? `· ${refState.validas} referência(s)` : '· opcional';
    $('ov-ref-list').innerHTML = items.length ? items.map(r => `<div class="ov-ref ${r.valida ? '' : 'stale'}" data-ref="${esc(r.id)}"><img src="${D.file(r.miniatura)}" alt="Referência em ${clock(r.t_ms)}"><span class="meta">${clock(r.t_ms)} no original${r.valida ? '' : '<br><b>' + esc(r.aviso) + '</b>'}</span><div class="links"><button class="ghost btn sm" data-ref-replace>Substituir</button><button class="ghost btn sm" data-ref-remove>Remover</button></div></div>`).join('')
      : '<p class="meta">Nenhuma referência ainda. A busca usa o nome lido nos rótulos; as referências ajudam quando o nome está pequeno, desfocado ou de lado.</p>';
    $('ov-ref-search').disabled = !refState.validas || D.busy;
  }
  async function loadRefs() { try { refState = await call('deteccao-referencias'); } catch (e) { refState = {itens: [], validas: 0}; } renderRefs(); }
  function openPlayer(t) {
    $('ov-ref-box').open = true; $('ov-player').hidden = false;
    const video = $('ov-video');
    if (!video.src) video.src = source();
    if (t != null) { const go = () => { video.currentTime = t / 1000; }; video.readyState ? go() : video.addEventListener('loadedmetadata', go, {once: true}); }
    $('ov-player').scrollIntoView({block: 'center', behavior: 'smooth'});
  }
  $('ov-open-player').onclick = () => openPlayer(null);
  async function pick(tMs, replace = null) {
    picking = {t: Math.round(tMs), replace}; rect = null;
    $('ov-rect').hidden = true; $('ov-confirm').disabled = true; $('ov-picker-error').textContent = '';
    $('ov-picker-title').textContent = (replace ? 'Substituir referência · ' : 'Nova referência · ') + clock(tMs) + ' no original';
    try {
      const frame = await call('deteccao-referencia-quadro', {t_ms: picking.t});
      picking.quadro = frame.arquivo; picking.t = frame.t_ms;
      $('ov-frame').src = D.file(frame.arquivo);
      picker.showModal();
    } catch (e) { $('ov-ref-status').textContent = e.message; }
  }
  $('ov-use-frame').onclick = () => { const v = $('ov-video'), replace = $('ov-use-frame').dataset.replace || null; delete $('ov-use-frame').dataset.replace; v.pause(); pick(v.currentTime * 1000, replace); };
  // Desenho do retângulo sobre o quadro (mouse, caneta ou toque).
  let drag = null;
  const stage = $('ov-stage');
  const point = e => { const b = $('ov-frame').getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - b.left) / b.width)), Math.min(1, Math.max(0, (e.clientY - b.top) / b.height))]; };
  function draw(a, b) {
    const x0 = Math.min(a[0], b[0]), y0 = Math.min(a[1], b[1]), x1 = Math.max(a[0], b[0]), y1 = Math.max(a[1], b[1]);
    rect = [(x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0];
    // Posição em pixels sobre a imagem exibida (o contêiner pode ser mais largo que o quadro reduzido).
    const img = $('ov-frame'), w = img.clientWidth, h = img.clientHeight;
    Object.assign($('ov-rect').style, {left: img.offsetLeft + x0 * w + 'px', top: img.offsetTop + y0 * h + 'px', width: (x1 - x0) * w + 'px', height: (y1 - y0) * h + 'px'});
    $('ov-rect').hidden = false; $('ov-confirm').disabled = rect[2] < .015 || rect[3] < .02;
  }
  stage.addEventListener('pointerdown', e => { e.preventDefault(); stage.setPointerCapture(e.pointerId); drag = point(e); draw(drag, drag); });
  stage.addEventListener('pointermove', e => { if (drag) draw(drag, point(e)); });
  stage.addEventListener('pointerup', e => { if (drag) { draw(drag, point(e)); drag = null; } });
  $('ov-picker-cancel').onclick = () => picker.close();
  $('ov-confirm').onclick = async () => {
    if (!rect || !picking) return;
    $('ov-confirm').disabled = true;
    try {
      refState = await call('deteccao-referencia-salvar', {t_ms: picking.t, caixa: rect, quadro: picking.quadro, substituir: picking.replace});
      picker.close(); renderRefs();
      $('ov-ref-status').textContent = 'Referência salva no projeto. Clique em Buscar com estas referências para procurar no vídeo.';
    } catch (e) { $('ov-picker-error').textContent = e.message; $('ov-confirm').disabled = false; }
  };
  $('ov-ref-list').addEventListener('click', async e => {
    const box = e.target.closest('[data-ref]'); if (!box) return;
    const ref = refState.itens.find(r => r.id === box.dataset.ref);
    if (e.target.matches('[data-ref-remove]')) {
      if (!confirm('Remover esta referência? A próxima busca deixa de usá-la; as aparições já aprovadas continuam como estão.')) return;
      try { refState = await call('deteccao-referencia-remover', {id: ref.id}); renderRefs(); $('ov-ref-status').textContent = 'Referência removida.'; }
      catch (error) { $('ov-ref-status').textContent = error.message; }
    } else if (e.target.matches('[data-ref-replace]')) {
      openPlayer(ref.t_ms);
      $('ov-ref-status').textContent = 'Pause no quadro desejado e clique em Usar este quadro como referência para substituir.';
      $('ov-use-frame').dataset.replace = ref.id;
    }
  });
  $('ov-ref-search').onclick = () => { $('ov-ref-status').textContent = 'Busca iniciada. O que já foi lido é reaproveitado.'; D.analyze(); };
  // Marcação manual de uma aparição que ficou de fora.
  function manualInfo() {
    const {inicio, fim} = manual;
    $('ov-send-manual').disabled = inicio == null || fim == null || fim - inicio < 100;
    $('ov-manual-info').textContent = inicio == null && fim == null ? 'Aparição que ficou de fora: marque o início e o fim no player e envie. Ela entra aprovada e vai para a preparação dos takes.'
      : `Início ${inicio == null ? '—' : clock(inicio)} · fim ${fim == null ? '—' : clock(fim)}${inicio != null && fim != null && fim <= inicio ? ' · o fim precisa vir depois do início' : ''}`;
  }
  $('ov-mark-in').onclick = () => { manual.inicio = Math.round($('ov-video').currentTime * 1000); manualInfo(); };
  $('ov-mark-out').onclick = () => { manual.fim = Math.round($('ov-video').currentTime * 1000); manualInfo(); };
  $('ov-send-manual').onclick = async () => {
    try {
      const result = await call('deteccao-manual', {inicio_ms: manual.inicio, fim_ms: manual.fim});
      const middle = Math.round((manual.inicio + manual.fim) / 2);
      D.state = result; D.render(); manual = {inicio: null, fim: null}; manualInfo();
      $('ov-ref-status').innerHTML = 'Aparição enviada para os takes. Prepare os takes para cobri-la. <button class="ghost btn sm" id="ov-manual-ref">Usar um quadro deste trecho como referência</button>';
      $('ov-manual-ref').onclick = () => pick(middle);
      refreshAll();
    } catch (e) { $('ov-manual-info').textContent = e.message; }
  };

  /* ------------------------------------------------------------ revisão lado a lado */
  const side = document.createElement('dialog'); side.className = 'ov-dialog'; side.id = 'ov-side';
  side.innerHTML = `<div class="ov-body"><div class="ov-banner"><b id="ov-side-title"></b><span class="ov-keys">← Anterior · → Próximo · A Aprovar · D Descartar · Espaço reproduz · Esc fecha</span></div>
   <div class="op-chips" id="ov-side-chips"></div><p class="meta" id="ov-side-meta"></p>
   <div class="ov-pair"><div><b>Trecho original</b><video id="ov-side-original" preload="metadata" controls playsinline></video></div><div><b>Take escolhido</b> <select id="ov-side-take" hidden></select><video id="ov-side-take-video" preload="metadata" controls playsinline muted></video><p class="meta" id="ov-side-take-info"></p></div></div>
   <div class="links"><button class="ghost" id="ov-side-prev">← Anterior</button><button id="ov-side-approve">Aprovar</button><button class="ghost" id="ov-side-discard">Descartar</button><button class="ghost" id="ov-side-play">Reproduzir juntos</button><button class="ghost" id="ov-side-swap">Trocar take</button><button class="ghost" id="ov-side-ref">Usar este quadro como referência</button><button class="ghost" id="ov-side-next">Próximo →</button><button class="ghost" id="ov-side-close">Fechar</button></div>
   <p class="err" id="ov-side-error" role="alert"></p></div>`;
  document.body.append(side);
  let order = [], position = 0, current = null, takes = null;
  async function showItem() {
    const id = order[position], items = D.state?.intervalos || [];
    current = items.find(i => i.id === id);
    $('ov-side-error').textContent = '';
    if (!current) { $('ov-side-title').textContent = 'Aparição não encontrada. Atualize a lista.'; return; }
    const n = items.indexOf(current) + 1;
    $('ov-side-title').textContent = `#${n} · ${clock(current.inicio_ms)} – ${clock(current.fim_ms)} · ${position + 1} de ${order.length}`;
    $('ov-side-chips').innerHTML = (current.motivos || []).map(m => `<span class="op-chip">${esc(m)}</span>`).join('') + `<span class="op-chip">${esc({sugerido: 'para revisar', aprovado: 'aprovada', descartado: 'descartada'}[current.status])}</span>`;
    $('ov-side-approve').disabled = current.status === 'aprovado'; $('ov-side-discard').disabled = current.status === 'descartado';
    const original = $('ov-side-original');
    const from = (current.cobertura_inicio_ms ?? current.inicio_ms) / 1000, to = (current.cobertura_fim_ms ?? current.fim_ms) / 1000;
    original.src = source() + `#t=${from.toFixed(2)},${to.toFixed(2)}`;
    takes = null; $('ov-side-take').hidden = true; $('ov-side-take-video').removeAttribute('src'); $('ov-side-take-info').textContent = 'Carregando os takes…';
    try { takes = await call('visual-aparicao-takes', {id}); } catch (e) { $('ov-side-take-info').textContent = e.message; return; }
    if (order[position] !== id) return;
    $('ov-side-meta').textContent = `Aparição ${clock(takes.inicio_ms)} – ${clock(takes.fim_ms)} · cobertura ${clock(takes.cobertura_inicio_ms)} – ${clock(takes.cobertura_fim_ms)} no original` + (takes.frestas.length ? ` · ${takes.frestas.length} fresta(s) sem take` : '');
    if (!takes.takes.length) { $('ov-side-take-info').textContent = takes.preparado ? 'Nenhum take cobre esta aparição. Aprove-a e prepare os takes, ou resolva a fresta em Conferir cobertura.' : 'Prepare os takes para comparar com o take escolhido.'; $('ov-side-swap').disabled = true; return; }
    const select = $('ov-side-take');
    select.innerHTML = takes.takes.map((t, i) => `<option value="${i}">${esc(t.nome || 'Take')} · ${premiere(t.cobre_de_s)}–${premiere(t.cobre_ate_s)}</option>`).join('');
    select.hidden = takes.takes.length < 2; select.value = '0'; loadTake(0);
  }
  function loadTake(i) {
    const t = takes.takes[i], video = $('ov-side-take-video');
    video.src = t.url; video.dataset.offset = String(Math.max(0, t.cobre_de_s - t.inicio_s));
    video.addEventListener('loadedmetadata', () => { video.currentTime = Number(video.dataset.offset || 0); }, {once: true});
    $('ov-side-take-info').textContent = `${t.nome || 'Take'}${t.kit ? ' · kit ' + t.kit : ''} · ${premiere(t.inicio_s)}–${premiere(t.fim_s)} no Premiere`;
    $('ov-side-swap').disabled = !window.VisualUX;
  }
  $('ov-side-take').onchange = e => loadTake(Number(e.target.value));
  function openSide(id) {
    order = [...document.querySelectorAll('#op-list [data-op]')].map(b => b.dataset.op);
    if (!order.includes(id)) order = (D.state?.intervalos || []).map(i => i.id);
    position = Math.max(0, order.indexOf(id));
    side.showModal(); showItem();
  }
  function move(step) { if (!order.length) return; position = Math.min(order.length - 1, Math.max(0, position + step)); showItem(); }
  async function decide(status) {
    if (!current || D.busy) return;
    try { D.state = await D.post('revisar', {itens: [{id: current.id, status}]}); D.render(); refreshAll(); }
    catch (e) { $('ov-side-error').textContent = e.message; return; }
    if (position < order.length - 1) move(1); else showItem();
  }
  function playBoth() {
    const a = $('ov-side-original'), b = $('ov-side-take-video');
    a.currentTime = (current.cobertura_inicio_ms ?? current.inicio_ms) / 1000; b.currentTime = Number(b.dataset.offset || 0);
    a.play().catch(() => {}); if (b.src) b.play().catch(() => {});
  }
  $('ov-side-prev').onclick = () => move(-1); $('ov-side-next').onclick = () => move(1);
  $('ov-side-approve').onclick = () => decide('aprovado'); $('ov-side-discard').onclick = () => decide('descartado');
  $('ov-side-play').onclick = playBoth;
  $('ov-side-ref').onclick = () => { const v = $('ov-side-original'); v.pause(); side.close(); pick(v.currentTime * 1000); };
  $('ov-side-swap').onclick = async () => {
    const t = takes?.takes[Number($('ov-side-take').value || 0)]; if (!t || !window.VisualUX) return;
    try { await window.VisualUX.replace(t.indice); $('ov-side-error').textContent = 'Take trocado. Prepare os takes de novo para atualizar a cobertura.'; showItem(); }
    catch (e) { $('ov-side-error').textContent = e.message; }
  };
  $('ov-side-close').onclick = () => side.close();
  side.addEventListener('close', () => {
    [$('ov-side-original'), $('ov-side-take-video')].forEach(v => { v.pause(); v.removeAttribute('src'); v.load(); });
    // Volta para a mesma aparição, com o filtro, a seleção e a posição da lista preservados.
    const card = current && document.querySelector(`#op-list [data-op="${CSS.escape(current.id)}"]`);
    if (card) { card.closest('details')?.setAttribute('open', ''); card.scrollIntoView({block: 'center'}); card.querySelector('[data-op-side]')?.focus({preventScroll: true}); }
  });
  side.addEventListener('keydown', e => {
    if (e.target.matches('input,select,textarea')) return;
    const key = e.key.toLowerCase();
    if (key === 'arrowleft') { e.preventDefault(); move(-1); }
    else if (key === 'arrowright') { e.preventDefault(); move(1); }
    else if (key === 'a') { e.preventDefault(); decide('aprovado'); }
    else if (key === 'd') { e.preventDefault(); decide('descartado'); }
    else if (key === ' ' && !e.target.matches('video,button')) { e.preventDefault(); playBoth(); }
  });
  document.addEventListener('visual:lado-a-lado', e => openSide(e.detail.id));

  /* ------------------------------------------------------------ frestas antes do XML */
  const gaps = document.createElement('section'); gaps.className = 'card'; gaps.id = 'ov-gaps'; gaps.hidden = true;
  gaps.innerHTML = `<h3>Conferir cobertura do produto antigo</h3><p class="meta">Compara as aparições aprovadas com os takes que realmente ficarão em V2, no tempo final da sequência (com as expansões de áudio e os fechamentos de margem).</p><div id="ov-gaps-list"></div><div id="ov-gaps-progress" hidden></div>`;
  const panel = $('old-product-panel'); panel.after(gaps);
  let gapState = null;
  function renderGaps() {
    const r = gapState; if (!r) { gaps.hidden = true; return; }
    const open = r.frestas || [], marked = r.marcadas || [];
    gaps.hidden = !r.preparado && !marked.length;
    if (gaps.hidden) return;
    const row = p => `<div class="ov-gap" data-gap="${esc(p.id)}"><b>${clock(p.inicio_ms)} – ${clock(p.fim_ms)} no original</b> · ${premiere(p.premiere_inicio_s)} – ${premiere(p.premiere_fim_s)} no Premiere · ${p.quadros} quadro(s) sem take
      <div class="links"><button class="ghost btn sm" data-gap-adjust ${p.aparicoes?.length ? '' : 'disabled'}>Ajustar take</button><button class="ghost btn sm" data-gap-reprepare>Repreparar este intervalo</button><button class="ghost btn sm" data-gap-mark>Marcar para revisão no Premiere</button></div></div>`;
    $('ov-gaps-list').innerHTML = (open.length ? `<p><b style="color:var(--err)">${open.length} fresta(s) mostram o produto antigo sem take.</b> O XML final só é gerado depois de resolver ou marcar cada uma.</p>` + open.map(row).join('')
      : r.preparado ? (marked.length ? `<p class="rm-ok">✓ Nenhuma fresta aberta.</p><p class="meta">${marked.length} trecho(s) ficam sem take e serão resolvidos no Premiere.</p>` : '<p class="rm-ok">✓ Todas as aparições aprovadas estão cobertas pelos takes em V2.</p>') : '')
      + (marked.length ? `<details><summary>${marked.length} marcada(s) para revisão no Premiere</summary>${marked.map(m => `<p class="meta" data-gap="${esc(m.id)}">${clock(m.start)} – ${clock(m.end)} no original · ${premiere(m.premiere_inicio_s)} no Premiere · marcador PENDÊNCIA VISUAL no XML <button class="ghost btn sm" data-gap-unmark>Desfazer marcação</button></p>`).join('')}</details>` : '');
  }
  async function loadGaps() { try { gapState = await call('visual-frestas'); } catch (e) { gapState = null; } renderGaps(); }
  gaps.addEventListener('click', async e => {
    const box = e.target.closest('[data-gap]'); if (!box) return;
    const id = box.dataset.gap, piece = (gapState?.frestas || []).find(p => p.id === id);
    try {
      if (e.target.matches('[data-gap-adjust]') && piece) openSide(piece.aparicoes[0]);
      else if (e.target.matches('[data-gap-mark]')) {
        if (!confirm('Este trecho ficará sem take e com o marcador “PENDÊNCIA VISUAL · produto antigo” no XML. As falas aprovadas e os outros takes continuam como estão. Continuar?')) return;
        gapState = await call('visual-frestas-marcar', {ids: [id], autorizado: true}); renderGaps(); refreshAll();
      } else if (e.target.matches('[data-gap-unmark]')) { gapState = await call('visual-frestas-desmarcar', {ids: [id]}); renderGaps(); refreshAll(); }
      else if (e.target.matches('[data-gap-reprepare]')) {
        const job = await call('visual-frestas-repreparar', {ids: [id]});
        const box2 = $('ov-gaps-progress');
        if (window.RMJob) window.RMJob.watch(job, box2, {onDone: r => { window.VisualUX?.refresh?.(); loadGaps(); refreshAll(); return `<p>${r.frestas_restantes ? r.frestas_restantes + ' fresta(s) ainda abertas.' : 'Intervalo refeito sem frestas.'} Os demais takes foram reaproveitados.</p>`; }});
      }
    } catch (error) { $('ov-gaps-list').insertAdjacentHTML('afterbegin', `<p class="err" role="alert">${esc(error.message)}</p>`); }
  });

  /* ------------------------------------------------------------ próxima pendência ao reabrir */
  const banner = document.createElement('section'); banner.className = 'card ov-banner'; banner.id = 'ov-next'; banner.hidden = true;
  banner.innerHTML = '<div><b id="ov-next-title">Continuar de onde parou</b><p class="meta" id="ov-next-detail"></p></div><button id="ov-next-action"></button>';
  (document.querySelector('.wizard-nav') || panel).after(banner);
  let summary = null;
  function renderBanner() {
    const next = summary?.proxima;
    banner.hidden = !next || next.acao === 'concluido';
    if (banner.hidden) return;
    const a = summary.aparicoes, c = summary.cobertura;
    $('ov-next-action').textContent = next.rotulo;
    $('ov-next-detail').textContent = [a.aprovadas ? `${a.aprovadas} aparição(ões) aprovada(s)` : '', c.preparado ? `${c.cobertas} de ${c.a_cobrir} coberta(s)` : 'takes a preparar', c.marcadas ? `${c.marcadas} marcada(s) para o Premiere` : '', 'áudios, busca e takes atuais são reaproveitados'].filter(Boolean).join(' · ');
  }
  $('ov-next-action').onclick = async () => {
    const next = summary?.proxima; if (!next) return;
    document.querySelector(`[data-flow-step="${next.etapa}"]`)?.click();
    await new Promise(r => setTimeout(r, 120));
    if (next.acao === 'revisar_aparicoes') { D.filter('revisar'); D.open(); const first = document.querySelector('#op-list [data-op]'); if (first) openSide(first.dataset.op); }
    else if (next.acao === 'frestas') { gaps.scrollIntoView({block: 'start', behavior: 'smooth'}); }
    else if (next.acao === 'preparar_takes') { $('flow-auto-takes')?.scrollIntoView({block: 'center', behavior: 'smooth'}); $('flow-auto-takes')?.focus(); }
    else if (next.acao === 'aguardar') { D.open(); }
  };

  /* ------------------------------------------------------------ resumo de conferência na entrega */
  const report = document.createElement('section'); report.className = 'card'; report.id = 'ov-delivery'; report.hidden = true;
  report.innerHTML = '<h3>Conferência do produto antigo na imagem</h3><div class="ov-numbers" id="ov-delivery-numbers"></div><p class="meta" id="ov-delivery-note"></p>';
  // Logo abaixo da Conferência da entrega, visível também depois do XML salvo.
  const placeReport = () => {
    const anchor = $('editorial-check')?.closest('section');
    if (anchor) { if (report.previousElementSibling !== anchor) anchor.after(report); return; }
    const target = $('final-checklist'); if (target && report.nextElementSibling !== target) target.before(report);
  };
  function renderReport() {
    placeReport();
    if (!summary || !summary.aparicoes.total) { report.hidden = true; return; }
    report.hidden = false;
    const a = summary.aparicoes, c = summary.cobertura;
    $('ov-delivery-numbers').innerHTML = [[a.aprovadas, 'aparições aprovadas'], [c.preparado ? c.cobertas : '—', 'cobertas por takes em V2'], [c.marcadas, 'marcadas para revisão no Premiere'], [c.frestas, 'frestas abertas'], [a.para_revisar, 'ainda para revisar']]
      .map(([n, t]) => `<div><b>${n}</b><span class="meta">${t}</span></div>`).join('');
    $('ov-delivery-note').textContent = (a.so_marcacao ? `${a.so_marcacao} aprovada(s) antes da 1ª menção ficam só marcadas, conforme a escolha do projeto. ` : '') + (c.frestas ? 'Resolva ou marque as frestas em Takes antes de salvar o XML final.' : c.marcadas ? 'Os trechos marcados recebem o marcador PENDÊNCIA VISUAL · produto antigo no XML e aparecem no relatório.' : '');
  }

  /* ------------------------------------------------------------ atualização */
  let pending = null;
  async function refreshAll() {
    clearTimeout(pending);
    pending = setTimeout(async () => {
      if (!D.scope) return;
      try { summary = await call('visual-conferencia'); } catch (e) { summary = null; }
      renderBanner(); renderReport(); loadGaps();
    }, 250);
  }
  let lastSignature = '';
  document.addEventListener('visual:render', () => { const s = window.VisualUX?.state, sig = JSON.stringify([s?.prepared?.signature, s?.issues?.length, s?.pendencias_visuais?.length]); if (sig !== lastSignature) { lastSignature = sig; refreshAll(); } });
  document.addEventListener('visual:busca-concluida', () => { loadRefs(); refreshAll(); });
  document.addEventListener('visual:busca-ocupada', e => { $('ov-ref-search').disabled = !refState.validas || e.detail.busy; });
  document.querySelectorAll('[data-flow-step]').forEach(b => b.addEventListener('click', () => setTimeout(refreshAll, 200)));
  let lastScope = '';
  document.addEventListener('visual:conferencia-atualizada', () => { if (D.scope !== lastScope) { lastScope = D.scope; refState = {itens: [], validas: 0}; manual = {inicio: null, fim: null}; $('ov-video').removeAttribute('src'); $('ov-player').hidden = true; loadRefs(); } refreshAll(); });
  window.VisualReview = {openSide, pick, refresh: refreshAll, get summary() { return summary; }};
})();
