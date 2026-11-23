import unittest
from unittest.mock import patch
from plataforma import deteccao_visual as D, visual_refino as R

class RefinementTests(unittest.TestCase):
 def test_weak_almost_complete_label_is_not_lost(self):
  # Leituras reais do Rosedil: sobreposição da legenda e final do rótulo borrado.
  for text in ('ROSEDP', 'ROSEDD', 'ROSEDIver analyzed'):
   rows=D.group([(0,[]),(1,[[text,.97,.65,.3]]),(2,[])],[],['rosedil'])
   self.assertEqual(len(rows),1,text)
   self.assertNotEqual(D.confidence(rows[0]),'alta')
 def test_generic_brain_never_becomes_vapobrain(self):
  rows=D.group([(t,[[text,1,.8,.4]]) for t,text in enumerate(('your brain','brain games','brain','blood brain barrier'))],[],['vapobrain'])
  self.assertEqual(rows,[])
 def test_ocr_character_confusions_are_compared_to_the_full_name(self):
  self.assertGreaterEqual(D.match([['G0LDEN NERVE5',.9,.4,.3]],['golden nerves'])[0],.99)
  self.assertEqual(D.group([(0,[['ROSEDIL',.55,.4,.3]])],[],['rosedil'])[0]['ocr_confianca'],.55)
  self.assertNotEqual(D.confidence(D.group([(0,[['ROSEDIL',.55,.4,.3]])],[],['rosedil'])[0]),'alta')
 def test_words_from_distant_regions_cannot_form_a_brand(self):
  self.assertLess(D.match([['GOLDEN',1,.1,.2],['NERVES',1,.9,.2]],['golden nerves'])[0],.8)
 def test_repeated_product_in_two_shots_does_not_merge_across_a_cut(self):
  hit=[['ROSEDIL',1,.4,.2]]
  rows=D.group([(0,[]),(1,hit),(1.5,[]),(2,hit),(3,[])],[(1.5,40)],['rosedil'])
  self.assertEqual(len(rows),2)
 def test_two_negatives_keep_similar_background_scenes_separate(self):
  hit=[['OLD BRAND',1,.4,.2]]; other=[['OTHER ITEM',1,.4,.2]]
  samples=[(0,[]),(1,hit),(1.5,other),(2,other),(2.75,hit),(3.25,[])]
  rows=D.group(samples,[(1.5,6),(2.5,7)],['old brand'])
  self.assertEqual(len(rows),2)
  self.assertLess(rows[0]['fim_ms'],rows[1]['inicio_ms'])
 def test_split_review_never_duplicates_interval_ids_or_bulk_approves_new_coverage(self):
  old=[{'id':'approved','status':'aprovado','inicio_ms':0,'fim_ms':4000,'inicio_detectado_ms':0,'fim_detectado_ms':4000}]
  new=[{'id':str(i),'status':'sugerido','inicio_ms':a,'fim_ms':b,'inicio_detectado_ms':a,'fim_detectado_ms':b} for i,(a,b) in enumerate(((0,2000),(2000,4000)))]
  rows=D.merge_review(old,new)
  self.assertEqual(len({r['id'] for r in rows}),2)
  # 3.11: as duas partes estão dentro da área aprovada pelo editor e herdam a decisão (ids distintos).
  self.assertEqual(sum(r['status']=='aprovado' for r in rows),2)
  extended=[{'id':'new','status':'sugerido','inicio_ms':0,'fim_ms':12000,'inicio_detectado_ms':0,'fim_detectado_ms':12000}]
  self.assertEqual(D.merge_review(old,extended)[0]['status'],'sugerido')
 def test_no_one_second_tolerance_hides_uncovered_product(self):
  item={'id':'a','status':'sugerido','inicio_ms':1000,'fim_ms':2500}
  with patch.object(D,'load',return_value={'intervalos':[item]}),patch.object(D,'outdated',return_value=''),patch.object(D,'fala_windows',return_value=[(1000,2100)]),patch.object(D,'window',side_effect=ValueError),patch.object(D.T,'source',side_effect=ValueError),patch.object(D.M,'JOBS',{}):
   row=D.view('/tmp/project')['intervalos'][0]
   self.assertFalse(row['coberto_pela_fala']);self.assertEqual(row['sem_cobertura_ms'],400)
 def test_missing_speech_warning_is_never_hidden_by_visual_refresh(self):
  item={'id':'a','status':'sugerido','inicio_ms':1000,'fim_ms':2000,'fala_sem_troca':True}
  with patch.object(D,'load',return_value={'intervalos':[item]}),patch.object(D,'outdated',return_value=''),patch.object(D,'fala_windows',return_value=[(0,3000)]),patch.object(D,'window',side_effect=ValueError),patch.object(D.T,'source',side_effect=ValueError),patch.object(D.M,'JOBS',{}):
   self.assertFalse(D.view('/tmp/project')['intervalos'][0]['coberto_pela_fala'])
 def test_refinement_targets_find_short_shots_between_coarse_samples(self):
  points,_=R.targets([(0,[]),(1,[]),(2,[])],[(.25,40),(.75,40)],['rosedil'],0,2,D.match,D.group)
  self.assertIn(.5,points)
 def test_refinement_adds_missed_medium_shot(self):
  cuts=[(5,40),(8,40),(10,40)]
  points,_=R.targets([(t,[]) for t in range(12)],cuts,['old brand'],0,12,D.match,D.group)
  self.assertIn(5.5,points)
 def test_refinement_handles_portrait_without_overlong_input(self):
  self.assertEqual(R.image_size({'width':1080,'height':1920},1440),(810,1440))
  self.assertEqual(R.image_size({'width':1920,'height':1080},1440),(1440,810))
 def test_adjacent_text_is_required_to_reconstruct_split_name(self):
  far=[['OLD',1,.2,.1,.1,.05],['BRAND',1,.2,.1,.9,.05]]
  self.assertLess(D.match(far,['old brand'])[0],.95)
  close=[['OLD',1,.2,.1,.35,.05],['BRAND',1,.2,.1,.49,.05]]
  self.assertEqual(D.match(close,['old brand'])[0],1)
 def test_label_reference_is_visual_and_requires_review(self):
  lookalike=['our old brand product',.82,.8,.35,.5,.15,'referencia_visual']
  row=D.group([(0,[]),(1,[lookalike]),(2,[])],[],['old brand'])[0]
  self.assertEqual((row['local'],D.confidence(row),row['legenda_ms']),('imagem','revisar',[]))
  self.assertIn('Aparência parecida', D.reason(row))
 def test_refinement_budget_also_checks_last_offer(self):
  hit=[['ROSEDIL',1,.4,.2]];samples=[]
  for i in range(150):samples.extend([(i*10,[]),(i*10+2,hit),(i*10+4,[])])
  points,skipped=R.targets(samples,[],['rosedil'],0,1500,D.match,D.group)
  self.assertLessEqual(len(points),R.MAX_POINTS);self.assertGreater(max(points),1450);self.assertGreater(skipped,0)

class WorkerSamplingTests(unittest.TestCase):
 def test_local_product_flash_between_one_second_samples_is_read(self):
  import json,tempfile,numpy as np
  from pathlib import Path
  from types import SimpleNamespace
  from plataforma import ocr_worker as W
  frames=[]
  for k in range(13):
   rgb=np.zeros((180,320,3),dtype=np.uint8)
   if k in (5,6):rgb[80:100,90:125]=255
   frames.append((k/4,rgb))
  with tempfile.TemporaryDirectory() as d,patch.object(W,'frames',return_value=iter(frames)),patch.object(W,'read',side_effect=lambda _,rgb:[['ROSEDIL',1,.5,.2]] if rgb.max() else []):
   path=Path(d)/'unit.jsonl';W.unit(None,SimpleNamespace(),0,path)
   data=[json.loads(line) for line in path.read_text().splitlines()]
   self.assertTrue(any(row.get('ocr') and row['t'] in (1.25,1.5) for row in data))
   self.assertTrue(any(row.get('local') and row['t']==1.25 for row in data))
 def test_cached_small_motion_still_selects_a_refinement_timestamp(self):
  import tempfile
  from pathlib import Path
  with tempfile.TemporaryDirectory() as d:
   D.unit_file(Path(d),0).write_text('{"t":1.25,"d":1.1,"local":true}\n{"t":1.5,"d":0.5}\n')
   samples,changes=D.read_samples(Path(d),[0],0,6)
  self.assertIsNone(D.cut_between(changes,0,4))
  points,_=R.targets(samples,changes,['old brand'],0,6,D.match,D.group)
  self.assertIn(1.25,points)
 def test_corner_crop_recovers_label_and_remaps_position(self):
  import numpy as np
  from plataforma import ocr_worker as W
  rgb=np.zeros((800,1200,3),dtype=np.uint8)
  rgb[96:144,852:948]=255
  def read(_,frame,details=False):
   if frame.shape==rgb.shape or not frame.max():
    return []
   y,x=np.nonzero(frame[:,:,0])
   return [['OLD BRAND',.99,float(y.mean())/frame.shape[0],.15,float(x.mean())/frame.shape[1],.1]]
  with patch.object(W,'read',side_effect=read):
   rows=W.detailed_read(None,rgb,['old brand'])
  score,_,hit=D.match(rows,['old brand'])
  self.assertEqual(score,1)
  self.assertAlmostEqual(hit[2],.15,places=2)
  self.assertAlmostEqual(hit[4],.75,places=2)
 def test_unchanged_frame_reuse_has_a_refresh_limit(self):
  import json,tempfile,numpy as np
  from pathlib import Path
  from types import SimpleNamespace
  from plataforma import ocr_worker as W
  frame=np.zeros((180,320,3),dtype=np.uint8)
  with tempfile.TemporaryDirectory() as d,patch.object(W,'frames',return_value=iter((k/4,frame) for k in range(41))),patch.object(W,'read',return_value=[]) as read:
   path=Path(d)/'unit.jsonl';W.unit(None,SimpleNamespace(),0,path)
   self.assertEqual(read.call_count,4)

class PreparedCoverageTests(unittest.TestCase):
 def test_actual_v2_missing_one_frame_is_reported(self):
  from plataforma import visuais as V
  required=[{'id':'visual','start':1000,'end':2000}]
  with patch.object(D,'coverage_rows',return_value=required),patch.object(V.T,'source',return_value='source.mp4'),patch.object(V.T,'probe',return_value={'fps':25,'duration':4}),patch('plataforma.armazenamento.visual_margin_ms',return_value=0),patch.object(V.T,'load',return_value={'itens':[]}):
   self.assertEqual(V.coverage_gaps('unused',{},[{'start_frame':25,'end_frame':49}])[0]['quadros_sem_cobertura'],1)
   self.assertEqual(V.coverage_gaps('unused',{},[{'start_frame':25,'end_frame':50}]),[])
 def test_only_current_manual_exception_can_cover_a_gap(self):
  from plataforma import visuais as V
  state={'manual_markers':[{'id':'manual','start':1000,'end':2000}]}
  state['manual_markers'][0]['token']=V.manual_token(state,'manual',1000,2000)
  with patch.object(D,'coverage_rows',return_value=[{'id':'v','start':1000,'end':2000}]),patch.object(V.T,'source',return_value='source.mp4'),patch.object(V.T,'probe',return_value={'fps':25,'duration':4}),patch('plataforma.armazenamento.visual_margin_ms',return_value=0),patch.object(V.T,'load',return_value={'itens':[]}):
   self.assertEqual(V.coverage_gaps('unused',state,[]),[])
   state['coverage_policy']={'changed':True}
   self.assertEqual(len(V.coverage_gaps('unused',state,[])),1)
 def test_expanded_timeline_is_compared_on_the_same_axis(self):
  from plataforma import visuais as V
  changes=[{'a':0,'b':20,'extra':10,'start':0}]
  with patch.object(D,'coverage_rows',return_value=[{'id':'v','start':1000,'end':2000}]),patch.object(V.T,'source',return_value='source.mp4'),patch.object(V.T,'probe',return_value={'fps':25,'duration':4}),patch('plataforma.armazenamento.visual_margin_ms',return_value=0),patch.object(V.T,'load',return_value={'itens':[]}),patch('plataforma.montagem.edits',return_value=changes):
   self.assertEqual(V.coverage_gaps('unused',{'timeline_final':True},[{'start_frame':35,'end_frame':60}]),[])

class FillingRegressionTests(unittest.TestCase):
 def test_speech_that_becomes_marker_cannot_remove_approved_label_coverage(self):
  from plataforma import visuais as V
  state={'mentions':[],'cobrir_falas':True}
  plan={'itens':[{'id':'speech','original':'test'}]}
  with patch.object(V,'audio_windows',return_value=[['speech',400,900]]),patch.object(V,'first_product_mention',return_value=1000),patch.object(V.T,'probe',return_value={'fps':25,'duration':3}),patch.object(V.T,'source',return_value='source.mp4'),patch.object(V.T,'load',return_value=plan),patch('plataforma.armazenamento.visual_margin_ms',return_value=0),patch.object(V,'coverage_policy',return_value={'primeira_mencao_ms':1000}),patch.object(D,'coverage_rows',return_value=[{'id':'old','start':500,'end':950,'produto_antigo':True}]):
   rows=V.covered_mentions('unused',state)
   self.assertEqual([(r['start'],r['end']) for r in rows],[(500,950)])
 def test_single_frame_remainder_is_not_discarded(self):
  from plataforma import visuais as V
  rows=[{'id':'kit','start':1000,'end':1960}]
  with patch.object(D,'coverage_rows',return_value=[{'id':'old','start':1000,'end':2000,'produto_antigo':True}]):
   result=V.old_product_rows('unused',rows,[(1000,1960)],duration=3000,margin=0)
  self.assertEqual([(r['start'],r['end']) for r in result],[(1000,1960),(1960,2000)])


 def test_padding_respects_first_mention_and_runtime_and_merges_overlaps(self):
  from plataforma import visuais as V
  sightings=[
   {'id':'old-3','start':3400,'end':4000,'limite_inicio_ms':1600,'produto_antigo':True},
   {'id':'old-1','start':1800,'end':2000,'limite_inicio_ms':1600,'produto_antigo':True},
   {'id':'old-2','start':2400,'end':2650,'limite_inicio_ms':1600,'produto_antigo':True},
  ]
  with patch.object(D,'coverage_rows',return_value=sightings):
   result=V.old_product_rows('unused',[{'id':'kit','start':2300,'end':3000}],[(2300,3000)],duration=4100,margin=1500)
  self.assertEqual([(r['start'],r['end']) for r in result],[(1600,2300),(2300,3000),(3000,4100)])
  self.assertEqual(sightings[1]['start'],1800)

 def test_manually_reviewed_times_stay_exact_and_bridge_obeys_visual_floor(self):
  from plataforma import visuais as V
  rows=[
   {'id':'manual','start':4400,'end':4800,'limite_inicio_ms':3600,'produto_antigo':True,'ajustado':True},
   {'id':'older','start':3650,'end':3700,'limite_inicio_ms':3600,'produto_antigo':True},
  ]
  with patch.object(D,'coverage_rows',return_value=rows):
   result=V.old_product_rows('unused',[{'id':'speech','start':2750,'end':3500}],[],duration=7000,margin=100)
  self.assertEqual([(r['start'],r['end']) for r in result],[(2750,3500),(3600,3800),(4400,4800)])

 def test_xml_coverage_checks_padded_edges_around_approved_sightings(self):
  from plataforma import visuais as V
  sightings=[{'id':'visual','start':2200,'end':2400,'limite_inicio_ms':1000}]
  with patch.object(D,'coverage_rows',return_value=sightings),patch.object(V.T,'source',return_value='source.mp4'),patch.object(V.T,'probe',return_value={'fps':25,'duration':4}),patch.object(V.T,'load',return_value={'itens':[]}),patch('plataforma.armazenamento.visual_margin_ms',return_value=1500):
   self.assertEqual(V.coverage_gaps('unused',{},[{'start_frame':26,'end_frame':98}])[0]['quadros_sem_cobertura'],1)
   self.assertEqual(V.coverage_gaps('unused',{},[{'start_frame':25,'end_frame':98}]),[])
