/* Otimização · trocar valores dos kits: mesmo fluxo da troca, partindo da VSL finalizada, com preços e kits em primeiro plano. */
(() => {
  const $=id=>document.getElementById(id);
  const drop=$('drop');if(!drop)return;
  const FLAG='dr.otimizacao.pendente';
  let active=false;
  const card=document.createElement('div');card.className='card';card.id='optimize-card';
  card.innerHTML=`<b>Otimização · trocar valores dos kits</b>
  <p class="meta">Para uma VSL já finalizada: troca somente preços e quantidades dos kits. O nome do produto e o modo de uso são mantidos. Usa o mesmo fluxo — vozes, takes, XML e legendas — com os preços e kits abertos na etapa Falas.</p>
  <button class="ghost" id="optimize-toggle">Começar uma otimização</button><p class="meta" id="optimize-status" role="status"></p>`;
  drop.closest('section').before(card);
  const labels={prod:$('prod')?.closest('label'),novo:$('novo')?.closest('label')};
  const original={prod:labels.prod?.firstChild?.textContent,novo:labels.novo?.firstChild?.textContent};
  function relabel(on){
    if(labels.prod)labels.prod.firstChild.textContent=on?'Produto que aparece na VSL finalizada (vazio = o app identifica)':original.prod;
    if(labels.novo)labels.novo.firstChild.textContent=on?'Nome do produto (apenas identificação; não será substituído)':original.novo;
  }
  function pending(on){
    try{on?sessionStorage.setItem(FLAG,'1'):sessionStorage.removeItem(FLAG);}catch{}
    $('optimize-toggle').textContent=on?'Voltar para a troca de potes normal':'Começar uma otimização';
    $('optimize-status').textContent=on?'Modo otimização: envie a VSL finalizada abaixo. Na etapa Falas os preços e kits já aparecem abertos.':'';
    relabel(on);
  }
  const isPending=()=>{try{return sessionStorage.getItem(FLAG)==='1';}catch{return false;}};
  window.RipagemOptimization={pending:isPending};
  $('optimize-toggle').onclick=()=>pending(!isPending());
  pending(isPending());
  const call=async(body={})=>{const r=await fetch('/fatiador/trocas/otimizacao',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder,...body})});const d=await r.json();if(!r.ok)throw Error(d.erro||'Não foi possível concluir.');return d;};
  const banner=document.createElement('p');banner.className='ux-stat';banner.id='optimize-banner';banner.hidden=true;
  document.querySelector('.wizard-nav')?.after(banner);
  function present(state){
    active=state.ativo;banner.hidden=!active;document.dispatchEvent(new CustomEvent('optimization:state'));
    banner.innerHTML=active?`<b>Otimização · trocar valores dos kits</b> · somente preços e quantidades de kits · nome e modo de uso preservados`:'';
    const help=document.querySelector('[data-w-panel="3"] > p.meta');
    if(help){help.dataset.original??=help.textContent;help.textContent=active?'Otimização: cole a solicitação das três ofertas em Preços e kits e clique em “Identificar e adaptar os três kits”. Depois confira e aprove os textos.':help.dataset.original;}
    document.body.classList.toggle('optimization-only',active);
    if(!active)return;
    // Preços e kits saem do “opcional” e ficam no topo da etapa Falas.
    const panel=$('pcard')?.closest('details');
    if(panel){panel.open=true;panel.querySelector('summary').textContent='Preços e kits da otimização';$('wizard-slot-3')?.prepend(panel);}
    if($('pdetect')&&!$('pdet')?.textContent.trim())$('pdetect').click();
  }
  const previousShow=window.show;
  if(previousShow)window.show=async function(s){
    try{
      const response=await fetch('/fatiador/trocas/otimizacao',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder:s.folder})});
      const state=await response.json();if(!response.ok)throw Error(state.erro||'Não foi possível confirmar o modo de otimização.');
      await previousShow.call(this,state.ativo?{...s,frases:[],resumo_frases:'Somente preços e kits: informe os valores novos abaixo.'}:s);present(state);
    }catch(e){$('wizard-error').textContent=e.message;}
  };
  const style=document.createElement('style');style.textContent='.optimization-only .practical-form,.optimization-only .product-form,.optimization-only #old-product-early,.optimization-only [data-filter="form"]{display:none!important}';document.head.append(style);
  const previousApply=window.applyPrices;
  if(previousApply)window.applyPrices=async function(){
    await previousApply.apply(this,arguments);
    // Com valores novos gerados, a lista única é refeita incluindo as frases de preço e kit.
    if(active&&typeof PR!=='undefined'&&window.loadSwapPlan&&!document.querySelector('#pres .err'))await window.loadSwapPlan(true);
  };
})();
