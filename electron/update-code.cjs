'use strict';
const fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto');
const top=new Set(['app.py','index.html','VERSION','iniciar.py','requirements.txt']);
const allowed=name=>top.has(name)||/^plataforma\/[^/]+\.py$/.test(name)||(/^plataforma\/static\//.test(name)&&/\.(html|css|js|svg|png|ico)$/.test(name));
const version=s=>/^\d+\.\d+\.\d+$/.test(s.trim())?s.trim().split('.').map(Number):[0,0,0];
const newer=(a,b)=>{for(let i=0;i<3;i++)if(a[i]!==b[i])return a[i]>b[i];return false;};
async function upgradeCode(source,root){
 const incoming=await fs.readFile(path.join(source,'VERSION'),'utf8');let installed='0.0.0';try{installed=await fs.readFile(path.join(root,'VERSION'),'utf8');}catch{}
 if(!newer(version(incoming),version(installed)))return {changed:false};
 const files=[];async function walk(dir,prefix=''){for(const e of await fs.readdir(dir,{withFileTypes:true})){const name=prefix+e.name;if(e.isSymbolicLink())throw Error('Código do instalador contém link inesperado.');if(e.isDirectory())await walk(path.join(dir,e.name),name+'/');else if(allowed(name))files.push(name);}}await walk(source);
 if(!files.includes('app.py'))throw Error('Atualização do instalador incompleta.');
 // Não escreve através de links existentes na pasta escolhida.
 for(const name of files){let dest=root;for(const part of name.split('/')){dest=path.join(dest,part);try{if((await fs.lstat(dest)).isSymbolicLink())throw Error('A atualização encontrou um link na pasta de código: '+dest);}catch(e){if(e.code!=='ENOENT')throw e;}}}
 const backup=path.join(root,'.atualizacoes','antes-instalador-'+installed.trim()+'-'+crypto.randomUUID()),changed=[];await fs.mkdir(backup,{recursive:true});
 try{
  for(const name of files.sort((a,b)=>Number(a==='VERSION')-Number(b==='VERSION'))){const dest=path.join(root,name),old=path.join(backup,name);let exists=true;try{await fs.access(dest);}catch{exists=false;}
   if(exists){await fs.mkdir(path.dirname(old),{recursive:true});await fs.copyFile(dest,old);}await fs.mkdir(path.dirname(dest),{recursive:true});const temporary=dest+'.update-'+crypto.randomUUID();
   try{await fs.copyFile(path.join(source,name),temporary);await fs.rename(temporary,dest);}finally{await fs.rm(temporary,{force:true});}changed.push({name,exists});
  }
 }catch(error){for(const {name,exists} of changed.reverse()){const dest=path.join(root,name);if(exists)await fs.copyFile(path.join(backup,name),dest);else await fs.rm(dest,{force:true});}throw error;}
 return {changed:true,version:incoming.trim(),backup};
}
module.exports={upgradeCode};
