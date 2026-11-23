const path=require('node:path'),{spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
async function main(){
 const p=spawnSync(process.platform==='win32'?'python':'python3',[path.join(__dirname,'prepare_windows_engine.py')],{cwd:root,stdio:'inherit'});
 if(p.status!==0)throw Error('Não foi possível preparar o motor Windows.');
 const builder=require('electron-builder'),{Arch}=require('builder-util');
 const artifacts=await builder.build({targets:builder.Platform.WINDOWS.createTarget(['nsis'],Arch.x64),config:require('../windows-builder.cjs')});
 for(const artifact of artifacts)console.log(artifact);
}
main().catch(error=>{console.error(error);process.exitCode=1;});
