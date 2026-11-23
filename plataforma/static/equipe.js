/* A sessão pertence ao servidor local. A interface recebe somente o perfil. */
(() => {
  const byId = (id) => document.getElementById(id);
  const endpoint = '/api/equipe/';
  let session = null;
  let sending = false;
  let lastActivity = 0;

  window.RipagemEquipe = {get sessao() { return session; }, get perfil() { return session?.perfil || null; }};

  async function api(action, body) {
    const options = {cache: 'no-store'};
    if (body !== undefined) {
      options.method = 'POST';
      options.headers = {'Content-Type': 'application/json'};
      options.body = JSON.stringify(body);
    }
    const response = await fetch(endpoint + action, options);
    const result = await response.json();
    if (!response.ok) {
      const error = new Error(result.erro || result.mensagem || 'Não foi possível consultar a conta.');
      error.status = response.status;
      throw error;
    }
    return result;
  }

  function allowedDestination(raw) {
    try {
      const url = new URL(raw || '/', location.origin);
      if (url.origin === location.origin && ['/', '/fatiador'].includes(url.pathname)) {
        return url.pathname + url.search + url.hash;
      }
    } catch {}
    return '/';
  }

  function openLogin() {
    const current = allowedDestination(location.pathname + location.search + location.hash);
    location.replace('/entrar?voltar=' + encodeURIComponent(current));
  }

  function loginPage() {
    const forms = [byId('equipe-login'), byId('equipe-recuperacao'), byId('equipe-confirmacao')];
    const forgot = byId('equipe-esqueci'), invite = byId('equipe-convite'), back = byId('equipe-voltar');
    const message = byId('equipe-mensagem');
    const email = byId('equipe-email'), password = byId('equipe-senha');
    const recoveryEmail = byId('equipe-recuperar-email'), confirmationEmail = byId('equipe-confirmar-email');
    const code = byId('equipe-codigo'), newPassword = byId('equipe-nova-senha');
    const next = allowedDestination(new URLSearchParams(location.search).get('voltar'));
    let inviteMode = false;

    function setMessage(text, error = false) {
      message.textContent = text;
      message.dataset.erro = error ? 'sim' : '';
    }

    function mode(index) {
      forms.forEach((form, i) => { form.hidden = i !== index; });
      forgot.hidden = invite.hidden = index !== 0;
      back.hidden = index === 0;
      byId('equipe-titulo').textContent = [
        'Entre na sua conta',
        'Recupere sua senha',
        inviteMode ? 'Ative sua conta' : 'Defina uma nova senha'
      ][index];
      byId('equipe-ajuda').textContent = [
        'Use o e-mail cadastrado pela sua equipe.',
        'Informe o e-mail cadastrado para receber um código.',
        'Use o código enviado ao seu e-mail.'
      ][index];
      forms[index].querySelector('input').focus();
    }

    async function submit(event, task) {
      event.preventDefault();
      if (sending) return;
      const origin = event.currentTarget;
      sending = true;
      const controls = document.querySelectorAll('.equipe-acesso-card input, .equipe-acesso-card button');
      controls.forEach((control) => { control.disabled = true; });
      setMessage('');
      try { await task(); }
      catch (error) { setMessage(error.message || 'Tente novamente em instantes.', true); }
      finally {
        sending = false;
        controls.forEach((control) => { control.disabled = false; });
        const visible = forms.find((form) => !form.hidden);
        if (visible && visible !== origin) visible.querySelector('input').focus();
      }
    }

    forms[0].addEventListener('submit', (event) => submit(event, async () => {
      try {
        const result = await api('entrar', {email: email.value.trim(), senha: password.value});
        if (!result.autenticado) throw new Error(result.mensagem || 'Confira os dados da conta e tente novamente.');
        location.replace(next);
      } finally { password.value = ''; }
    }));

    forms[1].addEventListener('submit', (event) => submit(event, async () => {
      await api('recuperar', {email: recoveryEmail.value.trim()});
      confirmationEmail.value = recoveryEmail.value.trim();
      mode(2);
      setMessage('Confira seu e-mail para receber o código.');
    }));

    forms[2].addEventListener('submit', (event) => submit(event, async () => {
      try {
        await api('redefinir', {
          email: confirmationEmail.value.trim(), codigo: code.value.trim(),
          nova_senha: newPassword.value, convite: inviteMode
        });
        email.value = confirmationEmail.value.trim();
        code.value = '';
        mode(0);
        setMessage('Senha salva. Entre com os dados da sua conta.');
      } finally { newPassword.value = ''; }
    }));

    forgot.addEventListener('click', () => {
      inviteMode = false;
      recoveryEmail.value = email.value;
      mode(1);
      setMessage('');
    });
    invite.addEventListener('click', () => {
      inviteMode = true;
      confirmationEmail.value = email.value;
      mode(2);
      setMessage('');
    });
    back.addEventListener('click', () => {
      code.value = newPassword.value = '';
      inviteMode = false;
      mode(0);
      setMessage('');
    });

    api('sessao').then((result) => {
      if (result.autenticado || result.configurado === false) location.replace(next);
      else if (result.mensagem && result.estado !== 'aguardando_login' && !sending) setMessage(result.mensagem, true);
    }).catch(() => {
      if (!sending) setMessage('Serviço de login indisponível. Tente novamente em instantes.', true);
    });
  }

  function registerTeam(ready) {
    if (typeof routes === 'undefined') return;
    routes['/equipe'] = async () => {
      const view = byId('view');
      const section = document.createElement('div');
      section.innerHTML = '<div class="page-h"><div><h1>Equipe</h1><p>Gerencie os acessos e acompanhe as ripagens da equipe.</p></div></div>';
      view.replaceChildren(section);
      await ready;
      if (!section.isConnected) return;
      if (session?.perfil?.funcao !== 'administrador') {
        const notice = document.createElement('p');
        notice.textContent = 'Esta tela está disponível para administradores.';
        section.append(notice);
        return;
      }
      section.insertAdjacentHTML('beforeend', `
        <section class="card">
          <h2>Editar acessos</h2>
          <form id="equipe-novo-editor" class="row equipe-filtros">
            <label class="f">Nome do editor<input name="nome" maxlength="100" required></label>
            <label class="f">E-mail<input name="email" type="email" maxlength="254" required></label>
            <label class="f">Código de editor<input name="codigo" maxlength="32" placeholder="EV08" required></label>
            <label class="f">Entrega do convite<select name="convite_manual"><option value="sim">Código para compartilhar</option><option value="nao">E-mail automático (SMTP)</option></select></label>
            <button type="submit" class="btn pri">Convidar editor</button>
          </form>
          <p class="equipe-detalhe" data-team-status role="status"></p>
          <div class="equipe-admin-table"><table class="t">
            <thead><tr><th>Nome e e-mail</th><th>Código</th><th>Função</th><th>Último login</th><th>Acesso</th></tr></thead>
            <tbody data-team-list></tbody>
          </table></div>
        </section>
        <section class="card">
          <h2>Relatórios de ripagem</h2>
          <div class="row equipe-filtros">
            <label class="f">Editor<select data-report-editor><option value="">Todos</option></select></label>
            <label class="f">Versão<select data-report-version><option value="">Todas</option></select></label>
            <label class="f">De<input data-report-from type="date"></label>
            <label class="f">Até<input data-report-until type="date"></label>
            <button type="button" class="btn" data-report-refresh>Atualizar</button>
            <button type="button" class="btn" data-report-export disabled>Exportar CSV</button>
          </div>
          <p class="equipe-detalhe" data-report-status role="status"></p>
          <div class="equipe-admin-table"><table class="t">
            <thead><tr><th>Editor</th><th>Data</th><th>Tempo</th><th>Espera</th><th>Retrabalho</th><th>Fora do app</th><th>Falhas e tentativas</th><th>Entrega</th></tr></thead>
            <tbody data-report-list></tbody>
          </table></div>
        </section>`);
      const find = (selector) => section.querySelector(selector);
      const invite = find('#equipe-novo-editor');
      const teamStatus = find('[data-team-status]'), reportStatus = find('[data-report-status]');
      let profiles = [], reports = [], visibleReports = [], pendingAdmin = false;

      function status(node, message, error = false) {
        node.textContent = message;
        node.dataset.erro = error ? 'sim' : '';
      }
      function time(value) {
        if (!value) return '—';
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('pt-BR', {dateStyle: 'short', timeStyle: 'short'});
      }
      function duration(ms) {
        if (!Number.isFinite(ms)) return '—';
        const seconds = Math.round(ms / 1000);
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor(seconds % 3600 / 60);
        return (hours ? hours + ' h ' : '') + (minutes ? minutes + ' min ' : '') + seconds % 60 + ' s';
      }
      function element(tag, value) {
        const node = document.createElement(tag);
        node.textContent = value;
        return node;
      }
      function input(value, label, length) {
        const field = document.createElement('input');
        field.type = 'text';
        field.value = value;
        field.maxLength = length;
        field.setAttribute('aria-label', label);
        return field;
      }
      function button(text, callback) {
        const control = element('button', text);
        control.type = 'button';
        control.className = 'btn sm ghost';
        control.addEventListener('click', callback);
        return control;
      }
      async function adminAction(body, done) {
        if (pendingAdmin) return;
        pendingAdmin = true;
        status(teamStatus, 'Salvando…');
        section.querySelectorAll('form button, [data-team-list] button').forEach((b) => { b.disabled = true; });
        try {
          const result = await api('admin', body);
          if (body.acao === 'convidar') invite.reset();
          if (result.codigo_ativacao) {
            status(teamStatus, 'Código de ativação: ' + result.codigo_ativacao + '. Envie só ao editor. Ele informa o código em Ativar convite no aplicativo.');
            try { await loadTeam(); } catch (error) { /* Preserve o código nesta tela. */ }
          } else {
            await loadTeam();
            status(teamStatus, done);
          }
        } catch (error) { status(teamStatus, error.message, true); }
        finally {
          pendingAdmin = false;
          for (const b of section.querySelectorAll('form button, [data-team-list] button:not([data-acesso-bloqueado])')) b.disabled = false;
        }
      }
      function renderTeam() {
        const rows = profiles.map((profile) => {
          const row = document.createElement('tr');
          const who = element('td', '');
          const nome = input(profile.nome ?? '', 'Nome de ' + (profile.email || 'editor'), 100);
          who.append(nome, element('p', profile.email || ''));
          who.lastChild.className = 'equipe-detalhe';
          const code = element('td', '');
          const codigo = input(profile.codigo ?? '', 'Código de ' + profile.nome, 32);
          codigo.className = 'equipe-codigo';
          const edit = button('Salvar', () => adminAction({
            acao: 'editar', id: profile.id, nome: nome.value.trim(), codigo: codigo.value.trim()
          }, 'Perfil atualizado.'));
          code.append(codigo, edit);
          const access = element('td', profile.ativo ? 'Ativo' : 'Desativado');
          const change = button(profile.ativo ? 'Desativar' : 'Reativar', () => adminAction({
            acao: profile.ativo ? 'desativar' : 'reativar', id: profile.id
          }, profile.ativo ? 'Acesso desativado.' : 'Acesso reativado.'));
          if (profile.funcao === 'administrador') {
            change.dataset.acessoBloqueado = '';
            change.disabled = true;
          }
          access.append(document.createElement('br'), change);
          row.append(who, code, element('td', profile.funcao === 'administrador' ? 'Administrador' : 'Editor'),
            element('td', time(profile.ultimo_login)), access);
          return row;
        });
        find('[data-team-list]').replaceChildren(...rows);
        options(find('[data-report-editor]'), profiles.map((profile) => [profile.id, profile.nome]));
      }
      function options(select, values) {
        const previous = select.value;
        select.replaceChildren(select.options[0], ...values.map(([id, name]) => new Option(name, id)));
        if (values.some(([id]) => id === previous)) select.value = previous;
      }
      async function loadTeam() {
        const result = await api('admin', {acao: 'listar'});
        profiles = result.perfis || [];
        renderTeam();
        renderReports();
      }
      function renderReports() {
        const editor = find('[data-report-editor]').value;
        const version = find('[data-report-version]').value;
        const start = find('[data-report-from]').value;
        const end = find('[data-report-until]').value;
        const names = new Map(profiles.map((profile) => [profile.id, profile.nome]));
        visibleReports = reports.filter((report) => {
          const date = report.atualizado_em;
          return (!editor || report.usuario === editor) && (!version || report.versao_app === version)
            && (!start || new Date(date) >= new Date(start + 'T00:00:00'))
            && (!end || new Date(date) <= new Date(end + 'T23:59:59.999'));
        });
        find('[data-report-list]').replaceChildren(...visibleReports.map((report) => {
          const row = document.createElement('tr');
          const timing = duration(report.tempo_ripagem_ms);
          const timeCell = element('td', timing + (report.medicao_completa ? '' : ' · parcial'));
          const stages = Object.entries(report.etapas_ms || {});
          if (stages.length) {
            const details = document.createElement('details');
            details.append(element('summary', 'Ver etapas'));
            const labels = {transcricao: 'Transcrição', voz: 'Voz', busca_visual: 'Busca visual', takes: 'Takes', exportacao: 'Exportação'};
            for (const [key, value] of stages) details.append(element('p', (labels[key] || key) + ' · ' + duration(value)));
            timeCell.append(details);
          }
          row.append(element('td', names.get(report.usuario) || 'Editor indisponível'), element('td', time(report.atualizado_em)), timeCell,
            element('td', duration(report.espera_ms)), element('td', duration(report.retrabalho_ms)), element('td', duration(report.fora_app_ms)),
            element('td', (report.falhas ?? 0) + ' falha(s) · ' + (report.tentativas ?? 0) + ' tentativa(s)'),
            element('td', (report.xml_revisao ? 'XML de revisão' : 'XML salvo') +
              (report.pendencias_visuais ? ' · ' + report.pendencias_visuais + ' pendência(s) visual(is)' : '')));
          return row;
        }));
        find('[data-report-export]').disabled = !visibleReports.length;
      }
      async function loadReports() {
        status(reportStatus, 'Consultando relatórios…');
        const result = await api('relatorios');
        reports = result.relatorios || [];
        const versions = [...new Set(reports.map((report) => report.versao_app).filter(Boolean))].sort();
        options(find('[data-report-version]'), versions.map((version) => [version, version]));
        renderReports();
        status(reportStatus, reports.length ? reports.length + ' relatório(s) disponível(is).' : 'Nenhuma ripagem sincronizada ainda.');
      }
      function exportReports() {
        const users = new Map(profiles.map((profile) => [profile.id, profile]));
        const columns = [
          'projeto_id', 'editor', 'codigo', 'versao_app', 'sistema', 'atualizado_em', 'medicao_completa',
          'tempo_ripagem_ms', 'espera_ms', 'retrabalho_ms', 'fora_app_ms', 'xml_revisao', 'pendencias_visuais',
          'tentativas', 'falhas', 'transcricao_ms', 'voz_ms', 'busca_visual_ms', 'takes_ms', 'exportacao_ms'
        ];
        const csvCell = (value) => {
          const raw = String(value ?? '');
          const safe = /^[\s]*[=+@-]/.test(raw) ? "'" + raw : raw;
          return '"' + safe.replaceAll('"', '""') + '"';
        };
        const lines = [columns.map(csvCell).join(';')];
        for (const report of visibleReports) {
          const profile = users.get(report.usuario) || {};
          const record = {...report, editor: profile.nome, codigo: profile.codigo};
          for (const [key, value] of Object.entries(report.etapas_ms || {})) record[key + '_ms'] = value;
          lines.push(columns.map((key) => csvCell(record[key])).join(';'));
        }
        const resource = URL.createObjectURL(new Blob(['\uFEFF', lines.join('\r\n')], {type: 'text/csv;charset=utf-8'}));
        const link = document.createElement('a');
        link.href = resource;
        link.download = 'ripagem-maker-relatorios.csv';
        document.body.append(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(resource), 30_000);
      }
      invite.addEventListener('submit', (event) => {
        event.preventDefault();
        const fields = Object.fromEntries(new FormData(invite));
        adminAction({acao: 'convidar', ...fields, convite_manual: fields.convite_manual === 'sim'}, 'Convite enviado.');
      });
      for (const key of ['editor', 'version', 'from', 'until']) find('[data-report-' + key + ']').addEventListener('change', renderReports);
      find('[data-report-export]').addEventListener('click', exportReports);
      find('[data-report-refresh]').addEventListener('click', () => loadReports().catch((error) => status(reportStatus, error.message, true)));
      await Promise.allSettled([
        loadTeam().catch((error) => status(teamStatus, error.message, true)),
        loadReports().catch((error) => status(reportStatus, error.message, true))
      ]);
    };
  }

  function mountAccount() {
    const sidebar = document.querySelector('.side .foot'), editor = document.querySelector('#equipe-posicao');
    if (!sidebar && !editor) return;
    const account = document.createElement('details');
    account.className = 'equipe-conta' + (editor ? ' equipe-conta-fatiador' : '');
    account.hidden = true;
    account.innerHTML = '<summary><strong data-eq-name></strong> <span data-eq-code></span></summary><div class="equipe-menu"><p class="equipe-detalhe" data-eq-role></p><button type="button" class="ghost">Sair</button><p class="equipe-detalhe" data-eq-status role="status" hidden></p></div>';
    (sidebar || editor).before(account);
    const team = document.createElement('a');
    team.href = '/#/equipe';
    team.textContent = 'Equipe';
    team.hidden = true;
    if (sidebar) {
      team.dataset.r = '/equipe';
      sidebar.closest('.side').querySelector('.nav').append(team);
    } else { account.querySelector('.equipe-menu').prepend(team); }

    const status = account.querySelector('[data-eq-status]');
    const logout = account.querySelector('button');

    function update(result) {
      if (!result || typeof result.configurado !== 'boolean') return;
      session = result;
      document.dispatchEvent(new CustomEvent('ripagem:equipe-sessao', {detail: result}));
      if (result.configurado && !result.autenticado) {
        openLogin();
        return;
      }
      if (!result.perfil) {
        account.hidden = team.hidden = true;
        return;
      }
      const profile = result.perfil;
      team.hidden = profile.funcao !== 'administrador';
      account.querySelector('[data-eq-name]').textContent = profile.nome;
      account.querySelector('[data-eq-code]').textContent = profile.codigo ? '· ' + profile.codigo : '';
      account.querySelector('[data-eq-role]').textContent = profile.funcao === 'administrador' ? 'Administrador' : 'Editor';
      status.textContent = result.estado === 'indisponivel' ? (result.mensagem || 'Serviço de login indisponível.') : '';
      status.hidden = !status.textContent;
      account.hidden = false;
    }

    async function heartbeat() {
      if (!session?.autenticado || Date.now() - lastActivity < 30_000) return;
      lastActivity = Date.now();
      try { update(await api('atividade', {})); }
      catch (error) {
        if (error.status === 401 || error.status === 403) openLogin();
      }
    }

    logout.addEventListener('click', async () => {
      logout.disabled = true;
      try {
        await api('sair', {});
        openLogin();
      } catch (error) {
        status.textContent = error.message;
        status.hidden = false;
        logout.disabled = false;
      }
    });

    const ready = api('sessao').then(update).catch((error) => {
      if (error.status === 401 || error.status === 403) openLogin();
    });
    if (sidebar) registerTeam(ready);
    window.addEventListener('focus', heartbeat);
    window.setInterval(heartbeat, 60_000);
  }

  if (byId('equipe-login')) loginPage();
  else mountAccount();
})();
