"""Atualizações de código por ZIP, sem incluir nem substituir dados do usuário."""
import hashlib,io,json,os,re,shutil,tempfile,uuid,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parent.parent
PENDING=False
MAX_BYTES=25*1024*1024
TOP={'app.py','index.html','VERSION','iniciar.py','requirements.txt','desktop_boot.py','desktop_win.py','prepare_windows.py'}
def allowed(name):
 p=PurePosixPath(name)
 if '\\' in name or p.is_absolute() or '..' in p.parts or str(p)!=name:return False
 return name in TOP or (len(p.parts)==2 and p.parts[0]=='plataforma' and p.suffix=='.py') or (len(p.parts)>=3 and p.parts[:2]==('plataforma','static') and p.suffix in ('.html','.css','.js','.svg','.png','.ico'))
def version(root=None):
 p=Path(root or ROOT)/'VERSION'
 return p.read_text().strip() if p.exists() else '2.1.0'
def status(runtime=None):return {'versao':version(),'versao_em_execucao':runtime,'reinicio_necessario':PENDING or bool(runtime and runtime!=version()),'formato':'ripagem-update-v1'}
def number(value):
 if not isinstance(value,str) or not re.fullmatch(r'\d+\.\d+\.\d+',value):raise ValueError('Versão do pacote inválida.')
 return tuple(map(int,value.split('.')))
def apply(data,root=None):
 global PENDING
 root=Path(root or ROOT).resolve()
 if len(data)>MAX_BYTES:raise ValueError('Pacote maior que 25 MB.')
 try:
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   infos=z.infolist();names=[i.filename for i in infos]
   if len(names)!=len(set(names)) or len(names)>2000 or sum(i.file_size for i in infos)>MAX_BYTES:raise ValueError('Pacote inválido ou grande demais.')
   if 'atualizacao.json' not in names or z.getinfo('atualizacao.json').file_size>1024*1024:raise ValueError('Escolha um ZIP de atualização do Ripagem Maker, não o instalador.')
   manifest=json.loads(z.read('atualizacao.json'))
   if not isinstance(manifest,dict):raise ValueError('Manifesto inválido.')
   files=manifest.get('arquivos')
   if manifest.get('formato')!='ripagem-update-v1' or not isinstance(files,dict):raise ValueError('Formato de atualização inválido.')
   if number(manifest.get('versao'))<number(version(root)):raise ValueError('Esse pacote é de uma versão anterior à instalada.')
   if set(names)!=set(files)|{'atualizacao.json'} or not {'app.py','VERSION'}<=set(files):raise ValueError('Pacote incompleto.')
   contents={}
   for name,digest in files.items():
    if not allowed(name) or not (root/name).resolve().is_relative_to(root):raise ValueError('O pacote tenta alterar arquivos fora do código do app.')
    raw=z.read(name)
    if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('O pacote está corrompido. Baixe novamente.')
    contents[name]=raw
   if contents['VERSION'].decode().strip()!=manifest['versao']:raise ValueError('Versão inconsistente.')
 except (zipfile.BadZipFile,KeyError,UnicodeError,json.JSONDecodeError) as e:raise ValueError('Pacote de atualização inválido.') from e
 backup=root/'.atualizacoes'/('antes-'+version(root)+'-'+uuid.uuid4().hex[:8]);backup.mkdir(parents=True)
 changed=[]
 with tempfile.TemporaryDirectory(prefix='.update-',dir=root) as temporary:
  stage=Path(temporary)
  for name,raw in contents.items():
   target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
  try:
   for name in sorted(contents,key=lambda n:(n=='VERSION',n)):
    target=root/name;old=backup/name
    if target.exists():old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,old)
    target.parent.mkdir(parents=True,exist_ok=True);os.replace(stage/name,target);changed.append(name)
  except Exception:
   for name in reversed(changed):
    old=backup/name;target=root/name
    if old.exists():shutil.copy2(old,target)
    else:target.unlink(missing_ok=True)
   raise
 PENDING=True
 return {'versao':manifest['versao'],'reinicio_necessario':True,'arquivos':len(contents),'backup':str(backup)}
