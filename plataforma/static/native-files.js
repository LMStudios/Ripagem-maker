/* As ações nativas confirmam o destino; downloads normais continuam no navegador/Mac. */
(()=>{
 const notify=(text,error=false)=>{
  let box=document.getElementById('native-file-result');if(!box){box=document.createElement('div');box.id='native-file-result';box.setAttribute('role','status');Object.assign(box.style,{position:'fixed',bottom:'18px',left:'18px',right:'18px',padding:'16px',background:'#202024',color:'#fff',zIndex:9999,border:'1px solid #8870ff',borderRadius:'10px',wordBreak:'break-word'});document.body.append(box);}
  box.replaceChildren(document.createTextNode(text));const close=document.createElement('button');close.textContent='Fechar';close.style.marginLeft='12px';close.onclick=()=>box.remove();box.append(close);box.style.borderColor=error?'#e77979':'#8870ff';
 };
 const bridge=()=>window.ripagemDesktop||window.pywebview?.api;
 const choose=async()=>{try{const d=await bridge().choose_folder();if(!d.ok)throw Error(d.erro);if(!d.cancelado)window.dispatchEvent(new CustomEvent('dr-folder-selected',{detail:d.pasta}));}catch(e){notify('Não foi possível selecionar a pasta: '+e.message,true);}};
 function install(){
  if(!bridge()?.choose_folder)return;
  window.webkit=window.webkit||{};window.webkit.messageHandlers=window.webkit.messageHandlers||{};window.webkit.messageHandlers.chooseStorage={postMessage:choose};
 }
 window.addEventListener('pywebviewready',install);install();
 async function saveWithPicker(address){
  let handle;
  try{
   handle=await window.showSaveFilePicker({suggestedName:decodeURIComponent(address.pathname.split('/').pop())});
  }catch(error){
   if(error.name==='AbortError')return {ok:true,cancelado:true};
   throw error;
  }
  const response=await fetch(address);
  if(!response.ok||!response.body)throw Error('Arquivo não encontrado.');
  await response.body.pipeTo(await handle.createWritable());
  return {ok:true,arquivo:handle.name};
 }
 async function finishStudio(project,xml,download){
  const response=await fetch('/fatiador/trocas/studio-tempo',{
   method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({folder:project,xml_salvo:xml,...(download?{copiar_para_downloads:download}:{})}),keepalive:true
  });
  const summary=await response.json();
  if(!response.ok||!summary.medicao_encerrada)throw Error(summary.erro||'Não foi possível registrar a conclusão.');
  document.dispatchEvent(new CustomEvent('ripagem:studio-saved',{detail:{folder:project,summary}}));
  return summary;
 }
 document.addEventListener('click',async e=>{
  const a=e.target.closest('a');if(!a||!a.href)return;
  const address=new URL(a.href,location.href);
  if(address.origin!==location.origin||!address.pathname.startsWith('/files/')||(!a.hasAttribute('download')&&address.searchParams.get('dl')!=='1'))return;
  const saver=bridge(),xml=a.dataset.studioXml;
  const classicMac=!!(xml&&!saver?.save_file&&window.webkit?.messageHandlers?.chooseStorage);
  if(!saver?.save_file&&!(xml&&(classicMac||window.showSaveFilePicker)))return;
  const [, ,encodedProject,...file]=address.pathname.split('/');
  const project=xml?decodeURIComponent(encodedProject):null;
  e.preventDefault();if(a.dataset.saving)return;
  a.dataset.saving='1';a.setAttribute('aria-busy','true');notify('Escolha onde salvar a cópia…');
  try{
   if(classicMac){
    const result=await finishStudio(project,xml,file.map(decodeURIComponent).join('/'));
    notify('Cópia salva em '+result.destino+'. Tempo finalizado.');
    return;
   }
   const result=saver?.save_file?await saver.save_file(a.href):await saveWithPicker(address);
   if(!result.ok)throw Error(result.erro);
   if(result.cancelado){notify('Salvamento cancelado. O original continua na pasta do trabalho.');return;}
   const saved='Cópia salva em '+result.arquivo;
   if(!project){notify(saved);return;}
   try{await finishStudio(project,xml);notify(saved+'. Tempo finalizado.');}
   catch(error){notify(saved+'. A medição ainda não foi encerrada. '+error.message,true);}
  }catch(error){notify('Não foi possível salvar. '+error.message+' O original continua na pasta do trabalho.',true);}
  finally{delete a.dataset.saving;a.removeAttribute('aria-busy');}
 },true);
})();
