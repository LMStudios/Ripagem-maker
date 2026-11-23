import json
import unittest
import test_trocas_completas as base
from plataforma import formas as F,trocas as T

class FormRuleTests(unittest.TestCase):
 def config(self,source='patch',target='dropper',**kw):return F.normalize({'ativo':True,'origem':source,'destino':target,**kw})
 def test_patch_usage_and_plural(self):
  text,notes=F.adapt('Apply the patch to your skin daily.',self.config(uso_novo='Follow the confirmed instructions for the drops.'))
  self.assertEqual(text,'Follow the confirmed instructions for the drops.');self.assertFalse(F.pending(notes));self.assertNotIn('skin',text);self.assertNotIn('daily',text)
  self.assertEqual(F.adapt('These patches work.',self.config(target='capsule'))[0],'These capsules work.')
 def test_forms_and_word_boundaries(self):
  for source in F.FORMS:
   for target in F.FORMS:
    if source==target:continue
    text=F.FORMS[source]['en'][0];result,_=F.adapt(text,self.config(source,target));self.assertEqual(result,F.FORMS[target]['en'][0])
  self.assertFalse(F.match('Dispatch the package.',self.config()))
 def test_portuguese_and_explicit_usage(self):
  text,_=F.adapt('Aplique um adesivo na sua pele.',self.config(target='capsule',uso_novo='Siga a orientação confirmada para as cápsulas.'))
  self.assertEqual(text,'Siga a orientação confirmada para as cápsulas.')
  c=self.config(uso_original='apply one patch daily',uso_novo='follow the confirmed dropper instructions')
  self.assertEqual(F.adapt('Please apply one patch daily.',c)[0],'Please follow the confirmed dropper instructions.')
 def test_no_dose_calculated_and_mechanism_flagged(self):
  text,notes=F.adapt('The transdermal patch works for 24 hours.',self.config(target='powder'))
  self.assertIn('24 hours',text);self.assertIn('transdermal',text);self.assertTrue(F.pending(notes));self.assertEqual(text,'The transdermal patch works for 24 hours.')
 def test_once_and_for_all_is_not_a_dose(self):
  original='If I could adapt all the extracts in my formula into a patch, I could put an end to this once and for all.'
  expected=original.replace('a patch','a dropper')
  text,notes=F.adapt(original,self.config());self.assertEqual(text,expected);self.assertFalse(F.pending(notes))
  for target in ('capsule','powder','gummy','liquid'):
   with self.subTest(target=target):
    text,notes=F.adapt(original,self.config(target=target));self.assertNotIn('patch',text);self.assertFalse(F.pending(notes))
 def test_actual_once_per_day_still_requires_usage(self):
  original='Use the patch once per day.';text,notes=F.adapt(original,self.config());self.assertEqual(text,original);self.assertTrue(F.pending(notes))
 def test_config_validation(self):
  for c in ({'ativo':True,'origem':'patch','destino':'patch'},{'ativo':True,'origem':'unknown','destino':'powder'},{'ativo':True,'origem':'patch','destino':'powder','uso_original':'test'}):
   with self.assertRaises(ValueError):F.normalize(c)

class FormPlanTests(unittest.TestCase):
 setUpClass=classmethod(base.FlowTests.setUpClass.__func__)
 tearDownClass=classmethod(base.FlowTests.tearDownClass.__func__)
 setUp=base.FlowTests.setUp
 tearDown=base.FlowTests.tearDown
 job=base.FlowTests.job
 approve=base.FlowTests.approve
 add_audio=base.FlowTests.add_audio
 def setup_words(self):
  raw={'words':[{'text':word,'start':3500+i*100,'end':3580+i*100,'speaker':'B'} for i,word in enumerate('Apply the patch daily.'.split())]}
  (self.out/'transcricao_bruta.json').write_text(json.dumps(raw))
 def test_adds_mentions_without_product_and_persists_configuration(self):
  self.add_audio();original=T.load(self.out);self.setup_words()
  c={'ativo':True,'origem':'patch','destino':'dropper','uso_novo':'Follow the confirmed instructions for the drops.'};plan=T.build(self.out,'Oldbrand',form_config=c)
  added=[r for r in plan['itens'] if r.get('forma_detectada')]
  self.assertEqual(len(added),1);self.assertEqual(added[0]['novo'],'Follow the confirmed instructions for the drops.');self.assertFalse(added[0]['aprovado']);self.assertEqual(added[0]['speaker'],'B')
  self.assertEqual(plan['itens'][0]['audio'],original['itens'][0]['audio'])
  self.assertEqual(T.build(self.out,'Oldbrand')['forma']['destino'],'dropper')
  disabled=T.build(self.out,'Oldbrand',form_config={'ativo':False});self.assertEqual(len(disabled['itens']),2)
 def test_changed_text_invalidates_audio_and_does_not_duplicate_sentence(self):
  file=self.out/'frases_TEST.json';meta=json.loads(file.read_text());meta['frases'][0].update(text='Oldbrand patch works.',novo='Newbrand patch works.');file.write_text(json.dumps(meta))
  self.plan=T.build(self.out,'Oldbrand');self.add_audio()
  raw={'words':[{'text':w,'start':1000+i*300,'end':1400+i*300,'speaker':'A'} for i,w in enumerate('Oldbrand patch works.'.split())]};(self.out/'transcricao_bruta.json').write_text(json.dumps(raw))
  p=T.build(self.out,'Oldbrand',form_config={'ativo':True,'origem':'patch','destino':'capsule'})
  self.assertEqual(len(p['itens']),2);self.assertEqual(p['itens'][0]['novo'],'Newbrand capsule works.');self.assertNotIn('audio',p['itens'][0]);self.assertFalse(p['itens'][0]['aprovado'])
 def test_formulation_reference_updates_plan_without_usage_details(self):
  original='If I could adapt all the extracts in my formula into a patch, I could put an end to this once and for all.'
  words=[{'text':w,'start':3500+i*40,'end':3535+i*40,'speaker':'B'} for i,w in enumerate(original.split())];(self.out/'transcricao_bruta.json').write_text(json.dumps({'words':words}))
  p=T.build(self.out,'Oldbrand',form_config={'ativo':True,'origem':'patch','destino':'dropper'});row=next(r for r in p['itens'] if r.get('origem')=='forma');self.assertEqual(row['novo'],original.replace('a patch','a dropper'));self.assertFalse(row['forma_pendente']);self.assertFalse(row['aprovado'])
 def test_invalid_configuration_does_not_modify_saved_plan(self):
  before=T.plan_path(self.out).read_bytes()
  with self.assertRaises(ValueError):T.build(self.out,'Oldbrand',form_config={'ativo':True,'origem':'bad','destino':'powder'})
  self.assertEqual(before,T.plan_path(self.out).read_bytes())

class FullAdaptationTests(unittest.TestCase):
 def config(self,source='patch',target='dropper',**kw):return F.normalize(dict(ativo=True,origem=source,destino=target,**kw))
 def test_old_route_dose_frequency_and_duration_are_not_carried_over(self):
  c=self.config(uso_novo='Use the drops according to the confirmed label instructions.')
  for original in ['Wear two patches on your skin for 24 hours.','Peel it off and replace it twice daily.','Apply one patch to your wrist every day.']:
   text,notes=F.adapt(original,c);self.assertEqual(text,c['uso_novo']);self.assertFalse(F.pending(notes))
 def test_complete_mechanism_requires_confirmed_description(self):
  original='The transdermal patch bypasses your stomach and releases compounds into your bloodstream.'
  text,notes=F.adapt(original,self.config(uso_novo='Use the drops as directed.'))
  self.assertEqual(text,original);self.assertTrue(F.pending(notes))
  c=self.config(descricao_nova='The product comes as a liquid formula.')
  text,notes=F.adapt(original,c);self.assertEqual(text,c['descricao_nova']);self.assertFalse(F.pending(notes));self.assertNotIn('transdermal',text)
 def test_reverse_forms_replace_the_entire_instruction(self):
  for source,original in [('capsule','Swallow two capsules daily.'),('powder','Mix one scoop of powder with water.'),('dropper','Put the drops under your tongue.'),('gummy','Chew two gummies every day.')]:
   c=self.config(source,'patch',uso_novo='Follow the confirmed patch instructions.');text,notes=F.adapt(original,c);self.assertEqual(text,c['uso_novo']);self.assertFalse(F.pending(notes))
 def test_unrelated_sentence_is_preserved(self):
  c=self.config(uso_novo='Use the drops as directed.');text,_=F.adapt('The product is available now. Apply the patch to your skin daily.',c)
  self.assertEqual(text,'The product is available now. Use the drops as directed.')
 def test_target_contradictions_do_not_survive(self):
  original='There are no pills to swallow.';c=self.config(target='capsule')
  text,notes=F.adapt(original,c);self.assertEqual(text,original);self.assertTrue(F.pending(notes))
  text,notes=F.adapt(original,self.config(target='capsule',descricao_nova='The product comes in capsules.'));self.assertEqual(text,'The product comes in capsules.');self.assertFalse(F.pending(notes))
 def test_no_unconfirmed_generic_rewrite(self):
  for text in ('Transdermal absorption.','Wear it for 24 hours.','Apply the patch to your skin.'):
   new,notes=F.adapt(text,self.config());self.assertEqual(new,text);self.assertTrue(F.pending(notes))

class PendingPlanTests(unittest.TestCase):
 job=base.FlowTests.job
 approve=base.FlowTests.approve
 add_audio=base.FlowTests.add_audio
 setUpClass=classmethod(base.FlowTests.setUpClass.__func__)
 tearDownClass=classmethod(base.FlowTests.tearDownClass.__func__)
 setUp=base.FlowTests.setUp
 tearDown=base.FlowTests.tearDown
 def test_pending_semantics_block_generation_until_explicit_confirmation(self):
  meta=json.loads((self.out/'frases_TEST.json').read_text());meta['frases'][0].update(text='Oldbrand patch uses transdermal absorption.',novo='Newbrand patch uses transdermal absorption.');(self.out/'frases_TEST.json').write_text(json.dumps(meta))
  p=T.build(self.out,'Oldbrand',form_config={'ativo':True,'origem':'patch','destino':'dropper'});rid=p['itens'][0]['id'];self.assertTrue(p['itens'][0]['forma_pendente'])
  p=T.save(self.out,[{'id':rid,'aprovado':True}])
  with self.assertRaisesRegex(ValueError,'modo de uso'):T.approved(p)
  p=T.save(self.out,[{'id':rid,'novo':'Newbrand comes as drops.','forma_confirmada':True}]);self.assertEqual(len(T.approved(p)),1)
  self.assertTrue(T.build(self.out,'Oldbrand')['itens'][0]['forma_confirmada'])
  p=T.save(self.out,[{'id':rid,'novo':'Edited Newbrand text.'}]);self.assertFalse(p['itens'][0]['forma_confirmada'])
 def test_adjacent_pronoun_instruction_is_identified_without_brand(self):
  words=[{'text':t,'start':1000+i*150,'end':1140+i*150,'speaker':'A'} for i,t in enumerate('This patch is easy to use. Peel it off daily.'.split())]
  c=F.normalize({'ativo':True,'origem':'patch','destino':'dropper','uso_novo':'Use the drops as directed.'})
  rows=F.augment([],{'words':words},c,[],None);self.assertEqual(len(rows),2);self.assertEqual(rows[1]['novo'],'Use the drops as directed.')
 def test_bulk_confirmation_preserves_audio_selection_and_unrelated_rows(self):
  import copy
  base.FlowTests.add_audio(self)
  p=T.load(self.out);third=copy.deepcopy(p['itens'][1]);third['id']='unrelated';p['itens'].append(third)
  for r in p['itens'][:2]:r.update(forma_detectada=True,forma_pendente=False,forma_confirmada=False)
  p['itens'][1]['aprovado']=False;p['previa']={'arquivo':'existing.mp4'};p['revisao']={'status':'existing'};T.write(T.plan_path(self.out),p);original=copy.deepcopy(p)
  approved=T.save(self.out,[{'id':r['id'],'forma_confirmada':True,'forma_texto_esperado':r['novo']} for r in p['itens'] if r.get('forma_detectada')])
  self.assertTrue(all(r['forma_confirmada'] for r in approved['itens'][:2]));self.assertEqual(approved['itens'][2],original['itens'][2]);self.assertFalse(approved['itens'][1]['aprovado']);self.assertEqual([r['audio'] for r in approved['itens']],[r['audio'] for r in original['itens']]);self.assertEqual(approved['previa'],original['previa']);self.assertEqual(approved['revisao'],original['revisao'])
  T.save(self.out,[{'id':p['itens'][0]['id'],'novo':'Changed instruction.'}]);self.assertFalse(T.load(self.out)['itens'][0]['forma_confirmada'])
 def test_bulk_confirmation_is_atomic_if_a_text_changes(self):
  p=T.load(self.out)
  for r in p['itens']:r.update(forma_detectada=True,forma_pendente=False)
  T.write(T.plan_path(self.out),p);before=T.plan_path(self.out).read_bytes();changes=[{'id':r['id'],'forma_confirmada':True,'forma_texto_esperado':r['novo']} for r in p['itens']];changes[1]['forma_texto_esperado']='Stale text'
  with self.assertRaisesRegex(ValueError,'mudou'):T.save(self.out,changes)
  self.assertEqual(T.plan_path(self.out).read_bytes(),before)

 def test_pending_form_cannot_be_confirmed_with_the_original_instruction(self):
  plan=T.load(self.out);row=plan['itens'][0]
  row.update(forma_detectada=True,forma_pendente=True,novo='Just 2 drops per day.',base_novo='Just 2 drops per day.')
  T.write(T.plan_path(self.out),plan)
  before=T.plan_path(self.out).read_bytes()
  with self.assertRaisesRegex(ValueError,'modo de uso original'):
   T.save(self.out,[{'id':row['id'],'forma_confirmada':True,'novo':' Just 2 drops per day. '}])
  self.assertEqual(T.plan_path(self.out).read_bytes(),before)
  updated=T.save(self.out,[{'id':row['id'],'forma_confirmada':True,'novo':'It comes in capsule form.'}])
  self.assertTrue(updated['itens'][0]['forma_confirmada'])
