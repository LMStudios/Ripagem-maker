// Nunca publica um motor Mac no Windows, nem binários da arquitetura errada.
const fs=require('node:fs'),path=require('node:path');
async function verify(context,base){
 const info=JSON.parse(fs.readFileSync(path.join(base,'runtime.json'),'utf8'));
 const arch=({0:'ia32',1:'x64',3:'arm64'})[context.arch];
 const machine=({aarch64:'arm64',arm64:'arm64',AMD64:'x64',x86_64:'x64'})[info.machine];
 if(info.platform!==context.electronPlatformName||machine!==arch)throw Error('Prepare o motor no sistema e arquitetura de destino antes de empacotar.');
 const binaries=info.kind==='python-embedded'?['bin/python/python.exe','bin/ffmpeg/ffmpeg.exe','bin/ffmpeg/ffprobe.exe']:['bin/ripagem-engine/'+(info.platform==='win32'?'ripagem-engine.exe':'ripagem-engine')];
 for(const relative of binaries){
  const binary=path.join(base,relative);if(!fs.existsSync(binary))throw Error('Motor incluído não encontrado: '+relative);
  if(info.platform==='win32'){
   const data=fs.readFileSync(binary),offset=data.readUInt32LE(0x3c);
   if(data.toString('ascii',0,2)!=='MZ'||data.toString('ascii',offset,offset+4)!=='PE\0\0'||data.readUInt16LE(offset+4)!==0x8664)throw Error('O binário não é Windows x64: '+relative);
  }
 }
 if(info.kind==='python-embedded'&&!fs.existsSync(path.join(base,'bin/python/engine_entry.py')))throw Error('Inicializador Python incluído não encontrado.');
}
module.exports=context=>verify(context,path.resolve(__dirname,'../engine'));
module.exports.verify=verify;
