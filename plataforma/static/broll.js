/* Buscador de b-roll por frase (Takes → aba B-roll). Os clipes são sugestões até o editor escolher. */
(() => {
  const R = window.RMJob;
  if (!R) return;

  function mount(host, library = false) {
  const $ = id => card.querySelector('#' + CSS.escape(id));
  let libraryPath = '';
  const libraryId = 'biblioteca';
  const esc = R.esc;
  const work = () => { if (library) return libraryPath; try { return folder || ''; } catch (e) { return ''; } };
  const post = (action, body = {}) => library ? R.call('/api/ferramentas/broll/' + action, body) : R.call('/fatiador/trocas/' + action, {folder: work(), ...body});
  const fileUrl = rel => (library ? '/ferramentas/arquivo/' : '/files/') + [ ...(library ? work().split('/') : [work()]), ...rel.split('/')].map(encodeURIComponent).join('/');
  const clock = ms => { const s = Math.floor(ms / 1000); return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0'); };
  const BADGE = {limpo: ['Limpo', 'br-ok'], texto: ['Texto na tela', 'br-warn'], marca_dagua: ["Marca d'água", 'br-bad']};

  const style = document.getElementById('broll-styles') || document.createElement('style');
  style.id = 'broll-styles';
  style.textContent = `
  #broll-panel .br-top{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:6px 0 8px}
  #broll-panel .br-top input[type=search]{flex:1 1 220px;min-width:160px}
  #broll-panel .br-list{max-height:min(62vh,640px);overflow:auto;border:1px solid var(--line,#2a2f3a);border-radius:10px}
  #broll-panel .br-row{display:grid;grid-template-columns:52px minmax(0,1fr) minmax(0,34%) auto;gap:8px;align-items:center;padding:7px 10px;border-bottom:1px solid var(--line,#2a2f3a)}
  #broll-panel .br-row.br-open{background:rgba(127,127,127,.07)}
  #broll-panel .br-time{font-variant-numeric:tabular-nums;opacity:.75;font-size:12px}
  #broll-panel .br-text{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:13px;cursor:pointer}
  #broll-panel .br-tags{display:flex;gap:4px;margin-top:2px;font-size:11px}
  #broll-panel .br-tag{padding:0 6px;border-radius:8px;background:rgba(127,127,127,.18)}
  #broll-panel .br-row input{width:100%;font-size:12px}
  #broll-panel .br-cands{grid-column:1/-1;display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,190px),1fr));gap:8px;padding:4px 0 6px}
  #broll-panel .br-card{border:1px solid var(--line,#2a2f3a);border-radius:9px;overflow:hidden;font-size:12px;display:flex;flex-direction:column}
  #broll-panel .br-card.br-chosen{outline:2px solid var(--ok,#58c48a)}
  #broll-panel .br-card video,#broll-panel .br-card img{width:100%;aspect-ratio:16/9;object-fit:cover;background:#000;display:block;cursor:pointer}
  #broll-panel .br-card .br-body{padding:6px 8px;display:flex;flex-direction:column;gap:4px;flex:1}
  #broll-panel .br-card .br-title{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;opacity:.8}
  #broll-panel .br-badge{align-self:flex-start;padding:1px 7px;border-radius:8px;font-weight:600;font-size:11px}
  #broll-panel .br-ok{background:rgba(88,196,138,.18);color:var(--ok,#58c48a)}
  #broll-panel .br-warn{background:rgba(245,202,122,.18);color:var(--warn,#f5ca7a)}
  #broll-panel .br-bad{background:rgba(240,110,110,.18);color:var(--err,#f07070)}
  #broll-panel .br-card .row{gap:6px;margin-top:auto}
  #broll-panel .br-progress{grid-column:1/-1}
  #broll-panel .br-src{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding-top:4px}
  #broll-panel .br-src input{flex:1 1 240px;width:auto}
  #broll-panel{container-type:inline-size;min-width:0}
  #broll-panel .br-top input,#broll-panel .br-src input{min-width:0;max-width:100%}
  #broll-panel .br-tags{flex-wrap:wrap}
  #broll-panel .br-row input{min-width:0}
  #broll-panel .br-card .row{flex-wrap:wrap}
  #broll-panel .br-library-row{grid-template-columns:minmax(0,1fr) auto}
  #broll-panel .br-text{background:none;border:0;color:inherit;text-align:left;padding:0;max-width:100%;overflow-wrap:anywhere}
  @container (max-width:620px){
    #broll-panel .br-row{grid-template-columns:44px minmax(0,1fr)}
    #broll-panel .br-row input,#broll-panel .br-go{grid-column:1/-1}
    #broll-panel .br-library-row{grid-template-columns:minmax(0,1fr)}
    #broll-panel .br-go{justify-self:start}
  }`;
  document.head.append(style);

  const card = document.createElement('section');
  card.className = 'card';
  card.id = 'broll-panel';
  card.innerHTML = library ? `<div class="br-top"><label class="meta"><input type="checkbox" id="broll-clean"> Só clipes limpos</label></div>
    <p class="err" id="broll-error" role="alert"></p>
    <div class="br-row br-library-row">
      <input type="search" data-br-query="${libraryId}" aria-label="O que procurar?" placeholder="O que procurar? Ex.: mulher olhando no espelho" maxlength="120">
      <button type="button" class="btn br-go" data-br-search="${libraryId}">Buscar no YouTube</button>
      <div id="broll-progress-${libraryId}" class="br-progress" hidden></div>
      <div id="broll-library-sources" class="br-progress"></div>
      <div id="broll-list" class="br-progress" aria-live="polite"></div>
    </div>` : `<h3 style="margin:0">B-roll por frase <span class="meta" id="broll-summary"></span></h3>
   <p class="meta">Revise as frases a partir da primeira menção ao produto. Busque um clipe ou cole um link. Ao clicar em “Usar nesta frase”, o clipe entra em V3 no XML, sem áudio.
   </p><p id="broll-start" class="meta"></p>
   <div class="br-top"><input type="search" id="broll-filter-text" placeholder="Procurar na fala…" aria-label="Procurar na fala">
    <select id="broll-filter" aria-label="Mostrar"><option value="todas">Todas as frases</option><option value="fresta">Com fresta visual</option><option value="buscadas">Já buscadas</option><option value="escolhidas">Com b-roll escolhido</option></select>
    <label class="meta"><input type="checkbox" id="broll-clean"> Só clipes limpos</label></div>
   <p class="err" id="broll-error" role="alert"></p>
   <div class="br-list" id="broll-list" role="list"></div>
   <div class="row" style="margin-top:6px"><button type="button" class="ghost" id="broll-more" hidden>Mostrar mais frases</button></div>`;
  host.append(card);

  let data = null, open = null, limit = 40;
  const watchers = {};
  function visibleRows() {
    if (!data) return [];
    const q = $('broll-filter-text').value.trim().toLowerCase(), f = $('broll-filter').value;
    return data.frases.filter(r => (!q || r.texto.toLowerCase().includes(q)) &&
      (f === 'todas' || (f === 'fresta' && r.fresta) || (f === 'buscadas' && r.buscada) || (f === 'escolhidas' && r.escolha)));
  }
  const auto = () => !!window.ripagemDesktop?.collect_broll;
  function sources(r) {
    const q = encodeURIComponent(r.busca || '');
    const search = auto()
      ? `<span class="meta">Buscar também:</span><button type="button" class="ghost btn sm" data-br-collect="tiktok" data-frase="${esc(r.id)}">TikTok</button><button type="button" class="ghost btn sm" data-br-collect="pinterest" data-frase="${esc(r.id)}">Pinterest</button><span class="meta">ou cole um link:</span>`
      : `<span class="meta">TikTok e Pinterest:</span>
      <a class="ghost btn sm" href="https://www.tiktok.com/search/video?q=${q}" target="_blank" rel="noopener">Procurar no TikTok ↗</a>
      <a class="ghost btn sm" href="https://www.pinterest.com/search/videos/?q=${q}" target="_blank" rel="noopener">Procurar no Pinterest ↗</a>`;
    return `<div class="br-src">${search}
      <input type="url" data-br-link="${esc(r.id)}" placeholder="Cole aqui o link do vídeo escolhido" aria-label="Link do vídeo do TikTok, Pinterest ou YouTube">
      <button type="button" class="ghost btn sm" data-br-add="${esc(r.id)}">Adicionar</button></div>`;
  }
  function candidates(r) { return sources(r) + cardsOf(r); }
  function cardsOf(r) {
    const clean = $('broll-clean').checked;
    const list = r.candidatos.filter(c => c.existe !== false && (!clean || c.status === 'limpo'));
    const order = {limpo: 0, texto: 1, marca_dagua: 2};
    list.sort((a, b) => order[a.status] - order[b.status]);
    if (!list.length) return `<p class="meta br-cands">${r.buscada ? 'Nenhum clipe ' + (clean ? 'limpo ' : '') + 'nesta busca. Mude as palavras e busque de novo.' : 'Clique em Buscar para ver sugestões.'}</p>`;
    return '<div class="br-cands">' + list.map(c => {
      const [label, cls] = BADGE[c.status] || BADGE.texto, chosen = r.escolha?.candidato === c.id;
      const why = [...(c.marca_dagua || []), ...(c.texto || [])].slice(0, 3).join(' · ');
      const action = library
        ? `<a class="btn sm" href="${fileUrl(c.arquivo)}?dl=1" download>Baixar clipe</a>`
        : chosen
          ? `<button type="button" class="ghost btn sm" data-br-unchoose="${esc(r.id)}">Remover</button><span class="rm-ok">✓ Em V3</span>`
          : `<button type="button" class="btn sm" data-br-choose="${esc(r.id)}" data-cand="${esc(c.id)}">Usar nesta frase</button>`;
      return `<div class="br-card${chosen ? ' br-chosen' : ''}"><img src="${fileUrl(c.miniatura)}" alt="" loading="lazy" data-br-play="${esc(c.arquivo)}" title="Clique para assistir">
       <div class="br-body"><span class="br-badge ${cls}">${label}</span>${why ? `<span class="meta" title="${esc(why)}">${esc(why.slice(0, 60))}</span>` : ''}
       <span class="br-title" title="${esc(c.titulo)}">${esc(c.titulo)}</span><span class="meta">${c.duracao_s}s · ${c.largura}×${c.altura} · <a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.fonte || 'YouTube')}</a></span>
       <div class="row">${action}</div></div></div>`;
    }).join('') + '</div>';
  }
  function render() {
    const list = $('broll-list');
    if (library) {
      if (data) list.innerHTML = cardsOf(data.frases[0]);
      return;
    }
    $('broll-start').textContent = data
      ? data.primeira_mencao_ms == null ? 'Confirme o nome do produto em Falas para localizar a primeira menção.' : `Primeira menção em ${clock(data.primeira_mencao_ms)}.`
      : '';
    if (!data) { list.innerHTML = '<p class="meta" style="padding:10px">Abra um projeto com transcrição.</p>'; return; }
    $('broll-summary').textContent = data.escolhidos ? `· ${data.escolhidos} escolhido(s), ${data.segundos}s em V3` : '';
    const rows = visibleRows();
    list.innerHTML = rows.slice(0, limit).map(r => {
      const tags = [r.fresta ? '<span class="br-tag" title="Produto antigo visível sem take nesta frase">fresta visual</span>' : '',
        r.escolha ? '<span class="br-tag rm-ok">b-roll escolhido</span>' : '',
        r.buscada ? `<span class="br-tag">${r.candidatos.length} clipe(s)</span>` : ''].join('');
      return `<div class="br-row${open === r.id ? ' br-open' : ''}" role="listitem" data-row="${esc(r.id)}">
        <span class="br-time">${clock(r.inicio_ms)}<br>${((r.fim_ms - r.inicio_ms) / 1000).toFixed(1)}s</span>
        <div><button type="button" class="br-text" data-br-toggle="${esc(r.id)}" aria-expanded="${open === r.id}" title="${esc(r.texto)}">${esc(r.texto)}</button><div class="br-tags">${tags}</div></div>
        <input type="text" value="${esc(r.busca)}" data-br-query="${esc(r.id)}" aria-label="Busca de b-roll para a frase" maxlength="120">
        <button type="button" class="ghost btn sm br-go" data-br-search="${esc(r.id)}">Buscar</button>
        <div class="br-progress" id="broll-progress-${esc(r.id)}" hidden></div>
        ${open === r.id ? candidates(r) : ''}</div>`;
    }).join('') || '<p class="meta" style="padding:10px">Nenhuma frase com esse filtro.</p>';
    $('broll-more').hidden = rows.length <= limit;
    // Buscas em andamento continuam mostrando o progresso depois de redesenhar a lista.
    Object.entries(watchers).forEach(([id, job]) => { const box = $('broll-progress-' + id); if (box) watchJob(id, job, box); });
  }
  function watchJob(id, job, box) {
    R.watch(job, box, {onDone: result => { delete watchers[id]; open = id; refresh(); return `<p class="meta">${result.encontrados} clipe(s), ${result.limpos} limpo(s).</p>`; },
      onError: () => { delete watchers[id]; }});
  }
  async function refresh() {
    if (!library && !work()) return;
    const current = work();
    try {
      const next = await post('broll-estado');
      if (!library && work() !== current) return;
      data = next;
      if (library) libraryPath = data.pasta; $('broll-error').textContent = data.motor?.ok === false ? data.motor.erro : ''; }
    catch (e) { data = null; $('broll-error').textContent = /transcricao_bruta|No such file/.test(e.message) ? '' : e.message; }
    render();
  }
  card.addEventListener('click', async e => {
    const t = e.target;
    if (t.matches('button[data-br-search], button[data-br-add], button[data-br-collect]')) {
      const id = t.dataset.brSearch || t.dataset.brAdd || t.dataset.frase;
      if (watchers[id] || t.disabled) return;
      t.disabled = true;
    }
    try {
      if (t.closest('[data-br-toggle]')) { const id = t.closest('[data-br-toggle]').dataset.brToggle; open = open === id ? null : id; render(); return; }
      if (t.dataset.brPlay) { const v = document.createElement('video'); v.src = fileUrl(t.dataset.brPlay); v.controls = v.autoplay = v.muted = v.loop = true; t.replaceWith(v); return; }
      if (t.dataset.brSearch) {
        const id = t.dataset.brSearch, query = card.querySelector(`[data-br-query="${CSS.escape(id)}"]`).value;
        $('broll-error').textContent = '';
        const job = await post('broll-buscar', {frase: id, consulta: query});
        watchers[id] = job; open = id;
        watchJob(id, job, $('broll-progress-' + id));
        return;
      }
      if (t.dataset.brCollect) {
        const id = t.dataset.frase, site = t.dataset.brCollect, name = site === 'tiktok' ? 'TikTok' : 'Pinterest';
        const query = card.querySelector(`[data-br-query="${CSS.escape(id)}"]`).value.trim();
        const box = $('broll-progress-' + id);
        $('broll-error').textContent = '';
        box.hidden = false;
        box.innerHTML = `<p class="meta"><span class="rm-spin"></span> Procurando no ${name}… Se uma janela do ${name} abrir, entre na sua conta ou conclua a verificação; a busca continua sozinha.</p>`;
        card.querySelectorAll('[data-br-collect]').forEach(b => b.disabled = true);
        try {
          const found = await window.ripagemDesktop.collect_broll(site, query, 8);
          if (!found.ok) throw Error(found.erro);
          const job = await post('broll-links', {frase: id, urls: found.links, consulta: query, fonte: found.fonte});
          watchers[id] = job; open = id; watchJob(id, job, $('broll-progress-' + id));
        } catch (error) { box.innerHTML = ''; box.hidden = true; $('broll-error').textContent = error.message; }
        finally { card.querySelectorAll('[data-br-collect]').forEach(b => b.disabled = false); }
        return;
      }
      if (t.dataset.brAdd) {
        const id = t.dataset.brAdd, url = card.querySelector(`[data-br-link="${CSS.escape(id)}"]`).value.trim();
        if (!url) { $('broll-error').textContent = 'Cole o link do vídeo do TikTok, Pinterest ou YouTube.'; return; }
        $('broll-error').textContent = '';
        const job = await post('broll-link', {frase: id, url});
        watchers[id] = job; watchJob(id, job, $('broll-progress-' + id));
        return;
      }
      if (t.dataset.brChoose) { data = await post('broll-escolher', {frase: t.dataset.brChoose, candidato: t.dataset.cand}); render(); return; }
      if (t.dataset.brUnchoose) { data = await post('broll-escolher', {frase: t.dataset.brUnchoose, candidato: ''}); render(); return; }
    } catch (error) { $('broll-error').textContent = error.message; }
    finally { if (t.matches('button[data-br-search], button[data-br-add], button[data-br-collect]')) t.disabled = false; }
  });
  card.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.dataset.brLink) { e.preventDefault(); card.querySelector(`[data-br-add="${CSS.escape(e.target.dataset.brLink)}"]`).click(); return; }
    if (e.key === 'Enter' && e.target.dataset.brQuery) { e.preventDefault(); card.querySelector(`[data-br-search="${CSS.escape(e.target.dataset.brQuery)}"]`).click(); } });
  ['broll-filter-text', 'broll-filter', 'broll-clean'].forEach(id => $(id)?.addEventListener('input', () => { limit = 40; render(); }));
  if (library) {
    const query = card.querySelector('[data-br-query]');
    $('broll-library-sources').innerHTML = sources({id: libraryId});
    query.addEventListener('input', () => {
      const q = encodeURIComponent(query.value.trim());
      $('broll-library-sources').querySelectorAll('a').forEach(a => {
        const href = new URL(a.href);
        href.search = 'q=' + q;
        a.href = href;
      });
    });
    refresh();
    return;
  }
  $('broll-more').onclick = () => { limit += 40; render(); };
  document.querySelectorAll('[data-flow-step="4"]').forEach(b => b.addEventListener('click', () => setTimeout(refresh, 300)));
  const previous = window.loadSwapPlan;
  if (previous) window.loadSwapPlan = async (...args) => { await previous(...args); refresh(); };
  window.BrollUX = {refresh, get state() { return data; }};
  render();
  }
  window.mountBrollLibrary = host => mount(host, true);
  const takes = document.getElementById('flow-takes-content');
  if (takes) mount(takes);
})();
