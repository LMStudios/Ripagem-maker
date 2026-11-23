'use strict';
const {contextBridge,ipcRenderer}=require('electron');
const bridge=Object.freeze({
 choose_folder:()=>ipcRenderer.invoke('files:choose'),
 choose_video:()=>ipcRenderer.invoke('files:choose-video'),
 collect_broll:(site,query,limit)=>ipcRenderer.invoke('broll:collect',String(site),String(query),Number(limit)||8),
 save_file:address=>ipcRenderer.invoke('files:save',String(address)),
 open_path:(file,reveal=false)=>ipcRenderer.invoke('files:open',String(file),Boolean(reveal)),
 restart:()=>ipcRenderer.invoke('app:retry'),
 logs:()=>ipcRenderer.invoke('app:logs')
});
contextBridge.exposeInMainWorld('ripagemDesktop',bridge);
// Compatibility with the existing 3.2 file controls when opening an older workspace.
contextBridge.exposeInMainWorld('pywebview',Object.freeze({api:bridge}));
