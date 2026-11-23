const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('plataforma/static/fatiador-ux.js','utf8');
const code=src.slice(src.indexOf(' function flush(){'),src.indexOf('\n function changed()'));
function setup(save){const context={dirty:true,saving:false,saveFlight:null,version:1,timer:null,clearTimeout(){},saveStatus(){},$:()=>({textContent:''}),document:{activeElement:null},U:{busy:false,save,render(){context.renders++}},renders:0};vm.createContext(context);vm.runInContext(code,context);return context;}
(async()=>{
 let resolve,calls=0;let c=setup(()=>{calls++;return new Promise(r=>resolve=r)});let a=c.flush(),b=c.flush();assert.equal(a,b);assert.equal(calls,1);assert.equal(c.saving,true);resolve();assert.equal(await b,true);assert.equal(c.saving,false);assert.equal(c.dirty,false);assert.equal(c.saveFlight,null);assert.equal(c.renders,1);
 let pending=[];calls=0;c=setup(()=>{calls++;return new Promise(r=>pending.push(r))});a=c.flush();c.version++;pending.shift()();await new Promise(r=>setImmediate(r));assert.equal(calls,2);assert.equal(c.renders,0);pending.shift()();assert.equal(await a,true);assert.equal(c.renders,1);assert.equal(c.dirty,false);
 c=setup(async()=>{throw Error('network')});assert.equal(await c.flush(),false);assert.equal(c.dirty,true);assert.equal(c.saving,false);assert.equal(c.saveFlight,null);c.U.save=async()=>{};assert.equal(await c.flush(),true);
 c=setup(async()=>{throw Error('should not run')});c.U.busy=true;assert.equal(await c.flush(),false);assert.equal(c.saving,false);assert.equal(c.saveFlight,null);
 console.log('4 autosave concurrency checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
