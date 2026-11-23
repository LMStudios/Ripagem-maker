const {test}=require('node:test'),assert=require('node:assert/strict');
const {Playback}=require('../plataforma/static/audio-player.js');
class Media {
 constructor(){this.handlers={};this.attrs={};this.paused=true;this.duration=8;this.currentTime=0;this.readyState=1;this.plays=0;this.loads=0;}
 addEventListener(name,fn){this.handlers[name]=fn;}
 setAttribute(k,v){this.attrs[k]=v;}getAttribute(k){return this.attrs[k]||null;}removeAttribute(k){delete this.attrs[k];}
 set src(v){this.attrs.src=v;}get src(){return this.attrs.src;}
 load(){this.loads++;this.currentTime=0;}pause(){this.paused=true;}
 play(){this.plays++;this.paused=false;return Promise.resolve();}
 fire(name){this.handlers[name]?.();}
}
function setup(){let count=0;const media=new Media(),changes=[];const engine=new Playback(()=>{count++;return media;},item=>changes.push({state:item.state,position:item.position}));return {engine,media,changes,count:()=>count};}
const row=n=>({src:'/files/test/'+n+'.mp3',position:0,duration:8,state:'paused'});
test('mil trocas de frase usam somente um decodificador e só carregam após ouvir',async()=>{
 const t=setup();assert.equal(t.count(),0);let old;
 for(let i=0;i<1000;i++){const item=row(i);await t.engine.toggle(item);assert.equal(item.state,'playing');if(old)assert.equal(old.state,'paused');old=item;}
 assert.equal(t.count(),1);assert.equal(t.media.plays,1000);assert.equal(t.media.controls,false);assert.equal(t.media.disableRemotePlayback,true);assert.equal(t.media.attrs['x-webkit-airplay'],'deny');t.engine.stop(true);
});
test('pausa, retoma e busca preservam a posição sem recarregar o mesmo arquivo',async()=>{
 const {engine,media}=setup(),item=row(1);await engine.toggle(item);engine.seek(item,3);await engine.toggle(item);assert.equal(item.position,3);assert.equal(item.state,'paused');await engine.toggle(item);assert.equal(media.currentTime,3);assert.equal(media.loads,1);engine.stop(true);
});
test('terminar permite ouvir novamente desde o começo',async()=>{
 const {engine,media}=setup(),item=row(1);await engine.toggle(item);media.currentTime=8;media.fire('ended');assert.equal(item.state,'ended');await engine.toggle(item);assert.equal(media.currentTime,0);engine.stop(true);
});
test('rejeição tardia de uma frase não interrompe a seguinte',async()=>{
 const {engine,media}=setup();let reject;media.play=()=>new Promise((_,r)=>reject=r);const first=row(1),pending=engine.toggle(first);media.play=()=>Promise.resolve();const second=row(2);await engine.toggle(second);reject(Error('old request aborted'));await pending;assert.equal(engine.active,second);assert.equal(second.state,'playing');engine.stop(true);
});
test('duplo clique cancela carregamento sem reproduzir outra frase nem marcar aprovação',async()=>{
 const {engine,media}=setup();let resolve;media.play=()=>new Promise(r=>resolve=r);const item=row(1),pending=engine.toggle(item);await engine.toggle(item);resolve();await pending;assert.equal(engine.active,null);assert.equal(item.state,'paused');assert.equal(item.aprovado,undefined);
});
test('arquivo com erro libera o player e permite repetir ou ouvir outro',async()=>{
 const {engine,media}=setup(),first=row(1);await engine.toggle(first);media.fire('error');assert.equal(first.state,'error');assert.match(first.error,/baixe o áudio/);assert.equal(media.src,undefined);const second=row(2);await engine.toggle(second);assert.equal(second.state,'playing');engine.stop(true);
});
test('retirar a frase da tela libera a mídia e invalida uma reprodução pendente',async()=>{
 const {engine,media}=setup();let resolve;media.play=()=>new Promise(r=>resolve=r);const item=row(1),pending=engine.toggle(item);engine.stop(true);resolve();await pending;assert.equal(engine.active,null);assert.equal(media.src,undefined);assert.equal(item.state,'paused');
});
test('posição inválida não causa seek fora do áudio',async()=>{
 const {engine,media}=setup(),item=row(1);await engine.toggle(item);engine.seek(item,-100);assert.equal(media.currentTime,0);engine.seek(item,100);assert.equal(media.currentTime,8);engine.seek(item,NaN);assert.equal(media.currentTime,0);engine.stop(true);
});
