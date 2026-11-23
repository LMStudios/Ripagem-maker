import copy,unittest
from pathlib import Path
from unittest.mock import patch
import test_workflow_studio as base
from plataforma import visuais as V,trocas as T,ml_core as M
class RandomFallbackTests(unittest.TestCase):
 setUpClass=classmethod(base.StudioTests.setUpClass.__func__)
 tearDownClass=classmethod(base.StudioTests.tearDownClass.__func__)
 setUp=base.StudioTests.setUp
 tearDown=base.StudioTests.tearDown
 job=base.StudioTests.job
 approve=base.StudioTests.approve
 add_audio=base.StudioTests.add_audio
 setup_full=base.StudioTests.setup_full
 def pending(self):
  self.setup_full(duration=4);V.save(self.out,{'modo_takes':'encaixar'});V.add(self.out,{'start':5000,'end':7000,'kit':94})
  # Outro vídeo distinto, classificado como Produto.
  s=V.load(self.out);a=copy.deepcopy(s['assets'][0]);other=next((Path(__file__).parent/'fixtures/MATERIAIS_POTES_TESTE').glob('kit_3*.mp4'));meta=V.probe(other);a.update(id='second-product',kit=3,path=str(other.resolve()),stamp=[other.stat().st_size,other.stat().st_mtime_ns],duration=meta['duration']);s['assets'].append(a);V.write(self.out,s)
  s=V.schedule(self.out,seed=1);self.assertEqual([i['kit'] for i in s['issues']],[94]);return s
 def test_missing_kit_requires_explicit_authorization_and_preserves_resolved(self):
  s=self.pending();existing=copy.deepcopy(s['segments']);rows=copy.deepcopy(s['mentions']);audio=T.plan_path(self.out).read_bytes();ids=[i['mention'] for i in s['issues']]
  result=V.fill_random_job(self.job(),self.out,ids,V.signature(s));after=V.load(self.out)
  self.assertEqual(result['preenchidas'],1);self.assertFalse(after['issues']);self.assertTrue(after['prepared']);self.assertEqual(after['mentions'],rows);self.assertEqual(T.plan_path(self.out).read_bytes(),audio)
  self.assertEqual(after['segments'][:len(existing)],existing);fallback=[v for v in after['segments'] if v.get('aleatorio_autorizado')];self.assertTrue(fallback);self.assertTrue(all(v['kit_detectado']==94 for v in fallback))
  for a,b in zip(after['segments'],after['segments'][1:]):self.assertNotEqual(a['asset'],b['asset'])
  again=V.schedule(self.out,seed=5);self.assertFalse(again['issues']);self.assertEqual(len(again['fallbacks']),1)
 def test_changed_window_does_not_inherit_authorization(self):
  s=self.pending();ids=[i['mention'] for i in s['issues']];V.fill_random_job(self.job(),self.out,ids,V.signature(s));s=V.load(self.out);row=next(r for r in s['mentions'] if r['kit']==94);row['kit']=93;V.write(self.out,s);s=V.schedule(self.out)
  self.assertTrue(any(i.get('kit')==93 for i in s['issues']))
 def test_stale_plan_and_unknown_pending_do_not_change_state(self):
  s=self.pending();before=V.path(self.out).read_bytes()
  for ids,expected in [(['unknown'],V.signature(s)),([s['issues'][0]['mention']],'stale')]:
   with self.assertRaises(ValueError):V.fill_random_job(self.job(),self.out,ids,expected)
   self.assertEqual(V.path(self.out).read_bytes(),before)
 def test_support_is_not_used_when_no_product_video_exists(self):
  s=self.pending()
  for a in s['assets']:a['uso']='apoio'
  V.write(self.out,s)
  with self.assertRaisesRegex(ValueError,'classificados como Produto'):V.fill_random_job(self.job(),self.out,[i['mention'] for i in s['issues']],V.signature(s))
