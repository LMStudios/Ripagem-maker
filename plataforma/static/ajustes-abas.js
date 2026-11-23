/* Ajustes em abas (3.12): os cartões criados pelos outros scripts são agrupados por assunto.
   Nenhum cartão é removido; só aparece o grupo escolhido. A aba fica lembrada nesta janela. */
(() => {
  if (typeof routes === 'undefined' || !routes['/ajustes']) return;
  const GROUPS = [
    ['geral', 'Fluxo e notificações', /Fluxo de Troca|Notificaç|Experiência/i],
    ['integracoes', 'Integrações', /Integraç|API|chave|Equipe|Conta|login/i],
    ['takes', 'Takes e áudio', /Margem|Tratamento de áudio|Limpar o início|Transcrição e cortes/i],
    ['pastas', 'Pastas e armazenamento', /Pasta|Mover um projeto|Armazenamento|Limpeza/i],
    ['versao', 'Versão e atualizações', /Versão|Atualiza/i],
  ];
  const css = document.createElement('style');
  css.textContent = `.aj-tabs{display:flex;flex-wrap:wrap;gap:4px;border-bottom:1px solid var(--line);margin:4px 0 16px;position:sticky;top:0;background:var(--bg);z-index:5;padding-top:6px}
  .aj-tabs button{background:none!important;border:0!important;border-bottom:2px solid transparent!important;border-radius:0!important;padding:9px 12px!important;color:var(--mute)!important;cursor:pointer;font:inherit;box-shadow:none!important}
  .aj-tabs button[aria-selected=true]{color:var(--text,#eef0f5)!important;border-bottom-color:#8b5cf6!important}
  #view[data-aj] > [data-aj-group]:not([data-aj-group=""]):not(.aj-on){display:none!important}`;
  document.head.append(css);
  const key = 'rm.ajustes.aba';
  let active = (() => { try { return sessionStorage.getItem(key) || 'geral'; } catch (e) { return 'geral'; } })();
  let observer = null;
  const group = card => { const title = (card.querySelector('h1,h2,h3,summary')?.textContent || '').trim(); return (GROUPS.find(g => g[2].test(title)) || ['geral'])[0]; };
  function apply(view) {
    if (!view.querySelector(':scope > .aj-tabs')) {
      const tabs = document.createElement('div'); tabs.className = 'aj-tabs'; tabs.setAttribute('role', 'tablist');
      tabs.innerHTML = GROUPS.map(([id, label]) => `<button type="button" role="tab" data-aj-tab="${id}">${label}</button>`).join('');
      (view.querySelector(':scope > .page-h') || view.firstElementChild)?.after(tabs);
      tabs.addEventListener('click', e => { const b = e.target.closest('[data-aj-tab]'); if (!b) return; active = b.dataset.ajTab; try { sessionStorage.setItem(key, active); } catch (error) {} apply(view); });
    }
    view.dataset.aj = '';
    [...view.children].forEach(card => {
      if (card.classList.contains('page-h') || card.classList.contains('aj-tabs')) { card.dataset.ajGroup = ''; return; }
      card.dataset.ajGroup = card.dataset.ajGroup || group(card);
      card.classList.toggle('aj-on', card.dataset.ajGroup === active);
    });
    view.querySelectorAll('[data-aj-tab]').forEach(b => {
      b.setAttribute('aria-selected', String(b.dataset.ajTab === active));
      b.hidden = ![...view.children].some(c => c.dataset.ajGroup === b.dataset.ajTab);
    });
  }
  const previous = routes['/ajustes'];
  routes['/ajustes'] = async (...args) => {
    const result = await previous(...args);
    const view = document.getElementById('view');
    observer?.disconnect();
    apply(view);
    // Cartões que chegam depois (dados carregados em segundo plano) entram no grupo certo.
    observer = new MutationObserver(() => { if (location.hash.startsWith('#/ajustes')) apply(view); else { observer.disconnect(); delete view.dataset.aj; } });
    observer.observe(view, {childList: true});
    return result;
  };
})();
