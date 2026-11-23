import json,unittest
from itertools import product
from types import SimpleNamespace
from unittest.mock import patch
from plataforma import formas as F,gemini_formas as G
class RouteAdaptationTests(unittest.TestCase):
 def test_route_questions_keep_question_tense_and_avoid_skin(self):
  endings={'oral':'orally','ingerir':'by mouth','sublingual':'under the tongue'}
  for target,route,prefix,verb in product(('dropper','capsule','powder','gummy','liquid'),endings,('So what if','What if'),('applied','apply')):
   with self.subTest(target=target,route=route,prefix=prefix,verb=verb):
    c=F.normalize(dict(ativo=True,origem='patch',destino=target,via_uso=route));original=f'{prefix} I {verb} my formula through the skin?';text,notes=F.adapt(original,c)
    self.assertEqual(text,f'{prefix} I {"used" if verb=="applied" else "use"} my formula {endings[route]}?');self.assertFalse(F.pending(notes));self.assertNotIn('absorption',text)
 def test_no_route_does_not_guess_or_invent_absorption(self):
  original='So what if I applied my formula through the skin?';text,notes=F.adapt(original,F.normalize(dict(ativo=True,origem='patch',destino='dropper')));self.assertEqual(text,original);self.assertTrue(F.pending(notes))
 def test_standalone_mechanism_becomes_administration_not_equivalent_absorption(self):
  for route,expected in [('oral','Oral administration.'),('ingerir','Oral administration.'),('sublingual','Sublingual administration.')]:
   text,notes=F.adapt('Transdermal absorption.',F.normalize(dict(ativo=True,origem='patch',destino='dropper',via_uso=route)));self.assertEqual(text,expected);self.assertFalse(F.pending(notes))
 def test_portuguese_and_spanish_questions_are_not_generic_instruction(self):
  c=F.normalize(dict(ativo=True,origem='patch',destino='dropper',via_uso='sublingual'))
  for original,expected in [('E se eu aplicasse minha fórmula pela pele?','E se eu usasse minha fórmula sob a língua?'),('¿Y si yo aplicara mi fórmula a través de la piel?','¿Y si yo usara mi fórmula debajo de la lengua?')]:
   self.assertTrue(F.match(original,c));self.assertEqual(F.adapt(original,c)[0],expected)
 def test_route_detected_without_product_name_in_transcript(self):
  c=F.normalize(dict(ativo=True,origem='patch',destino='dropper',via_uso='oral'));text='So what if I applied my formula through the skin?';words=[dict(text=w,start=1000+i*100,end=1090+i*100,speaker='B') for i,w in enumerate(text.split())];rows=F.augment([],{'words':words},c,[],'SizeFix');self.assertEqual(len(rows),1);self.assertEqual(rows[0]['novo'],'So what if I used my formula orally?');self.assertEqual(rows[0]['speaker'],'B')
 def test_route_does_not_transfer_dose_release_or_scientific_claim(self):
  c=F.normalize(dict(ativo=True,origem='patch',destino='dropper',via_uso='oral'))
  for original in ('Wear two patches for 24 hours.','The exact same technology used in nicotine or hormone patches.','Each layer of the patch dissolves at different times, releasing compounds throughout the day.','The patch bypasses your stomach and enters your bloodstream.'):
   with self.subTest(original=original):
    text,notes=F.adapt(original,c);self.assertEqual(text,original);self.assertTrue(F.pending(notes))
 def test_routes_are_validated_and_preserved(self):
  for target,route in [('patch','oral'),('dropper','cutanea'),('capsule','unknown')]:
   with self.assertRaises(ValueError):F.normalize(dict(ativo=True,origem='gummy',destino=target,via_uso=route))
 def test_gemini_rejects_skin_residue_even_without_old_noun(self):
  for answer in ('So what if I applied my formula through the skin?','It works on your skin.','Transdermal absorption.'):
   data={'itens':[dict(id='r',texto=answer,pendente=False,motivo='test')]};response=SimpleNamespace(ok=True,status_code=200,json=lambda:{'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(data)}]}}]})
   with patch.object(G.requests,'post',return_value=response) as api:
    result=G.request([dict(id='r',original=answer)],'SizeFix',F.normalize(dict(ativo=True,origem='patch',destino='dropper',via_uso='oral')),'TEST_ONLY');self.assertTrue(result[0]['pendente']);self.assertEqual(result[0]['texto'],'');self.assertEqual(json.loads(api.call_args.kwargs['json']['contents'][0]['parts'][0]['text'])['forma']['via_uso'],'oral')

 def test_gemini_rejects_old_release_claim_even_with_new_form_noun(self):
  for answer in ('The dropper releases compounds throughout the day.','The drops use a multi-layer release system.','Sublingual absorption delivers the formula faster.'):
   data={'itens':[dict(id='r',texto=answer,pendente=False,motivo='test')]};response=SimpleNamespace(ok=True,status_code=200,json=lambda:{'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(data)}]}}]})
   with patch.object(G.requests,'post',return_value=response):
    result=G.request([dict(id='r',original='The patch uses timed release.')],'SizeFix',F.normalize(dict(ativo=True,origem='patch',destino='dropper',via_uso='oral')),'TEST_ONLY');self.assertTrue(result[0]['pendente']);self.assertEqual(result[0]['texto'],'')
