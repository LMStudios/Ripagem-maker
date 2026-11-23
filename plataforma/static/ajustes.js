routes['/ajustes']=async()=>{
  const data=await api('/api/ajustes');
  $('#view').innerHTML=`<div class="page-h"><div><h1>Ajustes</h1><p>Gerencie chaves, pastas, atualizações e espaço em disco.</p></div></div><section class="card"><h2>Transcrição e cortes</h2><p class="small mute">Defina pausas, expressões e durações usadas nos cortes de microleads.</p><a class="btn" href="#/regras">Configurar regras de corte →</a></section><div class="card"><h2>Pasta principal dos arquivos</h2><p class="small mute">A ferramenta cria as subpastas Fatiador, Montagens e Biblioteca. Os trabalhos antigos continuam disponíveis no local anterior; não serão movidos.</p><label class="f">Pasta principal<input id="storage-path" type="text" value="${esc(data.pasta_principal)}" placeholder="Ex.: /Users/seu-usuario/Documents/Ripagem Maker"></label><div class="row" style="margin-top:12px"><button class="btn" id="storage-choose">Escolher pasta…</button><button class="btn pri" id="storage-save">Salvar pasta principal</button><button class="btn" id="storage-default">Usar pastas padrão</button></div><p class="small mute">No Ripagem Maker.app, “Escolher pasta” abre o seletor do Mac. No navegador, cole o caminho completo no campo.</p><p id="storage-message" role="status"></p><div id="storage-folders"></div></div>`;
  function show(d){$('#storage-folders').innerHTML='<h3>Destino dos novos arquivos</h3>'+Object.entries(d.pastas).map(([k,v])=>`<p><b>${{fatiador:'Troca de potes',montagens:'Vídeos e XMLs de ML',videos:'Vídeos de origem'}[k]}</b><br><span class="mono small">${esc(v)}</span></p>`).join('');}
  show(data);
  const choose={postMessage:()=>window.webkit?.messageHandlers?.chooseStorage?.postMessage({})};
  $('#storage-choose').onclick=()=>{if(window.webkit?.messageHandlers?.chooseStorage)choose.postMessage({});else{$('#storage-message').textContent='Cole o caminho completo da pasta no campo acima e clique em Salvar pasta principal.';$('#storage-path').focus();}};
  window.onStorageFolderSelected=e=>{if($('#storage-path'))$('#storage-path').value=e.detail;};
  window.removeEventListener('dr-folder-selected',window.previousStorageListener);window.previousStorageListener=window.onStorageFolderSelected;window.addEventListener('dr-folder-selected',window.previousStorageListener);
  async function save(value){const b=$('#storage-save');b.disabled=true;try{const d=await post('/api/ajustes',{pasta_principal:value});$('#storage-path').value=d.pasta_principal;show(d);$('#storage-message').textContent='Pasta salva. Os próximos trabalhos usarão este destino; não precisa reiniciar.';}catch(e){$('#storage-message').textContent=e.message;}finally{b.disabled=false;}}
  $('#storage-save').onclick=()=>save($('#storage-path').value);$('#storage-default').onclick=()=>save('');
};

// Limpeza acessível em Ajustes; andamento continua mesmo ao trocar de página.
const storageSettingsRoute=routes['/ajustes'];
routes['/ajustes']=async()=>{
 await storageSettingsRoute();
 let token=null,pending=null,timer=null;
 const size=n=>{if(!n)return '0 MB';if(n<1024**2)return Math.ceil(n/1024)+' KB';return n>=1024**3?(n/1024**3).toFixed(1)+' GiB':(n/1024**2).toFixed(1)+' MB';};
 const box=document.createElement('section');box.className='card';box.id='cleanup-card';box.innerHTML=`<h2>Limpeza segura de materiais</h2><p>Economize espaço sem perder trabalhos ou quebrar as mídias no Premiere.</p><ul class="small mute"><li>Consolida cópias idênticas no APFS, mantendo cada arquivo e seu caminho.</li><li>Remove somente caches de compilação que o app pode recriar.</li><li>Preserva vídeos originais, transcrições, áudios, XMLs e versões anteriores.</li></ul><p class="small mute">A análise inclui as pastas atuais e anteriores configuradas no aplicativo. Não mexe em outras pastas do Mac. Execute quando não houver trabalhos em andamento.</p><p id="cleanup-free"></p><div class="row"><button class="btn" id="cleanup-analyze">Analisar espaço</button><button class="btn pri" id="cleanup-run" disabled>Executar limpeza segura</button></div><div id="cleanup-progress" hidden style="margin-top:16px"><p id="cleanup-step" role="status"></p><progress id="cleanup-bar" max="1" style="width:100%;accent-color:var(--acc)"></progress><button class="btn" id="cleanup-cancel">Cancelar</button></div><p id="cleanup-error" role="alert" class="err"></p><div id="cleanup-analysis" aria-live="polite"></div><div id="cleanup-result" aria-live="polite"></div>`;
 $('#view').append(box);
 const get=id=>document.getElementById(id);
 function lock(value){get('cleanup-analyze').disabled=value;get('cleanup-run').disabled=value||!token;get('storage-save').disabled=value;get('storage-default').disabled=value;}
 function analyzed(a){token=a&&(a.duplicados||a.caches)?a.token:null;get('cleanup-analysis').innerHTML=a?`<div class="banner" style="display:block"><b>${a.duplicados} cópia(s) para otimizar · ${a.caches} arquivo(s) de cache</b><p>Duplicação detectada: até ${size(a.duplicacao_bytes)} · caches: ${size(a.cache_bytes)}.</p><p class="small mute">${size(a.ja_otimizado_bytes)} de cópias já estão consolidadas. O espaço recuperado é medido ao terminar. No APFS, algumas cópias podem já compartilhar armazenamento.</p>${a.exemplos?.length?`<details><summary>Ver cópias encontradas</summary>${a.exemplos.map(p=>`<p class="mono small">${esc(p)}</p>`).join('')}</details>`:''}${!token?'<p>Não há acúmulo seguro para limpar agora.</p>':''}</div>`:'';lock(!!pending);}
 function result(r){get('cleanup-result').innerHTML=r?`<div class="banner" style="display:block"><b>Última limpeza: ${size(r.liberado_bytes)} recuperados</b><p>${r.consolidados} cópia(s) consolidada(s) · ${r.caches_removidos} cache(s) removido(s).</p><p class="small mute">Originais, transcrições, áudios, XMLs e caminhos das mídias preservados.</p>${(r.avisos||[]).map(w=>`<p class="small">${esc(w)}</p>`).join('')}</div>`:'';}
 async function status(){const s=await api('/api/limpeza');if(!box.isConnected)return;get('cleanup-free').textContent='Espaço livre nos discos utilizados: '+size(s.livre_bytes);result(s.ultima);}
 async function poll(){if(!pending||!get('cleanup-card'))return;try{
  const j=await api('/api/ml/job/'+pending);if(!box.isConnected)return;get('cleanup-step').textContent=j.step;
  if(j.status==='na_fila'||j.progresso?.indeterminado)get('cleanup-bar').removeAttribute('value');else get('cleanup-bar').value=j.pct||0;
  if(['na_fila','executando'].includes(j.status)){timer=setTimeout(poll,1500);return;}
  pending=null;sessionStorage.removeItem('ripagem.cleanup');get('cleanup-cancel').hidden=true;
  if(j.status==='concluido'){if(j.result?.token)analyzed(j.result);else{token=null;get('cleanup-analysis').innerHTML='';result(j.result);}}else{token=null;get('cleanup-error').textContent=j.error||(j.status==='cancelado'?'Operação cancelada. Os arquivos de trabalho foram preservados.':'A operação não terminou. Analise novamente.');}
  lock(false);await status();
 }catch(e){if(box.isConnected){get('cleanup-error').textContent='Não foi possível consultar o progresso. Tentando novamente…';timer=setTimeout(poll,4000);}}}
 async function start(endpoint,body={}){get('cleanup-error').textContent='';lock(true);try{const j=await post(endpoint,body);pending=j.id;sessionStorage.setItem('ripagem.cleanup',j.id);if(!box.isConnected)return;get('cleanup-progress').hidden=false;get('cleanup-cancel').hidden=false;get('cleanup-step').textContent='Aguardando início…';get('cleanup-bar').removeAttribute('value');poll();}catch(e){get('cleanup-error').textContent=e.message;lock(false);}}
 get('cleanup-analyze').onclick=()=>start('/api/limpeza/analisar');get('cleanup-run').onclick=()=>token&&start('/api/limpeza/executar',{token});get('cleanup-cancel').onclick=()=>pending&&post('/api/ml/job/'+pending+'/cancelar');
 await status();pending=sessionStorage.getItem('ripagem.cleanup');if(pending){get('cleanup-progress').hidden=false;lock(true);poll();}
};

const settingsWithCleanup=routes['/ajustes'];
routes['/ajustes']=async()=>{
 await settingsWithCleanup();
 const d=await api('/api/ajustes');
 const card=document.createElement('section');card.className='card';
 card.innerHTML=`<h2>Limpar o início das trocas de fala</h2><p>Remova o resquício do áudio antigo antes de cada fala substituída e feche o intervalo em todas as trilhas.</p><label class="f">Margem à esquerda (ms)<input id="speech-margin" type="number" min="0" max="500" step="10" value="${Number(d.margem_fala_ms??200)}"></label><p class="small mute">0 desativa. Padrão: 200 ms. Fragmentos de até 120 ms entre trocas próximas também são removidos. Ajuste a margem e confira a prévia para não cortar a palavra anterior. Áudio e vídeo avançam juntos; a fala nova começa imediatamente após o corte, sem vazio. Aplica às próximas prévias e XMLs do Fatiador; arquivos já exportados continuam iguais.</p><button class="btn pri" id="speech-margin-save">Salvar margem</button><p id="speech-margin-status" role="status"></p>`;
 document.querySelector('#view .page-h').after(card);
 if(!Object.prototype.hasOwnProperty.call(d,'margem_fala_ms')){card.querySelector('button').disabled=true;card.querySelector('[role=status]').textContent='Para ativar este novo ajuste, feche o app com ⌘Q e abra novamente. A chave de voz desta sessão precisará ser informada outra vez.';}
 card.querySelector('#speech-margin-save').onclick=async()=>{
  const b=card.querySelector('button');const value=Number(card.querySelector('input').value);b.disabled=true;
  try{if(!Number.isInteger(value)||value<0||value>500)throw Error('Informe de 0 a 500 ms.');await post('/api/ajustes',{margem_fala_ms:value});card.querySelector('[role=status]').textContent='Margem salva. Gere uma nova prévia ou um novo XML para aplicar.';}catch(e){card.querySelector('[role=status]').textContent=e.message;}finally{b.disabled=false;}
 };
};

const settingsBeforeAssembly=routes['/ajustes'];
routes['/ajustes']=async()=>{
 await settingsBeforeAssembly();
 const card=document.createElement('section');card.className='card';
 card.innerHTML=`<h2>Transcrição · AssemblyAI</h2><p id="assembly-state" role="status">Consultando configuração…</p><label class="f">Chave da API<input id="assembly-key" type="password" autocomplete="off" spellcheck="false" placeholder="Cole a chave para configurar ou substituir"></label><p class="small mute">Salva somente neste computador. Cada pessoa configura sua própria chave. A transcrição envia o áudio selecionado ao AssemblyAI e pode consumir créditos.</p><button class="btn pri" id="assembly-save" disabled>Salvar chave</button><p id="assembly-result" role="status"></p>`;
 document.querySelector('#view .page-h').after(card);
 const input=card.querySelector('input'),button=card.querySelector('button'),state=card.querySelector('#assembly-state'),message=card.querySelector('#assembly-result');
 try{const d=await api('/api/assembly-chave');state.textContent=d.configurada?'Chave configurada. Cole outra abaixo se quiser substituir.':'Nenhuma chave configurada.';button.disabled=false;}
 catch(e){state.textContent='Feche o app e abra novamente para ativar este novo ajuste.';return;}
 button.onclick=async()=>{
  button.disabled=true;message.textContent='Salvando…';
  try{await post('/api/assembly-chave',{chave:input.value.trim()});input.value='';state.textContent='Chave configurada.';message.textContent='Chave salva. As próximas transcrições já usarão esta chave; não precisa reiniciar.';}
  catch(e){message.textContent=e.message;}
  finally{button.disabled=false;}
 };
};

const settingsBeforeUpdates=routes['/ajustes'];
routes['/ajustes']=async()=>{
 await settingsBeforeUpdates();
 const box=document.createElement('section');box.className='card';
 box.innerHTML=`<h2>Versão e atualizações</h2><p id="update-version">Consultando versão…</p><p>Recebeu uma versão nova? Escolha o ZIP de atualização enviado pelo responsável pelo Ripagem Maker. O mesmo pacote serve para Mac e Windows.</p><label class="f">Pacote de atualização<input type="file" accept=".zip" id="update-file"></label><p class="small mute">Use apenas pacotes de quem mantém o aplicativo. Trabalhos, chaves e configurações são preservados; uma cópia do código anterior é guardada. Termine as tarefas antes de atualizar. Depois, feche e abra o app.</p><button class="btn pri" id="update-apply" disabled>Aplicar atualização</button><p role="status" id="update-result"></p>`;
 document.querySelector('#view .page-h').after(box);
 const input=box.querySelector('input'),button=box.querySelector('button'),message=box.querySelector('#update-result');
 try{const d=await api('/api/versao');box.querySelector('#update-version').textContent='Versão instalada: '+d.versao;if(d.reinicio_necessario){message.textContent='Atualização aplicada. Feche e abra o aplicativo.';input.disabled=true;return;}}
 catch(e){box.querySelector('#update-version').textContent='Feche e abra o app para ativar o atualizador.';input.disabled=true;return;}
 input.onchange=()=>{button.disabled=!input.files.length;message.textContent='';};
 button.onclick=async()=>{
  const file=input.files[0];if(!file)return;
  if(file.size>25*1024*1024){message.textContent='O pacote deve ter até 25 MB.';return;}
  button.disabled=true;input.disabled=true;message.textContent='Verificando e aplicando atualização…';let success=false;
  try{const response=await fetch('/api/atualizar',{method:'POST',headers:{'Content-Type':'application/zip'},body:file});const d=await response.json();if(!response.ok)throw Error(d.erro||'Não foi possível atualizar.');success=true;message.textContent='Versão '+d.versao+' aplicada. Feche e abra o Ripagem Maker para continuar. Não precisa reinstalar.';}
  catch(e){message.textContent=e.message;}
  finally{if(!success){button.disabled=false;input.disabled=false;}}
 };
};

const settingsBeforeIntegrations=routes['/ajustes'];
routes['/ajustes']=async()=>{
 await settingsBeforeIntegrations();
 document.getElementById('assembly-save')?.closest('section')?.remove();
 const card=document.createElement('section');card.className='card';card.innerHTML='<h2>Integrações e APIs</h2><p>Configure uma vez neste computador. As chaves permanecem após fechar e atualizar o app e são guardadas no cofre do sistema.</p>';
 document.querySelector('#view .page-h').after(card);
 let status;try{status=await api('/api/integracoes');}catch(e){card.append(document.createTextNode('Feche e abra o app para ativar Integrações e APIs.'));return;}
 for(const [provider,name] of [['assemblyai','AssemblyAI · transcrição'],['elevenlabs','ElevenLabs · vozes'],['minimax','MiniMax · opcional'],['gemini','Gemini · adaptação do modo de uso']]){
  const row=document.createElement('div');row.className='card';row.innerHTML=`<h3>${name}</h3><p data-api-state></p><label class="f">Chave da API<input type="password" autocomplete="off" spellcheck="false" placeholder="Cole somente para configurar ou substituir"></label><div class="row"><button class="btn pri" data-api-save>Salvar chave</button><button class="btn" data-api-test>Testar conexão</button><button class="btn" data-api-remove>Remover chave</button></div><p role="status" data-api-message></p>`;if(provider==='minimax'){const more=document.createElement('details');more.innerHTML='<summary>Outra integração de voz · MiniMax</summary>';more.append(row);card.append(more);}else card.append(row);
  if(provider==='gemini'){const note=document.createElement('p');note.className='small mute';note.textContent='Gemini 3.5 Flash-Lite: use uma chave de projeto sem faturamento ativo para a faixa gratuita. Há cotas; o app não controla o plano do Google. Textos enviados na faixa gratuita podem ser usados para melhorar os serviços do Google.';row.append(note);const link=document.createElement('a');link.href='https://aistudio.google.com/apikey';link.target='_blank';link.rel='noopener noreferrer';link.textContent='Criar ou consultar minha chave no Google AI Studio';row.append(link);}
  const input=row.querySelector('input'),message=row.querySelector('[data-api-message]');
  function state(d){row.querySelector('[data-api-state]').textContent=(d.configurada?'Configurada · ':'Não configurada · ')+d.armazenamento+(d.aviso?' · '+d.aviso:'');row.querySelector('[data-api-test]').disabled=!d.configurada||provider==='minimax';row.querySelector('[data-api-test]').hidden=provider==='minimax';row.querySelector('[data-api-remove]').disabled=!d.configurada;}
  state(status[provider]||{configurada:false,armazenamento:'Reabra o app atualizado para ativar este serviço'});
  async function action(acao){
   row.querySelectorAll('button').forEach(b=>b.disabled=true);message.textContent=acao==='testar'?'Testando conexão…':'Salvando…';
   try{const d=await post('/api/integracoes',{servico:provider,acao,...(acao==='salvar'?{chave:input.value.trim()}:{})});input.value='';status=await api('/api/integracoes');state(status[provider]||{configurada:false,armazenamento:'Reabra o app atualizado para ativar este serviço'});message.textContent=acao==='testar'?d.mensagem:acao==='remover'?'Chave removida deste computador.':'Chave salva no cofre do sistema. Já está disponível para as próximas tarefas.';}
   catch(e){message.textContent=e.message;}
   finally{row.querySelector('[data-api-save]').disabled=false;state(status[provider]||{configurada:false,armazenamento:'Reabra o app atualizado para ativar este serviço'});}
  }
  row.querySelector('[data-api-save]').onclick=()=>action('salvar');row.querySelector('[data-api-test]').onclick=()=>action('testar');row.querySelector('[data-api-remove]').onclick=()=>action('remover');
 }
 const note=document.createElement('p');note.className='small mute';note.textContent='Testar conexão consulta o serviço sem gerar áudio ou transcrição. Cada colega usa as próprias chaves. As chaves não acompanham os pacotes de atualização.';card.append(note);
};

const settingsBeforeVisualMargin=routes['/ajustes'];
routes['/ajustes']=async()=>{
 await settingsBeforeVisualMargin();const d=await api('/api/ajustes');
 const card=document.createElement('section');card.className='card';card.innerHTML=`<h2>Margem dos takes</h2><p>Estende os takes antes e depois da fala substituída ou da aparição aprovada do produto antigo.</p><label class="f">Margem de cada lado (ms)<input type="number" min="0" max="3000" step="100" value="${Number(d.margem_visual_ms??1500)}"></label><p class="small mute">Padrão de 1.500 ms em cada lado, dentro dos limites de cobertura do projeto. Janelas próximas se unem sem sobrepor takes. Prepare os takes e gere um novo XML após alterar. O fechamento das margens de fala também ajusta as imagens para manter a sincronização.</p><button class="btn pri">Salvar margem visual</button><p role="status"></p>`;
 document.querySelector('#view .page-h').after(card);
 card.querySelector('button').onclick=async()=>{const b=card.querySelector('button');b.disabled=true;try{const value=Number(card.querySelector('input').value);if(!Number.isInteger(value)||value<0||value>3000)throw Error('Informe de 0 a 3000 ms.');await post('/api/ajustes',{margem_visual_ms:value});card.querySelector('[role=status]').textContent='Margem salva. Prepare os takes novamente e gere o XML.';}catch(e){card.querySelector('[role=status]').textContent=e.message;}finally{b.disabled=false;}};
};

const settingsBeforeNotifications = routes['/ajustes'];
routes['/ajustes'] = async () => {
  await settingsBeforeNotifications();
  const heading = document.querySelector('#view .page-h');
  if (location.hash !== '#/ajustes' || !heading) return;
  const card = document.createElement('section');
  card.className = 'card';
  card.innerHTML = '<h2>Notificações de tarefas</h2><p>Receba um aviso do sistema quando uma tarefa demorada terminar ou precisar de atenção, mesmo com outra janela aberta.</p><label class="row"><input type="checkbox" id="task-notifications" disabled> Avisar sobre tarefas demoradas</label><p class="small mute">Vale para o modo manual e automático. O sistema pode silenciar avisos no modo Foco ou quando as notificações estão desativadas.</p><button class="btn" id="task-notifications-test" disabled>Enviar aviso de teste</button><p role="status" id="task-notifications-status"></p>';
  heading.after(card);
  const toggle = card.querySelector('input');
  const test = card.querySelector('button');
  const status = card.querySelector('[role=status]');
  try {
    const data = await api('/api/notificacoes');
    toggle.checked = data.ativo;
    toggle.disabled = !data.disponivel;
    test.disabled = !data.disponivel || !data.ativo;
    if (data.sistema === 'macos') {
      const note = card.querySelector('.small');
      note.textContent += ' No macOS, os avisos são enviados pelo Editor de Scripts e aparecem com o título Ripagem Maker.';
    }
    if (!data.disponivel) status.textContent = 'Os avisos do sistema estão disponíveis no Mac e no Windows.';
  } catch (error) { status.textContent = error.message; return; }

  toggle.onchange = async () => {
    const enabled = toggle.checked;
    toggle.disabled = test.disabled = true;
    try {
      const data = await post('/api/notificacoes', {ativo: enabled});
      toggle.checked = data.ativo;
      status.textContent = data.ativo ? 'Avisos ativados neste computador.' : 'Avisos desativados neste computador.';
    } catch (error) {
      toggle.checked = !enabled;
      status.textContent = error.message;
    } finally {
      toggle.disabled = false;
      test.disabled = !toggle.checked;
    }
  };
  test.onclick = async () => {
    test.disabled = true;
    try {
      await post('/api/notificacoes/teste', {});
      status.textContent = 'Aviso solicitado. Confira a central de notificações do sistema.';
    } catch (error) { status.textContent = error.message; }
    finally { test.disabled = !toggle.checked; }
  };
};

const settingsBeforeGuidedFlow = routes['/ajustes'];
routes['/ajustes'] = async () => {
 await settingsBeforeGuidedFlow();
 const header = document.querySelector('#view .page-h');
 if (!header || !location.hash.startsWith('#/ajustes')) return;
 const card = document.createElement('section');
 card.className = 'card';
 card.innerHTML = '<h2>Fluxo de Troca de potes</h2><label class="f"><span><input type="checkbox"> Incluir prévia no fluxo</span></label><p class="small mute">Com a opção desligada, depois de Takes você pode gerar o XML diretamente; a legenda é opcional. Você pode abrir a prévia na entrega quando precisar.</p>';
 const input = card.querySelector('input');
 const key = 'ripagem.flow.preview';
 input.checked = localStorage.getItem(key) === '1';
 input.onchange = () => localStorage.setItem(key, input.checked ? '1' : '0');
 header.after(card);
};
