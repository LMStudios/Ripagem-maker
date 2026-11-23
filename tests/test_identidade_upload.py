import json,threading,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import quote
from http.server import ThreadingHTTPServer
import app
class NamingUploadTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.server=ThreadingHTTPServer(('127.0.0.1',0),app.H);threading.Thread(target=self.server.serve_forever,daemon=True).start();self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown);self.url='http://127.0.0.1:'+str(self.server.server_port)+'/upload'
 def test_initial_metadata_reaches_job_without_calling_asr(self):
  tasks=[]
  class Fake:
   def __init__(self,**kw):tasks.append(kw)
   def start(self):pass
  cfg={'numero_vsl':'2','copy':'C46','editor':'EV8','pitch_manual':''}
  request=Request(self.url,data=b'FAKE_FILE_NOT_TRANSCRIBED',headers={'X-Nomenclatura':quote(json.dumps(cfg)),'X-Filename':'test.mp4','X-New-Product':'Nervelin'},method='POST')
  with patch.object(app,'UPLOADS',Path(self.temp.name)),patch.object(app,'JOBS',{}),patch.object(app,'threading',SimpleNamespace(Thread=Fake)):
   with urlopen(request) as response:self.assertEqual(response.status,200)
  self.assertEqual(tasks[0]['args'][8]['nomenclatura']['numero_vsl'],'02');self.assertEqual(tasks[0]['args'][8]['nomenclatura']['editor'],'EV8')
 def test_invalid_metadata_rejected_before_upload_or_job(self):
  request=Request(self.url,data=b'NO_UPLOAD',headers={'X-Nomenclatura':quote(json.dumps({'numero_vsl':'-1'}))},method='POST')
  with patch.object(app,'UPLOADS',Path(self.temp.name)):
   with self.assertRaises(HTTPError) as error:urlopen(request)
  self.assertEqual(error.exception.code,400);self.assertFalse(list(Path(self.temp.name).iterdir()))

 def test_optimization_mode_reaches_job_before_any_product_search(self):
  tasks=[]
  class Fake:
   def __init__(self,**kw):tasks.append(kw)
   def start(self):pass
  request=Request(self.url,data=b'FAKE_FILE_NOT_TRANSCRIBED',headers={'X-Optimization':'1','X-Filename':'test.mp4','X-Product':'GlycoWise','X-New-Product':'Otherbrand','X-Nomenclatura':quote(json.dumps({'pitch_manual':'52_22'}))},method='POST')
  with patch.object(app,'UPLOADS',Path(self.temp.name)),patch.object(app,'JOBS',{}),patch.object(app,'threading',SimpleNamespace(Thread=Fake)):
   with urlopen(request) as response:self.assertEqual(response.status,200)
  prod=tasks[0]['args'][8]
  self.assertTrue(prod['otimizacao']);self.assertEqual(prod['novo'],'GlycoWise');self.assertEqual(prod['nomenclatura']['pitch_manual'],'52:22')

 def test_preflight_low_space_does_not_create_upload_or_job(self):
  request=Request(self.url+'/check',data=json.dumps({'bytes':5_958_747_138}).encode(),headers={'Content-Type':'application/json'},method='POST')
  with patch.object(app,'UPLOADS',Path(self.temp.name)),patch.object(app,'JOBS',{}),patch('plataforma.uploads.shutil.disk_usage',return_value=SimpleNamespace(free=3_860_000_000)):
   with self.assertRaises(HTTPError) as error:urlopen(request)
   self.assertEqual(error.exception.code,400);result=json.loads(error.exception.read());self.assertIn('3,86 GB',result['erro']);self.assertEqual(app.JOBS,{})
  self.assertFalse(list(Path(self.temp.name).iterdir()))

 def test_preflight_success_never_starts_transcription(self):
  request=Request(self.url+'/check',data=json.dumps({'bytes':100}).encode(),method='POST')
  with patch.object(app,'UPLOADS',Path(self.temp.name)),patch.object(app,'JOBS',{}),patch('plataforma.uploads.shutil.disk_usage',return_value=SimpleNamespace(free=10**10)):
   with urlopen(request) as response:result=json.load(response)
   self.assertTrue(result['ok']);self.assertEqual(result['bytes'],100);self.assertEqual(app.JOBS,{})
  self.assertFalse(list(Path(self.temp.name).iterdir()))
