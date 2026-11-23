/* Um único decodificador para a revisão inteira, sem controles remotos do macOS. */
(function(root){
 'use strict';
 class Playback {
  constructor(createMedia,changed=()=>{}){this.createMedia=createMedia;this.changed=changed;this.media=null;this.active=null;this.serial=0;this.timeout=null;}
  emit(){if(this.active)this.changed(this.active);}
  init(){
   if(this.media)return this.media;
   const a=this.media=this.createMedia();a.controls=false;a.preload='none';a.disableRemotePlayback=true;
   a.setAttribute('x-webkit-airplay','deny');a.setAttribute('controlslist','noremoteplayback nodownload');
   const update=()=>{if(!this.active)return;this.active.duration=Number.isFinite(a.duration)?a.duration:0;this.active.position=a.currentTime||0;this.emit();};
   a.addEventListener('loadedmetadata',()=>{if(this.active?.position)a.currentTime=Math.min(this.active.position,a.duration||0);update();});a.addEventListener('timeupdate',update);
   a.addEventListener('playing',()=>{clearTimeout(this.timeout);if(this.active){this.active.state='playing';update();}});
   a.addEventListener('ended',()=>{if(this.active){this.active.state='ended';this.active.position=0;this.emit();}});
   a.addEventListener('error',()=>this.fail('Não foi possível ouvir este arquivo. Tente novamente ou baixe o áudio.'));
   return a;
  }
  stop(release=false){
   ++this.serial;clearTimeout(this.timeout);
   if(this.media){if(this.active)this.active.position=this.media.currentTime||0;if(!this.media.paused)this.media.pause();}
   if(this.active){this.active.state='paused';this.emit();this.active=null;}
   if(release&&this.media){this.media.removeAttribute('src');this.media.load();}
  }
  fail(message){if(!this.active)return;const item=this.active;this.stop(true);item.state='error';item.error=message;this.changed(item);}
  async toggle(item){
   if(this.active===item&&(item.state==='playing'||item.state==='loading')){this.stop();return;}
   this.stop();const a=this.init(),token=this.serial;this.active=item;item.error='';item.state='loading';this.emit();
   try{
    if(a.getAttribute('src')!==item.src){a.src=item.src;a.load();}
    if(item.state==='ended'||(a.duration&&item.position>=a.duration))item.position=0;
    // O seek pode aguardar os metadados na primeira carga; reproduzir desde zero é seguro.
    if(a.readyState>0)a.currentTime=item.position||0;
    this.timeout=setTimeout(()=>{if(this.serial===token)this.fail('O áudio demorou para carregar. Tente novamente ou baixe o arquivo.');},15000);
    await a.play();
    if(this.serial!==token)return;
    clearTimeout(this.timeout);item.state='playing';this.emit();
   }catch(error){if(this.serial===token)this.fail(error?.name==='NotAllowedError'?'Clique novamente em Ouvir para iniciar o áudio.':'Não foi possível ouvir este arquivo. Tente novamente ou baixe o áudio.');}
  }
  seek(item,value){item.position=Math.max(0,Math.min(item.duration||0,Number(value)||0));if(this.active===item&&this.media?.readyState>0)this.media.currentTime=item.position;this.changed(item);}
 }
 if(typeof module!=='undefined'&&module.exports){module.exports={Playback};return;}
 const doc=root.document;if(!doc)return;
 const clock=n=>{n=Math.max(0,Math.floor(n||0));return Math.floor(n/60)+':'+String(n%60).padStart(2,'0');};
 const engine=new Playback(()=>doc.createElement('audio'),item=>{
  const loading=item.state==='loading',playing=item.state==='playing';
  item.button.textContent=loading?'Cancelar':playing?'Pausar':'Ouvir';
  item.button.setAttribute('aria-label',loading?'Cancelar carregamento do áudio':playing?'Pausar áudio':'Ouvir áudio');
  item.box.setAttribute('aria-busy',String(loading));item.time.textContent=clock(item.position)+' / '+clock(item.duration);
  item.seek.max=item.duration||1;item.seek.value=item.position||0;item.seek.disabled=!item.duration;
  item.seek.setAttribute('aria-valuetext',clock(item.position)+' de '+clock(item.duration));
  item.status.textContent=item.error||(loading?'Carregando áudio…':'');item.download.hidden=!item.error;
 });
 function mount(container){container.querySelectorAll('[data-audio-placeholder]').forEach(p=>{
  // A revisão revela e monta a frase selecionada. As demais podem continuar leves.
  if(p.closest('[data-swap-row][hidden]'))return;
  const box=doc.createElement('div');box.className='review-audio';box.dataset.audioSrc=p.dataset.audioPlaceholder;
  box.innerHTML='<div class="review-audio-controls"><button type="button" class="ghost">Ouvir</button><input type="range" min="0" max="1" step="0.05" value="0" disabled aria-label="Posição do áudio"><span class="review-audio-time">0:00 / 0:00</span></div><span class="review-audio-status" role="status"></span><a hidden>Baixar áudio</a>';
  const item={src:p.dataset.audioPlaceholder,box,position:0,duration:0,state:'paused',button:box.querySelector('button'),seek:box.querySelector('input'),time:box.querySelector('.review-audio-time'),status:box.querySelector('[role=status]'),download:box.querySelector('a')};
  item.button.setAttribute('aria-label','Ouvir áudio');item.download.href=item.src+(item.src.includes('?')?'&':'?')+'dl=1';
  item.button.onclick=()=>{doc.querySelectorAll('audio,video').forEach(a=>{if(!a.paused)a.pause();});engine.toggle(item);};
  item.seek.oninput=()=>engine.seek(item,item.seek.value);p.replaceWith(box);
 });}
 function hidden(item){if(!item.box.isConnected||item.box.closest('[hidden]'))return true;let node=item.box.parentElement;while(node){if(node.tagName==='DETAILS'&&!node.open)return true;node=node.parentElement;}return false;}
 function release(container){if(engine.active&&container.contains(engine.active.box))engine.stop(true);}
 const observer=new MutationObserver(records=>{
  if(engine.active&&hidden(engine.active))engine.stop(true);
  for(const r of records)for(const n of r.addedNodes||[])if(n.nodeType===1){if(n.matches('[data-audio-placeholder]'))mount(n.parentElement);else if(n.querySelector('[data-audio-placeholder]'))mount(n);}
 });
 observer.observe(doc.body,{subtree:true,childList:true,attributes:true,attributeFilter:['hidden']});
 doc.addEventListener('toggle',()=>{if(engine.active&&hidden(engine.active))engine.stop(true);},true);
 doc.addEventListener('play',e=>{if(e.target.matches('audio,video'))engine.stop();},true);
 root.addEventListener('pagehide',()=>engine.stop(true));
 root.RipagemAudio={mount,release};mount(doc);
})(typeof window!=='undefined'?window:globalThis);
