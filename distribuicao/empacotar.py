"""Allowlist explícita: nenhum dado de workspace ou credencial é distribuído."""
from pathlib import Path
import zipfile,hashlib,json
ROOT=Path(__file__).resolve().parent.parent
DEST=ROOT/'distribuicao/pacotes'
def files():
 yield ROOT/'app.py';yield ROOT/'index.html';yield ROOT/'VERSION'
 yield from (ROOT/'plataforma').glob('*.py')
 yield from (p for p in (ROOT/'plataforma/static').rglob('*') if p.is_file() and p.suffix in ('.html','.css','.js','.svg','.png','.ico'))
def build():
 DEST.mkdir(exist_ok=True)
 common=[(p,p.relative_to(ROOT).as_posix()) for p in files()]
 common += [(ROOT/'distribuicao'/n,n) for n in ('iniciar.py','requirements.txt','LEIA-ME.txt')]
 for system,launcher in [('Mac','Abrir Ripagem Maker.command'),('Windows','Abrir Ripagem Maker.cmd')]:
  entries=common+[(ROOT/'distribuicao'/launcher,launcher)]
  archive=DEST/f'Ripagem-Maker-{system}.zip'
  with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
   for path,name in entries:z.write(path,'Ripagem Maker/'+name)
  print(archive)
 checks={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in DEST.glob('*.zip')}
 (DEST/'SHA256.json').write_text(json.dumps(checks,indent=2))
if __name__=='__main__':build()
