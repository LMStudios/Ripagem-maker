/* Apresentação do fluxo completo. As ferramentas avulsas mantêm a entrada direta. */
(() => {
  const query = new URLSearchParams(location.search);
  const U = window.SwapUX, V = window.VisualUX;
  if (!U || !V || query.has('ferramenta') || query.has('etapa')) return;

  const byId = id => document.getElementById(id);
  const shell = byId('guided-fatiador');
  const nav = shell.querySelector('.wizard-nav');
  const step = n => nav.querySelector('[data-flow-step="' + n + '"]');
  const slot = n => byId('wizard-slot-' + n);
  const previewPreference = 'ripagem.flow.preview';
  const activeStep = () => nav.querySelector('[aria-current="step"]')?.dataset.flowStep;
  const offerPanel = byId('pcard').closest('details');
  const saved = byId('saved-work').closest('.card');
  const upload = byId('drop').closest('section');
  const start = byId('go');
  const setup = start.closest('.card');
  const name = byId('projeto-nome');
  const destination = byId('novo');
  const projectChoices = { usage: '', prices: '', fields: {} };
  const formFields = ['from', 'to', 'route', 'usage-new', 'description'];
  const formDefaults = {from:'', to:'', route:'oral', 'usage-new':'', description:''};
  let entryMode = query.has('trabalho') || query.get('inicio') === 'continuar' ? 'resume' : query.get('inicio') === 'novo' ? 'new' : 'home';
  let pendingNew = false;
  let guidedWork = '';
  let resumeWork = '';
  let applying = false;
  let attemptedChoices = '';
  let starting = false;

  function block(tag, className, html) {
    const node = document.createElement(tag);
    node.className = className;
    node.innerHTML = html;
    return node;
  }

  document.body.classList.add('guided-ripagem');
  const landing = block('section', 'guide-landing', `
    <p class="guide-kicker">ESTÚDIO DE EDIÇÃO</p><h2>Troca de potes</h2>
    <p>Prepare uma nova versão da sua VSL ou retome um trabalho salvo.</p>
    <div class="guide-entry-actions">
      <button type="button" data-entry="new"><b>Nova ripagem</b><span>Comece com um vídeo ou áudio.</span></button>
      <button type="button" class="ghost" data-entry="resume"><b>Continuar projeto</b><span>Volte à próxima pendência.</span></button>
    </div>`);
  const back = block('button', 'ghost guide-back', '← Voltar ao início');
  back.type = 'button';
  shell.before(landing);
  slot(1).prepend(back);
  const title = byId('wizard-title-1');
  const help = title.nextElementSibling;
  const advanced = block('details', 'guide-advanced', '<summary>Personalizar transcrição e entrega</summary>');
  const advancedFields = [byId('lang').closest('label'), byId('transcribe-range').parentElement,
    byId('prod').closest('label'), byId('alias').closest('label'), byId('cutp').closest('label')];
  advanced.append(...advancedFields, ...setup.querySelectorAll(':scope > details'));
  const identity = byId('delivery-pitch-setup')?.closest('.delivery-identity');
  if (identity) {
    const naming = block('details', 'guide-naming', '<summary>Nome da sequência e equipe</summary>');
    naming.append(identity);
    advanced.append(naming);
  }
  const profile = byId('ux-profile-setup')?.closest('details');
  if (profile) advanced.append(profile);
  const autoSetup = byId('auto-enabled')?.closest('section');
  if (autoSetup) advanced.append(autoSetup);
  if (byId('optimize-card')) advanced.append(byId('optimize-card'));
  const automatic = byId('op-auto-upload')?.closest('label');
  if (automatic) advanced.append(automatic);

  const entryFields = block('div', 'guide-fields', '');
  name.closest('label').firstChild.textContent = 'Nome do projeto';
  destination.closest('label').replaceChildren(document.createTextNode('Produto novo'), destination);
  entryFields.append(name.closest('label'), destination.closest('label'));
  upload.prepend(entryFields);
  const saveTo = block('p', 'meta guide-path', 'Consultando a pasta dos projetos…');
  const launch = block('div', 'guide-launch', '');
  // Elementos opcionais: ausentes nesta tela, viravam o texto "null".
  launch.append(...[start, byId('transcription-naming-error'), byId('transcription-naming-fix'), saveTo].filter(Boolean));
  upload.append(advanced, launch);
  start.textContent = 'Começar ripagem →';
  slot(1).append(saved);
  setup.hidden = true;
  slot(1).querySelector('.guide-back').after(upload);
  shell.querySelector('[data-w-next="2"]').hidden = true;
  const sourceHelp = byId('studio-source-size').nextElementSibling;
  sourceHelp.textContent = 'Clique no bloco para escolher outro arquivo.';

  function storage(data) {
    const full = data?.pastas?.fatiador || '';
    // Mostra só o nome da pasta; o caminho completo fica no texto de ajuda.
    saveTo.title = full;
    saveTo.replaceChildren(document.createTextNode(full
      ? 'Salvo em ' + full.split(/[\\/]/).filter(Boolean).slice(-2).join('/') + ' · ' : 'Destino dos projetos · '));
    const link = document.createElement('a');
    link.href = '/#/ajustes';
    link.textContent = 'Alterar pasta';
    saveTo.append(link);
  }
  fetch('/api/ajustes').then(r => r.json()).then(storage).catch(() => storage());
  document.addEventListener('ripagem:storage-configured', e => storage(e.detail));

  function entry() {
    shell.hidden = entryMode === 'home';
    landing.hidden = entryMode !== 'home';
    shell.dataset.entry = entryMode;
    upload.hidden = entryMode !== 'new';
    saved.hidden = entryMode !== 'resume';
    back.hidden = entryMode === 'work';
    title.textContent = entryMode === 'resume' ? 'Continuar projeto' : 'Nova ripagem';
    help.textContent = entryMode === 'resume'
      ? 'Escolha um trabalho para voltar à próxima pendência.'
      : 'Confira o arquivo e o nome do produto. A transcrição começa ao clicar em Começar ripagem.';
  }
  landing.querySelectorAll('[data-entry]').forEach(button => {
    button.onclick = () => {
      entryMode = button.dataset.entry;
      if (entryMode === 'new' && guidedWork) {
        file = null;
        wizardReady = false;
        transcriptionConfirmed = false;
        byId('file').value = '';
        name.value = '';
        destination.value = '';
        byId('prod').value = '';
        byId('alias').value = '';
        byId('studio-source-confirmation').hidden = true;
        byId('drop').classList.remove('has-source');
        byId('fname').textContent = 'Ou clique para escolher um arquivo neste computador.';
        progress.classList.add('hidden');
        updateWizard();
      }
      entry();
      if (entryMode === 'new') document.dispatchEvent(new CustomEvent('ripagem:new-project-draft'));
      step(1).click();
    };
  });
  back.onclick = () => {
    entryMode = 'home';
    entry();
    landing.querySelector('[data-entry]').focus();
  };
  const workBack = block('button', 'ghost guide-work-back', '← Nova ripagem ou continuar projeto');
  workBack.type = 'button';
  workBack.onclick = back.onclick;
  slot(1).append(workBack);

  let suggested = '';
  document.addEventListener('ripagem:source-selected', () => {
    if (entryMode === 'home' || entryMode === 'work') {
      entryMode = 'new';
      entry();
    }
    if (!name.value.trim() || name.value === suggested) {
      suggested = file.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').trim().slice(0, 80);
      name.value = suggested;
      name.dispatchEvent(new Event('input', {bubbles:true}));
    }
    byId('fname').textContent = 'Arquivo pronto. Clique em Começar ripagem quando quiser iniciar.';
  });

  const prep = block('section', 'card guide-prep', `
    <h3>Enquanto a transcrição acontece</h3><p class="meta">Indique o que também precisa mudar. Você pode ajustar suas escolhas em Falas.</p>
    <fieldset data-choice="usage"><legend>Precisa mudar a forma ou o modo de uso?</legend>
      <button type="button" class="ghost" value="yes">Sim</button><button type="button" class="ghost" value="no">Não</button>
      <div class="guide-form-fields" hidden></div>
    </fieldset>
    <fieldset data-choice="prices"><legend>Precisa alterar preços ou kits?</legend>
      <button type="button" class="ghost" value="yes">Sim</button><button type="button" class="ghost" value="no">Não</button>
      <p class="meta guide-price-help" hidden>Vamos detectar os valores e kits falados. Você define os novos valores e confere o texto em Falas.</p>
    </fieldset>`);
  const retry = block('button', 'ghost', 'Tentar transcrição novamente');
  retry.type = 'button';
  retry.hidden = true;
  const progress = byId('prog');
  progress.after(prep, retry);
  byId('wizard-title-2').textContent = 'Transcrição em andamento';
  byId('wizard-title-2').nextElementSibling.hidden = true;

  for (const field of formFields) {
    const original = byId('form-' + field);
    const copy = original.cloneNode(true);
    copy.id = 'guide-form-' + field;
    if (field === 'from' || field === 'to') copy.prepend(new Option('Selecione a forma', ''));
    const label = block('label', '', '');
    label.textContent = {
      from:'Forma original', to:'Nova forma', route:'Via de uso', 'usage-new':'Instrução de uso confirmada', description:'Descrição confirmada'
    }[field];
    label.append(copy);
    prep.querySelector('.guide-form-fields').append(label);
    copy.addEventListener('input', () => {
      projectChoices.fields[field] = copy.value;
      if (field === 'to') byId('guide-form-route').value = copy.value === 'patch' ? 'cutanea' : 'oral';
      if (field === 'to' || field === 'route') routes();
      persist();
    });
  }
  function routes() {
    const route = byId('guide-form-route');
    const skin = byId('guide-form-to').value === 'patch', spray = byId('guide-form-to').value === 'spray';
    for (const option of route.options) option.disabled = skin ? option.value !== 'cutanea' : !spray && option.value === 'cutanea';
    if ((skin && route.value !== 'cutanea') || (!skin && !spray && route.value === 'cutanea')) route.value = skin ? 'cutanea' : 'oral';
    projectChoices.fields.route = route.value;
  }
  function choiceUI() {
    prep.querySelectorAll('[data-choice]').forEach(group => {
      const value = projectChoices[group.dataset.choice];
      group.querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', button.value === value));
      group.lastElementChild.hidden = value !== 'yes';
    });
    for (const field of formFields) {
      const input = byId('guide-form-' + field);
      input.value = projectChoices.fields[field] ?? formDefaults[field];
      projectChoices.fields[field] = input.value;
    }
    routes();
    const priceOnly = window.RipagemOptimization?.pending() || U.plan?.somente_valores;
    prep.querySelector('[data-choice="usage"]').hidden = !!priceOnly;
    prep.querySelector('[data-choice="prices"]').hidden = !!priceOnly;
  }
  prep.querySelectorAll('[data-choice] button').forEach(button => button.onclick = () => {
    projectChoices[button.closest('[data-choice]').dataset.choice] = button.value;
    choiceUI();
    persist();
  });

  const projectKey = work => 'ripagem.guide.' + work;
  const uploadKey = 'ripagem.guide.upload';
  let pendingUpload = {};
  document.addEventListener('ripagem:transcription-job', e => {
    pendingUpload = {id:e.detail, name:file?.name || ''};
    persist();
  });
  document.addEventListener('ripagem:transcription-ended', () => sessionStorage.removeItem(uploadKey));
  function read(key, fallback = {}) {
    try { return JSON.parse(localStorage.getItem(key)) || fallback; }
    catch { return fallback; }
  }
  function persist() {
    if (pendingNew) {
      sessionStorage.setItem(uploadKey, JSON.stringify({...pendingUpload, choices:projectChoices}));
    } else if (guidedWork) {
      const key = projectKey(guidedWork);
      localStorage.setItem(key, JSON.stringify({...read(key), choices:projectChoices}));
    }
  }

  const originalStart = start.onclick;
  start.onclick = async () => {
    if (!file || wizardBusy || starting) return;
    if (byId('auto-enabled')?.checked) {
      document.dispatchEvent(new Event('ripagem:guide-automatic-start'));
      return;
    }
    starting = true;
    if (!name.value.trim()) {
      name.value = suggested || file.name.replace(/\.[^.]+$/, '').slice(0, 80);
    }
    if (!pendingNew) Object.assign(projectChoices, {usage:'', prices:'', fields:{}});
    pendingUpload = {};
    choiceUI();
    transcriptionConfirmed = true;
    await wizardStep(2);
    starting = false;
    if (activeStep() !== '2') return;
    retry.hidden = true;
    originalStart();
    pendingNew = wizardBusy;
    if (pendingNew) persist();
    else {
      await wizardStep(1);
      byId('transcription-naming-error').scrollIntoView({block:'center'});
    }
  };
  retry.onclick = () => {
    retry.hidden = true;
    if (file) originalStart();
    else { entryMode = 'new'; entry(); step(1).click(); }
  };
  new MutationObserver(() => {
    const error = byId('step').classList.contains('err');
    retry.hidden = !error;
    byId('wizard-title-2').textContent = error ? 'Transcrição interrompida' : 'Transcrição em andamento';
  }).observe(byId('step'), {attributes:true, attributeFilter:['class']});

  const extras = document.querySelector('.studio-extras');
  const projectDetails = block('details', 'card guide-project-details', '<summary>Resumo da VSL e pitch</summary>');
  const summary = document.querySelector('.studio-summary');
  summary.before(projectDetails);
  projectDetails.append(summary, ...document.querySelectorAll('.practical-pitch'));
  byId('wizard-title-3').textContent = 'Revise as falas que vão mudar';
  byId('wizard-title-5').textContent = 'Prepare e confira a legenda';
  byId('wizard-title-4').textContent = 'Entrega · XML para o Premiere';
  byId('flow-title-4').textContent = 'Takes do produto';
  byId('flow-title-5').textContent = 'Confira a montagem';
  const review = block('section', 'card guide-review', `
    <p class="guide-kicker">REVISÃO</p><h3>O que precisa da sua atenção?</h3>
    <div class="guide-review-actions">
      <button type="button" class="ghost" data-review="mentions">Menções <span></span></button>
      <button type="button" class="ghost" data-review="usage">Modo de uso <span></span></button>
      <button type="button" class="ghost" data-review="audio">Áudios <span></span></button>
    </div>
    <div class="guide-review-links">
      <button type="button" class="ghost" data-review="search">Corrigir identificação</button>
      <button type="button" class="ghost" data-review="prices" hidden>Configurar preços e kits</button>
    </div><p class="meta" role="status"></p>`);
  slot(3).prepend(review);
  const notice = review.querySelector('[role="status"]');
  const filter = key => document.querySelector('[data-filter="' + key + '"]')?.click();
  const reveal = node => {
    if (!node) return;
    for (let parent = node.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') parent.open = true;
    }
    node.scrollIntoView({block:'center', behavior:'smooth'});
  };
  function prices() {
    reveal(byId('pdetect'));
    if (offerPanel) offerPanel.open = true;
    if (!byId('pdet').childElementCount && !byId('pdetect').disabled) byId('pdetect').click();
  }
  review.querySelectorAll('[data-review]').forEach(button => button.onclick = () => {
    switch (button.dataset.review) {
      case 'mentions': byId('speech-texts').click(); if (mentionCoverage?.folder === folder && mentionCoverage.coverage?.pendencias?.some(r => ['sem_fala','fora_da_selecao','texto_antigo'].includes(r.status))) document.dispatchEvent(new Event('mentions:open-review')); else {filter('issues'); reveal(byId('ux-list'));} break;
      case 'usage': byId('speech-texts').click(); filter('form'); reveal(byId('ux-list')); break;
      case 'audio':
        if (U.plan?.itens.some(row => row.aprovado && !row.audio?.fit)) {
          byId('speech-generate').click(); filter('fit');
        } else { byId('speech-listen').click(); filter('listen'); }
        reveal(byId('ux-list')); break;
      case 'search':
        if (extras) extras.open = true;
        reveal(byId('prod2'));
        byId('prod2').focus({preventScroll:true});
        break;
      case 'prices': prices(); break;
    }
  });

  const voiceHelp = block('p', 'meta guide-voice', '');
  voiceHelp.append('Se uma fala falhar, escolha outro provedor ou importe somente o áudio dessa frase. ');
  const importVoice = block('button', 'ghost', 'Localizar fala para importar');
  importVoice.type = 'button';
  importVoice.onclick = () => {
    filter('fit');
    const uploadInput = document.querySelector('#ux-editor [data-swap-upload]');
    reveal(uploadInput?.closest('details') || byId('ux-list'));
    if (uploadInput) reveal(uploadInput);
  };
  voiceHelp.append(importVoice);
  byId('swap-provider').closest('label').after(voiceHelp);

  let mentionCoverage = null;
  document.addEventListener('mentions:coverage', e => {mentionCoverage = e.detail; renderReview();});
  function renderReview() {
    const rows = U.plan?.itens || [];
    const keys = new Set(rows.filter(row => row.mencoes_revisar?.length && !row.mencao_descartada && !row.aprovado).map(row => row.id));
    if (mentionCoverage?.folder === folder) for (const item of mentionCoverage.coverage?.pendencias || []) if (['sem_fala','fora_da_selecao','texto_antigo'].includes(item.status)) keys.add(item.id_fala || item.id);
    const mentions = [...keys];
    const usage = rows.filter(row => (row.forma_detectada || row.forma_pendente) && !row.forma_confirmada);
    const audio = rows.filter(row => row.aprovado && !row.audio?.aprovado);
    for (const [key, group] of Object.entries({mentions, usage, audio})) {
      const button = review.querySelector('[data-review="' + key + '"]');
      button.querySelector('span').textContent = group.length;
      button.classList.toggle('guide-pending', group.length > 0);
    }
    review.querySelector('[data-review="search"]').hidden = !!U.plan?.somente_valores;
    review.querySelector('[data-review="usage"]').hidden = !!U.plan?.somente_valores;
    review.querySelector('[data-review="prices"]').hidden = projectChoices.prices !== 'yes' || !!U.plan?.somente_valores;
  }

  async function applyChoices() {
    if (applying || !guidedWork || !U.plan || U.busy || U.plan.somente_valores) return;
    const key = projectKey(guidedWork), state = read(key);
    if (state.prepared || !state.newProject || attemptedChoices === guidedWork) return;
    attemptedChoices = guidedWork;
    applying = true;
    try {
      if (projectChoices.usage === 'yes') {
        const config = projectChoices.fields;
        if (!config.from || !config.to || config.from === config.to) {
          const toggle = byId('practical-form-toggle');
          if (toggle.getAttribute('aria-expanded') !== 'true') toggle.click();
          notice.textContent = 'Para adaptar o modo de uso, escolha duas formas diferentes em Configurar adaptação.';
        } else {
          if (await U.flushDraft() === false || U.hasDraft()) throw Error('Salve as edições antes de aplicar o modo de uso.');
          const plan = await U.call('forma', {forma:{
            ativo:true, origem:config.from, destino:config.to, via_uso:config.route,
            uso_novo:config['usage-new'] || '', descricao_nova:config.description || ''
          }});
          if (key !== projectKey(folder)) return;
          if (U.hasDraft()) {
            await U.flushDraft();
            await window.loadSwapPlan();
          } else U.acceptPlan(plan);
          document.dispatchEvent(new Event('form:config-saved'));
          notice.textContent = 'Modo de uso aplicado. Confira as sugestões antes de aprovar.';
        }
      }
      if (projectChoices.prices === 'yes') {
        if (extras) extras.open = true;
        if (offerPanel) offerPanel.open = true;
        if (!byId('pdet').childElementCount && !byId('pdetect').disabled) byId('pdetect').click();
      }
      localStorage.setItem(key, JSON.stringify({...state, prepared:true, choices:projectChoices}));
    } catch (error) {
      notice.textContent = 'Configuração pendente. ' + error.message;
    } finally {
      applying = false;
      renderReview();
    }
  }

  async function resume() {
    if (!resumeWork || resumeWork !== folder || !U.plan || U.busy) return;
    const work = resumeWork;
    resumeWork = '';
    try {
      const gate = await U.call('workflow');
      if (work !== folder || activeStep() !== '3') return;
      if (gate.takes_liberados) {
        const state = read(projectKey(work));
        const target = state.stage === 7 ? 6 : [4, 5, 6].includes(state.stage) ? state.stage : 4;
        step(target)?.click();
      } else if (gate.estado === 'pronto_para_gerar') byId('speech-generate').click();
      else if (gate.estado === 'aguardando_conferencia') byId('speech-listen').click();
    } catch (error) { notice.textContent = 'Confira o estado do projeto. ' + error.message; }
  }

  document.addEventListener('ripagem:project-opened', () => {
    const isNew = pendingNew;
    pendingNew = false;
    resumeWork = '';
    attemptedChoices = '';
    guidedWork = folder;
    entryMode = 'work';
    entry();
    const key = projectKey(folder);
    if (isNew) {
      localStorage.setItem(key, JSON.stringify({choices:projectChoices, newProject:true}));
      sessionStorage.removeItem(uploadKey);
    } else {
      Object.assign(projectChoices, {usage:'', prices:'', fields:{}}, read(key).choices || {});
      resumeWork = folder;
    }
    renderReview();
  });
  document.addEventListener('swap:render', () => {
    renderReview();
    if (guidedWork === folder) {
      applyChoices();
      resume();
    }
  });
  document.addEventListener('swap:state', () => {
    renderReview();
    if (!U.busy && guidedWork === folder) { applyChoices(); resume(); }
  });

  document.addEventListener('ripagem:prices-applied', async e => {
    if (!e.detail.frases?.length || projectChoices.prices !== 'yes' || U.plan?.somente_valores) return;
    if (await U.flushDraft() === false || U.hasDraft()) {
      notice.textContent = 'Preços preparados. Salve as edições antes de incluir as novas falas.';
      return;
    }
    byId('swap-prices').checked = true;
    await window.loadSwapPlan(true);
    notice.textContent = U.plan?.incluir_precos
      ? 'Preços e kits incluídos na revisão de falas.' : 'Não foi possível incluir os preços. Use Incluir trocas de preços na revisão.';
  });
  document.addEventListener('optimization:state', choiceUI);

  const previewButton = byId('flow-to-preview');
  const quickButton = byId('flow-quick');
  const previewOn = () => localStorage.getItem(previewPreference) === '1';
  const previewToggle = block('a', 'guide-preview-setting', 'Configurar prévia em Ajustes');
  previewToggle.href = '/#/ajustes';
  previewButton.after(previewToggle);
  const stageNames = {1:'Arquivo', 2:'Transcrição', 3:'Falas', 4:'Takes', 5:'Prévia', 7:'Legenda · opcional', 6:'Entrega'};
  for (const [n, label] of Object.entries(stageNames)) { step(n).textContent = label; step(n).setAttribute('aria-label',label); }
  previewButton.textContent = 'Ver prévia da montagem';
  quickButton.textContent = 'Continuar para a legenda →';
  byId('flow-quick').closest('section').querySelector('h3').textContent = 'Gerar XML para o Premiere';
  byId('flow-quick').closest('section').querySelector('p').textContent = 'Gere o XML com os takes e áudios aprovados. A legenda fica disponível como opção na entrega.';
  const optionalPreview = block('button', 'ghost', 'Ver prévia da montagem');
  optionalPreview.type = 'button';
  optionalPreview.onclick = () => step(5).click();
  const backFromCaptions = document.querySelector('[data-w-panel="5"] [data-w-back]');
  if (backFromCaptions) backFromCaptions.onclick = () => step(previewOn() ? 5 : 4).click();
  byId('final-checklist').after(optionalPreview);
  function previewUI() {
    const enabled = previewOn();
    step(5).hidden = !enabled;
    shell.classList.toggle('guide-preview-on', enabled);
    quickButton.classList.toggle('ghost', enabled);
    quickButton.textContent = enabled ? 'Pular prévia e gerar XML' : 'Gerar XML para o Premiere →';
  }
  window.addEventListener('storage', e => { if (e.key === previewPreference) previewUI(); });
  window.addEventListener('pageshow', previewUI);

  let lastStage = '';
  function stageChanged() {
    const stage = activeStep();
    if (!stage || lastStage === stage) return;
    lastStage = stage;
    if (guidedWork === folder && Number(stage) >= 4 && !resumeWork) {
      const key = projectKey(folder);
      localStorage.setItem(key, JSON.stringify({...read(key), stage:Number(stage)}));
    }

  }
  new MutationObserver(stageChanged).observe(nav, {subtree:true, attributes:true, attributeFilter:['aria-current']});

  const root = byId('visual-root');
  window.addEventListener('dr-folder-selected', e => {
    if (activeStep() === '4' && e.detail && root.value === e.detail && !V.busy && !U.busy) byId('flow-auto-takes').click();
  });
  root.addEventListener('keydown', e => {
    if (e.key === 'Enter' && root.value.trim()) {
      e.preventDefault();
      byId('flow-auto-takes').click();
    }
  });

  previewUI();
  entry();
  renderReview();

  if (!query.has('trabalho')) {
    try {
      const task = JSON.parse(sessionStorage.getItem(uploadKey));
      if (task?.id) {
        pendingUpload = task;
        pendingNew = true;
        Object.assign(projectChoices, task.choices || {});
        entryMode = 'new';
        entry();
        choiceUI();
        transcriptionConfirmed = true;
        // Restore the progress panel even though the browser cannot restore a file input.
        const previousFile = file;
        file = {name:task.name, size:1};
        wizardStep(2).then(() => {
          file = previousFile;
          wizardBusy = true;
          updateWizard();
          progress.classList.remove('hidden');
          byId('pname').textContent = task.name;
          byId('step').textContent = 'Retomando o acompanhamento…';
          poll(task.id);
        });
      }
    } catch { sessionStorage.removeItem(uploadKey); }
  }
})();
