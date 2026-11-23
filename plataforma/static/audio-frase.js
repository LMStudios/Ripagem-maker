/* Importação local por frase: não muda a etapa e não chama serviços de voz. */
(()=>{
 const U=window.SwapUX,workspace=document.querySelector('.ux-workspace');if(!U||!workspace)return;
 const note=document.createElement('p');note.className='phrase-import-help meta';note.textContent='Já tem a gravação? Arraste um áudio sobre a frase na lista ou no texto aberto. Um arquivo por vez, até 50 MB.';
 const status=document.createElement('p');status.className='phrase-import-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');status.hidden=true;
 workspace.before(note,status);
 let target=null;
 const clear=()=>{target?.classList.remove('phrase-audio-over');target=null;};
 const rowFor=e=>e.target?.closest?.('[data-ux-row],[data-swap-row]');
 const isFile=e=>Array.from(e.dataTransfer?.types||[]).includes('Files');
 const message=text=>{status.textContent=text;status.hidden=false;};
 document.addEventListener('dragover',e=>{
  const row=rowFor(e);if(!row||!isFile(e))return;
  e.preventDefault();e.stopPropagation();e.dataTransfer.dropEffect=U.busy?'none':'copy';
  if(target!==row){clear();target=row;row.classList.add('phrase-audio-over');}
 },true);
 document.addEventListener('dragleave',e=>{if(target&&!target.contains(e.relatedTarget))clear();},true);
 document.addEventListener('dragend',clear,true);
 document.addEventListener('drop',e=>{
  const row=rowFor(e);if(!row)return;
  const files=Array.from(e.dataTransfer?.files||[]);if(!files.length&&!isFile(e))return;
  e.preventDefault();e.stopImmediatePropagation();clear();
  if(U.busy){message('Aguarde a tarefa atual terminar para importar outro áudio.');return;}
  if(files.length!==1){message('Arraste apenas um arquivo de áudio para cada frase.');return;}
  U.importAudio(row.dataset.uxRow||row.dataset.swapRow,files[0]);
 },true);
 document.addEventListener('swap:import-status',e=>{if(e.detail.folder===folder)message(e.detail.message);});
 document.addEventListener('swap:finished',e=>{
  if(e.detail.origin!=='audio-import')return;
  const index=U.plan?.itens.findIndex(r=>r.id===e.detail.rowId);
  message(e.detail.status==='concluido'?'Gravação importada'+(index>=0?' na frase '+(index+1):'')+'. Ouça e aprove o áudio antes de continuar.':'A importação não foi concluída. Confira o aviso e tente novamente.');
 });
 let work=folder;document.addEventListener('swap:render',()=>{clear();if(work!==folder){work=folder;status.hidden=true;}});
})();
