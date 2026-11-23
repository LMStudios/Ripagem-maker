'use strict';
const path = require('node:path');
function localURL(address, origin) {
  try { const u=new URL(address);return u.origin===origin && !u.username && !u.password; } catch{return false;}
}
function fileRelative(address, origin) {
  const u=new URL(address);
  if(!localURL(address,origin)||!u.pathname.startsWith('/files/')) throw Error('Arquivo fora do trabalho local.');
  const relative=decodeURIComponent(u.pathname.slice(7));
  if(!relative||relative.includes('\\')||relative.includes('\0')||relative.split('/').some(s=>s==='..')||path.posix.isAbsolute(relative)) throw Error('Caminho inválido.');
  return relative;
}
function safeExternal(address) {try {const u=new URL(address);return ['https:','http:'].includes(u.protocol)&&!u.username&&!u.password;}catch{return false;}}
module.exports={localURL,fileRelative,safeExternal};
