/* Ripagem Maker — interface (vanilla JS, sem dependências externas) */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = t => { t = Math.max(0, t || 0); const m = Math.floor(t / 60), s = t - m * 60; return `${String(m).padStart(2, "0")}:${s.toFixed(2).padStart(5, "0")}`; };
const fmtS = t => `${(t || 0).toFixed(1)} s`;
const api = async (path, opt = {}) => {
  const r = await fetch(path, { headers: opt.body && typeof opt.body === "string" ? { "Content-Type": "application/json" } : {}, ...opt });
  let d = {}; try { d = await r.json(); } catch (e) { }
  if (!r.ok) throw new Error(d.erro || `Erro ${r.status}`);
  return d;
};
const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body || {}) });
function toast(msg, err) { const t = document.createElement("div"); t.className = "toast" + (err ? " err" : ""); t.textContent = msg; $("#toasts").append(t); setTimeout(() => t.remove(), err ? 7000 : 3500); }
const ls = { get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; } }, set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { } } };

const STATUS = {
  na_fila: ["Na fila", "run"], analisando: ["Analisando", "run"], executando: ["Processando", "run"], pronto: ["Pronto", "ok"],
  concluido: ["Concluído", "ok"], erro: ["Erro", "err"], cancelado: ["Cancelado", "warn"], sem_audio: ["Sem áudio", "warn"],
  precisa_confirmar: ["Confirme o corte", "warn"], sem_corte: ["Sem corte possível", "err"], enviado: ["Na fila", "run"]
};
const chip = s => { const [t, c] = STATUS[s] || [s, ""]; return `<span class="chip ${c}">${esc(t)}</span>`; };

const S = { videos: [], views: {}, lead: ls.get("ml.lead", null), body: ls.get("ml.body", null), cuts: {}, job: null, sys: null, rules: null, batch: ls.get("ml.batch", null) };
let pollTimer = null;

/* ======================================================================= roteador */
const routes = { "/": viewHome, "/microlead": viewMicrolead, "/lote": viewBatch, "/regras": viewRules };
async function render() {
  const r = location.hash.replace(/^#/, "").split("?")[0] || "/";
  $$(".nav a[data-r]").forEach(a => a.classList.toggle("on", a.dataset.r === (r==='/regras'?'/ajustes':r==='/microlead'?'/demanda':r)));
  clearInterval(pollTimer);
  try { await (routes[r] || viewHome)(); }
  catch (e) { $("#view").innerHTML = `<div class="banner err" role="alert"><b>O app local não respondeu.</b><span>${esc(e.message)} — confira se o Ripagem Maker está aberto e recarregue a página.</span></div>`; }
}
window.addEventListener("hashchange", render);

async function loadSys() {
  try {
    S.sys = await api("/api/sistema");
    const ok = S.sys.motor_padrao;
    $("#sys").innerHTML = `<span class="dot" style="background:${ok ? "var(--ok)" : "var(--err)"}"></span>${ok ? "Pronto para editar" : "Transcrição local indisponível"}<details class="clean-system-details"><summary>Sobre o processamento</summary><p>Edição local · transcrição e vozes externas opcionais.</p><p>Whisper ${S.sys.motor_padrao === "mlx" ? "MLX (GPU)" : "faster-whisper (CPU)"} · FFmpeg ${esc((S.sys.ffmpeg.match(/version (\S+)/) || [])[1] || "")}</p></details>`;
  } catch (e) { $("#sys").textContent = "Servidor local fora do ar"; }
}

/* ======================================================================= painel */
async function viewHome() {
  const jobs = await api("/api/ml/jobs").catch(() => []);
  const done = jobs.filter(j => j.status === "concluido" && j.kind === "render" && j.result?.arquivo && !(j.params?.spec?.opcoes?.previa)).slice(0, 6);
  $("#view").innerHTML = `
    <div class="page-h"><div><h1>Painel</h1><p>Ferramentas de edição para VSL, troca de potes e variações de criativos.</p></div>
      <span class="chip local">● Montagem local · serviços de voz opcionais</span></div>
    <section class="card home-start"><div><span class="chip lead">Fluxo principal</span><h2>Trocar potes do começo ao fim</h2><p>Arquivo → transcrição → falas → takes → entrega para o Premiere.</p><p class="small mute">Reabra um trabalho salvo para continuar com as transcrições, vozes e escolhas existentes.</p></div><a class="btn pri" href="/fatiador">Abrir troca de potes →</a></section>
    <section id="home-active" class="card" aria-live="polite" hidden></section>
    <div class="tools">
      <a class="card tool" href="#/demanda"><div class="ti">↔</div><h3>Microlead’s</h3><p>Receba a demanda, combine as fontes e entregue novas aberturas em vídeo ou XML.</p></a>
      <a class="card tool" href="#/nomes"><div class="ti">Aa</div><h3>Nomenclatura VTurb</h3><p>Padronize nomes de VSL, versões, microleads e ofertas.</p></a>
      <a class="card tool" href="#/ajustes"><div class="ti">⚙</div><h3>Ajustes</h3><p>Integrações, pastas, transcrição, regras de corte e manutenção.</p></a>
    </div>
    <div class="card" style="margin-top:18px"><h2>Últimos vídeos gerados</h2>
      ${done.length ? `<table class="t"><tr><th>Vídeo</th><th>Duração</th><th>Modo</th><th></th></tr>${done.map(j => `<tr><td>${esc(j.result.arquivo)}</td><td class="mono">${fmtS(j.result.duracao_s)}</td><td class="small">${j.result.copiou_fluxos ? "copiado sem recodificar" : "recodificado"}</td>
        <td style="text-align:right"><a class="btn sm" href="/media/out/${encodeURIComponent(j.result.arquivo)}" target="_blank">Assistir</a> <a class="btn sm" href="/media/out/${encodeURIComponent(j.result.arquivo)}?dl=1">Baixar</a></td></tr>`).join("")}</table>`
      : `<div class="empty">Nenhum vídeo gerado ainda nesta sessão.</div>`}</div>`;
  let updating=false,lastJobs='';
  const showActive=list=>{const node=$('#home-active');if(!node)return;const active=list.filter(j=>['na_fila','executando'].includes(j.status));node.hidden=!active.length;const html=active.length?'<h2>Em andamento · '+active.length+' tarefa(s)</h2>'+active.slice(0,4).map(j=>`<div class="home-job"><div class="row"><b>${esc(j.title)}</b><span class="sp"></span>${chip(j.status)}</div><p class="small mute">${esc(j.step||'Aguardando início')}</p><div class="bar ${j.status==='na_fila'||!j.pct?'ind':''}"><i style="width:${Math.round((j.pct||0)*100)}%"></i></div></div>`).join(''):'';if(html!==lastJobs){node.innerHTML=html;lastJobs=html;}return active.length;};
  if(showActive(jobs))pollTimer=setInterval(async()=>{if(updating||document.hidden||!$('#home-active'))return;updating=true;try{if(!showActive(await api('/api/ml/jobs')))clearInterval(pollTimer);}catch(e){/* Keep the last known status on a temporary disconnect. */}finally{updating=false;}},3000);

}

/* ======================================================================= biblioteca de vídeos */
async function refreshVideos() { S.videos = await api("/api/ml/videos"); return S.videos; }
const vById = id => S.videos.find(v => v.id === id);

function libraryHTML() {
  const motor = ls.get("ml.motor", S.sys?.motor_padrao || "mlx"), idioma = ls.get("ml.idioma", "auto");
  return `<div class="card"><h2>1 · Vídeos <span class="chip local">transcrição local</span></h2>
    <div class="drop" id="drop" tabindex="0" role="button" aria-label="Enviar vídeos"><b>Arraste os vídeos aqui</b><span class="mute">ou clique para escolher — pode enviar vários de uma vez (mp4, mov, m4v, webm)</span></div>
    <input type="file" id="fileIn" multiple accept="video/*" class="sr">
    <div class="row" style="margin-top:10px">
      <label class="f">Motor de transcrição<select id="motor">
        <option value="mlx" ${motor === "mlx" ? "selected" : ""}>Whisper MLX · GPU do Mac (recomendado)</option>
        <option value="fw" ${motor === "fw" ? "selected" : ""}>faster-whisper · CPU</option></select></label>
      <label class="f">Idioma<select id="idioma">${[["auto", "Detectar"], ["en", "Inglês"], ["pt", "Português"], ["es", "Espanhol"]].map(([v, t]) => `<option value="${v}" ${idioma === v ? "selected" : ""}>${t}</option>`).join("")}</select></label>
      <span class="sp"></span><span class="small mute">Nada é enviado para a internet: o áudio é transcrito neste computador.</span>
    </div>
    <div id="upl"></div>
    <div class="vlist" id="vlist"></div></div>`;
}

function vcardHTML(v) {
  const p = v.probe || {}, busy = ["na_fila", "analisando", "executando"].includes(v.status);
  const isL = S.lead === v.id, isB = S.body === v.id;
  return `<div class="vcard ${isL ? "is-lead" : ""} ${isB ? "is-body" : ""}">
    <div class="row"><div class="nm sp" title="${esc(v.nome)}">${esc(v.nome)}</div>${chip(v.status)}</div>
    <div class="small mute mono">${p.duracao ? fmt(p.duracao) : "—"} · ${p.largura ? `${p.largura}×${p.altura}` : ""} ${p.fps ? `· ${p.fps} fps` : ""} ${p.tem_audio === false ? "· sem áudio" : ""}</div>
    ${busy ? `<div class="bar ${v.pct ? "" : "ind"}"><i style="width:${Math.round((v.pct || 0) * 100)}%"></i></div><div class="small mute">${esc(v.step || "")}</div>` : ""}
    ${v.status === "erro" || v.status === "cancelado" ? `<div class="small" style="color:var(--err)">${esc(v.error || v.step || "")}</div>` : ""}
    <div class="row">
      <button class="btn sm lead ${isL ? "on" : ""}" data-act="lead" data-id="${v.id}" ${v.status !== "pronto" ? "disabled" : ""} aria-pressed="${isL}">Microlead</button>
      <button class="btn sm body ${isB ? "on" : ""}" data-act="body" data-id="${v.id}" ${v.status !== "pronto" ? "disabled" : ""} aria-pressed="${isB}">Body</button>
      <span class="sp"></span>
      ${busy ? `<button class="btn sm ghost" data-act="cancel" data-job="${v.job}" title="Cancelar análise">Cancelar</button>` : `<button class="btn sm ghost" data-act="re" data-id="${v.id}" title="Transcrever de novo">↻</button>`}
      <button class="btn sm ghost danger" data-act="del" data-id="${v.id}" aria-label="Remover ${esc(v.nome)}">✕</button>
    </div></div>`;
}

function bindLibrary(onChange) {
  const drop = $("#drop"), inp = $("#fileIn");
  drop.onclick = () => inp.click(); drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inp.click(); } };
  ["dragover", "dragenter"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", e => upload([...e.dataTransfer.files]));
  inp.onchange = () => upload([...inp.files]);
  $("#motor").onchange = e => ls.set("ml.motor", e.target.value);
  $("#idioma").onchange = e => ls.set("ml.idioma", e.target.value);
  $("#vlist").onclick = async e => {
    const b = e.target.closest("button[data-act]"); if (!b) return;
    const { act, id, job } = b.dataset;
    if (act === "lead") { S.lead = S.lead === id ? null : id; if (S.body === S.lead) S.body = null; ls.set("ml.lead", S.lead); ls.set("ml.body", S.body); }
    if (act === "body") { S.body = S.body === id ? null : id; if (S.lead === S.body) S.lead = null; ls.set("ml.body", S.body); ls.set("ml.lead", S.lead); }
    if (act === "cancel") await post(`/api/ml/job/${job}/cancelar`);
    if (act === "re") { await post(`/api/ml/video/${id}/reanalisar`, { motor: $("#motor").value, idioma: $("#idioma").value }); delete S.views[id]; }
    if (act === "del") { if (!confirm("Remover este vídeo da biblioteca? (o arquivo original no seu disco não é apagado)")) return; await post(`/api/ml/video/${id}/excluir`); if (S.lead === id) S.lead = null; if (S.body === id) S.body = null; }
    await refreshVideos(); onChange();
  };
}

async function upload(files) {
  files = files.filter(f => /video|quicktime|mp4|mov|m4v|webm|mkv/i.test(f.type + f.name));
  if (!files.length) return toast("Envie arquivos de vídeo.", true);
  for (const f of files) {
    const id = "u" + Math.random().toString(36).slice(2);
    $("#upl").insertAdjacentHTML("beforeend", `<div class="row small" id="${id}" style="margin-top:8px"><span class="sp">${esc(f.name)}</span><span class="mono" data-p>0%</span><div class="bar" style="width:160px"><i style="width:0"></i></div></div>`);
    await new Promise(res => {
      const x = new XMLHttpRequest(); x.open("POST", "/api/ml/upload");
      x.setRequestHeader("X-Filename", encodeURIComponent(f.name)); x.setRequestHeader("X-Motor", $("#motor").value); x.setRequestHeader("X-Idioma", $("#idioma").value);
      x.upload.onprogress = e => { if (e.lengthComputable) { const p = Math.round(e.loaded / e.total * 100); $(`#${id} [data-p]`).textContent = p + "%"; $(`#${id} i`).style.width = p + "%"; } };
      x.onload = () => { $(`#${id}`)?.remove(); if (x.status !== 200) toast(`Falha ao enviar ${f.name}`, true); res(); };
      x.onerror = () => { $(`#${id}`)?.remove(); toast("O app local não está respondendo.", true); res(); };
      x.send(f);
    });
    await refreshVideos(); drawLibrary();
  }
}
function drawLibrary() {
  const el = $("#vlist"); if (!el) return;
  el.innerHTML = S.videos.length ? S.videos.map(vcardHTML).join("") : `<div class="empty" style="grid-column:1/-1">Envie pelo menos dois vídeos: um para a microlead e outro para o body.</div>`;
}

/* ======================================================================= timeline */
class Timeline {
  constructor(el, opt) { Object.assign(this, opt); this.el = el; this.v0 = 0; this.v1 = Math.min(opt.dur, opt.initialSpan || opt.dur); this.draw(); }
  x(t) { return (t - this.v0) / (this.v1 - this.v0) * 100; }
  zoom(a, b) { this.v0 = Math.max(0, a); this.v1 = Math.min(this.dur, b); if (this.v1 - this.v0 < 2) this.v1 = Math.min(this.dur, this.v0 + 2); this.draw(); }
  draw() {
    const { role, dur, cut } = this, end = this.bodyEnd ?? dur;
    const regs = role === "lead" ? [["lead", 0, cut], ["disc", cut, dur]] : [["disc", 0, cut], ["body", cut, end], ["disc", end, dur]];
    const vis = (a, b) => b > this.v0 && a < this.v1;
    const box = (a, b) => `left:${this.x(Math.max(a, this.v0))}%;width:${this.x(Math.min(b, this.v1)) - this.x(Math.max(a, this.v0))}%`;
    const best = this.cands[0]?.t;
    this.el.innerHTML = `
      <div class="tl-zoom"><span class="small mute">Zoom</span>
        <button class="btn sm" data-z="all">Tudo</button><button class="btn sm" data-z="2m">0–2 min</button><button class="btn sm" data-z="cut">±15 s do corte</button>
        <span class="sp"></span><span class="small mono mute">${fmt(this.v0)} – ${fmt(this.v1)}</span></div>
      <div class="tl-track" role="group" aria-label="Linha do tempo">
        ${regs.filter(r => vis(r[1], r[2])).map(r => `<div class="tl-reg ${r[0]}" style="${box(r[1], r[2])}"></div>`).join("")}
        ${this.sil.filter(s => vis(s.s, s.e)).map(s => `<div class="tl-sil" style="${box(s.s, s.e)}" title="silêncio"></div>`).join("")}
        ${this.sents.filter(s => s.s > this.v0 && s.s < this.v1).map(s => `<div class="tl-tick" style="left:${this.x(s.s)}%"></div>`).join("")}
        ${this.cands.filter(c => c.t > this.v0 && c.t < this.v1).map((c, i) => `<div class="tl-cand ${c.t === best ? "best" : ""}" data-c="${this.cands.indexOf(c)}" style="left:${this.x(c.t)}%" title="Opção: ${fmt(c.t)} · ${c.pontos} pontos"></div>`).join("")}
        <div class="tl-play" style="left:${this.x(this.play || 0)}%;${(this.play || 0) < this.v0 || (this.play || 0) > this.v1 ? "display:none" : ""}"></div>
        <div class="tl-cut" role="slider" tabindex="0" aria-label="Ponto de corte" aria-valuemin="0" aria-valuemax="${dur.toFixed(2)}" aria-valuenow="${cut.toFixed(2)}" aria-valuetext="${fmt(cut)}" style="left:${this.x(cut)}%;${cut < this.v0 || cut > this.v1 ? "display:none" : ""}"></div>
      </div>
      <div class="tl-axis"><span>${fmt(this.v0)}</span><span>${fmt((this.v0 + this.v1) / 2)}</span><span>${fmt(this.v1)}</span></div>`;
    const track = $(".tl-track", this.el), handle = $(".tl-cut", this.el);
    const tAt = e => { const r = track.getBoundingClientRect(); return this.v0 + Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * (this.v1 - this.v0); };
    track.onclick = e => { if (e.target.closest(".tl-cut")) return; const c = e.target.closest(".tl-cand"); if (c) return this.onCut(this.cands[+c.dataset.c][this.role === "lead" ? "fim_lead" : "inicio_body"], true); this.onSeek(tAt(e)); };
    handle.onpointerdown = e => {
      handle.setPointerCapture(e.pointerId);
      handle.onpointermove = ev => { this.cut = tAt(ev); handle.style.left = this.x(this.cut) + "%"; handle.setAttribute("aria-valuetext", fmt(this.cut)); };
      handle.onpointerup = () => { handle.onpointermove = null; this.onCut(this.snap(this.cut)); };
    };
    handle.onkeydown = e => {
      if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return; e.preventDefault();
      const pts = this.points.map(p => this.cutFor(p)), dir = e.key === "ArrowRight" ? 1 : -1;
      const nx = dir > 0 ? pts.find(t => t > this.cut + 0.02) : [...pts].reverse().find(t => t < this.cut - 0.02);
      if (nx != null) this.onCut(nx);
    };
    $$("[data-z]", this.el).forEach(b => b.onclick = () => { const z = b.dataset.z; if (z === "all") this.zoom(0, dur); else if (z === "2m") this.zoom(0, 120); else this.zoom(this.cut - 15, this.cut + 15); });
  }
  cutFor(p) { return this.role === "lead" ? p.e + Math.min(this.padOut, p.gap / 2) : p.s - Math.min(this.padIn, p.gap / 2); }
  snap(t) { if (!this.points.length) return t; const p = this.points.reduce((a, b) => Math.abs((b.e + b.s) / 2 - t) < Math.abs((a.e + a.s) / 2 - t) ? b : a); return this.cutFor(p); }
  setPlay(t) { this.play = t; const p = $(".tl-play", this.el); if (p) { p.style.left = this.x(t) + "%"; p.style.display = t < this.v0 || t > this.v1 ? "none" : ""; } }
}

/* ======================================================================= editor microlead + body */
async function getView(id, force) { if (!S.views[id] || force) S.views[id] = await api(`/api/ml/video/${id}`); return S.views[id]; }

async function viewMicrolead() {
  if (!S.sys) await loadSys();
  await refreshVideos();
  if (S.lead && !vById(S.lead)) S.lead = null; if (S.body && !vById(S.body)) S.body = null;
  const step = !S.videos.length ? 0 : !(S.lead && S.body) ? 1 : 2;
  $("#view").innerHTML = `
    <div class="page-h"><div><h1>Microlead’s</h1><p>A microlead de um vídeo seguida pelo body de outro, num arquivo novo.</p></div>
      <span class="chip local">● processado neste computador</span></div>
    <div class="steps" aria-label="Etapas">${["Enviar vídeos", "Escolher microlead e body", "Revisar cortes", "Montar e exportar"].map((t, i) => `<span class="${i === step ? "on" : i < step ? "done" : ""}">${i + 1}. ${t}</span>`).join("")}</div>
    ${libraryHTML()}
    <div id="editor" style="margin-top:18px"></div>`;
  drawLibrary();
  bindLibrary(() => { drawLibrary(); drawEditor(); });
  drawEditor();
  pollTimer = setInterval(async () => {
    const before = JSON.stringify(S.videos.map(v => [v.id, v.status, Math.round((v.pct || 0) * 50)]));
    await refreshVideos();
    if (JSON.stringify(S.videos.map(v => [v.id, v.status, Math.round((v.pct || 0) * 50)])) !== before) { drawLibrary(); if (S.videos.some(v => (v.id === S.lead || v.id === S.body))) drawEditor(true); }
  }, 1500);
}

let TL = {};
async function drawEditor(soft) {
  const el = $("#editor"); if (!el) return;
  const L = vById(S.lead), B = vById(S.body);
  if (!L || !B) { el.innerHTML = `<div class="card"><h2>2 · Escolha os papéis</h2><div class="empty">Marque um vídeo como <span class="chip lead">Microlead</span> e outro como <span class="chip body">Body</span> na lista acima. Os vídeos precisam estar com status <span class="chip ok">Pronto</span>.</div></div>`; return; }
  if (soft && el.dataset.k === `${L.id}|${B.id}`) return;
  el.dataset.k = `${L.id}|${B.id}`;
  $$(".steps span").forEach((x, i) => { x.className = i === 2 ? "on" : i < 2 ? "done" : ""; });
  el.innerHTML = `<div class="empty">Carregando a análise…</div>`;
  const [vl, vb] = await Promise.all([getView(L.id), getView(B.id)]);
  const initCut = (v, role) => { const k = role === "lead" ? "fim_lead" : "inicio_body"; return v.meta.confirmado?.[k] ?? v.candidatos[0]?.[k] ?? (role === "lead" ? Math.min(30, v.meta.probe.duracao) : 0); };
  if (S.cuts.leadId !== L.id) { S.cuts.lead = initCut(vl, "lead"); S.cuts.leadId = L.id; }
  if (S.cuts.bodyId !== B.id) { S.cuts.body = initCut(vb, "body"); S.cuts.bodyId = B.id; S.cuts.bodyEnd = vb.meta.confirmado?.fim_body ?? null; }
  el.innerHTML = `
    <div class="grid g2">
      ${panelHTML("lead", vl)}
      ${panelHTML("body", vb)}
    </div>
    <div class="card" style="margin-top:18px" id="assemble"></div>`;
  for (const [role, v] of [["lead", vl], ["body", vb]]) bindPanel(role, v);
  drawAssemble();
}

function panelHTML(role, v) {
  const d = v.decisao, cls = { confiavel: "ok", confirmar: "warn", sem_opcoes: "err" }[d.status];
  const title = role === "lead" ? "Microlead" : "Body";
  return `<div class="card ed ${role === "body" ? "body-ed" : ""}" id="p-${role}">
    <h2><span class="chip ${role}">${title}</span> <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(v.meta.nome)}</span><span class="sp"></span><span class="small mute mono">${fmt(v.meta.probe.duracao)}</span></h2>
    <video id="vid-${role}" src="/media/v/${v.meta.id}" controls preload="metadata"></video>
    <div class="banner ${cls}" role="status"><b>${d.status === "confiavel" ? "Corte sugerido" : d.status === "confirmar" ? "Confirme o corte" : "Sem sugestão"}</b><span>${esc(d.msg)}</span></div>
    <div class="tl" id="tl-${role}"></div>
    <div class="legend"><span><i style="background:var(--${role === "lead" ? "lead" : "body"}-reg)"></i>${role === "lead" ? "fica (microlead)" : "fica (body)"}</span><span><i style="background:repeating-linear-gradient(135deg,var(--disc-soft) 0 3px,transparent 3px 6px);border:1px solid var(--line)"></i>descartado</span><span><i style="background:var(--line-2)"></i>silêncio</span><span><i style="background:var(--cand)"></i>opção sugerida</span></div>
    <div class="row" style="margin-top:10px">
      <label class="f">${role === "lead" ? "Microlead termina em" : "Body começa em"}<input type="text" class="mono" id="cut-${role}" size="9" aria-describedby="cuthint-${role}"></label>
      <button class="btn sm" data-nudge="-1" title="Corte na pausa anterior">← pausa</button><button class="btn sm" data-nudge="1" title="Corte na próxima pausa">pausa →</button>
      <button class="btn sm" data-listen>▶ Ouvir o corte</button>
      <span class="sp"></span><button class="btn sm" data-confirm title="Guarda este corte para usar no lote">Confirmar corte</button>
    </div>
    ${role === "body" ? `<div class="row" style="margin-top:8px"><label class="f">Body termina em<input type="text" class="mono" id="end-body" size="9" placeholder="até o fim"></label><span class="small mute" style="align-self:end">deixe vazio para ir até o fim do vídeo</span></div>` : ""}
    <div class="small mute" id="cuthint-${role}" style="margin-top:6px">Arraste o marcador preto, clique num losango laranja ou use ← → no marcador para pular entre pausas. O corte nunca cai no meio de uma palavra.</div>
    <h2 style="margin-top:14px;font-size:13.5px">Opções que as regras encontraram</h2>
    <div class="cuts" id="cands-${role}"></div>
    <h2 style="margin-top:14px;font-size:13.5px">Transcrição <span class="small mute">(clique para ir ao trecho)</span></h2>
    <div class="tr" id="tr-${role}"></div></div>`;
}

function bindPanel(role, v) {
  const key = role === "lead" ? "fim_lead" : "inicio_body";
  const vid = $(`#vid-${role}`), dur = v.meta.probe.duracao;
  const tl = TL[role] = new Timeline($(`#tl-${role}`), {
    role, dur, cut: S.cuts[role], bodyEnd: role === "body" ? S.cuts.bodyEnd : null, sil: v.silencios, sents: v.frases, cands: v.candidatos,
    points: v.pontos, padOut: v.regras.folga_fim_lead_ms / 1000, padIn: v.regras.folga_inicio_body_ms / 1000,
    initialSpan: Math.min(dur, Math.max(120, (S.cuts[role] || 0) + 30)),
    onSeek: t => { vid.currentTime = t; }, onCut: (t, fromCand) => setCut(role, t, fromCand)
  });
  vid.ontimeupdate = () => tl.setPlay(vid.currentTime);
  $(`#cut-${role}`).value = fmt(S.cuts[role]);
  $(`#cut-${role}`).onchange = e => { const m = e.target.value.match(/(?:(\d+):)?(\d+(?:[.,]\d+)?)/); if (!m) return toast("Use o formato mm:ss.cc", true); setCut(role, tl.snap((+(m[1] || 0)) * 60 + parseFloat(m[2].replace(",", ".")))); };
  $$(`#p-${role} [data-nudge]`).forEach(b => b.onclick = () => {
    const d = +b.dataset.nudge, cur = S.cuts[role], pts = tl.points.map(p => tl.cutFor(p));
    const t = d > 0 ? pts.find(x => x > cur + 0.02) : [...pts].reverse().find(x => x < cur - 0.02);
    if (t != null) setCut(role, t);
  });
  $(`#p-${role} [data-listen]`).onclick = () => listen(role);
  $(`#p-${role} [data-confirm]`).onclick = async () => {
    const body = { [key]: +S.cuts[role].toFixed(3) }; if (role === "body") body.fim_body = S.cuts.bodyEnd;
    await post(`/api/ml/video/${v.meta.id}/confirmar`, body); v.meta.confirmado = { ...(v.meta.confirmado || {}), ...body };
    toast(`Corte confirmado em ${fmt(S.cuts[role])}. O lote vai usar este corte.`);
  };
  if (role === "body") $("#end-body").onchange = e => { const t = e.target.value.trim(); const m = t.match(/(?:(\d+):)?(\d+(?:[.,]\d+)?)/); S.cuts.bodyEnd = t && m ? (+(m[1] || 0)) * 60 + parseFloat(m[2].replace(",", ".")) : null; tl.bodyEnd = S.cuts.bodyEnd; tl.draw(); drawAssemble(); };
  drawCands(role, v); drawTranscript(role, v);
}

function setCut(role, t, fromCand) {
  const v = S.views[role === "lead" ? S.lead : S.body], dur = v.meta.probe.duracao;
  t = Math.min(Math.max(0, t), dur);
  S.cuts[role] = +t.toFixed(3);
  const tl = TL[role]; tl.cut = S.cuts[role]; tl.draw();
  $(`#cut-${role}`).value = fmt(S.cuts[role]);
  drawCands(role, v); drawTranscript(role, v); drawAssemble();
  if (fromCand) toast(`Corte em ${fmt(t)}.`);
}

function drawCands(role, v) {
  const key = role === "lead" ? "fim_lead" : "inicio_body";
  $(`#cands-${role}`).innerHTML = v.candidatos.length ? v.candidatos.slice(0, 5).map((c, i) => `
    <div class="cand ${Math.abs(c[key] - S.cuts[role]) < 0.02 ? "sel" : ""}">
      <span class="sc" title="pontos">${c.pontos}</span>
      <div><div><b class="mono">${fmt(c[key])}</b> · pausa ${c.gap.toFixed(2)} s</div>
        <div class="small">“…${esc(c.antes.slice(-55))}” <span class="mute">|</span> “${esc(c.depois.slice(0, 55))}…”</div>
        <div class="why">${c.motivos.map(esc).join(" · ")}</div></div>
      <button class="btn sm" data-use="${i}">Usar</button></div>`).join("") : `<div class="empty">Nenhuma opção encontrada pelas regras. Defina o corte manualmente na timeline.</div>`;
  $$(`#cands-${role} [data-use]`).forEach(b => b.onclick = () => setCut(role, v.candidatos[+b.dataset.use][key], true));
}

function drawTranscript(role, v) {
  const cut = S.cuts[role], end = S.cuts.bodyEnd ?? Infinity;
  const tags = s => [...s.marcas.gancho.map(x => `<span class="chip">gancho</span>`).slice(0, 1), ...s.marcas.fim_lead.map(x => `<span class="chip warn">fim de lead</span>`).slice(0, 1), ...s.marcas.transicao.map(x => `<span class="chip run">abertura</span>`).slice(0, 1)].join("");
  $(`#tr-${role}`).innerHTML = v.frases.map(s => {
    const mid = (s.s + s.e) / 2;
    const cls = role === "lead" ? (mid < cut ? "lead" : "disc") : (mid > cut && mid < end ? "body" : "disc");
    return `<div class="s ${cls}" data-t="${s.s}"><span class="t">${fmt(s.s)}</span><span>${esc(s.texto)}</span>
      <span class="mk">${tags(s)}<button class="btn sm ghost cut-here" data-cuthere="${s.i}" title="${role === "lead" ? "Terminar a microlead depois desta frase" : "Começar o body nesta frase"}">✂ aqui</button></span></div>`;
  }).join("");
  $(`#tr-${role}`).onclick = e => {
    const c = e.target.closest("[data-cuthere]"), vid = $(`#vid-${role}`);
    if (c) { const s = v.frases[+c.dataset.cuthere]; const t = role === "lead" ? TL.lead.snap(s.e + 0.01) : TL.body.snap(s.s - 0.01); return setCut(role, t, true); }
    const row = e.target.closest("[data-t]"); if (row) { vid.currentTime = +row.dataset.t; vid.play(); }
  };
}

function listen(role) {
  const vid = $(`#vid-${role}`), cut = S.cuts[role];
  const [a, b] = role === "lead" ? [Math.max(0, cut - 3), cut] : [cut, cut + 4];
  vid.currentTime = a; vid.play();
  const stop = () => { if (vid.currentTime >= b) { vid.pause(); return; } if (!vid.paused) requestAnimationFrame(stop); };
  requestAnimationFrame(stop);
}

function opts() {
  const o = ls.get("ml.opts", { modo: "auto", formato: "mp4", resolucao: "body", fade_ms: 20 });
  return o;
}
function drawAssemble() {
  const el = $("#assemble"); if (!el) return;
  const vl = S.views[S.lead], vb = S.views[S.body]; if (!vl || !vb) return;
  const ld = S.cuts.lead, bs = S.cuts.body, be = S.cuts.bodyEnd ?? vb.meta.probe.duracao, bd = Math.max(0, be - bs), tot = ld + bd;
  const o = opts();
  el.innerHTML = `<h2>4 · Montar e exportar</h2>
    <div class="sum" aria-label="Composição do vídeo final"><div class="l" style="width:${ld / tot * 100}%">Microlead ${fmtS(ld)}</div><div class="b" style="width:${bd / tot * 100}%">Body ${fmtS(bd)}</div></div>
    <div class="small mute" style="margin:-6px 0 12px">${esc(vl.meta.nome)} 00:00 → ${fmt(ld)} &nbsp;+&nbsp; ${esc(vb.meta.nome)} ${fmt(bs)} → ${fmt(be)} &nbsp;=&nbsp; <b>${fmt(tot)}</b></div>
    <div class="row">
      <label class="f">Entrega<select id="o-entrega"><option value="video">Vídeo pronto</option><option value="xml">Somente XML para Premiere</option><option value="ambos">Vídeo + XML</option></select></label><label class="f">Processamento<select id="o-modo">
        <option value="auto">Automático — copia sem recodificar quando der</option><option value="exato">Exato — recodifica (x264, máxima qualidade)</option>
        <option value="rapido">Rápido — recodifica no hardware do Mac</option><option value="copiar">Só copiar — falha se não for possível</option></select></label>
      <label class="f">Formato<select id="o-formato"><option value="mp4">MP4 H.264 — publicação</option><option value="mov">MOV ProRes 422 HQ — edição</option></select></label>
      <label class="f">Resolução<select id="o-res"><option value="body">igual ao body</option><option value="lead">igual à microlead</option><option value="1080x1920">1080×1920 (9:16)</option><option value="1920x1080">1920×1080 (16:9)</option><option value="1080x1080">1080×1080 (1:1)</option><option value="720x1280">720×1280</option></select></label>
      <label class="f">Suavizar emenda (ms)<input type="number" id="o-fade" min="0" max="200" step="5" style="width:90px"></label>
    </div>
    <div class="row" style="margin-top:14px">
      <button class="btn" id="b-prev">Prévia da emenda</button>
      <button class="btn pri" id="b-go">Gerar entrega</button>
      <span class="sp"></span><span class="small mute">XML = sequência editável de ML + body com cortes secos e fontes locais (sem fades). Importe com ⌘I no Premiere. Prévia = 4 s de cada lado, em baixa resolução, para ouvir a emenda rápido.</span>
    </div>
    <div id="job" style="margin-top:14px"></div>`;
  $("#o-entrega").value = o.entrega || "video"; $("#o-modo").value = o.modo; $("#o-formato").value = o.formato; $("#o-res").value = o.resolucao; $("#o-fade").value = o.fade_ms;
  ["o-entrega", "o-modo", "o-formato", "o-res", "o-fade"].forEach(id => $("#" + id).onchange = () => ls.set("ml.opts", { entrega: $("#o-entrega").value, modo: $("#o-modo").value, formato: $("#o-formato").value, resolucao: $("#o-res").value, fade_ms: +$("#o-fade").value }));
  $("#b-prev").onclick = () => startRender(true);
  $("#b-go").onclick = () => startRender(false);
  const saveDelivery=$("#o-entrega").onchange;
  $("#o-entrega").onchange=()=>{saveDelivery();for(const id of ['o-modo','o-formato','o-res','o-fade'])$('#'+id).disabled=$('#o-entrega').value==='xml';};
  for(const id of ['o-modo','o-formato','o-res','o-fade'])$('#'+id).disabled=$('#o-entrega').value==='xml';
  if (S.job) drawJob();
}

async function startRender(preview) {
  const o = opts();
  const spec = { lead: { video: S.lead, inicio: 0, fim: S.cuts.lead }, body: { video: S.body, inicio: S.cuts.body, fim: S.cuts.bodyEnd }, opcoes: { ...o, previa: preview } };
  try { S.job = await post("/api/ml/montar", spec); drawJob(); pollJob(); } catch (e) { toast(e.message, true); }
}
async function pollJob() {
  if (!S.job) return;
  S.job = await api(`/api/ml/job/${S.job.id}`); drawJob();
  if (["na_fila", "executando"].includes(S.job.status)) setTimeout(pollJob, 600);
}
function drawJob() {
  const j = S.job, el = $("#job"); if (!el || !j) return;
  const busy = ["na_fila", "executando"].includes(j.status), r = j.result, prev = j.params?.spec?.opcoes?.previa;
  el.innerHTML = `<div class="card" style="background:var(--panel-2)">
    <div class="row"><b>${prev ? "Prévia da emenda" : "Vídeo final"}</b>${chip(j.status)}<span class="sp"></span>
      ${busy ? `<button class="btn sm" id="j-cancel">Cancelar</button>` : `<button class="btn sm" id="j-redo">Refazer</button>`}</div>
    ${busy ? `<div class="bar" style="margin:10px 0 6px"><i style="width:${Math.round(j.pct * 100)}%"></i></div><div class="small mute">${esc(j.step)} · ${Math.round(j.pct * 100)}% · processando localmente</div>` : ""}
    ${j.status === "erro" ? `<div class="banner err">${esc(j.error)}</div>` : ""}
    ${r?.arquivo ? `<div class="grid g2" style="margin-top:12px;align-items:start">
        <video src="/media/out/${encodeURIComponent(r.arquivo)}" controls autoplay></video>
        <div><dl class="kv">
          <dt>Duração</dt><dd class="mono">${fmt(r.duracao_s)} (esperado ${fmt(r.esperado_s)})</dd>
          <dt>Emenda em</dt><dd class="mono">${fmt(r.transicao_s)}</dd>
          <dt>Áudio × vídeo</dt><dd>${r.dif_av_ms <= 45 ? `<span class="chip ok">sincronizado · ${r.dif_av_ms} ms</span>` : `<span class="chip warn">diferença de ${r.dif_av_ms} ms</span>`}</dd>
          <dt>Resolução</dt><dd>${esc(r.saida_res)}</dd><dt>Tamanho</dt><dd>${r.tamanho_mb} MB</dd>
          <dt>Processamento</dt><dd>${r.copiou_fluxos ? "copiado sem recodificar" : "recodificado"}</dd></dl>
          <ul class="small mute" style="padding-left:18px">${(r.decisao || []).map(d => `<li>${esc(d)}</li>`).join("")}</ul>
          <div class="row"><a class="btn pri sm" href="/media/out/${encodeURIComponent(r.arquivo)}?dl=1">Exportar (baixar)</a>
            <button class="btn sm" id="j-finder">Mostrar no Finder</button>
            ${prev ? `<button class="btn sm" id="j-full">Montar o vídeo completo</button>` : ""}</div></div></div>` : ""}
    ${r?.xml?`<div class="banner"><p>Sequência editável pronta: microlead e body separados.</p><a class="btn pri" href="/media/out/${encodeURIComponent(r.xml)}?dl=1">Salvar XML para Premiere</a><p class="small">Premiere → Arquivo → Importar (⌘I) → abra DR ML + Body. Mantenha as fontes na pasta Biblioteca. O XML usa cortes secos, sem fades.</p></div>`:''}
  </div>`;
  $("#j-cancel") && ($("#j-cancel").onclick = async () => { await post(`/api/ml/job/${j.id}/cancelar`); pollJob(); });
  $("#j-redo") && ($("#j-redo").onclick = () => startRender(!!prev));
  $("#j-full") && ($("#j-full").onclick = () => startRender(false));
  $("#j-finder") && ($("#j-finder").onclick = () => post("/api/ml/abrir", { arquivo: r.arquivo }));
}

/* ======================================================================= lote */
async function viewBatch() {
  await refreshVideos();
  const ready = S.videos.filter(v => v.status === "pronto");
  const o = opts();
  const sel = ls.get("ml.batchSel", { leads: [], bodies: [] });
  $("#view").innerHTML = `
    <div class="page-h"><div><h1>Lote de combinações</h1><p>Escolha as microleads e os bodies. Cada combinação vira um vídeo, com status próprio.</p></div><span class="chip local">● local</span></div>
    ${ready.length < 2 ? `<div class="card"><div class="empty">Envie e analise pelo menos dois vídeos na ferramenta <a href="#/microlead">Microlead + Body</a>.</div></div>` : `
    <div class="grid g2">
      <div class="card"><h2><span class="chip lead">Microleads</span></h2><div class="checks" id="c-lead">${ready.map(v => `<label><input type="checkbox" value="${v.id}" ${sel.leads.includes(v.id) ? "checked" : ""}>${esc(v.nome)} ${v.confirmado?.fim_lead != null ? `<span class="chip ok">corte confirmado ${fmt(v.confirmado.fim_lead)}</span>` : ""}</label>`).join("")}</div></div>
      <div class="card"><h2><span class="chip body">Bodies</span></h2><div class="checks" id="c-body">${ready.map(v => `<label><input type="checkbox" value="${v.id}" ${sel.bodies.includes(v.id) ? "checked" : ""}>${esc(v.nome)} ${v.confirmado?.inicio_body != null ? `<span class="chip ok">corte confirmado ${fmt(v.confirmado.inicio_body)}</span>` : ""}</label>`).join("")}</div></div>
    </div>
    <div class="card" style="margin-top:16px"><div class="row">
      <label class="f">Combinações<select id="b-mode"><option value="all">Todas (cada microlead × cada body)</option><option value="pairs">Em pares, na ordem</option></select></label>
      <label class="f">Entrega<select id="b-entrega"><option value="video">Vídeos prontos</option><option value="xml">Somente XMLs para Premiere</option><option value="ambos">Vídeos + XMLs</option></select></label><label class="f">Quando o corte não for confiável<select id="b-skip"><option value="1">Pausar e pedir confirmação</option><option value="0">Usar a 1ª opção das regras mesmo assim</option></select></label>
      <label class="f">Processamento<select id="b-modo"><option value="auto">Automático</option><option value="exato">Exato (x264)</option><option value="rapido">Rápido (hardware)</option></select></label>
      <span class="sp"></span><span class="small mute" id="b-count"></span><button class="btn pri" id="b-go">Criar vídeos</button></div>
      <p class="small mute" style="margin:10px 0 0">O lote usa o corte que você confirmou em cada vídeo. Sem confirmação, usa a 1ª opção das regras — e só segue sozinho se as regras forem confiáveis.</p></div>`}
    <div id="b-res" style="margin-top:16px"></div>`;
  if (ready.length >= 2) {
    const count = () => {
      const L = $$("#c-lead input:checked").map(i => i.value), B = $$("#c-body input:checked").map(i => i.value);
      ls.set("ml.batchSel", { leads: L, bodies: B });
      const pairs = $("#b-mode").value === "all" ? L.flatMap(l => B.filter(b => b !== l).map(b => ({ lead: l, body: b }))) : L.map((l, i) => B[i] && B[i] !== l ? { lead: l, body: B[i] } : null).filter(Boolean);
      $("#b-count").textContent = `${pairs.length} vídeo(s)`; return pairs;
    };
    $$("#c-lead input, #c-body input").forEach(i => i.onchange = count); $("#b-mode").onchange = count; count();
    $("#b-modo").value = o.modo === "copiar" ? "auto" : o.modo;
    $("#b-go").onclick = async () => {
      const pairs = count(); if (!pairs.length) return toast("Escolha pelo menos uma microlead e um body diferentes.", true);
      try { const b = await post("/api/ml/lote", { pares: pairs, pular_incertos: $("#b-skip").value === "1", opcoes: { ...o, entrega: $("#b-entrega").value, modo: $("#b-modo").value, previa: false } }); S.batch = b.id; ls.set("ml.batch", b.id); drawBatch(); } catch (e) { toast(e.message, true); }
    };
  }
  if (S.batch) drawBatch();
}
async function drawBatch() {
  let b; try { b = await api(`/api/ml/lote/${S.batch}`); } catch (e) { return; }
  const nm = id => esc(vById(id)?.nome || id), busy = b.itens.some(i => ["enviado", "na_fila", "executando"].includes(i.status));
  $("#b-res").innerHTML = `<div class="card"><h2>Lote ${esc(b.id)} <span class="sp"></span><span class="small mute">${b.itens.filter(i => i.status === "concluido").length}/${b.itens.length} prontos</span></h2>
    <table class="t"><tr><th>Microlead</th><th>Body</th><th>Status</th><th></th></tr>
    ${b.itens.map(it => `<tr>
      <td>${nm(it.lead)}<div class="small mute mono">até ${it.corte_lead.t != null ? fmt(it.corte_lead.t) : "—"} · ${esc(it.corte_lead.origem)}</div></td>
      <td>${nm(it.body)}<div class="small mute mono">de ${it.corte_body.t != null ? fmt(it.corte_body.t) : "—"} · ${esc(it.corte_body.origem)}</div></td>
      <td>${chip(it.status)}${["executando", "na_fila", "enviado"].includes(it.status) ? `<div class="bar" style="margin-top:6px;width:140px"><i style="width:${Math.round((it.pct || 0) * 100)}%"></i></div>` : ""}${it.erro ? `<div class="small" style="color:var(--err)">${esc(it.erro)}</div>` : ""}</td>
      <td style="text-align:right">${it.resultado?.arquivo ? `<a class="btn sm" href="/media/out/${encodeURIComponent(it.resultado.arquivo)}" target="_blank">Assistir</a> <a class="btn sm" href="/media/out/${encodeURIComponent(it.resultado.arquivo)}?dl=1">Baixar</a>` : ""}
        ${it.resultado?.xml?`<a class="btn sm" href="/media/out/${encodeURIComponent(it.resultado.xml)}?dl=1">XML Premiere</a>`:""}
        ${it.status === "precisa_confirmar" || it.status === "sem_corte" ? `<button class="btn sm" data-rev="${it.lead}|${it.body}">Revisar cortes</button>` : ""}
        ${["executando", "na_fila", "enviado"].includes(it.status) && it.job ? `<button class="btn sm ghost" data-cancel="${it.job}">Cancelar</button>` : ""}</td></tr>`).join("")}</table></div>`;
  $$("[data-rev]").forEach(x => x.onclick = () => { const [l, bb] = x.dataset.rev.split("|"); S.lead = l; S.body = bb; ls.set("ml.lead", l); ls.set("ml.body", bb); location.hash = "#/microlead"; });
  $$("[data-cancel]").forEach(x => x.onclick = async () => { await post(`/api/ml/job/${x.dataset.cancel}/cancelar`); drawBatch(); });
  if (busy && location.hash.startsWith("#/lote")) setTimeout(drawBatch, 1000);
}

/* ======================================================================= regras */
async function viewRules() {
  const r = await api("/api/ml/regras");
  const num = (k, label, help, step = 1) => `<label class="f">${label}<input type="number" step="${step}" data-k="${k}" value="${r[k]}" style="width:120px"><span class="small mute" style="color:var(--mute)">${help}</span></label>`;
  const list = (k, label, help) => `<label class="f" style="flex:1;min-width:260px">${label}<textarea data-l="${k}">${esc(r[k].join("\n"))}</textarea><span class="small" style="color:var(--mute)">${help}</span></label>`;
  $("#view").innerHTML = `
    <div class="page-h"><div><a href="#/ajustes" class="small">← Ajustes</a><h1>Transcrição e cortes</h1><p>Sem IA: o app só olha pausas, pontuação, expressões e durações. Ele não entende a copy — por isso pede confirmação quando as regras não bastam.</p></div></div>
    <div class="card"><h2>Durações e pausas</h2><div class="row" style="align-items:flex-start">
      ${num("lead_min_s", "Microlead mínima (s)", "cortes antes disso perdem pontos")}
      ${num("lead_max_s", "Microlead máxima (s)", "cortes depois disso perdem pontos")}
      ${num("pausa_min_ms", "Pausa mínima (ms)", "pausa que conta como limite natural", 10)}
      ${num("pausa_forte_ms", "Pausa que separa frase (ms)", "mesmo sem pontuação", 10)}
      ${num("silencio_db", "Limiar de silêncio (dB)", "mais negativo = só silêncio real")}
      ${num("folga_fim_lead_ms", "Folga após a microlead (ms)", "respiro depois da última palavra", 10)}
      ${num("folga_inicio_body_ms", "Folga antes do body (ms)", "respiro antes da 1ª palavra", 10)}
      ${num("conf_pontos", "Pontos para ser confiável", "abaixo disso, pede confirmação", 0.5)}
      ${num("conf_margem", "Vantagem sobre a 2ª opção", "se a 2ª estiver perto, pede confirmação", 0.5)}
    </div></div>
    <div class="card" style="margin-top:16px"><h2>Expressões <span class="small mute">(uma por linha, sem diferenciar maiúsculas)</span></h2><div class="row" style="align-items:flex-start">
      ${list("fim_lead", "Fecham a microlead (+4)", "procuradas nas 2 frases antes do corte")}
      ${list("transicao_forte", "Abrem uma nova seção (+3)", "procuradas no início da frase depois do corte")}
      ${list("transicao_fraca", "Conectivos de transição (+1)", "sinal fraco: 'now', 'so'…")}
      ${list("ganchos", "Ganchos e aberturas (marcação)", "só destacam frases na transcrição")}
    </div></div>
    <div class="row" style="margin-top:16px"><button class="btn pri" id="r-save">Salvar regras</button><button class="btn" id="r-reset">Restaurar padrão</button><span class="small mute">As sugestões são recalculadas na hora — não precisa transcrever de novo.</span></div>`;
  $("#r-save").onclick = async () => {
    const body = {};
    $$("[data-k]").forEach(i => body[i.dataset.k] = parseFloat(i.value));
    $$("[data-l]").forEach(t => body[t.dataset.l] = t.value.split("\n").map(x => x.trim()).filter(Boolean));
    if (body.lead_min_s >= body.lead_max_s) return toast("A microlead mínima precisa ser menor que a máxima.", true);
    await post("/api/ml/regras", body); S.views = {}; toast("Regras salvas.");
  };
  $("#r-reset").onclick = async () => { if (!confirm("Voltar às regras padrão?")) return; await post("/api/ml/regras/padrao"); S.views = {}; viewRules(); toast("Regras padrão restauradas."); };
}

window.addEventListener("DOMContentLoaded", () => { loadSys(); render(); });
