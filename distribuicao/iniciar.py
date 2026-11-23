"""Inicializador distribuível; nunca usa configurações ou credenciais do autor."""
import os,platform,subprocess,sys,venv,shutil,urllib.request,webbrowser,time,json,uuid,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ENV=ROOT/'.runtime'
PY=ENV/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
def compatible_python():
 if (3,10)<=sys.version_info[:2]<(3,14):return None
 candidates=[]
 for version in ('3.12','3.13','3.11','3.10'):
  if os.name=='nt':candidates.append(['py','-'+version])
  else:
   candidates.extend([[str(p)] for p in (Path('/opt/homebrew/bin')/('python'+version),Path('/usr/local/bin')/('python'+version),Path('/Library/Frameworks/Python.framework/Versions')/version/'bin/python3')])
  candidates.append(['python'+version])
 for command in candidates:
  try:
   result=subprocess.run(command+['-c','import sys,struct;sys.exit(not ((3,10)<=sys.version_info[:2]<(3,14) and struct.calcsize("P")==8))'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
   if result.returncode==0:return command
  except (OSError,subprocess.TimeoutExpired):pass
 raise RuntimeError('Python '+platform.python_version()+' não é compatível. Nenhum Python 3.10 a 3.13 foi encontrado. Instale Python 3.12 (64 bits) em https://www.python.org/downloads/ e abra novamente.')

def runtime_valid():
 if not PY.exists():return False
 try:
  code='import sys,json,platform;print(json.dumps([sys.prefix,sys.base_prefix,list(sys.version_info[:2]),platform.machine()]))'
  result=subprocess.run([str(PY),'-c',code],capture_output=True,text=True,timeout=15)
  if result.returncode:return False
  prefix,base,version,machine=json.loads(result.stdout)
  return (Path(prefix).resolve()==ENV.resolve() and Path(base).resolve()==Path(sys.base_prefix).resolve()
          and version==list(sys.version_info[:2]) and machine==platform.machine())
 except (OSError,ValueError,subprocess.TimeoutExpired):return False

def ensure_runtime():
 if runtime_valid():return
 if ENV.exists():
  # Apenas o ambiente de dependências é movido; nenhuma mídia/configuração é tocada.
  previous=ENV.with_name('.runtime-anterior-'+uuid.uuid4().hex[:8]);ENV.rename(previous)
  print('Ambiente de outro computador ou inválido. Preparando um novo neste Mac/PC…',flush=True)
 else:print('Primeira abertura: preparando ambiente Python…',flush=True)
 venv.create(ENV,with_pip=True)
 if not runtime_valid():raise RuntimeError('Não foi possível criar o ambiente Python local.')

def dependency_fingerprint(desktop=False):
 raw=(ROOT/'requirements.txt').read_bytes()
 return hashlib.sha256(raw+str(sys.version_info[:2]).encode()+platform.machine().encode()+str(desktop).encode()).hexdigest()

def dependencies_ready(marker,desktop=False):
 return marker.exists() and marker.read_text().strip()==dependency_fingerprint(desktop)

def main():
 command=compatible_python()
 if command:
  print('Usando Python compatível encontrado neste computador.',flush=True)
  os.execvp(command[0],command+[str(Path(__file__).resolve())]+sys.argv[1:])
 if '--diagnostico' in sys.argv:
  print('Python compatível: '+sys.executable+' ('+platform.python_version()+')',flush=True)
  return 0
 ensure_runtime()
 marker=ENV/'instalado-v1'
 if not dependencies_ready(marker):
  subprocess.run([str(PY),'-m','pip','install','-r',str(ROOT/'requirements.txt')],check=True)
  if platform.system()=='Darwin' and platform.machine()=='arm64':
   subprocess.run([str(PY),'-m','pip','install','mlx-whisper'],check=True)
  marker.write_text(dependency_fingerprint())
 if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
  raise RuntimeError('Falta FFmpeg (incluindo ffprobe). Mac: brew install ffmpeg. Windows: winget install --id Gyan.FFmpeg -e. Depois feche este terminal e abra o iniciador novamente.')
 # Reutiliza somente um servidor reconhecido como este aplicativo.
 try:
  import json
  with urllib.request.urlopen('http://127.0.0.1:8765/api/recursos',timeout=2) as response:cap=json.load(response)
  if cap.get('forma_produto'):
   webbrowser.open('http://127.0.0.1:8765/');return
 except Exception:pass
 env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
 if '--embedded' in sys.argv:env['DRSTUDIO_EMBED']='1'
 else:env.pop('DRSTUDIO_EMBED',None)
 if '--embedded' in sys.argv:
  os.chdir(ROOT);os.execve(str(PY),[str(PY),str(ROOT/'app.py')],env)
 print('Ripagem Maker aberto. Mantenha esta janela aberta; Ctrl+C encerra o app.',flush=True)
 subprocess.run([str(PY),str(ROOT/'app.py')],cwd=ROOT,env=env,check=True)
 return 0
if __name__=='__main__':
 try:sys.exit(main() or 0)
 except KeyboardInterrupt:pass
 except Exception as e:
  print('\nNão foi possível iniciar: '+str(e),flush=True)
  if '--embedded' not in sys.argv:input('Pressione Enter para fechar…')
  sys.exit(1)
