"""Otimização não depende do nome do produto nem amplia a cobertura para a VSL inteira."""
import json,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
import test_trocas_completas as base
from plataforma import trocas as T,visuais as V,ml_core as M,automatico as A

class OptimizationTakesTests(unittest.TestCase):
 setUpClass=classmethod(base.FlowTests.setUpClass.__func__)
 tearDownClass=classmethod(base.FlowTests.tearDownClass.__func__)
 tearDown=base.FlowTests.tearDown
 job=base.FlowTests.job
 approve=base.FlowTests.approve
 add_audio=base.FlowTests.add_audio
 def setUp(self):
  base.FlowTests.setUp(self)
  self.guard=patch('plataforma.armazenamento.visual_margin_ms',return_value=0);self.guard.start();self.addCleanup(self.guard.stop)
  p=T.load(self.out);p.update(somente_valores=True,produto='Otimização de preços',produto_novo='Otimização de preços')
  for row,old,new in zip(p['itens'],['Two bottles cost $49.','Three bottles cost $39.'],['One bottle costs $59.','Three bottles cost $49.']):row.update(original=old,novo=new,base_novo=new,origem='preco_kit')
  T.write(T.plan_path(self.out),p)
  raw={'words':[{'text':text,'start':start+i*350,'end':start+i*350+300,'speaker':speaker} for start,speaker,words in [(1000,'A','Two bottles cost $49.'),(5000,'B','Three bottles cost $39.')] for i,text in enumerate(words.split())]}
  T.write(self.out/'transcricao_bruta.json',raw);T.write(self.out/'precos_TROCA.json',{'mapa_qtd':{'2|frascos':'1'},'frases':[]});self.add_audio()
  self.assets=self.out/'materiais';self.assets.mkdir()
  for kit,color in [(1,'red'),(1,'blue'),(3,'yellow'),(3,'green')]:
   subprocess.run([M.FFMPEG,'-y','-v','error','-f','lavfi','-i',f'color={color}:s=90x160:r=25:d=1','-an','-c:v','libx264',str(self.assets/f'{kit}_potes_{color}.mp4')],check=True)
 def test_prices_export_xml_with_complete_takes_without_product_name(self):
  self.assertIsNone(V.first_product_mention(self.out))
  state=V.load(self.out);state.update(modo_takes='inteiro',ajustar_janela=True);V.write(self.out,state)
  with patch.object(V,'first_product_mention',side_effect=AssertionError('Otimização não procura produto')),patch('plataforma.deteccao_visual.coverage_rows',side_effect=AssertionError('Não cobrir produto antigo')):
   V.automatic(self.job(),self.out,str(self.assets));segments=V.valid_prepared(self.out);result=T.fast_delivery_job(self.job(),self.out,True)
  xml=ET.parse(self.out/result['xml']);tracks=xml.findall('.//sequence/media/video/track');self.assertEqual(len(tracks),2);self.assertGreater(len(tracks[1].findall('clipitem')),0);self.assertEqual(result['trechos'],2);self.assertGreater(len(segments),0)
  state=V.load(self.out);self.assertFalse(state.get('coverage_markers'));self.assertEqual(state['coverage_policy']['escopo'],'somente_valores');self.assertEqual({r['kit'] for r in state['mentions']},{1,3})
 def test_prices_without_takes_preserves_v1_and_exports_xml(self):
  V.save(self.out,{'sem_takes':True})
  with patch.object(V,'automatic',side_effect=AssertionError('Não preparar takes dispensados')),patch.object(V,'first_product_mention',side_effect=AssertionError('Nome não obrigatório')):result=T.fast_delivery_job(self.job(),self.out,True)
  xml=ET.parse(self.out/result['xml']);self.assertEqual(len(xml.findall('.//sequence/media/video/track')),1);self.assertEqual(result['visuais'],0)
 def test_old_visual_plan_and_outside_quantity_do_not_expand_scope(self):
  raw=json.loads((self.out/'transcricao_bruta.json').read_text());raw['words']=[{'text':'Six','start':100,'end':200,'speaker':'C'},{'text':'bottles.','start':220,'end':400,'speaker':'C'}]+raw['words'];T.write(self.out/'transcricao_bruta.json',raw)
  s=V.load(self.out);s.update(modo_takes='inteiro',ajustar_janela=True,mentions=[{'id':'old','selected':True,'start':0,'end':8000,'kit':6,'text':'VSL inteira'}],basis='old-product-basis',coverage_markers=[{'id':'bad'}]);V.write(self.out,s)
  V.automatic(self.job(),self.out,str(self.assets));s=V.load(self.out)
  self.assertNotIn(6,{r['kit'] for r in s['mentions']});self.assertTrue(all(any(a<=r['start']<r['end']<=b for _,a,b in V.audio_windows(self.out)) for r in s['mentions']));self.assertFalse(s['coverage_markers'])
 def test_selection_invalidates_price_basis_and_scope_ids_are_stable(self):
  b=V.basis(self.out);rows=[{'id':'q','start':0,'end':8000,'kit':1,'selected':True}];once=V.price_scope_rows(self.out,rows);self.assertEqual(once,V.price_scope_rows(self.out,once))
  T.save(self.out,[{'id':T.load(self.out)['itens'][1]['id'],'aprovado':False}]);self.assertNotEqual(V.basis(self.out),b);self.assertFalse(V.basis_ok(self.out,b))
 def test_price_scope_reuses_one_snapshot_and_keeps_nested_overlaps(self):
  plan=T.load(self.out)
  plan['itens']=[
   {'id':'short','inicio_ms':200,'fim_ms':400,'aprovado':True},
   {'id':'long','inicio_ms':100,'fim_ms':700,'aprovado':True},
   {'id':'ignored','inicio_ms':250,'fim_ms':600,'aprovado':False},
   {'id':'later','inicio_ms':700,'fim_ms':900,'aprovado':True},
  ]
  rows=[{'id':'a','start':350,'end':420}, {'id':'b','start':600,'end':700}]
  with patch.object(T,'load',return_value=plan) as load:
   result=V.price_scope_rows(self.out,rows)
  self.assertEqual([(r['preco_base_id'],r['preco_fala'],r['start'],r['end']) for r in result],
                   [('a','long',350,420),('a','short',350,400),('b','long',600,700)])
  load.assert_called_once_with(self.out)
 def test_automatic_offer_helper_does_not_require_first_product(self):
  rows=[dict(r,ofertas_incluidas=[kit]) for r,kit in zip(T.load(self.out)['itens'],[1,3])]
  with patch.object(V,'first_product_mention',side_effect=AssertionError('Não exigir produto')):A.prepare_offer_mentions(self.out,rows)
  self.assertEqual(len(V.load(self.out)['mentions']),2)
