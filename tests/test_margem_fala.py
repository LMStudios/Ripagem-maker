import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from plataforma import armazenamento as S,montagem as MT
class MarginTests(unittest.TestCase):
 def test_settings_preserve_folder_and_margin(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(S,'CONFIG',Path(tmp)/'settings.json'):
   S.save_margin(120);S.save('');self.assertEqual(S.status()['margem_fala_ms'],120)
   for bad in [-1,501,True,2.5,'100']:
    with self.assertRaises(ValueError):S.save_margin(bad)
 def test_margin_never_eats_previous_replacement(self):
  with patch.object(MT,'margin_ms',return_value=200):
   self.assertEqual(MT.mute_start(100,0,25),95)
   self.assertEqual(MT.mute_start(100,98,25),98)
   self.assertEqual(MT.mute_start(2,0,25),0)

 def test_small_original_fragment_between_replacements_is_muted(self):
  with patch.object(MT,'margin_ms',return_value=200):
   self.assertEqual(MT.mute_start(100,92,25),92)
   self.assertEqual(MT.mute_start(100,90,25),95)
  with patch.object(MT,'margin_ms',return_value=0):self.assertEqual(MT.mute_start(100,98,25),100)
 def test_default_audio_and_visual_margins_and_preserved_configuration(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(S,'CONFIG',Path(tmp)/'settings.json'):
   self.assertEqual(MT.margin_ms(),200);self.assertEqual(S.visual_margin_ms(),1500);self.assertEqual(S.status()['margem_visual_ms'],1500)
   S.save_margin(150);S.save_visual_margin(1200)
   self.assertEqual(MT.margin_ms(),150);self.assertEqual(S.status()['margem_visual_ms'],1200)
   S.save_visual_margin(1000)
   self.assertEqual(S.visual_margin_ms(),1000)
   for bad in [-1,3001,True,1.2,'1000']:
    with self.assertRaises(ValueError):S.save_visual_margin(bad)
