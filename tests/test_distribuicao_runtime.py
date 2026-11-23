import importlib.util,json,tempfile,unittest,sys,platform
from pathlib import Path
from unittest.mock import patch,Mock
spec=importlib.util.spec_from_file_location('starter',Path(__file__).resolve().parents[1]/'distribuicao/iniciar.py');L=importlib.util.module_from_spec(spec);spec.loader.exec_module(L)
class RuntimeTests(unittest.TestCase):
 def test_missing_library_recreates_without_deleting_user_data(self):
  with tempfile.TemporaryDirectory() as tmp:
   env=Path(tmp)/'.runtime';env.mkdir();(env/'old-marker').touch();media=Path(tmp)/'video.mp4';media.write_bytes(b'keep')
   with patch.object(L,'ENV',env),patch.object(L,'runtime_valid',side_effect=[False,True]),patch.object(L.venv,'create') as create:
    L.ensure_runtime();create.assert_called_once_with(env,with_pip=True)
   self.assertEqual(media.read_bytes(),b'keep');self.assertEqual(len(list(Path(tmp).glob('.runtime-anterior-*/old-marker'))),1)
 def test_runtime_checks_local_interpreter(self):
  with tempfile.TemporaryDirectory() as tmp:
   py=Path(tmp)/'python';py.touch()
   result=Mock(returncode=0,stdout=json.dumps([str(L.ENV),sys.base_prefix,list(sys.version_info[:2]),platform.machine()]))
   with patch.object(L,'PY',py),patch.object(L.subprocess,'run',return_value=result):self.assertTrue(L.runtime_valid())
   result.stdout=json.dumps(['/outro/mac',sys.base_prefix,list(sys.version_info[:2]),platform.machine()])
   with patch.object(L,'PY',py),patch.object(L.subprocess,'run',return_value=result):self.assertFalse(L.runtime_valid())
