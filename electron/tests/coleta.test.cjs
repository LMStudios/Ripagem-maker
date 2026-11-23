const {test}=require('node:test');const assert=require('node:assert/strict');
const C=require('../coleta.cjs');
test('only TikTok video and Pinterest pin links, deduplicated and without tracking',()=>{
 assert.deepEqual(C.normalize('tiktok',['https://www.tiktok.com/@ana.b/video/7693107797650640141?is_from_webapp=1','https://www.tiktok.com/@ana.b/video/7693107797650640141','https://www.tiktok.com/@x/photo/123','http://www.tiktok.com/@x/video/1234567','https://evil.example/@x/video/7693107797650640141','javascript:alert(1)']),['https://www.tiktok.com/@ana.b/video/7693107797650640141']);
 assert.deepEqual(C.normalize('pinterest',['https://br.pinterest.com/pin/1055599908888476/?mt=login','https://www.pinterest.com/pin/1055599908888476/','https://www.pinterest.com/ideas/x/123/']),['https://br.pinterest.com/pin/1055599908888476/']);
 assert.equal(C.normalize('tiktok',Array.from({length:30},(_,i)=>`https://www.tiktok.com/@a/video/77000000000${i+10}`),5).length,5);
 assert.throws(()=>C.normalize('instagram',[]));
});
test('search terms are required and trimmed',()=>{assert.throws(()=>C.cleanQuery('   '));assert.equal(C.cleanQuery(' a   b ').length,3);assert.equal(C.cleanQuery('x'.repeat(300)).length,120);});
test('browser agent hides Electron and app tokens',()=>assert.equal(C.browserAgent('Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/140.0 ripagem-maker-electron/4.0.0 Electron/45.1.0 Safari/537.36'),'Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/140.0 Safari/537.36'));
test('only sign-in popups of known providers are allowed',()=>{for(const u of ['https://accounts.google.com/o/oauth2','https://www.facebook.com/login','https://br.pinterest.com/login/'])assert.equal(C.signIn(u),true);for(const u of ['https://evil.example','http://accounts.google.com','https://accounts.google.com.evil.example','file:///x'])assert.equal(C.signIn(u),false);});
test('preload exposes the collector with typed arguments',()=>{const vm=require('node:vm'),fs=require('node:fs');let api;const calls=[];vm.runInNewContext(fs.readFileSync(require.resolve('../preload.cjs'),'utf8'),{require:()=>({contextBridge:{exposeInMainWorld:(n,v)=>{if(n==='ripagemDesktop')api=v;}},ipcRenderer:{invoke:(...a)=>calls.push(a)}})});api.collect_broll('tiktok','mirror','x');assert.deepEqual(calls,[['broll:collect','tiktok','mirror',8]]);});
