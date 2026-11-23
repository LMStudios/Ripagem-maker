import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from plataforma.native_files import FileBridge
class NativeFilesTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.jobs=self.root/'jobs';self.jobs.mkdir();self.job=self.jobs/'work';self.job.mkdir();self.xml=self.job/'montagem.xml';self.xml.write_bytes(b'<xmeml/>')
  self.window=Mock();self.window.get_current_url.return_value='http://127.0.0.1:8765/fatiador'
  self.bridge=FileBridge(SimpleNamespace(FileDialog=SimpleNamespace(SAVE=1,FOLDER=2)));self.bridge._window=self.window
 def test_save_confirms_exact_destination_and_preserves_original(self):
  target=self.root/'copied.xml';self.window.create_file_dialog.return_value=[str(target)]
  with patch('plataforma.native_files.S.resolve',return_value=self.xml),patch('plataforma.native_files.S.roots',return_value=[self.jobs]):
   result=self.bridge.save_file('http://127.0.0.1:8765/files/work/montagem.xml?dl=1')
  self.assertTrue(result['ok']);self.assertEqual(result['arquivo'],str(target.resolve()));self.assertEqual(target.read_bytes(),self.xml.read_bytes())
 def test_cancel_does_not_copy(self):
  self.window.create_file_dialog.return_value=None
  with patch('plataforma.native_files.S.resolve',return_value=self.xml),patch('plataforma.native_files.S.roots',return_value=[self.jobs]):r=self.bridge.save_file('http://127.0.0.1:8765/files/work/montagem.xml')
  self.assertTrue(r['cancelado'])
 def test_remote_page_cannot_open_native_dialog(self):
  self.window.get_current_url.return_value='https://external.example/'
  self.assertFalse(self.bridge.choose_folder()['ok']);self.window.create_file_dialog.assert_not_called()
 def test_folder_returns_selected_path(self):
  self.window.create_file_dialog.return_value=[str(self.job)]
  self.assertEqual(self.bridge.choose_folder()['pasta'],str(self.job))
 def test_missing_file_reports_path(self):
  self.xml.unlink()
  with patch('plataforma.native_files.S.resolve',return_value=self.xml),patch('plataforma.native_files.S.roots',return_value=[self.jobs]):r=self.bridge.save_file('http://127.0.0.1:8765/files/work/montagem.xml')
  self.assertFalse(r['ok']);self.assertIn(str(self.xml),r['erro'])
