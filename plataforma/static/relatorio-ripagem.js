(() => {
  const slot = document.getElementById('wizard-slot-4');
  if (!slot) return;
  const card = document.createElement('section');
  card.className = 'card';
  card.hidden = true;
  card.dataset.relatorioRipagem = '';
  card.innerHTML = `
    <h3>Relatório da ripagem</h3>
    <p data-rm-report-summary class="meta"></p>
    <div class="links">
      <button type="button" class="ghost" data-rm-report-export>Exportar relatório</button>
    </div>
    <details data-rm-report-detail>
      <summary>Ver tempos e deixar feedback</summary>
      <ul data-rm-report-stages></ul>
      <form data-rm-report-form>
        <label>O que mais atrasou?
          <select name="etapa">
            <option value="">Selecione se quiser</option><option value="transcricao">Transcrição</option>
            <option value="voz">Voz</option><option value="busca_visual">Busca visual</option>
            <option value="takes">Takes</option><option value="exportacao">Exportação</option>
            <option value="legenda">Legenda</option><option value="outro">Outro</option>
          </select>
        </label>
        <label>Minutos fora do app<input name="minutos" type="number" min="0" max="43200" step="any"></label>
        <label>O que precisou ajustar? <span class="meta">Observação salva neste computador</span>
          <textarea name="comentario" maxlength="1000" rows="2"></textarea>
        </label>
        <button type="submit" class="ghost">Salvar feedback</button>
      </form>
      <p data-rm-report-message role="status" class="meta"></p>
    </details>`;
  slot.append(card);
  const form = card.querySelector('form'), message = card.querySelector('[data-rm-report-message]');
  const labels = {transcricao:'Transcrição', voz:'Voz', busca_visual:'Busca visual', takes:'Takes', exportacao:'Exportação'};
  const time = ms => ms == null ? 'Sem medição' : new Intl.NumberFormat('pt-BR', {maximumFractionDigits:1}).format(ms / 60000) + ' min';
  let data, scope, reading = 0;
  const currentFolder = () => typeof folder !== 'undefined' ? folder : '';
  function render(item) {
    data = item;
    card.hidden = !item;
    if (!item) return;
    const d = item.resumo;
    card.querySelector('[data-rm-report-summary]').textContent =
      `${d.xml_revisao ? 'XML de revisão' : 'XML salvo'} · ${time(d.tempo_ripagem_ms)} no app${d.medicao_completa ? '' : ' · medição parcial'} · ${d.falhas} falha(s) registrada(s)`;
    const stages = card.querySelector('[data-rm-report-stages]');
    stages.replaceChildren();
    const entries = Object.entries(d.etapas_ms || {}).map(([stage, value]) => [labels[stage] || 'Etapa', time(value)]);
    entries.push(['Espera que bloqueou o fluxo', time(d.espera_ms)], ['Retrabalho', time(d.retrabalho_ms)]);
    for (const [label, value] of entries) {
      const row = document.createElement('li');
      row.textContent = label + ' · ' + value;
      stages.append(row);
    }
    form.hidden = window.RipagemEquipe?.perfil?.id !== d.usuario;
    form.elements.etapa.value = d.feedback_etapa || '';
    form.elements.minutos.value = d.fora_app_ms == null ? '' : d.fora_app_ms / 60000;
    form.elements.comentario.value = item.observacao_local || '';
  }
  async function load(force = false) {
    const project = currentFolder();
    if (!project || !window.RipagemEquipe?.perfil || (!force && project === scope)) return;
    scope = project;
    const sequence = ++reading;
    render(null);
    try {
      const response = await fetch('/api/equipe/relatorio-xml?folder=' + encodeURIComponent(project));
      if (response.ok && sequence === reading && project === currentFolder()) render(await response.json());
    } catch {}
  }
  document.addEventListener('swap:render', () => load());
  document.addEventListener('ripagem:equipe-sessao', () => load());
  document.addEventListener('ripagem:studio-saved', () => load(true));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const project = currentFolder();
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      const response = await fetch('/api/equipe/relatorio-feedback', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({folder:project, etapa:form.elements.etapa.value,
          minutos:form.elements.minutos.value ? Number(form.elements.minutos.value) : null,
          comentario:form.elements.comentario.value})
      });
      const result = await response.json();
      if (project !== currentFolder()) return;
      if (!response.ok) throw Error(result.erro);
      render(result);
      message.textContent = 'Feedback salvo.';
    } catch (error) {
      if (project === currentFolder()) message.textContent = error.message || 'Não foi possível salvar o feedback.';
    } finally { button.disabled = false; }
  });
  card.querySelector('[data-rm-report-export]').onclick = () => {
    if (!data) return;
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type:'application/json'}));
    link.download = 'relatorio-ripagem.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 15000);
  };
})();
