import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from plataforma import limpeza as L,ml_core as M,armazenamento as S

class CleanupTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.media=self.root/'saidas';self.media.mkdir();self.home=self.root/'cleanup';self.cache=self.root/'cache.pyc';self.cache.write_bytes(b'cache')
  self.a=self.media/'a.mp4';self.b=self.media/'b.mp4';self.a.write_bytes(b'original-content'*800000);self.b.write_bytes(self.a.read_bytes());self.outside=self.root/'outside.mp4';self.outside.write_bytes(b'keep me')
  self.patches=[patch.object(L,'HOME',self.home),patch.object(L,'roots',return_value=[self.media]),patch.object(L,'cache_files',side_effect=lambda:[self.cache] if self.cache.exists() else []),patch.object(S,'PROJECT',self.root),patch.object(M,'JOBS',{}),patch.object(S,'MAINTENANCE',False)]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.temp.cleanup()
 def job(self):return M.Job('limpeza','Teste',None)
 def test_analysis_clone_cache_and_reanalysis(self):
  self.media.joinpath('link.mp4').symlink_to(self.outside)
  result=L.analyze(self.job());self.assertEqual(result['duplicados'],1);self.assertEqual(result['caches'],1)
  done=L.execute(self.job(),result['token']);self.assertEqual(done['consolidados'],1);self.assertFalse(self.cache.exists());self.assertTrue(self.a.exists() and self.b.exists());self.assertEqual(self.a.read_bytes(),self.b.read_bytes())
  again=L.analyze(self.job());self.assertEqual(again['duplicados'],0);self.assertEqual(again['ja_otimizado_bytes'],self.a.stat().st_size)
  with self.b.open('r+b') as f:f.write(b'CHANGED')
  self.assertTrue(self.a.read_bytes().startswith(b'original'))
  self.assertEqual(self.outside.read_bytes(),b'keep me')
 def test_changed_file_not_replaced(self):
  result=L.analyze(self.job());self.b.write_bytes(b'new user content')
  with self.assertRaisesRegex(ValueError,'mudaram'):L.execute(self.job(),result['token'])
  self.assertEqual(self.b.read_bytes(),b'new user content');self.assertTrue(self.cache.exists())
 def test_token_and_outside_paths_are_rejected(self):
  result=L.analyze(self.job())
  with self.assertRaises(ValueError):L.execute(self.job(),'invalid')
  plan=L.read(self.home/'plano.json',{});plan['duplicates'][0]['path']=str(self.outside);L.write(self.home/'plano.json',plan)
  with self.assertRaises(ValueError):L.execute(self.job(),result['token'])
  self.assertEqual(self.outside.read_bytes(),b'keep me')
 def test_clone_failure_preserves_original(self):
  result=L.analyze(self.job());before=self.b.read_bytes()
  with patch.object(L.subprocess,'run',return_value=type('R',(),{'returncode':1})()):done=L.execute(self.job(),result['token'])
  self.assertEqual(done['consolidados'],0);self.assertTrue(done['avisos']);self.assertEqual(self.b.read_bytes(),before)
 def test_cancel_and_maintenance_reset(self):
  job=self.job();job.cancel=True
  with self.assertRaises(M.Cancelled):L.maintenance(job,lambda:L.analyze(job),lambda:[])
  self.assertFalse(S.MAINTENANCE)
  other=self.job();other.status='executando'
  with patch.dict(M.JOBS,{other.id:other}):
   with self.assertRaises(ValueError):L.maintenance(self.job(),lambda:None,lambda:[])
  self.assertFalse(S.MAINTENANCE)
 def test_cannot_submit_new_work_during_cleanup(self):
  with patch.object(S,'MAINTENANCE',True):
   with self.assertRaisesRegex(ValueError,'limpeza'):M.submit('render','Teste',lambda j:None,'render')
 def test_legacy_verified_cleanup_is_not_repeated(self):
  result=L.analyze(self.job());plan=L.read(self.home/'plano.json',{});row=plan['duplicates'][0];L.execute(self.job(),result['token'])
  L.write(self.root/'limpeza_relatorio_20261025.json',{'groups':[[{'path':str(self.a),'hash':row['hash']},{'path':str(self.b),'hash':row['hash']}]],'consolidated':[{'path':row['path'],'canonical':row['canonical']}]})
  (self.home/'catalogo.json').unlink();again=L.analyze(self.job());self.assertEqual(again['duplicados'],0);self.assertGreater(again['ja_otimizado_bytes'],0)
 def test_corrupt_clone_is_never_installed(self):
  result=L.analyze(self.job());before=self.b.read_bytes()
  def bad_copy(cmd,**kwargs):Path(cmd[-1]).write_bytes(b'corrupt');return type('R',(),{'returncode':0})()
  with patch.object(L.subprocess,'run',side_effect=bad_copy):
   with self.assertRaisesRegex(ValueError,'mudou'):L.execute(self.job(),result['token'])
  self.assertEqual(self.b.read_bytes(),before);self.assertFalse(list(self.media.glob('.ripagem-clone-*')))
