"""Stage allowlisted code only; optionally freeze the Python engine on the target OS."""
import argparse,importlib.util,json,hashlib,shutil,subprocess,sys,platform
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parent
p=argparse.ArgumentParser();p.add_argument('--freeze',action='store_true');args=p.parse_args()
spec=importlib.util.spec_from_file_location('cleanpack',ROOT/'distribuicao/empacotar.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
dest=HERE/'engine'/'code';dest.mkdir(parents=True,exist_ok=True)
for f in m.files():
 target=dest/f.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,target)
for n in ('iniciar.py','requirements.txt'):shutil.copy2(ROOT/'distribuicao'/n,dest/n)
# Never copy workspace, .env, keyring entries, environments or user videos.
manifest={p.relative_to(dest).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.rglob('*') if p.is_file()}
(HERE/'engine'/'manifest.json').write_text(json.dumps(manifest,indent=2))
if args.freeze:
 command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--name','ripagem-engine','--distpath',str(HERE/'engine'/'bin'),'--workpath',str(HERE/'build-python'),'--specpath',str(HERE/'build-python'),'--collect-all','requests','--collect-all','numpy','--collect-all','keyring','--collect-all','faster_whisper','--collect-all','ctranslate2','--collect-all','av','--collect-all','tokenizers','--hidden-import','keyring.backends.macOS','--hidden-import','keyring.backends.Windows']
 command+=['--paths',str(ROOT/'plataforma'),'--hidden-import','asr_worker','--hidden-import','ocr_worker','--collect-all','rapidocr','--collect-all','yt_dlp']
 for optional in ('torch','torchvision','torchaudio','tensorflow','transformers','pandas','matplotlib','scipy','IPython','pytest','openpyxl'):
  command+=['--exclude-module',optional]
 for n in ('ffmpeg','ffprobe'):
  executable=shutil.which(n)
  if not executable:raise SystemExit('Instale '+n+' antes de congelar o motor.')
  command+=['--add-binary',executable+':.']
 command+=[str(HERE/'scripts/engine_entry.py')];subprocess.run(command,check=True)
if args.freeze:(HERE/'engine'/'runtime.json').write_text(json.dumps({'platform':sys.platform,'machine':platform.machine(),'python':platform.python_version()}))
print('Código preparado sem dados pessoais. Motor congelado: '+str(args.freeze))
