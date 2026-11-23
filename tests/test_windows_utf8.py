"""Regressão: iniciar sem API key com stdout cp1252 não pode derrubar o servidor."""
import os,sys,time,tempfile,subprocess,zipfile,urllib.request,json,unittest,socket
from pathlib import Path
class WindowsEncodingTests(unittest.TestCase):
 def test_no_key_startup_under_cp1252(self):
  root=Path(__file__).resolve().parents[1]
  with tempfile.TemporaryDirectory() as temp:
   import shutil
   dest=Path(temp)/'app';dest.mkdir();shutil.copy2(root/'app.py',dest/'app.py')
   shutil.copytree(root/'plataforma',dest/'plataforma',ignore=shutil.ignore_patterns('workspace','__pycache__'))
   with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
   env=os.environ.copy();env.pop('ASSEMBLYAI_API_KEY',None);env.update(PORT=str(port),DRSTUDIO_EMBED='1',PYTHONIOENCODING='cp1252')
   with (Path(temp)/'log').open('wb') as log:
    process=subprocess.Popen([sys.executable,'-c',"from plataforma import segredos;segredos.get=lambda p:None;import runpy;runpy.run_path('app.py',run_name='__main__')"],cwd=dest,env=env,stdout=log,stderr=log)
    try:
     for _ in range(60):
      if process.poll() is not None:self.fail('Servidor encerrou ao imprimir aviso de chave ausente')
      try:
       with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/assembly-chave',timeout=1) as response:
        self.assertEqual(json.load(response),{'configurada':False});break
      except OSError:time.sleep(.1)
     else:self.fail('Servidor não respondeu')
    finally:process.terminate();process.wait(timeout=10)
   text=(Path(temp)/'log').read_text(encoding='utf-8');self.assertIn('Configure a chave',text);self.assertNotIn('UnicodeEncodeError',text)
