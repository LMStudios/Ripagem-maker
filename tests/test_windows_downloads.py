import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
from plataforma import sistema
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('win_desktop',ROOT/'distribuicao/windows/desktop_win.py');W=importlib.util.module_from_spec(spec);spec.loader.exec_module(W)
class WindowsDownloadsTests(unittest.TestCase):
 def test_downloads_enabled_before_creating_window(self):
  fake=SimpleNamespace(settings={},start=Mock())
  def create(*a,**k):self.assertTrue(fake.settings['ALLOW_DOWNLOADS'])
  fake.create_window=Mock(side_effect=create)
  reply=Mock();reply.__enter__=Mock(return_value=reply);reply.__exit__=Mock(return_value=False);reply.read.return_value=b'{"forma_produto":true}'
  with tempfile.TemporaryDirectory() as tmp,patch.object(W,'LOG',Path(tmp)/'log'),patch.dict(sys.modules,{'webview':fake}),patch.object(W.urllib.request,'urlopen',return_value=reply):W.main()
  fake.create_window.assert_called_once();fake.start.assert_called_once_with(gui='edgechromium')
 def test_reveal_preserves_xml_and_rejects_outside(self):
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'work';out.mkdir();xml=out/'montagem.xml';xml.write_text('<xmeml/>');outside=Path(tmp)/'other.xml';outside.write_text('outside')
   with patch.object(sistema,'abrir') as open_file:
    result=sistema.revelar_entrega(out,'montagem.xml');open_file.assert_called_once_with(xml.resolve(),revelar=True);self.assertTrue(result['ok'])
    with self.assertRaises(ValueError):sistema.revelar_entrega(out,'../other.xml')
   self.assertEqual(xml.read_text(),'<xmeml/>')
 def test_delivery_status_requires_existing_file(self):
  from plataforma import trocas as T
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp);info=T.delivery_info(out,{'xml':'missing.xml'})
   self.assertFalse(info['xml_existe']);self.assertEqual(info['xml_absoluto'],str((out/'missing.xml').resolve()))
   (out/'missing.xml').write_text('<xmeml/>');self.assertTrue(T.delivery_info(out,{'xml':'missing.xml'})['xml_existe'])
