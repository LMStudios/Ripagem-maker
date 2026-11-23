const fs=require('node:fs'),path=require('node:path'),R=require('resedit');
module.exports=async context=>{
 if(context.electronPlatformName!=='win32')return;
 const engine=path.join(context.appOutDir,'resources','engine');
 if(fs.existsSync(path.join(engine,'bin','ripagem-engine')))throw Error('Motor de outra distribuição misturado ao Windows. Limpe a pasta de build.');
 const file=path.join(context.appOutDir,context.packager.appInfo.productFilename+'.exe');
 const exe=R.NtExecutable.from(fs.readFileSync(file),{ignoreCert:true}),resources=R.NtExecutableResource.from(exe);
 const ico=R.Data.IconFile.from(fs.readFileSync(path.resolve(__dirname,'../../plataforma/static/assets/app.ico')));
 R.Resource.IconGroupEntry.replaceIconsForResource(resources.entries,1,1033,ico.icons.map(icon=>icon.data));
 const version=R.Resource.VersionInfo.fromEntries(resources.entries)[0]||R.Resource.VersionInfo.createEmpty();
 const parts=context.packager.appInfo.version.match(/\d+/g).map(Number);while(parts.length<4)parts.push(0);
 version.setFileVersion(...parts.slice(0,4));version.setProductVersion(...parts.slice(0,4));
 for(const lang of version.getAllLanguagesForStringValues())version.removeAllStringValues(lang);
 version.setStringValues({lang:1033,codepage:1200},{CompanyName:'Ripagem Maker',FileDescription:'Ripagem Maker Electron',ProductName:'Ripagem Maker Electron',FileVersion:context.packager.appInfo.version,ProductVersion:context.packager.appInfo.version,OriginalFilename:path.basename(file)});
 version.outputToResourceEntries(resources.entries);resources.outputResource(exe);fs.writeFileSync(file,Buffer.from(exe.generate()));
 // Confere que ícone e versão sobreviveram à gravação, sem executar o binário.
 const checked=R.NtExecutableResource.from(R.NtExecutable.from(fs.readFileSync(file)));
 if(!R.Resource.IconGroupEntry.fromEntries(checked.entries).length||!R.Resource.VersionInfo.fromEntries(checked.entries).length)throw Error('Recursos do aplicativo Windows não foram confirmados.');
};
