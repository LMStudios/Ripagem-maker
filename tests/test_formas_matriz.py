import unittest
from formas_matrix_cases import cases,NOUNS
from plataforma import formas as F
class AllFormsMatrixTests(unittest.TestCase):
 def test_all_thirty_directions_and_editorial_cases(self):
  rows=cases();self.assertEqual(len({(r['source'],r['target']) for r in rows}),30)
  for row in rows:
   with self.subTest(source=row['source'],target=row['target'],lang=row['lang'],kind=row['kind'],text=row['text']):
    text,notes=F.adapt(row['text'],F.normalize(row['config']));self.assertEqual(text,row['expected']);self.assertEqual(F.pending(notes),row['pending'])

class ContextualPronounTests(unittest.TestCase):
 def test_all_directions_with_adjacent_usage_without_product_name(self):
  from itertools import permutations
  references={'en':'Our formula contains {form}.','pt':'Nossas fórmulas contêm {form}.','es':'Nuestras fórmulas contienen {form}.'}
  commands={
   'patch':('Apply it to your skin.','Aplique na pele.','Aplícalo en la piel.'),
   'dropper':('Shake it well.','Agite antes de usar.','Agítalo antes de usar.'),
   'capsule':('Swallow it with water.','Engula com água.','Trágala con agua.'),
   'powder':('Mix it with water.','Misture com água.','Disuélvelo en agua.'),
   'gummy':('Chew it slowly.','Mastigue lentamente.','Mastícala lentamente.'),
   'liquid':('Drink it slowly.','Beba aos poucos.','Bébelo lentamente.')}
  for source,target in permutations(NOUNS,2):
   for i,lang in enumerate(('en','pt','es')):
    with self.subTest(source=source,target=target,lang=lang):
     reference=references[lang].format(form=NOUNS[source][lang][0]);command=commands[source][i];words=[]
     for offset,text in ((1000,reference),(3000,command)):
      words.extend({'text':word,'start':offset+n*100,'end':offset+n*100+90,'speaker':'A'} for n,word in enumerate(text.split()))
     config=F.normalize({'ativo':True,'origem':source,'destino':target,'uso_novo':'Confirmed target instructions.'});result=F.augment([],{'words':words},config,[],'Newbrand');row=next((r for r in result if r['start']==3000),None)
     self.assertIsNotNone(row);self.assertEqual(row['novo'],'Confirmed target instructions.');self.assertFalse(row['forma_pendente']);self.assertEqual(row['speaker'],'A');self.assertEqual(row['end'],words[-1]['end'])

import json
import test_trocas_completas as B
from plataforma import trocas as T,gemini_formas as G
from unittest.mock import patch
from types import SimpleNamespace
class SavedPlansMatrixTests(unittest.TestCase):
 setUpClass=classmethod(B.FlowTests.setUpClass.__func__)
 tearDownClass=classmethod(B.FlowTests.tearDownClass.__func__)
 setUp=B.FlowTests.setUp
 tearDown=B.FlowTests.tearDown
 def test_all_directions_saved_plan_preserves_speaker_and_timestamps(self):
  from itertools import permutations
  for source,target in permutations(NOUNS,2):
   with self.subTest(source=source,target=target):
    original='Oldbrand formula contains '+NOUNS[source]['en'][0]+'.';new=original.replace('Oldbrand','Newbrand');meta={'produto':'Oldbrand','produto_novo':'Newbrand','frases':[{'n':1,'start':1000,'end':3000,'text':original,'novo':new,'speaker':'A'}]};(self.out/'frases_TEST.json').write_text(json.dumps(meta))
    raw={'words':[{'text':w,'start':1000+i*100,'end':1090+i*100,'speaker':'A'} for i,w in enumerate(original.split())]};(self.out/'transcricao_bruta.json').write_text(json.dumps(raw));result=T.build(self.out,'Oldbrand',form_config={'ativo':True,'origem':source,'destino':target});self.assertEqual(len(result['itens']),1);r=result['itens'][0]
    self.assertEqual(r['novo'],'Newbrand formula contains '+NOUNS[target]['en'][0]+'.');self.assertEqual((r['inicio_ms'],r['fim_ms'],r['speaker']),(1000,3000,'A'));self.assertFalse(r['aprovado']);self.assertFalse(r['forma_pendente']);self.assertNotIn('audio',r)

class GeminiValidationMatrixTests(unittest.TestCase):
 def test_every_direction_rejects_old_form_and_accepts_clean_suggestion(self):
  from itertools import permutations
  for source,target in permutations(NOUNS,2):
   for residual in (False,True):
    with self.subTest(source=source,target=target,residual=residual):
     word=NOUNS[source if residual else target]['en'][0];data={'itens':[{'id':'row1','texto':'The formula contains '+word+'.','pendente':False,'motivo':'Frase adaptada para teste.'}]};response=SimpleNamespace(ok=True,status_code=200,json=lambda:{'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(data)}]}}]})
     c=F.normalize({'ativo':True,'origem':source,'destino':target})
     with patch.object(G.requests,'post',return_value=response):result=G.request([{'id':'row1','original':'Test sentence.'}],'Newbrand',c,'TEST_ONLY')
     self.assertEqual(result[0]['pendente'],residual);self.assertEqual(bool(result[0]['texto']),not residual)
