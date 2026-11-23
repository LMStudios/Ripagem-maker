"""Price-only upload must never invoke product detection or product-phrase slicing."""
import json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import app
import test_trocas_completas as base
from plataforma import otimizacao as OT,trocas as T

class OptimizationPipelineTests(unittest.TestCase):
 setUpClass=classmethod(base.FlowTests.setUpClass.__func__)
 tearDownClass=classmethod(base.FlowTests.tearDownClass.__func__)
 def test_only_price_identification_even_with_product_names_present(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);src=root/'upload.mp4';shutil.copy2(self.source,src)
   data={'words':[{'text':'GlycoWise','start':1000,'end':1500,'speaker':'A'},{'text':'$49.','start':2000,'end':2500,'speaker':'A'}],
         'utterances':[{'text':'GlycoWise $49.','start':1000,'end':2500,'speaker':'A'}],'audio_duration':8,'language_code':'en'}
   selection={'inicio_ms':0,'fim_ms':8000,'duracao_original_s':8,'segunda_metade':False}
   states=[]
   with patch.object(app.RECORTE,'prepare',return_value=(src,selection)),patch.object(app.RECORTE,'restore_times',return_value=data),patch.object(app,'transcribe',return_value=data),patch.object(app,'set_state',side_effect=lambda jid,**kw:states.append(kw)),patch.object(app.STORAGE,'current',return_value=root),patch.object(app,'detect_product',side_effect=AssertionError('Product identification is forbidden')),patch.object(app,'write_phrases',side_effect=AssertionError('Product cutting is forbidden')):
    app.run_job('test',src,'GlycoWise.mp4','en','',0,10,prod={'product':'GlycoWise','novo':'GlycoWise','otimizacao':True},second_half=False)
   self.assertEqual(states[-1]['status'],'done',states[-1])
   out=root/states[-1]['folder'];self.assertTrue(OT.active(out))
   self.assertEqual(states[-1]['frases'],[])
   self.assertEqual(T.build(out,'GlycoWise')['itens'],[])
   app.write_prices(out,data,{'49':'29'},{},False)
   plan=T.build(out,'GlycoWise');self.assertEqual(len(plan['itens']),1)
   self.assertEqual(plan['itens'][0]['novo'],'GlycoWise $29.')
 def test_requested_136_target_matrix(self):
  for old,new,mapping in [
   ('2 bottles at $79 each, $158 total.','1 bottle at $59 each, $59 total.',{'79':'59','158':'59'}),
   ('3 bottles at $59 each, $177 total.','3 bottles at $39 each, $117 total.',{'59':'39','177':'117'}),
   ('6 bottles at $49 each, $294 total.','6 bottles at $29 each, $174 total.',{'49':'29','294':'174'})]:
   with self.subTest(old=old):self.assertEqual(app.swap_prices(old,mapping,{'2|frascos':'1'})[0],new)

 def test_unrelated_type_two_is_not_a_price_or_kit_change(self):
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp);OT.prepare(out,'GlycoWise')
   words=[]
   for index,text in enumerate(['Type','2','diabetes.','Buy','two','bottles.']):
    words.append({'text':text,'start':index*300,'end':index*300+250,'speaker':'A'})
   rows,_,_=app.write_prices(out,{'words':words},{},{'2|frascos':'1'},False)
   self.assertEqual(len(rows),1);self.assertEqual(rows[0]['novo'],'Buy one bottle.')
