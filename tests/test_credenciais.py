import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from plataforma import credenciais as C
class CredentialsTests(unittest.TestCase):
 def setUp(self):
  self.secrets={};self.patches=[]
  for name,fn in [('get',lambda p:self.secrets.get(p)),('set',lambda p,v:self.secrets.update({p:v})),('delete',lambda p:self.secrets.pop(p,None))]:
   mock=patch.object(C.store,name,side_effect=fn);mock.start();self.addCleanup(mock.stop)
 def test_save_replace_persist_and_no_plaintext(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(C,'ENV',Path(tmp)/'.env'),patch.dict(os.environ,{},clear=True):
   C.ENV.write_text('OTHER=preserved\nASSEMBLYAI_API_KEY='+('x'*32)+'\n');self.assertTrue(C.status()['configurada'])
   for value in ['a'*32,'b'*32]:
    self.assertEqual(C.save(value),{'configurada':True});self.assertEqual(C.key(),value)
   text=C.ENV.read_text();self.assertIn('OTHER=preserved',text);self.assertNotIn(C.NAME+'=',text);self.assertNotIn('b'*32,str(C.overview()))
   C.save('voice_key_test_123','elevenlabs');self.assertEqual(C.key('elevenlabs'),'voice_key_test_123');C.remove('elevenlabs');self.assertFalse(C.status('elevenlabs')['configurada'])
 def test_invalid_input_does_not_write(self):
  for value in [None,'','abc','a'*32+'\nOTHER=bad']:
   with self.assertRaises(ValueError):C.save(value)
  self.assertEqual(self.secrets,{})
 def test_store_failure_preserves_legacy(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(C,'ENV',Path(tmp)/'.env'):
   C.ENV.write_text(C.NAME+'=legacy_1234\n')
   with patch.object(C.store,'set',side_effect=RuntimeError('cofre bloqueado')):
    with self.assertRaises(RuntimeError):C.save('replacement_test')
   self.assertIn('legacy_1234',C.ENV.read_text())
 def test_test_calls_service_without_generation_or_secret_errors(self):
  C.save('secret_test_123456','elevenlabs')
  with patch.object(C.requests,'get',return_value=Mock(ok=True,status_code=200)) as request:
   self.assertTrue(C.test('elevenlabs')['ok']);self.assertIn('/v1/user',request.call_args.args[0])
  with patch.object(C.requests,'get',return_value=Mock(ok=False,status_code=401)):
   with self.assertRaises(ValueError) as error:C.test('elevenlabs')
   self.assertNotIn('secret_test_123456',str(error.exception))
