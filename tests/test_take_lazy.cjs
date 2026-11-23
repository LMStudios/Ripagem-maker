const test=require('node:test'),assert=require('node:assert/strict');
const Lazy=require('../plataforma/static/lazy-details.js');
class Details{constructor(){this.open=false;this.events={};this.pauses=0;}addEventListener(n,fn){this.events[n]=fn;}querySelectorAll(){return [{pause:()=>this.pauses++}];}toggle(value){this.open=value;this.events.toggle();}}
const tick=()=>new Promise(resolve=>setTimeout(resolve,10));
test('99 detalhes fechados não criam players ou seletores; somente o trecho aberto é montado',async()=>{let renders=0;const rows=Array.from({length:99},()=>new Details());rows.forEach(d=>Lazy.mount(d,()=>renders++));await tick();assert.equal(renders,0);rows[45].toggle(true);await tick();assert.equal(renders,1);rows[45].toggle(false);rows[45].toggle(true);await tick();assert.equal(renders,1);assert.equal(rows[45].pauses,1);});
test('fechar antes do frame cancela criação de mídia e permite abrir depois',async()=>{let renders=0;const d=new Details();Lazy.mount(d,()=>renders++);d.toggle(true);d.toggle(false);await tick();assert.equal(renders,0);d.toggle(true);await tick();assert.equal(renders,1);});
