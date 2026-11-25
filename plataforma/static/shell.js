/* Ripagem Maker 4 — casca de navegação: barra lateral recolhível e paleta de comandos (Ctrl/⌘ K).
   Só navegação: não chama rotas de geração, takes ou XML. */
(() => {
 const doc = document, root = doc.documentElement;
 const store = {get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { } }};
 const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
 const norm = s => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
 const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
 const ICON_SEARCH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>';
 const ICON_SIDE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/></svg>';

 /* ------------------------------------------------------------ comandos */
 const BASE = [
  ['Começar', 'Nova ripagem', 'Troca de potes do vídeo à entrega', '/fatiador?inicio=novo', 'swap', 'novo nova troca potes ripagem comecar'],
  ['Começar', 'Continuar projeto', 'Reabra um trabalho salvo', '/fatiador?inicio=continuar', 'folder', 'continuar retomar abrir'],
  ['Ir para', 'Painel', 'Visão geral e projetos recentes', '/#/', 'home', 'inicio home'],
  ['Ir para', 'Projetos', 'Todos os projetos e pastas', '/#/projetos', 'folder', 'pastas trabalhos'],
  ['Ir para', 'Troca de potes', 'Fluxo guiado completo', '/fatiador', 'swap', 'fatiador estudio'],
  ['Ir para', 'Microlead’s', 'Novas aberturas a partir de uma demanda', '/#/demanda', 'merge', 'microlead demanda ml vsl'],
  ['Ir para', 'Ferramentas avulsas', 'Transcrição, áudio, takes e legendas', '/#/ferramentas', 'tools', 'transcrever audio legenda broll'],
  ['Ir para', 'Caçar B-rolls', 'Busque ou baixe trechos de vídeo', '/#/ferramenta/broll', 'tools', 'broll b-roll video'],
  ['Ir para', 'Nomenclatura VTurb', 'Padronize nomes de VSL e ofertas', '/#/nomes', 'type', 'nomes vturb nome'],
  ['Ir para', 'Ajustes', 'Integrações, pastas, takes e atualizações', '/#/ajustes', 'gear', 'configuracoes preferencias chaves api'],
  ['Ir para', 'Experiência Studio', 'Orientações e estimativa de tempo', '/#/studio', 'spark', 'tempo economia guia'],
 ];
 let projects = null;
 const loadProjects = async () => {
  if (projects) return projects;
  try {
   const r = await fetch('/api/projetos'); const d = r.ok ? await r.json() : {};
   projects = (d.projetos || []).slice(0, 30).map(p => ['Projetos', p.nome || p.pasta, [p.produto, p.etapa].filter(Boolean).join(' · '),
    '/fatiador?' + new URLSearchParams({trabalho: p.pasta}), 'folder', norm(p.pasta)]);
  } catch (e) { projects = []; }
  return projects;
 };

 /* ------------------------------------------------------------ paleta */
 let box, input, list, items = [], sel = 0, lastFocus = null;
 function build() {
  box = doc.createElement('div');
  box.className = 'rm-cmd'; box.setAttribute('role', 'dialog'); box.setAttribute('aria-modal', 'true'); box.setAttribute('aria-label', 'Buscar e navegar');
  box.innerHTML = `<div class="rm-cmd-box"><div class="rm-cmd-head">${ICON_SEARCH}<input type="text" placeholder="Buscar páginas, ações e projetos…" aria-label="Buscar" autocomplete="off" spellcheck="false" role="combobox" aria-expanded="true" aria-controls="rm-cmd-list"></div>
   <ul class="rm-cmd-list" id="rm-cmd-list" role="listbox"></ul>
   <div class="rm-cmd-foot"><span><kbd>↑</kbd><kbd>↓</kbd>navegar</span><span><kbd>Enter</kbd>abrir</span><span><kbd>Esc</kbd>fechar</span></div></div>`;
  doc.body.append(box);
  input = box.querySelector('input'); list = box.querySelector('ul');
  box.addEventListener('mousedown', e => { if (e.target === box) close(); });
  input.addEventListener('input', () => { sel = 0; draw(); });
  input.addEventListener('keydown', e => {
   if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); if (items.length) { sel = (sel + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length; mark(); } }
   else if (e.key === 'Enter') { e.preventDefault(); go(items[sel]); }
   else if (e.key === 'Escape') { e.preventDefault(); close(); }
   else if (e.key === 'Tab') e.preventDefault();
  });
  list.addEventListener('click', e => { const li = e.target.closest('[data-i]'); if (li) go(items[+li.dataset.i]); });
  list.addEventListener('mousemove', e => { const li = e.target.closest('[data-i]'); if (li && +li.dataset.i !== sel) { sel = +li.dataset.i; mark(); } });
 }
 function draw() {
  const q = norm(input.value).trim().split(/\s+/).filter(Boolean);
  const all = BASE.concat(projects || []);
  items = all.filter(c => { const hay = norm(c[1] + ' ' + c[2] + ' ' + c[5]); return q.every(w => hay.includes(w)); });
  if (!q.length) items = items.filter(c => c[0] !== 'Projetos').concat((projects || []).slice(0, 5));
  if (!items.length) { list.innerHTML = `<li class="rm-cmd-empty">Nada encontrado para “${esc(input.value)}”.</li>`; return; }
  let group = '', html = '';
  items.forEach((c, i) => {
   if (c[0] !== group) { group = c[0]; html += `<li class="rm-cmd-group" role="presentation">${esc(group)}</li>`; }
   html += `<li class="rm-cmd-item" role="option" id="rm-cmd-${i}" data-i="${i}" style="--i:var(--i-${c[4]})"><span><b>${esc(c[1])}</b>${c[2] ? `<small>${esc(c[2])}</small>` : ''}</span></li>`;
  });
  list.innerHTML = html; mark();
 }
 function mark() {
  list.querySelectorAll('[aria-selected]').forEach(n => n.removeAttribute('aria-selected'));
  const n = list.querySelector(`[data-i="${sel}"]`);
  if (n) { n.setAttribute('aria-selected', 'true'); input.setAttribute('aria-activedescendant', n.id); n.scrollIntoView({block: 'nearest'}); }
 }
 function go(c) {
  if (!c) return; close(false);
  const url = new URL(c[3], location.origin);
  if (url.pathname === location.pathname && url.search === location.search && url.hash) location.hash = url.hash;
  else location.href = c[3];
 }
 function open() {
  if (!box) build();
  lastFocus = doc.activeElement; input.value = ''; sel = 0; draw();
  box.classList.add('on'); input.focus();
  loadProjects().then(() => { if (box.classList.contains('on')) draw(); });
 }
 function close(restore = true) {
  if (!box) return; box.classList.remove('on');
  if (restore && lastFocus && lastFocus.focus) lastFocus.focus();
 }
 window.RMCommand = {open, close};

 doc.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && !e.altKey && (e.key === 'k' || e.key === 'K')) { e.preventDefault(); box?.classList.contains('on') ? close() : open(); return; }
  if (e.key === '/' && !e.metaKey && !e.ctrlKey && !e.altKey) {
   const t = e.target; if (t.closest && t.closest('input,textarea,select,[contenteditable=""],[contenteditable=true]')) return;
   if (doc.querySelector('dialog[open]')) return;
   e.preventDefault(); open();
  }
 });

 const trigger = cls => {
  const b = doc.createElement('button'); b.type = 'button'; b.className = cls;
  b.innerHTML = `${ICON_SEARCH}<span>Buscar…</span><kbd>${isMac ? '⌘' : 'Ctrl'} K</kbd>`;
  b.title = `Buscar ou ir para (${isMac ? '⌘' : 'Ctrl'}+K)`; b.onclick = open; return b;
 };

 /* ------------------------------------------------------------ barra lateral */
 const side = doc.querySelector('.side');
 if (side) {
  const tools = doc.createElement('div'); tools.className = 'rm-side-tools';
  const collapse = doc.createElement('button'); collapse.type = 'button'; collapse.className = 'rm-collapse'; collapse.innerHTML = ICON_SIDE;
  const sync = () => { const on = root.classList.contains('rm-compact'); collapse.setAttribute('aria-pressed', String(on)); collapse.title = on ? 'Expandir barra lateral' : 'Recolher barra lateral'; collapse.setAttribute('aria-label', collapse.title); };
  collapse.onclick = () => { root.classList.toggle('rm-compact'); store.set('rm.compact', root.classList.contains('rm-compact') ? '1' : '0'); sync(); };
  if (store.get('rm.compact') === '1') root.classList.add('rm-compact');
  sync();
  tools.append(trigger('rm-search-trigger'), collapse);
  (side.querySelector('.brand') || side.firstChild).after(tools);
  // Dicas para o modo recolhido e para links injetados por outros módulos.
  const nav = side.querySelector('.nav');
  const label = () => nav && nav.querySelectorAll('a').forEach(a => { const t = a.textContent.trim(); if (t && a.title !== t) { a.title = t; a.setAttribute('aria-label', t); } });
  label(); if (nav) new MutationObserver(label).observe(nav, {childList: true, subtree: true, characterData: true});
 }

 /* Estúdio da troca de potes: atalho de busca no cabeçalho criado pelo layout. */
 const addHeadTrigger = () => {
  const head = doc.querySelector('.sl-head'); if (!head || head.querySelector('.rm-head-search')) return !!head;
  const b = trigger('rm-head-search ghost'); b.querySelector('span').textContent = 'Buscar'; head.insertBefore(b, head.querySelector('.sl-project')?.nextSibling || null); return true;
 };
 if (!side) {
  const tryHead = () => { if (!addHeadTrigger()) { const mo = new MutationObserver(() => { if (addHeadTrigger()) mo.disconnect(); }); mo.observe(doc.body, {childList: true}); setTimeout(() => mo.disconnect(), 15000); } };
  doc.readyState === 'loading' ? doc.addEventListener('DOMContentLoaded', tryHead) : setTimeout(tryHead);
 }
})();
