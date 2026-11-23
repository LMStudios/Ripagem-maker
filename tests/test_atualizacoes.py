import hashlib,io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from plataforma import atualizacoes as U

def package(files=None,version='2.2.0'):
 files=files or {'VERSION':version.encode(),'app.py':b'# new version\n'}
 data=io.BytesIO()
 with zipfile.ZipFile(data,'w') as z:
  for name,raw in files.items():z.writestr(name,raw)
  z.writestr('atualizacao.json',json.dumps({'formato':'ripagem-update-v1','versao':version,'arquivos':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()}}))
 return data.getvalue()
class UpdateTests(unittest.TestCase):
 def tearDown(self):U.PENDING=False
 def test_preserves_data_and_backs_up_code(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'app.py').write_text('# old');(root/'.env').write_text('keep');(root/'VERSION').write_text('2.1.0');(root/'saidas').mkdir();(root/'saidas/video.mp4').write_bytes(b'video')
   result=U.apply(package(),root)
   self.assertEqual((root/'.env').read_text(),'keep');self.assertEqual((root/'saidas/video.mp4').read_bytes(),b'video');self.assertEqual((Path(result['backup'])/'app.py').read_text(),'# old');self.assertEqual(U.version(root),'2.2.0');self.assertTrue(U.PENDING)
 def test_forbidden_paths_rejected_without_changes(self):
  for name in ('.env','../app.py','saidas/video.py','plataforma/workspace/ajustes.json','/app.py','plataforma/../app.py'):
   with tempfile.TemporaryDirectory() as tmp:
    files={'VERSION':b'2.2.0','app.py':b'new',name:b'bad'}
    with self.assertRaises(ValueError):U.apply(package(files),tmp)
    self.assertEqual(list(Path(tmp).iterdir()),[])
 def test_bad_hash_and_downgrade(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'VERSION').write_text('3.0.0')
   with self.assertRaises(ValueError):U.apply(package(),root)
 def test_failed_replace_rolls_back(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'app.py').write_text('old');(root/'VERSION').write_text('2.1.0')
   original=U.os.replace
   def fail_version(a,b):
    if Path(b).name=='VERSION':raise OSError('simulated failure')
    return original(a,b)
   with patch.object(U.os,'replace',side_effect=fail_version):
    with self.assertRaises(OSError):U.apply(package(),root)
   self.assertEqual((root/'app.py').read_text(),'old');self.assertEqual(U.version(root),'2.1.0');self.assertFalse(U.PENDING)

 def test_modified_package_hash_rejected(self):
  original=package();dest=io.BytesIO()
  with zipfile.ZipFile(io.BytesIO(original)) as z,zipfile.ZipFile(dest,'w') as new:
   for name in z.namelist():new.writestr(name,b'changed' if name=='app.py' else z.read(name))
  with tempfile.TemporaryDirectory() as root:
   with self.assertRaisesRegex(ValueError,'corrompido'):U.apply(dest.getvalue(),root)
   self.assertEqual(list(Path(root).iterdir()),[])

class OnlineUpdateTests(unittest.TestCase):
 def test_download_requires_matching_version_and_hash(self):
  from plataforma import equipe_auth
  data=package()
  catalog=json.dumps({'versao':'2.2.0','sha256':hashlib.sha256(data).hexdigest()}).encode()
  with patch.object(U,'version',return_value='2.1.0'), patch.object(equipe_auth,'configured',return_value=True):
   with patch.object(equipe_auth,'download_update',side_effect=[catalog,data]) as read:
    self.assertEqual(U.fetch_available('2.2.0'),data)
    self.assertEqual(read.call_args.args[0],'Ripagem-Maker-Atualizacao-2.2.0.zip')
   with patch.object(equipe_auth,'download_update',side_effect=[catalog,b'changed']):
    with self.assertRaisesRegex(ValueError,'corrompido'):U.fetch_available('2.2.0')
   with patch.object(equipe_auth,'download_update',return_value=catalog) as read:
    with self.assertRaisesRegex(ValueError,'mudou'):U.fetch_available('2.3.0')
    read.assert_called_once()

 def test_no_online_channel_and_no_release(self):
  from plataforma import equipe_auth
  with patch.object(equipe_auth,'configured',return_value=False):
   self.assertFalse(U.available()['configurado'])
  with patch.object(equipe_auth,'configured',return_value=True), patch.object(equipe_auth,'download_update',return_value=None):
   self.assertFalse(U.available()['disponivel'])

 def test_zip_cannot_install_a_different_version(self):
  with tempfile.TemporaryDirectory() as root:
   with self.assertRaisesRegex(ValueError,'não corresponde'):
    U.apply(package(),root,expected='2.3.0')
   self.assertEqual(list(Path(root).iterdir()),[])
