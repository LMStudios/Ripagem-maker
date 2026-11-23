/* Layout de estúdio da troca de potes (3.12).
   Reorganiza os elementos que os outros scripts já criaram: etapas à esquerda, cabeçalho de uma
   linha, barra de ação fixa com uma ação principal, gaveta de ferramentas por etapa e Takes em abas.
   Não altera regras de transcrição, vozes, takes ou XML: só muda onde cada controle aparece. */
(() => {
  const $ = id => document.getElementById(id), qa = (s, r = document) => [...r.querySelectorAll(s)];
  const guided = $('guided-fatiador'), nav = document.querySelector('.wizard-nav');
  if (!guided || !nav || document.body.classList.contains('sl-on')) return;
  document.body.classList.add('sl-on');
  const make = (tag, cls, html = '') => { const n = document.createElement(tag); if (cls) n.className = cls; n.innerHTML = html; return n; };

  /* ---------- cabeçalho de uma linha ---------- */
  const head = make('header', 'sl-head', '<a class="sl-brand" href="/" title="Painel"><i></i>Ripagem Maker</a><span class="sl-project" id="sl-project">Troca de potes</span><span id="sl-head-slot" style="display:flex;align-items:center;gap:10px"></span><button type="button" class="ghost" id="sl-folder" hidden>Pasta do projeto</button><button type="button" class="ghost" id="sl-tools" hidden>Ferramentas da etapa</button><a class="sl-link" href="/#/ajustes">Ajustes</a>');
  document.body.prepend(head);
  const slot = $('sl-head-slot');
  for (const node of [$('ov-next'), guided.querySelector('.graphite-help'), document.querySelector('.equipe-conta')]) if (node) slot.append(node);

  /* ---------- etapas à esquerda ---------- */
  const rail = make('aside', 'sl-rail');
  rail.append(nav, make('p', 'sl-rail-note', 'O ✓ indica etapa preparada. Etapas apagadas liberam quando a anterior termina.'));
  document.body.append(rail);

  /* ---------- barra de ação ---------- */
  const bar = make('footer', 'sl-bar', '<span class="sl-status" id="sl-status" role="status"></span><div id="sl-actions" class="row"></div>');
  document.body.append(bar);
  const actions = $('sl-actions');

  /* ---------- gaveta da etapa ---------- */
  const shade = make('div', 'sl-shade'), drawer = make('aside', 'sl-drawer', '<header><b id="sl-drawer-title">Ferramentas da etapa</b><button type="button" class="ghost" id="sl-drawer-close">Fechar</button></header><div class="sl-drawer-body" id="sl-drawer-body"></div>');
  drawer.setAttribute('aria-label', 'Ferramentas da etapa');
  document.body.append(shade, drawer);
  const panes = {};
  const pane = key => panes[key] || (panes[key] = Object.assign(make('div', 'sl-pane'), {hidden: true}), $('sl-drawer-body').append(panes[key]), panes[key]);
  const close = () => { drawer.classList.remove('on'); shade.classList.remove('on'); };
  const open = (key, title) => { Object.entries(panes).forEach(([k, p]) => p.hidden = k !== key); $('sl-drawer-title').textContent = title; drawer.classList.add('on'); shade.classList.add('on'); $('sl-drawer-close').focus(); };
  shade.onclick = close; $('sl-drawer-close').onclick = close;
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && drawer.classList.contains('on')) close(); });

  const bySummary = (root, text) => qa('details, section', root).find(n => (n.querySelector(':scope > summary, :scope > h2, :scope > h3')?.textContent || '').trim().startsWith(text));
  const panelOf = n => qa('.wizard-panel').find(p => p.contains(n) || p === n);
  // Ferramentas secundárias de cada etapa (data-flow-step) saem da página e vão para a gaveta.
  const tools = {
    3: () => [document.querySelector('section.practical-form'), document.querySelector('section.studio-summary'), document.querySelector('section.practical-pitch'), document.querySelector('details.studio-extras'), $('treat-panel'), $('old-product-early')],
    4: () => [document.querySelector('section.studio-quick'), $('practical-take-config')],
    6: () => [bySummary(guided, 'Exportações avulsas'), bySummary(guided, 'Identificação e nome do XML'), bySummary(guided, 'Opcional · entregar também a legenda')],
    7: () => [$('subtitle-video-panel')],
  };
  const counts = {};
  for (const [step, find] of Object.entries(tools)) {
    const nodes = find().filter(Boolean);
    counts[step] = nodes.length;
    nodes.forEach(n => { if (n.tagName === 'DETAILS') n.open = true; pane('step' + step).append(n); });
  }
  const location = $('project-location');
  if (location) { pane('pasta').append(location); location.hidden = false; }
  $('sl-folder').onclick = () => open('pasta', 'Pasta do projeto');
  $('sl-tools').onclick = () => open('step' + current(), 'Ferramentas da etapa');

  /* ---------- Takes em abas ---------- */
  const takesPanel = $('flow-title-4')?.closest('.wizard-panel'), host = $('flow-takes-content');
  let tab = 'preparo';
  const placeholder = make('p', 'meta', 'Prepare os takes para conferir a cobertura real em V2.');
  if (takesPanel && host) {
    takesPanel.dataset.slTabbed = '';
    const tabs = make('div', 'sl-tabs', '<button type="button" class="ghost" data-sl-go="preparo">Preparar takes</button><button type="button" class="ghost" data-sl-go="aparicoes">Produto antigo<span class="sl-count" id="sl-count-aparicoes"></span></button><button type="button" class="ghost" data-sl-go="cobertura">Cobertura<span class="sl-count" id="sl-count-cobertura"></span></button><button type="button" class="ghost" data-sl-go="broll">B-roll<span class="sl-count" id="sl-count-broll"></span></button>');
    tabs.setAttribute('role', 'tablist');
    takesPanel.querySelector(':scope > p.meta')?.after(tabs);
    const mark = (n, k) => n && (n.dataset.slTab = k);
    qa(':scope > .flow-automation, :scope > .flow-choice', takesPanel).forEach(n => mark(n, 'preparo'));
    [...host.children].forEach(n => mark(n, n.id === 'old-product-panel' ? 'aparicoes' : n.id === 'ov-gaps' ? 'cobertura' : n.id === 'broll-panel' ? 'broll' : 'preparo'));
    mark(placeholder, 'cobertura'); host.append(placeholder);
    const product = $('old-product-panel'); if (product) product.open = true;
    tabs.addEventListener('click', e => { const b = e.target.closest('[data-sl-go]'); if (b) { tab = b.dataset.slGo; syncTabs(); } });
  }
  function syncTabs() {
    if (!takesPanel) return;
    qa('[data-sl-tab]', takesPanel).forEach(n => n.classList.toggle('sl-tab-on', n.dataset.slTab === tab));
    qa('[data-sl-go]', takesPanel).forEach(b => b.setAttribute('aria-selected', String(b.dataset.slGo === tab)));
    const product = $('old-product-panel'); if (product && tab === 'aparicoes') product.open = true;
    const gaps = $('ov-gaps'); placeholder.hidden = !!gaps && !gaps.hidden;
    const state = window.OldProductUX?.state, pending = (state?.intervalos || []).filter(i => i.status === 'sugerido' && !i.coberto_pela_fala).length;
    const summary = window.VisualReview?.summary, open = summary?.cobertura?.frestas || 0;
    const a = $('sl-count-aparicoes'), c = $('sl-count-cobertura');
    if (a) { a.textContent = pending ? pending + ' para revisar' : ''; a.hidden = !pending; a.className = 'sl-count warn'; }
    if (c) { c.textContent = open ? open + ' fresta' + (open > 1 ? 's' : '') : ''; c.hidden = !open; c.className = 'sl-count warn'; }
    const br = $('sl-count-broll'), chosen = window.BrollUX?.state?.escolhidos || 0;
    if (br) { br.textContent = chosen ? chosen + ' em V3' : ''; br.hidden = !chosen; br.className = 'sl-count'; }
    if (tab === 'broll' && window.BrollUX && !window.BrollUX.state) window.BrollUX.refresh();
  }

  /* ---------- etapa atual e ação principal ---------- */
  const current = () => Number(nav.querySelector('[aria-current="step"]')?.dataset.flowStep || 1);
  const visible = n => !!n && !n.hidden && !n.closest('[hidden]') && getComputedStyle(n).display !== 'none';
  // Ação principal de cada etapa quando ela não é o "Continuar" da própria etapa.
  const stage31 = () => $('speech-texts') && !$('speech-texts').classList.contains('ghost');
  // Próxima etapa pela barra de etapas, quando o fluxo libera e a etapa não tem botão próprio.
  const stepButton = n => { const b = nav.querySelector(`[data-flow-step="${n}"]`); return b && !b.disabled ? Object.assign(b, {slLabel: 'Continuar para ' + b.textContent.trim()}) : null; };
  const primaryOf = {1: () => $('go'), 3: () => { const next = document.querySelector('[data-w-panel="3"] [data-w-next]'); return next && !next.hidden ? null : stage31() ? $('swap-all') : stepButton(4); }, 4: () => { const v = window.VisualUX?.state; return v?.prepared && !v.issues?.length && !v.cobertura_desatualizada ? stepButton(6) : $('flow-auto-takes'); }, 5: () => $('flow-finish'), 6: () => $('final-xml'), 7: () => $('final-caption-save')};
  const proxy = make('button', 'sl-primary'); proxy.type = 'button'; proxy.hidden = true;
  let target = null, movedRow = null, rowHome = null;
  proxy.onclick = () => target?.click();
  function placeRow(panel) {
    if (movedRow && rowHome && !panel?.contains(rowHome)) { rowHome.after(movedRow); movedRow = rowHome = null; }
    if (!panel || movedRow) return;
    const row = qa(':scope > .row', panel).pop();
    if (!row) return;
    rowHome = make('span'); rowHome.hidden = true; row.before(rowHome);
    movedRow = row; actions.append(row);
  }
  function statusText(step) {
    const pick = (...ids) => ids.map(id => $(id)).find(n => n && visible(n) && n.textContent.trim())?.textContent.trim() || '';
    if (step === 3) return pick('flow-speech-message', 'flow-change-warning') || (document.querySelector('section.studio-summary p:last-of-type')?.textContent.trim() || '');
    if (step === 4) return pick('flow-takes-state', 'flow-take-count');
    if (step === 6) return pick('final-error', 'final-xml-error') || 'Confira os itens e salve o XML para o Premiere.';
    return '';
  }
  function sync() {
    const step = current(), panel = qa('.wizard-panel').find(p => !p.hidden);
    // Números das etapas na ordem visível; o título não repete "Etapa N de 7".
    qa('[data-flow-step]', nav).forEach((b, i) => {
      b.dataset.slN = String(i + 1);
      const text = b.textContent.replace(/^\s*\d+\.\s*/, '');
      if (text !== b.textContent) b.textContent = text;
    });
    qa('.wizard-panel > h2').forEach(h => { const t = h.textContent.replace(/^Etapa \d+ de \d+ · /, ''); if (t !== h.textContent) h.textContent = t; });
    placeRow(panel);
    target = primaryOf[step]?.() || null;
    // Botão escondido pelo próprio fluxo (atributo hidden) não vira ação principal.
    const fromNav = !!target && nav.contains(target);
    if (target && !fromNav && (target.hidden || target.closest('[hidden]') || (!target.dataset.slProxied && !visible(target)))) target = null;
    if (target) {
      if (!fromNav) { target.dataset.slProxied = '1'; target.style.display = 'none'; }
      proxy.textContent = fromNav ? target.slLabel : target.textContent.trim(); proxy.disabled = target.disabled; proxy.hidden = false;
      if (proxy.parentElement !== actions) actions.append(proxy);
    } else proxy.hidden = true;
    // Uma ação principal: o "Continuar" da etapa só é principal quando não há outra.
    qa('button', movedRow || document.createElement('div')).forEach(b => b.classList.toggle('sl-primary', !target && !b.classList.contains('ghost') && !b.hasAttribute('data-w-back') && !/^Voltar/.test(b.textContent.trim()) && visible(b)));
    $('sl-status').textContent = statusText(step);
    const plan = window.SwapUX?.plan;
    $('sl-project').innerHTML = plan ? `<b>${(plan.produto || '').replace(/[<>&]/g, '')} → ${(plan.produto_novo || '').replace(/[<>&]/g, '')}</b>` : 'Troca de potes';
    let work = ''; try { work = folder; } catch (e) { work = ''; }
    $('sl-folder').hidden = !work;
    $('sl-tools').hidden = !counts[step];
    $('sl-tools').textContent = 'Ferramentas da etapa' + (counts[step] ? ` (${counts[step]})` : '');
    syncTabs();
    // Caminhos longos ocupam uma linha; o caminho completo fica no texto de ajuda.
    qa('.wizard-panel p, .wizard-panel code, .wizard-panel span').forEach(n => {
      if (n.dataset.slPath || n.children.length) return;
      const text = n.textContent.trim();
      if (/^(\/(Users|private|Volumes|home)\/|[A-Z]:\\)/.test(text)) { n.dataset.slPath = '1'; n.classList.add('sl-path'); n.title = text; }
    });
    fitWorkspace(step);
  }
  // Falas: a área de trabalho ocupa o espaço até a barra inferior; a lista rola por dentro.
  function fitWorkspace(step) {
    const ws = document.querySelector('.ux-workspace');
    if (!ws || step !== 3 || !visible(ws)) return;
    // Posição na página (independe da rolagem atual): a lista termina logo acima da barra.
    const top = ws.getBoundingClientRect().top + scrollY;
    const value = Math.max(300, Math.floor(innerHeight - bar.offsetHeight - 16 - top)) + 'px';
    if (ws.style.height !== value) ws.style.height = value;
  }
  addEventListener('resize', () => fitWorkspace(current()));
  new MutationObserver(sync).observe(nav, {attributes: true, subtree: true, attributeFilter: ['aria-current', 'disabled', 'data-state']});
  setInterval(sync, 700);
  sync();
  window.StudioLayout = {sync, open, close, tab: t => { tab = t; syncTabs(); }};
})();
