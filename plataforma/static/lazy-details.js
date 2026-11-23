/* Cria controles de mídia somente quando a pessoa abre o trecho. */
(function(root){
 function mount(details,render){
  let mounted=false,pending=false;
  const schedule=root.requestAnimationFrame||((fn)=>setTimeout(fn,0));
  function toggle(){
   if(!details.open){details.querySelectorAll('video,audio').forEach(media=>media.pause());return;}
   if(mounted||pending)return;
   pending=true;schedule(()=>{pending=false;if(!details.open||mounted)return;mounted=true;try{render();}catch(error){mounted=false;throw error;}});
  }
  details.addEventListener('toggle',toggle);if(details.open)toggle();
 }
 const api={mount};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.TakeLazy=api;
})(typeof window!=='undefined'?window:globalThis);
