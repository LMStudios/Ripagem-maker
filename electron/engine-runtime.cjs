'use strict';
const fs=require('node:fs'),path=require('node:path');
function bundledEngine(base,root,platform=process.platform){
 const python=path.join(base,'bin','python','python.exe');
 if(platform==='win32'&&fs.existsSync(python))return {command:python,args:[path.join(base,'bin','python','engine_entry.py'),root],binPaths:[path.join(base,'bin','ffmpeg'),path.join(base,'bin','python')]};
 const directory=path.join(base,'bin','ripagem-engine'),frozen=path.join(directory,platform==='win32'?'ripagem-engine.exe':'ripagem-engine');
 if(fs.existsSync(frozen))return {command:frozen,args:[root],binPaths:[path.join(directory,'_internal')]};
 return null;
}
module.exports={bundledEngine};
