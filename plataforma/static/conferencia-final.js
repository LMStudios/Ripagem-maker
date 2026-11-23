/* Conferência final do vídeo exportado e relatório de entrega para o cliente (Entrega). */
(() => {
  const R = window.RMJob, $ = id => document.getElementById(id), slot = $('wizard-slot-4');
  if (!R || !slot) return;
  const esc = R.esc;
  const work = () => { try { return folder || ''; } catch (e) { return ''; } };
  const card = document.createElement('section');
  card.className = 'card';
  card.id = 'final-check';
  card.innerHTML = `<h3>Conferência final do vídeo exportado</h3>
   <p class="meta">Depois de exportar no Premiere, escolha o vídeo pronto. O app ouve o áudio e lê a imagem neste computador e procura o produto antigo e os valores antigos. Gera um relatório para enviar ao cliente.</p>
   <div class="row"><button type="button" id="final-check-run">Conferir vídeo exportado…</button><span class="meta" id="final-check-last"></span></div>
   <div id="final-check-progress" hidden></div><div id="final-check-result"></div><p class="err" id="final-check-error" role="alert"></p>`;
  // Logo depois do bloco que gera o XML: a conferência vem depois da exportação no Premiere.
  const anchor = $('final-xml')?.closest('section');
  anchor ? anchor.after(card) : slot.prepend(card);
  const post = (action, body = {}) => R.call('/fatiador/trocas/' + action, {folder: work(), ...body});

  async function absolute(relative) {
    const place = await R.call('/api/projetos/local', {pasta: work()});
    return place.caminho.replace(/[\\/]$/, '') + (place.caminho.includes('\\') ? '\\' : '/') + relative.split('/').join(place.caminho.includes('\\') ? '\\' : '/');
  }
  function fileUrl(relative) { return '/files/' + [work(), ...relative.split('/')].map(encodeURIComponent).join('/'); }
  async function show(last) {
    const box = $('final-check-result');
    if (!last) { box.innerHTML = ''; $('final-check-last').textContent = ''; return; }
    $('final-check-last').textContent = `Última conferência: ${last.quando} · ${last.arquivo_video}`;
    const verdict = last.aprovado ? '<p class="rm-ok"><b>✓ Nenhuma menção ao produto antigo encontrada</b> no áudio, na imagem e na legenda gravada.</p>'
      : `<p><b style="color:var(--warn,#f5ca7a)">${last.pontos} ponto(s) para conferir</b> no vídeo exportado. Veja os tempos no relatório.</p>`;
    let actions = '';
    if (last.existe !== false) {
      try { actions = R.pathActions(await absolute(last.relatorio), 'Mostrar no Finder'); } catch (e) { actions = ''; }
      actions = `<p><a class="btn" href="${fileUrl(last.relatorio)}" target="_blank" rel="noopener">Abrir relatório de entrega</a></p>` + actions;
    }
    box.innerHTML = verdict + actions + '<p class="meta">O relatório é uma página única com os quadros embutidos: pode ser enviada ao cliente como está.</p>';
  }
  async function refresh() { if (!work()) return; try { show((await post('conferencia-final-estado')).ultima); } catch (e) { /* sem conferência ainda */ } }
  $('final-check-run').onclick = async () => {
    $('final-check-error').textContent = '';
    let path = '';
    try {
      const bridge = window.ripagemDesktop;
      if (bridge?.choose_video) {
        const chosen = await bridge.choose_video();
        if (!chosen.ok) throw Error(chosen.erro);
        if (chosen.cancelado) return;
        path = chosen.arquivo;
      } else path = (prompt('Cole o caminho completo do vídeo exportado (MP4 ou MOV):') || '').trim();
      if (!path) return;
      const job = await post('conferencia-final', {caminho: path});
      R.watch(job, $('final-check-progress'), {onDone: result => { refresh(); return `<p>${result.aprovado ? 'Conferência aprovada.' : result.pontos + ' ponto(s) para conferir.'}</p>`; }});
    } catch (e) { $('final-check-error').textContent = e.message; }
  };
  document.querySelectorAll('[data-flow-step="6"]').forEach(b => b.addEventListener('click', () => setTimeout(refresh, 300)));
  const previous = window.loadSwapPlan;
  if (previous) window.loadSwapPlan = async (...args) => { await previous(...args); refresh(); };
})();
