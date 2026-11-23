import io,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from plataforma.uploads import receive, check
class UploadTests(unittest.TestCase):
 def test_incomplete_is_removed_and_never_published(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'source.mp4'
   with self.assertRaisesRegex(ValueError,'interrompido'):receive(io.BytesIO(b'partial'),100,out)
   self.assertFalse(out.exists());self.assertEqual(list(Path(d).iterdir()),[])
 def test_disk_full_does_not_consume_body(self):
  with tempfile.TemporaryDirectory() as d,patch('plataforma.uploads.shutil.disk_usage',return_value=SimpleNamespace(free=0)):
   stream=io.BytesIO(b'123')
   with self.assertRaisesRegex(ValueError,'Espaço'):receive(stream,3,Path(d)/'source.wav')
   self.assertEqual(stream.tell(),0)
 def test_complete_preserves_existing_destination(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'source.wav';receive(io.BytesIO(b'123'),3,out);self.assertEqual(out.read_bytes(),b'123')
   with self.assertRaises(ValueError):receive(io.BytesIO(b'456'),3,out)
   self.assertEqual(out.read_bytes(),b'123')
 def test_invalid_sizes(self):
  for n in (0,-1,'invalid',21*1024**3,True,1.5,None):
   with self.assertRaises(ValueError):receive(io.BytesIO(b'123'),n,Path('/not-created'))
 def test_real_large_video_preflight_explains_disk_shortage_without_creating_media(self):
  with tempfile.TemporaryDirectory() as d,patch('plataforma.uploads.shutil.disk_usage',return_value=SimpleNamespace(free=3_860_000_000)):
   with self.assertRaisesRegex(ValueError,r'5,96 GB.*3,86 GB.*6,23 GB') as error:check(5_958_747_138,Path(d))
   self.assertIn('Nenhuma transcrição foi iniciada',str(error.exception));self.assertEqual(list(Path(d).iterdir()),[])
 def test_capacity_is_checked_again_after_successful_preflight(self):
  with tempfile.TemporaryDirectory() as d,patch('plataforma.uploads.shutil.disk_usage',side_effect=[SimpleNamespace(free=10**10),SimpleNamespace(free=0)]):
   self.assertTrue(check(100,Path(d))['ok']);stream=io.BytesIO(b'a'*100)
   with self.assertRaisesRegex(ValueError,'Espaço'):receive(stream,100,Path(d)/'source.mp4')
   self.assertEqual(stream.tell(),0);self.assertEqual(list(Path(d).iterdir()),[])
