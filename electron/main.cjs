'use strict';
const {app,BrowserWindow,dialog,ipcMain,shell,Menu}=require('electron');
const fs=require('node:fs');const fsp=fs.promises;const path=require('node:path');const {spawn}=require('node:child_process');const {pipeline}=require('node:stream/promises');const {Readable}=require('node:stream');
const {localURL,fileRelative,safeExternal}=require('./policy.cjs');
const {bundledEngine}=require('./engine-runtime.cjs');
const {upgradeCode}=require('./update-code.cjs');
const coleta=require('./coleta.cjs');
let win,child,origin,root,logFile,quitting=false,starting=false;
const preferredPort=Number(process.env.RIPAGEM_ELECTRON_PORT||8765);let port=preferredPort;
function bindable(p){return new Promise(resolve=>{const s=require('node:net').createServer();s.once('error',()=>resolve(false));s.listen(p,'127.0.0.1',()=>s.close(()=>resolve(true)));});}
// No Windows, faixas reservadas pelo Hyper-V/WSL/Docker recusam a porta (WinError 10013) mesmo sem outro programa nela.
async function freePort(){
 for(let p=preferredPort;p<preferredPort+20;p++)if(await bindable(p))return p;
 return new Promise((resolve,reject)=>{const s=require('node:net').createServer();s.once('error',reject);s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>resolve(p));});});
}
const startup=path.join(__dirname,'startup.html');
const wait=ms=>new Promise(r=>setTimeout(r,ms));
function stopChild(){
 if(!child)return;
 const pid=child.pid;
 if(pid){try{if(process.platform==='win32')spawn('taskkill',['/PID',String(pid),'/T','/F'],{windowsHide:true});else process.kill(-pid,'SIGTERM');}catch{child.kill();}}
 child=null;
}
function localSender(event,allowStartup=false){
 const frame=event.senderFrame;const address=frame?.url||'';
 if(event.sender!==win?.webContents||frame!==event.sender.mainFrame||!(localURL(address,origin)||(allowStartup&&address.startsWith(require('node:url').pathToFileURL(startup).href))))throw Error('Ação disponível somente na janela local do aplicativo.');
}
function wrap(channel,fn,allowStartup=false){ipcMain.handle(channel,async(event,...args)=>{try{localSender(event,allowStartup);return await fn(...args);}catch(error){return {ok:false,erro:error.message};}});}
async function online(){try{const r=await fetch(origin+'/api/recursos',{signal:AbortSignal.timeout(1000)});return r.ok&&(await r.json()).forma_produto;}catch{return false;}}
async function resolveRoot(){
 const config=path.join(app.getPath('userData'),'engine-root.json');
 if(process.env.RIPAGEM_ENGINE_ROOT)return path.resolve(process.env.RIPAGEM_ENGINE_ROOT);
 if(!app.isPackaged)return path.resolve(__dirname,'..');
 try{const saved=JSON.parse(await fsp.readFile(config,'utf8'));if(fs.existsSync(path.join(saved.root,'app.py')))return saved.root;}catch{}
 const chosen=path.join(app.getPath('userData'),'Aplicativo');
 await fsp.mkdir(chosen,{recursive:true});
 await fsp.cp(path.join(process.resourcesPath,'engine','code'),chosen,{recursive:true,errorOnExist:false,force:false});
 await fsp.mkdir(path.dirname(config),{recursive:true});await fsp.writeFile(config,JSON.stringify({root:chosen}));return chosen;
}
async function pythonCommand(){
 if(process.env.RIPAGEM_PYTHON)return [process.env.RIPAGEM_PYTHON];
 const local=path.join(root,'.runtime',process.platform==='win32'?'Scripts/python.exe':'bin/python');
 const candidates=[...(fs.existsSync(local)?[[local]]:[]),...(process.platform==='win32'?[['py','-3.12'],['python']]:[['/Library/Frameworks/Python.framework/Versions/3.13/bin/python3'],['/opt/homebrew/bin/python3.12'],['/usr/local/bin/python3.12'],['python3']])];
 for(const command of candidates){
  const valid=await new Promise(resolve=>{let done=false;const p=spawn(command[0],[...command.slice(1),'-c','import sys,requests,numpy,keyring;sys.exit(not ((3,10)<=sys.version_info[:2]<(3,14)))'],{stdio:'ignore',windowsHide:true});const timer=setTimeout(()=>{p.kill();finish(false);},6000);function finish(v){if(done)return;done=true;clearTimeout(timer);resolve(v);}p.on('error',()=>finish(false));p.on('exit',code=>finish(code===0));});
  if(valid)return command;
 }
 throw Error('Motor Python não encontrado. Use a edição com motor incluído ou instale as dependências pelo iniciador anterior. Nenhum trabalho foi alterado.');
}
async function ensureWindowsRuntime(engineBase){
 const installed=await new Promise(resolve=>{const p=spawn('reg.exe',['query','HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\14.0\\VC\\Runtimes\\x64','/v','Version','/reg:64'],{windowsHide:true});let output='';p.stdout.on('data',d=>output+=d);p.on('error',()=>resolve(false));p.on('exit',code=>{const m=output.match(/v14\.(\d+)\./);resolve(code===0&&m&&Number(m[1])>=44);});});
 if(installed)return;
 const installer=path.join(engineBase,'bin','vc_redist.x64.exe');
 if(!fs.existsSync(installer))throw Error('Componente Microsoft necessário não incluído. Reinstale usando o pacote completo.');
 const answer=await dialog.showMessageBox(win,{type:'info',title:'Componente Microsoft',message:'Preparar o componente Microsoft Visual C++',detail:'Este computador precisa do componente oficial Microsoft Visual C++ para o motor de áudio. O instalador está incluído. O Windows pedirá sua autorização de administrador. Seus arquivos não serão alterados.',buttons:['Instalar componente','Cancelar'],defaultId:0,cancelId:1,noLink:true});
 if(answer.response!==0)throw Error('Preparação do componente Microsoft cancelada. Clique em Tentar novamente quando quiser continuar.');
 const code=await new Promise((resolve,reject)=>{const p=spawn('powershell.exe',['-NoProfile','-NonInteractive','-Command',"$ErrorActionPreference='Stop'; $p=Start-Process -FilePath $env:RIPAGEM_VC_REDIST -ArgumentList '/install','/passive','/norestart' -Verb RunAs -Wait -PassThru; exit $p.ExitCode"],{env:{...process.env,RIPAGEM_VC_REDIST:installer},stdio:'ignore',windowsHide:true});p.on('error',reject);p.on('exit',resolve);});
 if(![0,1638,3010].includes(code))throw Error('O componente Microsoft não foi instalado (código '+code+'). Confirme a autorização do Windows e tente novamente.');
}
async function boot(){
 if(starting)return;starting=true;
 try{
  await win.loadFile(startup);
  if(!root)root=await resolveRoot();if(!root){app.quit();return;}
  origin='http://127.0.0.1:'+preferredPort;
  if(await online())throw Error('Já existe um aplicativo usando a porta '+preferredPort+'. Feche a outra versão e tente novamente. Ela não foi encerrada.');
  port=await freePort();origin='http://127.0.0.1:'+port;
  const engineBase=app.isPackaged?path.join(process.resourcesPath,'engine'):path.join(__dirname,'engine');
  if(app.isPackaged)await upgradeCode(path.join(engineBase,'code'),root);
  const bundled=bundledEngine(engineBase,root);
  if(process.platform==='win32'&&bundled?.command.endsWith('python.exe'))await ensureWindowsRuntime(engineBase);
  const command=bundled?[bundled.command]:await pythonCommand();
  const args=bundled?bundled.args:[...command.slice(1),path.join(root,'app.py')];
  const log=fs.openSync(logFile,'a');
  const env={...process.env,DRSTUDIO_EMBED:'1',PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8',PYTHONUNBUFFERED:'1',PORT:String(port),PATH:[...(bundled?.binPaths||[]),'/opt/homebrew/bin','/usr/local/bin',process.env.PATH||''].join(path.delimiter)};
  child=spawn(command[0],args,{cwd:root,env,stdio:['ignore',log,log],windowsHide:true,detached:process.platform!=='win32'});fs.closeSync(log);
  let startupError;child.on('error',error=>{startupError=error;});
  for(let i=0;i<120;i++){
   if(startupError)throw startupError;
   if(child.exitCode!==null)throw Error('O motor de processamento encerrou antes de abrir. Consulte a pasta de diagnóstico.');
   if(await online()){await win.loadURL(origin);return;}
   await wait(500);
  }
  throw Error('O processamento não respondeu em 60 segundos. Consulte a pasta de diagnóstico e tente novamente.');
 }catch(error){stopChild();await win.loadFile(startup,{query:{error:error.message}});}finally{starting=false;}
}
function nativeBridge(){
 wrap('broll:collect',async(name,query,limit)=>coleta.collect({BrowserWindow,session:require('electron').session,parent:win,name,query,limit}));
 wrap('files:choose-video',async()=>{const d=await dialog.showOpenDialog(win,{title:'Escolher o vídeo exportado',properties:['openFile'],filters:[{name:'Vídeo',extensions:['mp4','mov','m4v','mkv','webm']}]});return {ok:true,cancelado:d.canceled,arquivo:d.filePaths[0]||''};});
 wrap('files:choose',async()=>{const d=await dialog.showOpenDialog(win,{title:'Escolher pasta de materiais',properties:['openDirectory','createDirectory']});return {ok:true,cancelado:d.canceled,pasta:d.filePaths[0]||''};});
 wrap('files:save',async address=>{
  const u=new URL(address);if(u.pathname.startsWith('/files/'))fileRelative(address,origin);else if(!localURL(address,origin)||!u.pathname.startsWith('/media/out/'))throw Error('Arquivo fora do aplicativo.');
  const response=await fetch(address,{signal:AbortSignal.timeout(1800000)});if(!response.ok){await response.body?.cancel();throw Error('Arquivo não encontrado. Gere a entrega novamente.');}
  const disposition=response.headers.get('content-disposition')||'';
  const encoded=disposition.match(/filename\*=UTF-8''([^;]+)/i);const basic=disposition.match(/filename="([^"]+)"/i);
  let name=encoded?decodeURIComponent(encoded[1]):basic?basic[1]:decodeURIComponent(u.pathname.split('/').pop());name=path.basename(name).replace(/[<>:"/\\|?*\x00-\x1f]/g,'_');
  const d=await dialog.showSaveDialog(win,{title:'Salvar uma cópia',defaultPath:path.join(app.getPath('downloads'),name)});
  if(d.canceled){await response.body?.cancel();return {ok:true,cancelado:true,origem:address};}
  const temporary=d.filePath+'.'+require('node:crypto').randomUUID()+'.tmp';
  try{await pipeline(Readable.fromWeb(response.body),fs.createWriteStream(temporary,{flags:'wx'}));const size=(await fsp.stat(temporary)).size;const expected=response.headers.get('content-length');if(expected!==null&&size!==Number(expected))throw Error('Cópia incompleta. Tente novamente.');await fsp.rename(temporary,d.filePath);return {ok:true,arquivo:d.filePath,bytes:size};}finally{await fsp.rm(temporary,{force:true});}
 });
 wrap('files:open',async(file,reveal)=>{if(!path.isAbsolute(file))throw Error('Informe um caminho completo.');const info=await fsp.stat(file);if(!info.isDirectory()&&!info.isFile())throw Error('Caminho não é um arquivo ou pasta.');if(reveal)shell.showItemInFolder(file);else{const error=await shell.openPath(info.isDirectory()?file:path.dirname(file));if(error)throw Error(error);}return {ok:true,arquivo:file};});
 wrap('app:logs',async()=>{const error=await shell.openPath(path.dirname(logFile));if(error)throw Error(error);return {ok:true};},true);
 wrap('app:retry',async()=>{setImmediate(boot);return {ok:true};},true);
}
async function activeJobs(){const r=await fetch(origin+'/api/desktop/status',{signal:AbortSignal.timeout(2500)});if(!r.ok)throw Error('Não foi possível conferir as tarefas.');return (await r.json()).ativas;}
async function requestClose(){
 if(quitting)return;
 let active=0;try{if(child&&await online())active=await activeJobs();}catch{active=-1;}
 if(active!==0){const result=await dialog.showMessageBox(win,{type:'warning',message:active<0?'Não foi possível conferir as tarefas.':`Há ${active} tarefa(s) em andamento.`,detail:'Fechar agora interrompe o processamento desta versão. Os arquivos já salvos permanecem no trabalho.',buttons:['Continuar no app','Encerrar processamento e sair'],cancelId:0,defaultId:0,noLink:true});if(result.response===0)return;}
 quitting=true;
 if(child){try{await fetch(origin+'/api/equipe/fechar',{method:'POST',signal:AbortSignal.timeout(1000)});}catch{}}
 stopChild();
 app.quit();
}
if(!app.requestSingleInstanceLock())app.quit();else{
 app.on('second-instance',()=>{win?.show();win?.focus();});
 app.whenReady().then(async()=>{
  origin='http://127.0.0.1:'+preferredPort;
  await fsp.mkdir(app.getPath('logs'),{recursive:true});logFile=path.join(app.getPath('logs'),'engine.log');
  win=new BrowserWindow({title:'Ripagem Maker Electron',width:1400,height:900,minWidth:960,minHeight:640,backgroundColor:'#101114',icon:app.isPackaged?path.join(process.resourcesPath,'app-icon.png'):path.join(__dirname,'../plataforma/static/assets/app-icon.png'),webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true}});
  nativeBridge();
  win.webContents.setWindowOpenHandler(({url})=>{if(safeExternal(url))shell.openExternal(url);return {action:'deny'};});
  win.webContents.on('will-navigate',(event,url)=>{if(!localURL(url,origin)){event.preventDefault();if(safeExternal(url))shell.openExternal(url);}});
  win.webContents.session.setPermissionRequestHandler((_contents,_permission,callback)=>callback(false));
  // Handle downloads not covered by download links (e.g. dynamically generated exports).
  win.webContents.session.on('will-download',(_event,item)=>{item.setSaveDialogOptions({title:'Salvar arquivo do Ripagem Maker',defaultPath:path.join(app.getPath('downloads'),path.basename(item.getFilename()))});item.once('done',(_e,state)=>{if(state==='interrupted')dialog.showErrorBox('Download não concluído','Tente novamente. O arquivo original permanece na pasta do trabalho.');});});
  Menu.setApplicationMenu(Menu.buildFromTemplate([...(process.platform==='darwin'?[{label:app.name,submenu:[{role:'about'},{type:'separator'},{label:'Sair',accelerator:'Cmd+Q',click:requestClose}]}]:[]),{label:'Editar',submenu:[{role:'undo'},{role:'redo'},{type:'separator'},{role:'cut'},{role:'copy'},{role:'paste'},{role:'selectAll'}]},{label:'Visualizar',submenu:[{role:'resetZoom'},{role:'zoomIn'},{role:'zoomOut'},{role:'togglefullscreen'}]},{label:'Ajuda',submenu:[{label:'Abrir pasta de diagnóstico',click:()=>shell.openPath(path.dirname(logFile))},{label:'Versões para download',click:()=>shell.openExternal('https://drive.google.com/drive/folders/1aC-d_Bp-PMuG9pxSuzPAT5rZx35O3mUM')}]}]));
  win.on('close',event=>{if(!quitting){event.preventDefault();requestClose();}});
  app.on('before-quit',event=>{if(!quitting){event.preventDefault();requestClose();}});
  await boot();
 });
}
