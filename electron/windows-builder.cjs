const base=require('./package.json').build;
module.exports={...base,
 artifactName:'Ripagem-Maker-'+require('node:fs').readFileSync(require('node:path').resolve(__dirname,'../VERSION'),'utf8').trim()+'-Windows-${arch}.${ext}',
 extraResources:[{from:'engine-windows',to:'engine'},{from:'../plataforma/static/assets/app-icon.png',to:'app-icon.png'}],
 beforePack:'./scripts/verify-windows-engine.cjs',afterPack:'./scripts/brand-windows.cjs',
 win:{...base.win,signAndEditExecutable:false},
 nsis:{...base.nsis,shortcutName:'Ripagem Maker Electron',uninstallDisplayName:'Ripagem Maker Electron',installerLanguages:['pt_BR'],runAfterFinish:true},
};
