'use strict';
/* Coleta de links de vídeo do TikTok e do Pinterest numa janela própria do app.
   A janela usa uma sessão separada e persistente (o login do editor fica salvo nela),
   sem preload, sem Node e sem permissões. Só lê os links da página de resultados;
   quem baixa e confere é o motor (yt-dlp + OCR). */
const SITES = {
 tiktok: {
  name: 'TikTok',
  search: q => 'https://www.tiktok.com/search/video?q=' + encodeURIComponent(q),
  selector: 'a[href*="/video/"]',
  link: /^https:\/\/(?:www\.)?tiktok\.com\/@[\w.-]+\/video\/\d+/,
  gated: '',
  login: 'Entre na sua conta ou conclua a verificação do TikTok · a busca continua sozinha',
 },
 pinterest: {
  name: 'Pinterest',
  search: q => 'https://www.pinterest.com/search/videos/?q=' + encodeURIComponent(q) + '&rs=typed',
  selector: 'a[href*="/pin/"]',
  link: /^https:\/\/(?:[a-z]{2,3}\.)?(?:www\.)?pinterest\.[a-z.]{2,6}\/pin\/[\w-]*?\d+\/?/,
  // Sem login o Pinterest mostra os vídeos, mas esconde o link de cada pin.
  gated: '[data-test-id="gated-search-pins-feed"]',
  login: 'Entre na sua conta do Pinterest nesta janela (só na primeira vez) · a busca continua sozinha',
 },
};
const PARTITION = 'persist:ripagem-broll';
const prepared = new WeakSet();

function site(name) {
 const s = SITES[String(name || '')];
 if (!s) throw Error('Escolha TikTok ou Pinterest.');
 return s;
}

function cleanQuery(query) {
 const q = String(query || '').replace(/\s+/g, ' ').trim().slice(0, 120);
 if (!q) throw Error('Escreva o que procurar para esta frase.');
 return q;
}

/* Links únicos, sem parâmetros, só de vídeo/pin. */
function normalize(name, hrefs, limit = 8) {
 const s = site(name), seen = new Set(), out = [];
 for (const raw of hrefs || []) {
  let url;
  try { url = new URL(String(raw)); } catch { continue; }
  if (url.protocol !== 'https:') continue;
  const match = (url.origin + url.pathname).match(s.link);
  if (!match) continue;
  const clean = match[0].replace(/\/?$/, name === 'pinterest' ? '/' : '');
  const key = clean.match(/\d{6,}/)?.[0] || clean;
  if (seen.has(key)) continue;
  seen.add(key); out.push(clean);
  if (out.length >= limit) break;
 }
 return out;
}

/* Janelas de login aceitas (Entrar com Google, Apple ou Facebook); o resto é bloqueado. */
function signIn(address) {
 try {
  const u = new URL(String(address));
  return u.protocol === 'https:' && /(^|\.)(accounts\.google\.com|appleid\.apple\.com|facebook\.com|tiktok\.com|pinterest\.[a-z.]+)$/.test(u.hostname);
 } catch { return false; }
}

/* Navegador de verdade: o TikTok e o Pinterest recusam o identificador "Electron". */
function browserAgent(agent) {
 return String(agent || '').replace(/\s(?:Electron|ripagem-maker[\w-]*)\/\S+/gi, '');
}

async function collect({BrowserWindow, session, parent, name, query, limit = 8, timeoutMs = 120000, wait = ms => new Promise(r => setTimeout(r, ms))}) {
 const s = site(name), q = cleanQuery(query), max = Math.max(1, Math.min(20, Number(limit) || 8));
 const ses = session.fromPartition(PARTITION);
 if (!prepared.has(ses)) {
  prepared.add(ses);
  ses.setPermissionRequestHandler((_c, _p, cb) => cb(false));
  ses.setUserAgent(browserAgent(ses.getUserAgent()));
  ses.on('will-download', event => event.preventDefault());
 }
 const view = new BrowserWindow({parent, width: 1100, height: 820, show: false, title: s.name + ' · busca de b-roll (Ripagem Maker)',
  webPreferences: {session: ses, contextIsolation: true, nodeIntegration: false, sandbox: true, webSecurity: true}});
 view.webContents.setWindowOpenHandler(({url}) => signIn(url)
  ? {action: 'allow', overrideBrowserWindowOptions: {parent: view, width: 520, height: 700, webPreferences: {session: ses, contextIsolation: true, nodeIntegration: false, sandbox: true}}}
  : {action: 'deny'});
 let closed = false, shown = false;
 view.on('closed', () => { closed = true; });
 const started = Date.now();
 let found = [], stableSince = 0, lastReload = Date.now();
 try {
  view.loadURL(s.search(q)).catch(() => {});
  while (!closed && Date.now() - started < (shown ? Math.max(timeoutMs, 300000) : timeoutMs)) {
   await wait(1200);
   if (closed) break;
   let hrefs = [];
   // Só conta links da página de busca: depois do login o site pode voltar para a página inicial.
   const here = view.webContents.getURL();
   if (!here.includes('/search')) {
    if (Date.now() - lastReload > 8000 && /tiktok\.com|pinterest\./.test(here) && !/login|signup|auth|captcha/i.test(here)) { lastReload = Date.now(); view.loadURL(s.search(q)).catch(() => {}); }
    continue;
   }
   try {
    const page = await view.webContents.executeJavaScript(`({hrefs:Array.from(document.querySelectorAll(${JSON.stringify(s.selector)})).map(a=>a.href),gated:${s.gated ? `!!document.querySelector(${JSON.stringify(s.gated)})` : 'false'}})`, true);
    hrefs = page.hrefs;
    if (page.gated && !shown) { shown = true; view.setTitle(s.login); view.show(); }
    await view.webContents.executeJavaScript('window.scrollBy(0, window.innerHeight)', true);
   } catch { /* página ainda carregando */ }
   const now = normalize(name, hrefs, max);
   if (now.length > found.length) { found = now; stableSince = Date.now(); }
   if (found.length >= max) break;
   if (found.length && Date.now() - stableSince > 4000) break;
   // Sem resultado depois de alguns segundos: login, verificação ou aviso de cookies. Mostra a janela para o editor resolver.
   if (!found.length && !shown && Date.now() - started > 9000) {
    shown = true; view.setTitle(s.login); view.show();
   }
  }
 } finally {
  if (!closed) view.destroy();
 }
 if (!found.length) throw Error(closed ? 'A janela foi fechada antes de aparecerem resultados.' : `O ${s.name} não mostrou vídeos para essa busca. Tente outras palavras ou entre na conta na janela que abrir.`);
 return {ok: true, site: name, fonte: s.name, consulta: q, links: found, precisou_janela: shown};
}

module.exports = {SITES, PARTITION, normalize, browserAgent, cleanQuery, signIn, collect};
