/* Salva apenas alterações reais: uma tela antiga não reenvia todos os IDs de um plano recalculado. */
(function(root){
 function kit(value){return value==null||value===''||Number(value)===0?null:Number(value);}
 function changes(previous,draft){
  const assets=new Map((previous?.assets||[]).map(a=>[a.id,a]));
  const mentions=new Map((previous?.mentions||[]).map(r=>[r.id,r]));
  return {...draft,
   assets:(draft.assets||[]).filter(a=>{const old=assets.get(a.id);return !old||kit(a.kit)!==kit(old.kit)||(a.uso||'apoio')!==(old.uso||'apoio');}),
   mentions:(draft.mentions||[]).filter(r=>{const old=mentions.get(r.id);return !old||kit(r.kit)!==kit(old.kit)||Number(r.start)!==Number(old.start)||Number(r.end)!==Number(old.end)||!!r.selected!==!!old.selected;})};
 }
 const api={changes};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.VisualDraft=api;
})(typeof window!=='undefined'?window:globalThis);
