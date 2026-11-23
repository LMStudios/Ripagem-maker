/* Entrada de demandas e nomes VTurb. Tempos explícitos dispensam transcrição. */
let demandaCatalogo;
const catalogo = async () => demandaCatalogo ||= await api('/api/demanda/catalogo');
function nomeFields(c, prefix='n') {
  const select = (key, entries, selected) => `<label class="f">${key==='copy'?'Copywriter':'Editor'}<select id="${prefix}-${key}"><option value="">Selecione</option>${Object.entries(entries).map(([v,n])=>`<option value="${v}" ${v===selected?'selected':''}>${v} · ${esc(n)}</option>`).join('')}</select></label>`;
  return `<div class="row"><label class="f">Tipo<select id="${prefix}-tipo">${[['vsl','VSL'],['ml','Microlead'],['mod','Ripagem MOD'],['mod_ml','Ripagem MOD + ML'],['upsell','Upsell'],['close','Novos closes']].map(([v,t])=>`<option value="${v}">${t}</option>`).join('')}</select></label>
  ${[['produto','Produto',''],['vsl','VSL','01'],['lead','Lead','01'],['versao','Versão','1'],['ml','Número da ML',''],['alteracao','Alteração / característica',''],['upsell','Upsell','01'],['fluxo','Fluxo (opcional)',''],['pitch','Pitch · preço dos 6 potes (mm:ss)',''],['original','Nome original (novos closes)','']].map(([k,t,v])=>`<label class="f">${t}<input type="text" id="${prefix}-${k}" value="${v}" ${['produto','alteracao','original','pitch'].includes(k)?'':'inputmode="numeric"'}></label>`).join('')}
  ${select('copy',c.copy,'')}${select('editor',c.editores,'EV8')}</div>`;
}
function readName(prefix='n') {
  return Object.fromEntries(['tipo','produto','vsl','lead','versao','ml','alteracao','upsell','fluxo','pitch','original','copy','editor'].map(k=>[k,$(`#${prefix}-${k}`).value]));
}
function bindName(prefix='n') {
  const update=()=>{
    const kind=$(`#${prefix}-tipo`).value;
    const keys = kind==='close'?['original']:kind==='upsell'?['produto','versao','alteracao','upsell','fluxo','pitch','copy','editor']:
      ['produto','vsl','copy','editor','pitch',...(kind.startsWith('mod')?[]:['lead','versao','alteracao']),...(['ml','mod_ml'].includes(kind)?['ml']:[])];
    for(const k of ['produto','vsl','lead','versao','ml','alteracao','upsell','fluxo','pitch','original','copy','editor']) $(`#${prefix}-${k}`).closest('label').hidden=!keys.includes(k);
  };
  $(`#${prefix}-tipo`).onchange=update; update();
}
routes['/nomes']=async()=>{
  const c=await catalogo();
  $('#view').innerHTML=`<div class="page-h"><div><h1>Nomenclatura VTurb</h1><p>Selecione o padrão e preencha os dados. Editor padrão: EV8 · Luiz Miguel.</p></div></div><div class="card">${nomeFields(c)}<button class="btn pri" id="nome-gerar">Gerar nome</button><p id="nome-erro" role="alert"></p><textarea id="nome-saida" rows="3" readonly aria-label="Nome gerado" style="width:100%"></textarea><button class="btn" id="nome-copiar">Copiar nome</button><p class="small mute">O nome mantém o pitch com dois-pontos e os closes como 1/3/6. Nos arquivos, caracteres de caminho são substituídos por hífens.</p></div>`;
  bindName();
  $('#nome-gerar').onclick=async()=>{try {$('#nome-saida').value=(await post('/api/demanda/nome',readName())).nome;$('#nome-erro').textContent='';}catch(e){$('#nome-saida').value='';$('#nome-erro').textContent=e.message;}};
  $('#nome-copiar').onclick=async()=>{try{await navigator.clipboard.writeText($('#nome-saida').value);toast('Nome copiado.');}catch(e){toast('Selecione e copie o nome no campo.',true);}};
};
let demandaPlano=null;
routes['/demanda']=async()=>{
  $('#view').innerHTML=`<div class="page-h"><div><h1>Microlead’s</h1><p>Cole a solicitação com links numerados ou no formato “pegar essa ML e plugar nessa VSL”.</p></div></div>
  <div class="card"><label class="f">Solicitação completa<textarea id="d-texto" rows="10" placeholder="VSL: https://…\nDELAY: 58:40\n1. https://… (pegar essa ML até 1:32 e trocar pela da VSL que termina em 1:57)"></textarea></label><button class="btn pri" id="d-ler">Interpretar demanda</button><button class="btn" id="d-manual">Preencher manualmente</button><p class="small mute">Aceita MP4, playlists HLS (.m3u8) de vídeos completos e arquivos compartilhados do Google Drive. O link da página serve apenas como referência; a montagem usa os links de vídeo da explicação.</p></div><p><a class="btn" href="#/microlead">Montar com arquivos locais</a></p><div id="d-plano"></div><div id="d-jobs"></div>`;
  $('#d-texto').value=ls.get('dr.demanda.texto','');
  $('#d-ler').onclick=async()=>{try{ls.set('dr.demanda.texto',$('#d-texto').value);demandaPlano=await post('/api/demanda/interpretar',{texto:$('#d-texto').value});await showPlan();$('#d-plano').scrollIntoView({block:'start',behavior:'smooth'});}catch(e){toast(e.message,true);}};
  $('#d-manual').onclick=async()=>{demandaPlano={variacoes:[{}],avisos:[]};await showPlan();};
  if(demandaPlano) await showPlan();
  await demandaJobs();
  pollTimer=setInterval(()=>demandaJobs().catch(()=>{}),2000);
};
async function showPlan(){
  const p=demandaPlano,c=await catalogo();
  $('#d-plano').innerHTML=`<div class="card" style="margin-top:18px"><h2>Confira a direção da troca</h2><div id="d-resumo-montagem" class="banner" style="display:block"></div>${(p.observacoes||[]).map(a=>`<p class="small mute">${esc(a)}</p>`).join('')}${p.nicho||p.prazo?`<p class="small mute">${esc(p.nicho||'')}${p.prazo?' · Prazo informado: '+esc(p.prazo):''}</p>`:''}${(p.avisos||[]).map(a=>`<p class="banner">${esc(a)}</p>`).join('')}
  <div class="row">${[['base_url','VSL de destino · manter o restante deste vídeo'],['corte_original','Começar o restante da VSL em (mm:ss)'],['delay','DELAY recebido (referência)'],['pitch','Primeiro preço dos 6 potes na VSL original (mm:ss)'],['titulo','Título para arquivos sem nomenclatura']].map(([k,t])=>`<label class="f">${t}<input type="text" id="d-${k}" value="${esc(p[k]||'')}"></label>`).join('')}</div>
  <label><input type="checkbox" id="d-ajustar" ${p.ajustar_pitch!==false?'checked':''}> Ajustar o pitch informado conforme a duração da ML</label>
  <p class="small mute">Cada saída usa 00:00 até o fim da nova ML + o restante da VSL a partir do corte original, sem transição. Pitch é a primeira menção ao valor da oferta de 6 potes. Valores como 29 e 49 são pistas; confirme o contexto. DELAY não preenche o pitch automaticamente. Pitch ajustado = pitch original − lead removida + nova ML.</p>
  <div class="card" style="margin:16px 0"><label><input type="checkbox" id="d-validar" checked> Validar a transcrição e detectar o pitch em cada vídeo final</label><label class="f" style="margin-top:10px">Produto antigo e grafias alternativas (separe por vírgula)<input type="text" id="d-termos" placeholder="Ex.: NerveTin, Nerve Tin"></label><p class="small mute">Sem termos, será feita apenas a busca do pitch. A validação usa Whisper local e aumenta o tempo de processamento. O preço deve estar associado à oferta de 6 potes; valores isolados ficam para revisão. ${auditSelectors('d')}</p></div><div id="d-vars"></div><button class="btn" id="d-add">Adicionar variação</button>
  <details style="margin-top:18px"><summary>Gerar nomenclatura padronizada (opcional)</summary><p class="small mute">Sem produto preenchido, o arquivo usa o título e o número da variação. Para nomes com ML, informe a identificação de cada ML abaixo.</p>${nomeFields(c,'dn')}</details>
  <label class="f" style="margin-top:18px">O que entregar<select id="d-entrega"><option value="video">Vídeos prontos</option><option value="xml">Somente XML editável para Premiere</option><option value="ambos">Vídeos + XMLs para Premiere</option></select></label><p class="small mute">O XML importa as fontes e monta ML + body com cortes secos, sem renderizar nem aplicar fades. No Premiere: Arquivo → Importar (⌘I), escolha o XML e abra “DR ML + Body”. Não mova os vídeos de origem.</p><p id="d-error" role="alert"></p><button class="btn pri" id="d-run">Gerar todas as versões</button></div>`;
  $('#d-entrega').value=p.entrega||'video';
  $('#d-entrega').onchange=()=>{const only=$('#d-entrega').value==='xml';$('#d-validar').disabled=only;if(only)$('#d-validar').checked=false;};$('#d-entrega').onchange();
  $('#dn-tipo').value='mod_ml';bindName('dn');
  function addRow(item={}){
    const row=document.createElement('div'); row.className='row';row.style.marginTop='12px';row.dataset.variacao='1';
    row.innerHTML=`<label class="f">Vídeo de origem da nova ML<input type="text" data-url value="${esc(item.url||'')}"></label><label class="f">Fim da nova ML (mm:ss)<input type="text" data-fim value="${esc(item.fim||'')}"></label><label class="f">Número da ML (para nomenclatura)<input type="text" data-ml value="${esc(item.ml||'')}"></label><button class="btn" data-remove>Remover</button>`;
    $('[data-remove]',row).onclick=()=>{row.remove();summary();};row.addEventListener('input',summary);$('#d-vars').append(row);
  }
  (p.variacoes.length?p.variacoes:[{}]).forEach(addRow);$('#d-add').onclick=()=>{addRow();summary();};
  function summary(){const cut=$('#d-corte_original').value.trim(),base=$('#d-base_url').value.trim();$('#d-resumo-montagem').innerHTML=$$('[data-variacao]').map((row,i)=>{const end=$('[data-fim]',row).value.trim(),lead=$('[data-url]',row).value.trim();return `<p><b>Variação ${String(i+1).padStart(2,'0')}</b></p><p>1. Nova ML: <b>00:00 → ${esc(end||'definir fim')}</b><br><span class="small mono">${esc(lead||'definir vídeo de origem')}</span></p><p>2. Restante da VSL: <b>${esc(cut||'definir corte')} → final</b><br><span class="small mono">${esc(base||'definir VSL de destino')}</span></p>`;}).join('')||'Adicione uma variação para conferir a montagem.';}
  for(const id of ['d-corte_original','d-base_url'])$('#'+id).addEventListener('input',summary);summary();
  $('#d-run').onclick=async()=>{
    const btn=$('#d-run');btn.disabled=true;
    try{
      const plan=Object.fromEntries(['base_url','corte_original','delay','pitch','titulo'].map(k=>[k,$(`#d-${k}`).value.trim()]));
      plan.entrega=$('#d-entrega').value;plan.ajustar_pitch=$('#d-ajustar').checked && Boolean(plan.pitch);plan.nomenclatura=readName('dn');plan.validacao={ativo:$('#d-validar').checked,termos:$('#d-termos').value,motor:$('#d-a-motor').value,idioma:$('#d-a-idioma').value};
      plan.variacoes=$$('[data-variacao]').map(row=>Object.fromEntries(['url','fim','ml'].map(k=>[k,$(`[data-${k}]`,row).value.trim()])));
      await post('/api/demanda/executar',plan);demandaPlano=plan;$('#d-error').textContent='';toast('Demanda adicionada à fila.');await demandaJobs();
    }catch(e){$('#d-error').textContent=e.message;}finally{btn.disabled=false;}
  };
}
function progressHTML(j){
  if(!['executando','na_fila'].includes(j.status))return `<p>${esc(j.step)}</p>`;
  const p=j.progresso,step=j.step||'Processando',context=j.contexto;
  const download=p?.fase==='download'||/^(Baixando|Conectando para baixar)/.test(step);
  const indeterminate=j.status==='na_fila'||(p?p.indeterminado:(download||!j.pct));
  const pct=Math.max(0,Math.min(100,Math.round((j.pct||0)*100)));
  const label=p?.rotulo||(step.startsWith('Validação:')?'Validação':step.startsWith('Renderizando')?'Renderização':'Etapa atual');
  return `<div class="job-progress" role="status"><p><span class="job-spinner" aria-hidden="true"></span>${esc(context?context+' · ':'')}${esc(step)}</p>
    ${indeterminate?`<div class="job-meter unknown" aria-label="Processamento em andamento"><i></i></div><span class="small mute">${download?'Recebendo o arquivo; o progresso aparece em MB.':'Aguarde, esta etapa está em andamento.'}</span>`:`<div class="job-meter" role="progressbar" aria-label="${esc(label)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><i style="width:${pct}%"></i></div><span class="small mute">${pct}% desta etapa · ${esc(label)}</span>`}</div>`;
}
async function demandaJobs(){
  if(!$('#d-jobs'))return;
  const jobs=(await api('/api/ml/jobs')).filter(j=>j.kind==='demanda');
  const signature=JSON.stringify(jobs);if($('#d-jobs').dataset.signature===signature)return;$('#d-jobs').dataset.signature=signature;
  $('#d-jobs').innerHTML=jobs.map(j=>`<div class="card" style="margin-top:18px"><h3>${chip(j.status)} ${esc(j.title)}</h3>${progressHTML(j)}${j.error?`<p role="alert">${esc(j.error)}</p>`:''}${['na_fila','executando'].includes(j.status)?`<button class="btn" data-cancel="${j.id}">Cancelar</button>`:''}${(j.result?.versoes||[]).map(v=>`<p><b>${esc(v.nomenclatura)}</b><br>${v.arquivo?`<a class="btn sm" target="_blank" href="/media/out/${encodeURIComponent(v.arquivo)}">Assistir</a> <a class="btn sm" href="/media/out/${encodeURIComponent(v.arquivo)}?dl=1">Baixar vídeo</a>`:''} ${v.xml?`<a class="btn pri sm" href="/media/out/${encodeURIComponent(v.xml)}?dl=1">Salvar XML para Premiere</a>`:''}</p>${v.validacao?auditHTML(v.validacao):v.erro_validacao?`<p class="banner err">A validação falhou: ${esc(v.erro_validacao)}. O vídeo continua disponível; use a análise avulsa para tentar novamente.</p>`:""}`).join('')}${j.result?.manifesto?`<a href="/media/out/${encodeURIComponent(j.result.manifesto)}?dl=1">Baixar relatório com nomes e cortes</a>`:''}</div>`).join('');
  $$('[data-cancel]').forEach(b=>b.onclick=async()=>{await post(`/api/ml/job/${b.dataset.cancel}/cancelar`);await demandaJobs();});
}

function auditSelectors(prefix){return `<span class="row"><label class="f">Idioma<select id="${prefix}-a-idioma"><option value="auto">Detectar idioma</option><option value="en">Inglês</option><option value="pt">Português</option><option value="es">Espanhol</option></select></label><label class="f">Motor local<select id="${prefix}-a-motor"><option value="mlx">Whisper MLX (GPU)</option><option value="fw">faster-whisper (CPU)</option></select></label></span>`;}
function auditHTML(r){
  const link=(ext,label)=>r.exports?.[ext]?`<a class="btn sm" href="/media/out/${encodeURIComponent(r.exports[ext])}?dl=1">${label}</a>`:'';
  return `<div class="card" style="margin:12px 0"><h3>Validação da transcrição</h3><p>${r.validacao_produto==='nao_configurada'?'Produto antigo não configurado: nenhuma verificação de resquícios foi feita.':r.resquicios.length?`${r.resquicios.length} menção(ões) para conferir e trocar.`:'Nenhuma menção encontrada aos termos informados. Confira também o áudio.'}</p>
  <p><b>Pitch:</b> ${r.pitch?`${fmt(r.pitch.tempo)} · valor ${esc(r.pitch.valor)} · primeira ocorrência com contexto reconhecido de 6 potes`:'Pendente — '+(r.candidatos_pitch.length?'há candidatos que precisam de revisão.':'nenhum preço com contexto suficiente foi encontrado.')}</p>
  ${r.resquicios.length?`<table class="t"><tr><th>Trecho</th><th>Ocorrência</th><th>Frase a revisar</th></tr>${r.resquicios.map(h=>`<tr><td class="mono">${fmt(h.inicio)}–${fmt(h.fim)}</td><td>${esc(h.termo)}<br>${h.status==='revisar'?'Grafia parecida · revisar':'Termo encontrado'}</td><td>${esc(h.texto)}</td></tr>`).join('')}</table>`:''}
  ${r.candidatos_pitch.length?`<details><summary>Conferir candidatos de pitch (${r.candidatos_pitch.length})</summary>${r.candidatos_pitch.map(c=>`<p><b>${fmt(c.tempo)} · ${esc(c.valor)}</b> · ${c.status==='contexto_6_potes'?'Com contexto de 6 potes':'Revisar contexto'}<br>${esc(c.contexto)}</p>`).join('')}</details>`:''}
  <p>${link('json','Relatório JSON')}${link('jsx','Marcadores JSX')}${link('xml','Sequência XML')}${link('cortes','XML com cortes automáticos')}</p><p class="small">${r.cortes_automaticos?`${r.cortes_automaticos.trechos} trecho(s) separado(s) em vídeo e áudio no XML com cortes. Todo o conteúdo é preservado. Grafias parecidas ficam apenas marcadas para revisão.`:""}</p><p class="small mute">${esc(r.observacao)} Tempos desde o início do arquivo analisado. No Premiere: importe o XML para criar uma sequência nova com o vídeo e marcadores, ou execute o JSX em um host ExtendScript/CEP com a sequência correta aberta. O JSX pergunta onde o arquivo começa na sequência. Ele pressupõe o vídeo contínuo, sem cortes, retiming ou trechos reorganizados.</p></div>`;
}
routes['/validacao']=async()=>{
  const videos=await api('/api/ml/videos');
  $('#view').innerHTML=`<div class="page-h"><div><h1>Validar produto e pitch</h1><p>Analise um vídeo isolado, confira resquícios do produto antigo e exporte os trechos para o Premiere.</p></div></div><div class="card">
  <label class="f">Produto antigo e grafias alternativas<input type="text" id="a-termos" placeholder="Ex.: NerveTin, Nerve Tin"></label><p class="small mute">Informe todos os nomes antigos que devem sair. Deixe vazio para localizar apenas o pitch.</p>
  <label class="f">Arquivo do computador<input type="file" accept="video/*" id="a-file"></label><p class="small mute">Ou escolha um vídeo da biblioteca ou informe um link:</p>
  <label class="f">Biblioteca<select id="a-video"><option value="">Selecione</option>${videos.map(v=>`<option value="${esc(v.id)}">${esc(v.nome)}</option>`).join('')}</select></label>
  <label class="f">Link Drive compartilhado ou arquivo direto<input type="text" id="a-url" placeholder="https://…"></label>
  ${auditSelectors('a')}<p class="small mute">Pitch = primeira menção ao preço dos 6 potes. 29 e 49 são pistas, sem substituírem o contexto. A transcrição é local e pode levar alguns minutos.</p>
  <button class="btn pri" id="a-run">Transcrever, validar e gerar marcadores</button><p id="a-error" role="alert"></p></div><div id="a-jobs"></div>`;
  $('#a-run').onclick=async()=>{
    const button=$('#a-run');button.disabled=true;
    try{
      const file=$('#a-file').files[0],video=$('#a-video').value,url=$('#a-url').value.trim(),termos=$('#a-termos').value,motor=$('#a-a-motor').value,idioma=$('#a-a-idioma').value;
      if([Boolean(file),Boolean(video),Boolean(url)].filter(Boolean).length!==1)throw Error('Escolha somente uma fonte: arquivo, biblioteca ou link.');
      if(file) await api('/api/validacao/upload',{method:'POST',headers:{'X-Filename':encodeURIComponent(file.name),'X-Termos':encodeURIComponent(termos),'X-Motor':motor,'X-Idioma':idioma},body:file});
      else await post('/api/validacao',{video,url,termos,motor,idioma});
      $('#a-error').textContent='';toast('Validação adicionada à fila.');await auditJobs();
    }catch(e){$('#a-error').textContent=e.message;}finally{button.disabled=false;}
  };
  await auditJobs();pollTimer=setInterval(()=>auditJobs().catch(()=>{}),2500);
};
async function auditJobs(){
  if(!$('#a-jobs'))return;
  const jobs=(await api('/api/ml/jobs')).filter(j=>j.kind==='validacao');
  const signature=JSON.stringify(jobs);if($('#a-jobs').dataset.signature===signature)return;$('#a-jobs').dataset.signature=signature;
  $('#a-jobs').innerHTML=jobs.map(j=>`<div class="card" style="margin-top:18px"><h3>${chip(j.status)} ${esc(j.title)}</h3>${progressHTML(j)}${j.error?`<p class="banner err" role="alert">${esc(j.error)}</p>`:''}${j.result?.validacao?auditHTML(j.result.validacao):''}${['executando','na_fila'].includes(j.status)?`<button class="btn" data-a-cancel="${j.id}">Cancelar</button>`:''}</div>`).join('');
  $$('[data-a-cancel]').forEach(b=>b.onclick=async()=>{await post(`/api/ml/job/${b.dataset.aCancel}/cancelar`);await auditJobs();});
}
