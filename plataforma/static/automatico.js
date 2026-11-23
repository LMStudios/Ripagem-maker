/* O servidor executa a sequência. A tela inicia o upload e acompanha o projeto salvo. */
(() => {
  const $ = id => document.getElementById(id);
  const U = window.SwapUX;
  if (!U || !$('drop')) return;
  const setup = document.createElement('section');
  setup.className = 'card';
  setup.innerHTML = `<h3>Ripagem automática</h3>
    <p class="meta">Configure a troca, selecione o vídeo e indique a pasta dos takes. O app transcreve o vídeo inteiro, prepara as falas, monta os takes e gera XML e legendas. Se encontrar uma pendência, ele pausa na etapa certa.</p>
    <label><input type="checkbox" id="auto-enabled"> Usar o modo automático neste trabalho</label>
    <div id="auto-setup" hidden>
      <div class="row"><label>Trabalho<select id="auto-scope"><option value="produto">Troca de potes</option><option value="precos">Somente preços e kits</option></select></label>
      <label id="auto-new-label">Produto novo<input id="auto-new" placeholder="Nome oficial"></label></div>
      <label id="auto-price-label" hidden>Preços e kits<textarea id="auto-demand" rows="2" placeholder="2/3/6 para 1/3/6 ($59/$39/$29 - $59/$117/$174)"></textarea></label>
      <div class="row"><label>Pasta dos takes<input id="auto-folder" placeholder="Escolha ou cole o caminho completo"></label><button class="ghost" type="button" id="auto-choose">Escolher pasta…</button></div>
      <details><summary>Produto original, modo de uso e vozes</summary>
        <label>Produto original<input id="auto-old" placeholder="Vazio: o app tenta identificar"></label>
        <div id="auto-form"><div class="row"><label>Forma original<select id="auto-from"></select></label><label>Forma nova<select id="auto-to"></select></label></div>
        <label>Via de uso confirmada<select id="auto-route"><option value="">Não definida</option><option value="oral">Via oral</option><option value="ingerir">Ingestão</option><option value="sublingual">Sublingual</option><option value="cutanea">Cutânea</option></select></label>
        <label>Instrução confirmada do produto novo<input id="auto-usage" maxlength="1000"></label></div>
        <label>IDs das vozes existentes, um por linha<textarea id="auto-voices" rows="2" placeholder="A=id_da_voz&#10;B=outro_id"></textarea></label>
        <p class="meta">Usa o serviço de voz salvo em Ajustes. Se faltar um ID, o app prepara amostras locais e pausa para você definir a voz.</p>
        <label><input type="checkbox" id="auto-video"> Renderizar também o vídeo com legendas</label>
      </details>
      <label><input type="checkbox" id="auto-consent"> Autorizo a transcrição, o uso de créditos das vozes configuradas e a entrega automática dos materiais sem alertas.</label>
      <p id="auto-setup-status" class="meta" role="status"></p>
    </div>`;
  $('drop').after(setup);
  for (const id of ['auto-from', 'auto-to']) {
    $(id).append(new Option('Sem troca de forma', ''));
    for (const option of $('form-from').options) $(id).append(new Option(option.text, option.value));
  }
  const progress = document.createElement('section');
  progress.className = 'card';
  progress.hidden = true;
  progress.innerHTML = `<b>Ripagem automática</b><p id="auto-status" role="status"></p>
    <div class="links"><button type="button" class="ghost" id="auto-stop" hidden>Pausar</button>
    <button type="button" id="auto-resolve" hidden>Ir para a pendência</button>
    <button type="button" class="ghost" id="auto-resume" hidden>Retomar após corrigir</button></div>
    <div class="links" id="auto-files"></div>`;
  document.querySelector('.wizard-nav').after(progress);
  let requesting = false, timer, current, scope = '', picker = false, starting = false, tracked = false;
  const value = id => $(id).value.trim();
  const prices = () => value('auto-scope') === 'precos';
  const isRunning = () => !!current?.job;
  const setupMessage = text => { $('auto-setup-status').textContent = text; };

  function voiceMap() {
    const rows = value('auto-voices').split('\n').map(s => s.trim()).filter(Boolean);
    const voices = {};
    for (const row of rows) {
      const match = /^([A-Za-z0-9_-]{1,32})\s*=\s*([A-Za-z0-9_-]{1,200})$/.exec(row);
      if (!match || Object.hasOwn(voices, match[1])) throw Error('Informe um ID por speaker, no formato A=id_da_voz.');
      voices[match[1]] = match[2];
    }
    return voices;
  }

  function tryStart() {
    if (!$('auto-enabled').checked || starting || wizardBusy) return;
    if (!file || !value('auto-folder')) return setupMessage('Selecione o vídeo e a pasta dos takes.');
    if (prices() ? !value('auto-demand') : !value('auto-new')) {
      return setupMessage(prices() ? 'Informe a solicitação de preços e kits.' : 'Informe o produto novo.');
    }
    if (!$('auto-consent').checked) return setupMessage('Confira a configuração e autorize o início.');
    try {
      const from = value('auto-from'), to = value('auto-to');
      if (!prices() && (!!from !== !!to || from && from === to)) throw Error('Escolha duas formas diferentes ou deixe ambas em Sem troca de forma.');
      const voices = voiceMap();
      const wanted = prices();
      if (window.RipagemOptimization.pending() !== wanted) $('optimize-toggle').click();
      $('prod').value = value('auto-old');
      $('novo').value = wanted ? value('auto-old') : value('auto-new');
      $('delivery-product-setup').value = $('novo').value;
      const automatic = {pasta: value('auto-folder'), demanda: value('auto-demand'), vozes: voices,
        autoriza: true, renderizar_video: $('auto-video').checked,
        forma: {ativo: !wanted && !!from, origem: from, destino: to, via_uso: value('auto-route'), uso_novo: value('auto-usage')}};
      starting = true;
      transcriptionConfirmed = true;
      wizardStep(2).then(() => {
        startTranscription(automatic);
        if (wizardBusy) {
          $('auto-consent').checked = false;
          setupMessage('A execução automática foi iniciada.');
        }
      }).catch(e => setupMessage(e.message)).finally(() => { starting = false; });
    } catch (e) { setupMessage(e.message); }
  }

  setup.addEventListener('change', () => {
    $('auto-setup').hidden = !$('auto-enabled').checked;
    $('auto-price-label').hidden = !prices();
    $('auto-new-label').hidden = prices();
    $('auto-form').hidden = prices();
    $('auto-old').placeholder = prices() ? 'Obrigatório para posicionar os takes' : 'Vazio: o app tenta identificar';
    if (!document.body.classList.contains('guided-ripagem')) tryStart();
  });
  document.addEventListener('ripagem:source-selected', () => {
    if (!document.body.classList.contains('guided-ripagem')) tryStart();
  });
  document.addEventListener('ripagem:guide-automatic-start', tryStart);
  document.addEventListener('ripagem:automatic-upload-error', event => setupMessage(event.detail));
  $('auto-choose').onclick = () => {
    const bridge = window.webkit?.messageHandlers?.chooseStorage;
    if (!bridge) {
      setupMessage('Cole o caminho completo da pasta dos takes.');
      $('auto-folder').focus();
      return;
    }
    picker = true;
    bridge.postMessage({purpose: 'visual'});
  };
  window.addEventListener('dr-folder-selected', e => {
    if (!picker) return;
    picker = false;
    if (!$('auto-enabled').checked || !e.detail) return;
    $('auto-folder').value = e.detail;
    if (!document.body.classList.contains('guided-ripagem')) tryStart();
  });

  function fileLinks(result) {
    const container = $('auto-files');
    container.replaceChildren();
    if (!result) return;
    for (const [key, label] of [['pacote','Baixar entrega · XML + SRT'], ['xml','XML para o Premiere'], ['legenda','Legenda SRT'], ['json','Relatório'], ['video','Vídeo legendado']]) {
      if (!result[key]) continue;
      const link = document.createElement('a');
      link.href = url(result[key].replaceAll('\\','/')) + '?dl=1';
      link.download = '';
      if ((key === 'xml' || key === 'pacote') && result.xml) link.dataset.studioXml = result.xml;
      link.textContent = label;
      container.append(link);
    }
  }

  function showState(state) {
    progress.hidden = !state.ativo;
    if (!state.ativo) return;
    $('auto-status').textContent = state.job?.passo || state.mensagem;
    $('auto-stop').hidden = !isRunning();
    $('auto-resolve').hidden = isRunning() || state.estado !== 'pausado';
    $('auto-resume').hidden = $('auto-resolve').hidden;
    if (state.estado === 'concluido') fileLinks(state.entrega);
  }

  async function poll() {
    const work = folder;
    if (!work || requesting) return;
    clearTimeout(timer);
    if (work !== scope) {
      scope = work; tracked = false; current = null; fileLinks(null); progress.hidden = true;
    }
    requesting = true;
    try {
      const state = await U.call('automatico-estado');
      if (work !== folder) return;
      current = state;
      showState(state);
      if (isRunning()) {
        tracked = true;
        timer = setTimeout(poll, 1500);
      } else {
        if (tracked) {
          tracked = false;
          await window.loadSwapPlan(false);
          if (state.estado === 'concluido') document.querySelector('[data-flow-step="6"]').click();
        }
        if (state.estado === 'pausado') timer = setTimeout(poll, 2500);
      }
    } catch (e) {
      if (work === folder && tracked) {
        $('auto-status').textContent = 'Reconectando ao progresso da ripagem automática…';
        timer = setTimeout(poll, 3000);
      }
    } finally {
      requesting = false;
      if (work !== folder) poll();
    }
  }

  $('auto-stop').onclick = async () => {
    try { await U.call('automatico-parar'); }
    catch (e) { $('auto-status').textContent = e.message; }
  };
  $('auto-resolve').onclick = () => {
    if (current.fase === 'vozes') {
      document.querySelector('[data-flow-step="3"]').click();
      $('speech-generate').click();
    } else if (current.fase === 'entrega') {
      document.querySelector('[data-flow-step="6"]').click();
    } else if (current.fase === 'legendas') {
      document.querySelector('[data-flow-step="7"]').click();
    } else {
      document.querySelector('[data-flow-step="' + (current.fase === 'takes' ? 4 : 3) + '"]').click();
    }
  };
  $('auto-resume').onclick = async () => {
    const button = $('auto-resume');
    button.disabled = true;
    try {
      if (await U.flushDraft() === false || U.hasDraft()) throw Error('Salve as alterações antes de retomar.');
      if (current.fase === 'vozes' && U.plan) {
        await U.call('preferencias-voz', {salvar: true, config: U.voiceOptions()});
      }
      await U.call('automatico-continuar');
      await poll();
    } catch (e) { $('auto-status').textContent = e.message; }
    finally { button.disabled = false; }
  };
  document.addEventListener('ripagem:project-opened', poll);
  document.addEventListener('swap:render', () => { if (current?.estado === 'concluido') poll(); });
})();
