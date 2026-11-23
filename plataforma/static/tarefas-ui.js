/* Progresso de tarefas, ações de pasta (Abrir / Copiar caminho) e proteção contra clique duplo. Usado no painel e na troca de potes. */
(() => {
 if (window.RMJob) return;
 const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const css = document.createElement('style');
 css.textContent = `
 .rm-progress{border:1px solid var(--line);border-radius:10px;padding:14px;margin:12px 0;background:var(--card,var(--panel,transparent))}
 .rm-progress .rm-phase{font-weight:600;display:flex;align-items:center;gap:8px}
 .rm-progress .rm-detail{color:var(--mute);font-size:13px;margin:4px 0 8px}
 .rm-bar{height:8px;border-radius:4px;background:var(--line);overflow:hidden;position:relative}
 .rm-bar>i{display:block;height:100%;background:var(--acc);width:0;transition:width .3s}
 .rm-bar.rm-indet>i{width:35%;position:absolute;animation:rm-slide 1.3s ease-in-out infinite}
 @keyframes rm-slide{0%{left:-35%}100%{left:100%}}
 .rm-spin{width:14px;height:14px;border:2px solid var(--line);border-top-color:var(--acc);border-radius:50%;animation:rm-rot 1s linear infinite;flex:none}
 @keyframes rm-rot{to{transform:rotate(360deg)}}
 .rm-ok{color:var(--ok)} .rm-err{color:var(--err)}
 .rm-path{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:8px 0}
 .rm-path code{font-family:ui-monospace,Menlo,monospace;font-size:12px;word-break:break-all;background:color-mix(in srgb,var(--line) 45%,transparent);padding:3px 6px;border-radius:6px;flex:1 1 260px}
 .rm-form{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0;display:flex;flex-direction:column;gap:8px}
 .rm-form .rm-check{display:flex;flex-direction:row;align-items:center;gap:8px;font-size:14px;color:inherit}
 .rm-form .rm-row{display:flex;flex-wrap:wrap;gap:12px}
 .rm-form .rm-field{display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--mute);min-width:200px}
 .rm-form input[type=range]{width:100%;accent-color:var(--acc)}
 .rm-note{font-size:12px;color:var(--mute);margin:0}
 [data-rm-busy]{cursor:progress!important;opacity:.6}
 @media (prefers-reduced-motion:reduce){.rm-bar.rm-indet>i,.rm-spin{animation:none}}`;
 document.head.append(css);

 const call = async (path, body) => {
  const r = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  let d = {}; try { d = await r.json(); } catch (e) {}
  if (!r.ok) throw Error(d.erro || ('Erro ' + r.status));
  return d;
 };

 async function copy(text) {
  try { await navigator.clipboard.writeText(text); return true; }
  catch (e) {
   const t = document.createElement('textarea'); t.value = text; t.style.position = 'fixed'; t.style.opacity = '0'; document.body.append(t); t.select();
   const ok = document.execCommand('copy'); t.remove(); return ok;
  }
 }

 /* Caminho real com Abrir pasta e Copiar caminho (macOS e Windows). */
 function pathActions(path, label = 'Abrir pasta') {
  if (!path) return '';
  return `<div class="rm-path"><code>${esc(path)}</code><button type="button" class="ghost btn sm" data-rm-open="${esc(path)}">${esc(label)}</button><button type="button" class="ghost btn sm" data-rm-copy="${esc(path)}">Copiar caminho</button><span role="status" class="rm-detail"></span></div>`;
 }
 document.addEventListener('click', async e => {
  const open = e.target.closest('[data-rm-open]'), cp = e.target.closest('[data-rm-copy]');
  if (!open && !cp) return;
  e.preventDefault();
  const status = (open || cp).parentElement.querySelector('[role=status]');
  try {
   if (open) { await call('/api/ferramentas/abrir', {caminho: open.dataset.rmOpen}); if (status) status.textContent = 'Aberto no ' + (navigator.platform.startsWith('Win') ? 'Explorador' : 'Finder') + '.'; }
   else { const ok = await copy(cp.dataset.rmCopy); if (status) status.textContent = ok ? 'Caminho copiado.' : 'Selecione e copie o caminho acima.'; }
  } catch (error) { if (status) status.textContent = error.message; }
 });

 /* Acompanha uma tarefa: fase, barra (ou animação sem estimativa), cancelar e mensagem final. */
 function watch(job, box, opts = {}) {
  let stopped = false, timer = null;
  const id = typeof job === 'string' ? job : job.id;
  box.hidden = false;
  box.innerHTML = `<div class="rm-progress" aria-live="polite"><div class="rm-phase"><span class="rm-spin"></span><span data-phase>Na fila…</span></div><div class="rm-detail" data-detail></div><div class="rm-bar rm-indet"><i></i></div><div class="row" style="margin-top:10px;gap:8px"><button type="button" class="ghost btn sm" data-cancel>Cancelar</button></div><div data-end></div></div>`;
  const q = s => box.querySelector(s);
  q('[data-cancel]').onclick = async () => { q('[data-cancel]').disabled = true; q('[data-detail]').textContent = 'Cancelando… o que já terminou fica salvo.'; try { await call('/api/ml/job/' + id + '/cancelar', {}); } catch (e) { q('[data-detail]').textContent = e.message; } };
  if (opts.cancel === false) q('[data-cancel]').hidden = true;
  const tick = async () => {
   if (stopped || !box.isConnected) return;
   let j;
   try { j = await call('/api/ml/job/' + id); }
   catch (e) { q('[data-detail]').textContent = 'Consultando o progresso… (' + e.message + ')'; timer = setTimeout(tick, 2500); return; }
   const p = j.progresso || {}, bar = q('.rm-bar');
   q('[data-phase]').textContent = p.fase && j.status === 'executando' ? p.fase : (j.step || 'Processando');
   const known = !p.indeterminado && (j.pct > 0 || (p.total && p.processadas !== undefined));
   bar.classList.toggle('rm-indet', !known && ['na_fila','executando'].includes(j.status));
   if (known) bar.firstElementChild.style.width = Math.round(Math.min(1, j.pct || (p.processadas / p.total)) * 100) + '%';
   q('[data-detail]').textContent = j.status === 'na_fila' ? 'Aguardando outra tarefa terminar.' : (p.fase && j.step !== p.fase ? j.step : '') + (known ? ' · ' + Math.round((j.pct || 0) * 100) + '%' : '');
   if (['na_fila','executando'].includes(j.status)) { timer = setTimeout(tick, 900); return; }
   q('.rm-spin').remove(); q('[data-cancel]').hidden = true; bar.classList.remove('rm-indet');
   if (j.status === 'concluido') {
    bar.firstElementChild.style.width = '100%';
    q('[data-phase]').innerHTML = '<span class="rm-ok">✓ Concluído</span>';
    q('[data-detail]').textContent = j.step && j.step !== 'Concluído' ? j.step : '';
    if (opts.onDone) { try { const html = opts.onDone(j.result, j); if (typeof html === 'string') q('[data-end]').innerHTML = html; } catch (e) { q('[data-end]').textContent = e.message; } }
   } else {
    q('[data-phase]').innerHTML = j.status === 'cancelado' ? 'Cancelado' : '<span class="rm-err">Não foi concluído</span>';
    q('[data-detail]').textContent = j.status === 'cancelado' ? 'Os arquivos que já estavam prontos foram preservados.' : (j.error || 'Erro sem detalhes. Os arquivos foram preservados.');
    if (opts.onError) opts.onError(j);
   }
  };
  tick();
  return { stop() { stopped = true; clearTimeout(timer); } };
 }

 /* Clique duplo: o botão que disparou um envio fica ocupado até a resposta, sem travar o resto da tela. */
 let last = null;
 document.addEventListener('click', e => {
  const b = e.target.closest('button,[role=button],a.btn');
  if (!b) return;
  if (e.isTrusted && b.hasAttribute('data-rm-busy')) { e.preventDefault(); e.stopImmediatePropagation(); return; }
  last = {b, t: performance.now()};
 }, true);
 const nativeFetch = window.fetch.bind(window);
 window.fetch = (input, init = {}) => {
  const method = String(init.method || (input && input.method) || 'GET').toUpperCase();
  const owner = method !== 'GET' && last && performance.now() - last.t < 400 ? last.b : null;
  if (owner) { owner.setAttribute('data-rm-busy', ''); owner.setAttribute('aria-busy', 'true'); last = null; }
  const done = () => { if (owner) { owner.removeAttribute('data-rm-busy'); owner.removeAttribute('aria-busy'); } };
  return nativeFetch(input, init).then(r => { done(); return r; }, e => { done(); throw e; });
 };

 const treatForm = s => `<fieldset class="rm-form"><legend><b>Tratamento</b></legend>
   <label class="rm-check"><input type="checkbox" data-o="silencio" ${s.silencio ? 'checked' : ''}> Remover silêncio excedente no início e no fim (pausas internas ficam)</label>
   <div class="rm-row"><label class="rm-field"><span>Margem antes da fala (ms)</span><input type="number" data-o="margem_inicio_ms" min="20" max="500" step="10" value="${s.margem_inicio_ms}"></label><label class="rm-field"><span>Margem depois da fala (ms)</span><input type="number" data-o="margem_fim_ms" min="50" max="800" step="10" value="${s.margem_fim_ms}"></label></div>
   <p class="rm-note">As margens preservam consoantes, respirações e finais de palavra suaves.</p>
   <label class="rm-check"><input type="checkbox" data-o="ruido" ${s.ruido ? 'checked' : ''}> Reduzir ruído de fundo</label>
   <label class="rm-field"><span>Intensidade da redução: <b data-int>${s.intensidade}</b>%</span><input type="range" data-o="intensidade" min="0" max="100" step="5" value="${s.intensidade}"></label>
   <p class="rm-note">Suave por padrão para não deixar a voz metálica. Redução de ruído não separa voz de música: para isso use a ferramenta Separação de voz e trilha.</p></fieldset>`;
 const readTreat = root => { const o = {}; root.querySelectorAll('[data-o]').forEach(i => o[i.dataset.o] = i.type === 'checkbox' ? i.checked : Number(i.value)); return o; };
 document.addEventListener('input', e => { if (e.target.matches('[data-o=intensidade]')) { const s = e.target.closest('fieldset').querySelector('[data-int]'); if (s) s.textContent = e.target.value; } });
 window.RMJob = { watch, pathActions, copy, call, esc, treatForm, readTreat };
})();
