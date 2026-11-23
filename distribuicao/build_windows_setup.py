from pathlib import Path
import subprocess,zipfile,io,struct,hashlib
ROOT=Path(__file__).resolve().parent.parent
subprocess.run(['python3',str(ROOT/'distribuicao/build_windows_app.py')],check=True)
app=ROOT/'distribuicao/pacotes/Aplicativo-Windows/Ripagem Maker'
# Mantém a lista usada para migrar uma instalação anterior completa.
import json,shutil
shutil.copy2(ROOT/'distribuicao/windows/prepare_windows.py',app/'prepare_windows.py')
manifest=json.loads((app/'manifest.json').read_text());manifest.append('prepare_windows.py');(app/'manifest.json').write_text(json.dumps(manifest))
payload=io.BytesIO()
with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED) as z:
 for name in sorted(set(manifest)|{'Ripagem Maker.exe','LEIA-ME.txt'}):
  z.write(app/name,'Ripagem Maker/'+name)
 z.write(ROOT/'distribuicao/windows/instalar.ps1','instalar.ps1')
exe=ROOT/'distribuicao/pacotes/Instalar Ripagem Maker Windows.exe'
from windows_icon import resource
icon_resource=resource('/tmp/ripagem-cross-tools/ziglang/zig')
subprocess.run(['/tmp/ripagem-cross-tools/ziglang/zig','cc','-target','x86_64-windows-gnu','-O2','-municode','-Wl,--subsystem,windows',str(ROOT/'distribuicao/windows/setup.c'),str(icon_resource),'-o',str(exe),'-luser32','-lshell32'],check=True)
data=payload.getvalue()
with exe.open('ab') as f:f.write(data);f.write(struct.pack('<Q',len(data))+b'RMSETUP1')
exe.with_suffix('.sha256').write_text(hashlib.sha256(exe.read_bytes()).hexdigest()+'  '+exe.name+'\n')
print(exe)
