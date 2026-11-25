import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from plataforma import takes_completos as C, visuais as V, trocas as T

class WholeIntervalTests(unittest.TestCase):
 def run_plan(self, rows):
  with tempfile.TemporaryDirectory() as directory:
   state={'assets':[{'id':str(kit)+str(i),'kit':kit,'kind':'video','uso':'produto','duration':8}
                    for kit in (2,3,6) for i in range(2)],
          'modo_takes':'inteiro','ajustar_janela':True,'segments':[],'issues':[]}
   with patch('plataforma.workflow.require_takes'),patch.object(T,'source',return_value=Path(directory)/'source.mp4'),patch.object(T,'probe',return_value={'fps':25,'duration':50}),patch.object(T,'load',return_value={'itens':[]}),patch.object(C.MT,'edits',return_value=[]),patch.object(V,'covered_mentions',return_value=rows),patch.object(V,'first_product_mention',return_value=0),patch.object(V,'write'):
    return C.schedule(Path(directory),state,seed=1)
 def row(self,name,start,end,kit=None):
  return {'id':name,'start':start,'end':end,'kit':kit,'selected':True}
 def test_adjacent_compatible_windows_share_one_whole_video(self):
  result=self.run_plan([self.row('a',0,1100),self.row('b',1100,2000,3)])
  self.assertFalse(result['issues'])
  self.assertEqual(len(result['segments']),1)
  self.assertEqual(result['segments'][0]['kit'],3)
  self.assertEqual(result['segments'][0]['end_frame'],200)
  self.assertTrue(result['segments'][0]['take_completo'])
 def test_distinct_kits_stay_distinct_without_overlapping(self):
  result=self.run_plan([self.row('a',20000,23000,3),self.row('b',23000,26000,6)])
  self.assertFalse(result['issues'])
  a,b=result['segments']
  self.assertEqual([a['kit'],b['kit']],[3,6])
  self.assertLessEqual(a['end_frame'],b['start_frame'])
  self.assertTrue(all(r['end_frame']-r['start_frame']==200 for r in (a,b)))
 def test_impossible_whole_video_window_stays_pending(self):
  result=self.run_plan([self.row('a',0,1000,3),self.row('b',1000,2000,6)])
  self.assertTrue(result['issues'])

class CoverageOrderTests(unittest.TestCase):
 def test_first_mention_cut_keeps_earlier_visual_first(self):
  rows=[{'id':'fala','start':900,'end':2000},
        {'id':'visual','start':950,'end':1000,'produto_antigo':True}]
  state={'cobrir_falas':True}
  with patch.object(T,'load',return_value={}),patch.object(V,'coverage_policy',return_value={'primeira_mencao_ms':1000}),patch.object(V,'_covered_mentions',return_value=rows):
   result=V.covered_mentions(Path('.'),state)
  self.assertEqual([(r['id'],r['start'],r['end']) for r in result],
                   [('visual',950,1000),('fala',1000,2000)])
  self.assertEqual(state['coverage_markers'][0]['end'],1000)

class ManualIntervalTests(unittest.TestCase):
 def test_requires_explicit_authorization(self):
  with patch('plataforma.workflow.require_takes'):
   with self.assertRaises(ValueError):V.mark_manual(Path('.'),['x'])
 def test_resolves_only_selected_issue_and_invalidates_prepared(self):
  state={'segments':[{'asset':'keep'}],'issues':[{'mention':'x','inicio_ms':1,'fim_ms':2,'error':'duration'},{'mention':'y','inicio_ms':3,'fim_ms':4,'error':'duration'}],'prepared':{'signature':'old'},'coverage_policy':{'nomes':['old']},'audio_windows':[]}
  with patch('plataforma.workflow.require_takes'),patch.object(V,'current_state',return_value=state),patch.object(V,'write'):
   result=V.mark_manual(Path('.'),['x'],True)
  self.assertEqual(result['segments'],[{'asset':'keep'}])
  self.assertEqual([i['mention'] for i in result['issues']],['y'])
  self.assertIsNone(result['prepared'])
  row={'id':'x','start':1,'end':2}
  self.assertTrue(V.manual_authorized(result,row))
  row['end']=3
  self.assertFalse(V.manual_authorized(result,row))
  row['end']=2;result['coverage_policy']['nomes']=['new']
  self.assertFalse(V.manual_authorized(result,row))
 def test_stale_issue_cannot_be_authorized(self):
  with patch('plataforma.workflow.require_takes'),patch.object(V,'current_state',return_value={'issues':[]}):
   with self.assertRaises(ValueError):V.mark_manual(Path('.'),['stale'],True)

class ClosedTimelineTests(unittest.TestCase):
 def test_complete_video_survives_audio_margin_closures(self):
  from plataforma import fechamento as F,montagem as MT
  cuts=[(10,15),(30,33)]
  parts=F.expand(8,40,cuts)
  self.assertEqual(sum(b-a for a,b,_ in parts),32)
  self.assertEqual([(F.position(a,cuts),F.position(b,cuts)) for a,b,_ in parts],[(8,10),(10,25),(25,40)])
  self.assertEqual([src for _,_,src in parts],[0,2,17])
  with patch.object(MT,'edits',return_value=[]),patch.object(T,'source',return_value=Path('source.mp4')),patch.object(F,'windows',return_value=cuts):
   layout=MT.parts(None,Path('.'),[],[{'start_frame':8,'end_frame':40,'file':'take.mp4','timeline_final':True,'timeline_fechada':True}],{'fps':25,'duration':3,'video':True})
  self.assertEqual(sum(v['end']-v['start'] for v in layout['visuals']),32)
  self.assertTrue(all(v['timeline_fechada'] for v in layout['visuals']))
