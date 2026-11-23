/* Os metadados da entrega não mudam textos, vozes nem cortes. */
(()=>{
 const $=id=>document.getElementById(id),U=window.SwapUX;if(!U||!$('wizard-slot-1'))return;
 const empty={numero_vsl:'',copy:'',editor:'',pitch_manual:''};
 const legacyDraftKey='ripagem.delivery.draft';
 let draftKey=legacyDraftKey, profileCode='', editorEdited=false;
 let config=readDraft(),scope='',dirty=false,newSource=false,pitch='A IDENTIFICAR',saving=false;
 const isDraft=()=>!folder||newSource;
 const cards=[];

 function readDraft(){
  try{return {...empty,...JSON.parse(sessionStorage.getItem(draftKey)||'{}')};}
  catch{return {...empty};}
 }

 function applyProfile(session){
  const profile=session?.perfil;
  if(!profile?.codigo)return;
  const key=legacyDraftKey+'.'+(profile.id||profile.codigo);
  if(key!==draftKey){
   draftKey=key;
   if(isDraft()&&!dirty){
    config=readDraft();
    editorEdited=!!config.editor;
   }
  }
  profileCode=profile.codigo;
  if(isDraft()&&!editorEdited){config.editor=profileCode;render();}
 }

 function beginDraft(){
  if(profileCode&&folder&&!newSource){
   config=readDraft();
   editorEdited=!!config.editor;
   dirty=false;
  }
  newSource=true;
  if(profileCode&&!editorEdited)config.editor=profileCode;
  pitch='A IDENTIFICAR';
  render();
 }
 function card(where,suffix){
  const box=document.createElement('section');box.className='card delivery-identity';box.innerHTML=`<h3>Identificação da entrega</h3><p class="meta">Preencha desde o início. Estes dados serão usados no nome da sequência e do XML para o Premiere.</p><label>Produto novo para esta VSL<input id="delivery-product-${suffix}" maxlength="100" placeholder="Ex.: Nervelin"></label><div class="row"><label>Número da VSL<input id="delivery-number-${suffix}" type="number" min="1" max="999" placeholder="Ex.: 01"></label><label>Copy para revisão<input id="delivery-copy-${suffix}" maxlength="80" list="delivery-copy-list" placeholder="Código ou nome do copy"></label><label>Editor<input id="delivery-editor-${suffix}" maxlength="80" list="delivery-editor-list" placeholder="Código ou nome do editor"></label></div><details><summary>Já sei o pitch · preenchimento manual opcional</summary><label>Pitch confirmado (mm:ss ou hh:mm:ss)<input id="delivery-pitch-${suffix}" placeholder="Vazio = usar pitch da transcrição"></label><p class="meta">A identificação automática considera a primeira menção ao preço da oferta de seis potes na transcrição e recalcula o tempo após a montagem. DELAY não é usado como pitch. Um tempo preenchido aqui terá prioridade e será registrado como manual.</p></details><p class="meta">Nome previsto da sequência</p><p data-delivery-preview style="overflow-wrap:anywhere;font-weight:600"></p><p class="meta" data-delivery-pitch></p><button class="ghost" data-delivery-save>Salvar dados da entrega</button><p role="status" class="meta" data-delivery-status></p>`;
  where.append(box);cards.push({box,suffix});
  for(const [key,field] of [['numero_vsl','number'],['copy','copy'],['editor','editor'],['pitch_manual','pitch']])$('delivery-'+field+'-'+suffix).addEventListener('input',()=>{config[key]=$('delivery-'+field+'-'+suffix).value;if(key==='editor')editorEdited=true;dirty=true;persist();render();});
  $('delivery-product-'+suffix).addEventListener('input',()=>{if(folder&&!newSource)return;$('novo').value=$('delivery-product-'+suffix).value;$('novo').dispatchEvent(new Event('input',{bubbles:true}));});
  box.querySelector('[data-delivery-save]').onclick=save;
  return box;
 }
 const setup=card($('wizard-slot-1'),'setup');$('drop').closest('section').after(setup);
 card($('wizard-slot-4'),'finish');
 const lists=document.createElement('div');lists.innerHTML='<datalist id="delivery-copy-list"></datalist><datalist id="delivery-editor-list"></datalist>';document.body.append(lists);
 fetch('/api/demanda/catalogo').then(r=>r.json()).then(d=>{for(const [id,rows] of [['delivery-copy-list',d.copy],['delivery-editor-list',d.editores]])for(const [code,name] of Object.entries(rows||{})){const option=document.createElement('option');option.value=code;option.label=name;$(id).append(option);}}).catch(()=>{});
 function persist(){
  if(profileCode&&!isDraft())return;
  const draft=profileCode&&!editorEdited?{...config,editor:''}:config;
  sessionStorage.setItem(draftKey,JSON.stringify(draft));
 }
 function capture(){
  const n=String(config.numero_vsl).trim();if(n&&(!/^\d{1,3}$/.test(n)||Number(n)<1||Number(n)>999))throw Error('Número da VSL: use um valor entre 1 e 999.');
  config.pitch_manual=String(config.pitch_manual||'').trim().replace(/_/g,':');
  if(config.pitch_manual&&!/^\d{1,3}:[0-5]\d(?::[0-5]\d)?$/.test(config.pitch_manual.trim()))throw Error('Pitch manual: use mm:ss ou hh:mm:ss.');
  persist();render();return {...config};
 }
 function preview(){const n=String(config.numero_vsl||'').trim(),product=(folder&&!newSource?U.plan?.produto_novo:$('novo').value)||'';return 'FUNIL VSL '+(n?n.padStart(2,'0'):'XX')+' MOD - '+(product.trim().toUpperCase()||'PRODUTO A DEFINIR')+' - '+(config.copy.trim().toUpperCase()||'COPY A DEFINIR')+' - '+(config.editor.trim().toUpperCase()||'EDITOR A DEFINIR')+' - PITCH '+(config.pitch_manual||pitch);}
 function render(){
  for(const {box,suffix} of cards){
   for(const [key,field] of [['numero_vsl','number'],['copy','copy'],['editor','editor'],['pitch_manual','pitch']]){const e=$('delivery-'+field+'-'+suffix);if(document.activeElement!==e)e.value=config[key]||'';}
   const e=$('delivery-product-'+suffix);e.readOnly=!!folder&&!newSource;if(document.activeElement!==e)e.value=(folder&&!newSource?U.plan?.produto_novo:$('novo').value)||'';
   box.querySelector('[data-delivery-preview]').textContent=preview();box.querySelector('[data-delivery-pitch]').textContent=config.pitch_manual?'Pitch preenchido manualmente.':pitch==='A IDENTIFICAR'?'Pitch para confirmar. Veja o resultado da transcrição na etapa Falas.':'Pitch da oferta de seis potes na montagem: '+pitch;
   box.querySelector('[data-delivery-save]').disabled=saving||U.busy;box.querySelector('[data-delivery-save]').textContent=suffix==='finish'&&U.plan?.entrega?'Salvar dados e atualizar nome do XML':'Salvar dados da entrega';
  }
 }
 async function call(body){const r=await fetch('/fatiador/trocas/nomenclatura',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder,...body})});const d=await r.json();if(!r.ok)throw Error(d.erro||'Não foi possível salvar a identificação.');return d;}
 async function save(){if(saving)return;saving=true;render();try{const cfg=capture();if(folder&&!newSource){if(await U.flushDraft()===false||U.hasDraft())throw Error('Salve as alterações das falas antes de ajustar a entrega.');await U.save();const d=await call({salvar:true,config:cfg});config=d.config;pitch=d.origem_pitch==='manual_confirmado'?'A IDENTIFICAR':d.pitch;if(d.plano)U.acceptPlan(d.plano);if(d.plano?.entrega){const result=await U.call('renomear-entrega');document.dispatchEvent(new CustomEvent('delivery:renamed',{detail:result}));} }dirty=false;persist();for(const {box} of cards)box.querySelector('[data-delivery-status]').textContent=folder&&!newSource?'Dados salvos. Quando havia uma entrega atual, foi criada uma nova cópia do XML com o nome atualizado. As falas e os áudios continuam iguais.':'Dados guardados para a próxima transcrição.';}catch(e){for(const {box} of cards)box.querySelector('[data-delivery-status]').textContent=e.message;}finally{saving=false;render();}}
 let request=0;
 document.addEventListener('swap:render',async()=>{if(!U.plan)return;const changed=scope!==folder;if(changed){if(profileCode&&newSource)sessionStorage.removeItem(draftKey);scope=folder;dirty=false;newSource=false;config={...empty};}if(!dirty&&!newSource)config={...config,...(U.plan.nomenclatura||{})};render();const rev=++request,work=folder;try{const d=await call({});if(work!==folder||rev!==request)return;if(!dirty&&!newSource)config=d.config;pitch=d.origem_pitch==='manual_confirmado'?'A IDENTIFICAR':d.pitch;render();}catch(e){if(work===folder)for(const {box} of cards)box.querySelector('[data-delivery-status]').textContent=e.message;}});
 document.addEventListener('ripagem:pitch-ready',async()=>{if(!folder||newSource||dirty)return;const work=folder;try{const d=await call({});if(work===folder){pitch=d.origem_pitch==='manual_confirmado'?'A IDENTIFICAR':d.pitch;render();}}catch(e){for(const {box} of cards)box.querySelector('[data-delivery-status]').textContent=e.message;}});
 document.addEventListener('ripagem:source-selected',beginDraft);
 document.addEventListener('ripagem:new-project-draft',()=>{if(profileCode)beginDraft();});
 document.addEventListener('ripagem:equipe-sessao',event=>applyProfile(event.detail));
 document.addEventListener('swap:state',render);$('novo').addEventListener('input',render);
 window.RipagemNaming={capture};applyProfile(window.RipagemEquipe?.sessao);render();
})();
