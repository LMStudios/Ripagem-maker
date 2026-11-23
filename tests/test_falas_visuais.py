import copy,json,unittest
from unittest.mock import patch
from plataforma import falas_visuais as FV,trocas as T,deteccao_visual as D,validacao as L
import test_trocas_completas as B
class RecoveryTests(unittest.TestCase):
 setUpClass=classmethod(B.FlowTests.setUpClass.__func__)
 tearDownClass=classmethod(B.FlowTests.tearDownClass.__func__)
 setUp=B.FlowTests.setUp
 tearDown=B.FlowTests.tearDown
 job=B.FlowTests.job
 def setup_missing(self,text='Try Oldbrand today.',start=3400):
  words=[{'text':t,'start':start+i*180,'end':start+i*180+160,'speaker':'A'} for i,t in enumerate(text.split())]
  (self.out/'transcricao_bruta.json').write_text(json.dumps({'words':words}))
  D.write(self.out,{'nome':'Oldbrand','intervalos':[{'id':'vis1','inicio_ms':start,'fim_ms':start+600,'inicio_detectado_ms':start,'fim_detectado_ms':start+600,'status':'sugerido','legenda_ms':[start]}]})
  return FV.view(self.out)
 def apply(self,state,**kw):
  return FV.review(self.out,dict(id=state['itens'][0]['id'],base=state['base'],acao='adicionar',confirmou_audio=True,**kw))
 def test_full_phrase_add_and_preserve_other_audio_approvals(self):
  p=T.load(self.out);p['itens'][0].update(aprovado=True,audio={'fit':'kept.wav','aprovado':True});T.write(T.plan_path(self.out),p);prior=copy.deepcopy(p['itens'])
  s=self.setup_missing();self.assertEqual(len(s['itens']),1);r=s['itens'][0];self.assertEqual(r['original'],'Try Oldbrand today.');self.assertEqual(r['novo'],'Try Newbrand today.')
  result=self.apply(s);fresh=next(r for r in result['plano']['itens'] if r['origem']=='conferencia_visual');self.assertFalse(fresh['aprovado']);self.assertNotIn('audio',fresh);self.assertEqual(fresh['speaker'],'A');self.assertEqual(fresh['inicio_ms'],3400)
  self.assertEqual([r for r in result['plano']['itens'] if r['origem']!='conferencia_visual'],prior)
  with self.assertRaises(ValueError):self.apply(s)
  rebuilt=T.build(self.out,'Oldbrand');self.assertEqual(len(rebuilt['itens']),3);self.assertEqual(rebuilt['itens'][0]['audio'],prior[0]['audio'])
 def test_visual_text_is_not_a_voice_script_and_needs_confirmation(self):
  s=self.setup_missing('This formula works.');self.assertEqual(s['itens'][0]['situacao'],'conferir_audio');self.assertNotIn('Oldbrand',s['itens'][0]['original'])
  body={'id':s['itens'][0]['id'],'base':s['base'],'acao':'adicionar'}
  with self.assertRaises(ValueError):FV.review(self.out,body)
  FV.review(self.out,body|{'acao':'somente_visual'});self.assertEqual(FV.view(self.out)['itens'][0]['status'],'somente_visual');self.assertEqual(len(T.load(self.out)['itens']),2)
 def test_partial_existing_phrase_is_expanded_not_duplicated(self):
  s=self.setup_missing('Try Oldbrand today.',start=2800);self.assertEqual(s['itens'][0]['substitui_id'],self.plan['itens'][0]['id'])
  p=T.load(self.out);p['itens'][0]['audio']={'fit':'old.wav','aprovado':True};T.write(T.plan_path(self.out),p)
  result=self.apply(s);self.assertEqual(len(result['plano']['itens']),2);new=result['plano']['itens'][0];self.assertEqual(new['inicio_ms'],1000);self.assertEqual(new['fim_ms'],3320);self.assertNotIn('audio',new);self.assertEqual(new['historico_audio'][0]['fit'],'old.wav')
  rebuilt=T.build(self.out,'Oldbrand');self.assertEqual(len(rebuilt['itens']),2)
 def test_price_only_scope_stays_exclusive(self):
  self.setup_missing();p=T.load(self.out);p['somente_valores']=True;T.write(T.plan_path(self.out),p);self.assertEqual(FV.view(self.out)['itens'],[])
 def test_stale_product_change_rejects_apply(self):
  s=self.setup_missing();p=T.load(self.out);p['produto_novo']='Changed';T.write(T.plan_path(self.out),p)
  with self.assertRaisesRegex(ValueError,'mudou'):self.apply(s)
 def test_deduplicates_visual_intervals_and_keeps_speaker_boundary(self):
  self.setup_missing();d=D.load(self.out);d['intervalos'].append(dict(d['intervalos'][0],id='vis2'));D.write(self.out,d);s=FV.view(self.out);self.assertEqual(len(s['itens']),1)
 def test_audio_recheck_uses_original_time_offsets(self):
  s=self.setup_missing('This formula works.');row=s['itens'][0]
  with patch.object(FV.M,'run_proc'),patch.object(L,'transcribe',return_value={'words':[{'w':'Oldbrand.','s':2.0,'e':2.3}]}):FV.recheck(self.job(),str(self.out),row['id'],s['base'])
  recovered=[r for r in FV.view(self.out)['itens'] if r['origem_evidencia']=='audio_local'];self.assertEqual(len(recovered),1);self.assertEqual(recovered[0]['inicio_ms'],3400);self.assertEqual(recovered[0]['novo'],'Newbrand.')
  p=T.load(self.out);p['produto_novo']='Briomary Growth';T.write(T.plan_path(self.out),p)
  recovered=[r for r in FV.view(self.out)['itens'] if r['origem_evidencia']=='audio_local'];self.assertEqual(recovered[0]['novo'],'Briomary Growth.')
 def test_rejects_overlap_with_multiple_existing_rows(self):
  s=self.setup_missing('Try Oldbrand today.',start=2800);p=T.load(self.out);p['itens'][1]['inicio_ms']=3000;T.write(T.plan_path(self.out),p);s=FV.view(self.out)
  self.assertTrue(s['itens'][0]['conflito'])
  with self.assertRaisesRegex(ValueError,'sobrepostas'):self.apply(s)

 def test_visual_evidence_recovers_rosedil_asr_variants_without_rosemary_false_hit(self):
  plan={'produto':'Rosedil','produto_novo':'BIOMARY GROWTH'}
  for word in ('Rosadyl','Rosedill','Rosedale'):
   words=[{'text':word+'.','start':0,'end':100,'speaker':'A'}]
   self.assertTrue(FV.hits(words,plan),word)
   self.assertEqual(FV.proposed(self.out,plan,'Try '+word+'.')[0],'Try BIOMARY GROWTH.')
  self.assertFalse(FV.hits([{'text':'Rosemary','start':0,'end':100}],plan))
 def test_label_only_does_not_create_voice_candidate_without_speech_evidence(self):
  self.setup_missing('This formula works.');d=D.load(self.out);d['intervalos'][0].pop('legenda_ms');D.write(self.out,d);self.assertEqual(FV.view(self.out)['itens'],[])

 def test_split_name_and_possessive_are_recovered_only_with_continuous_speech(self):
  p={'produto':'Rosedil','produto_novo':'BIOMARY GROWTH'}
  self.assertEqual(FV.proposed(self.out,p,"Try Rose Dill's formula.")[0],"Try BIOMARY GROWTH's formula.")
  words=[{'text':'Rose','start':0,'end':100,'speaker':'A'},{'text':'Dill','start':2000,'end':2200,'speaker':'A'}]
  self.assertFalse(FV.hits(words,p));words[1].update(start=150,end=300,speaker='B');self.assertFalse(FV.hits(words,p))

 def test_batch_approval_preserves_existing_audio_and_requires_authorization(self):
  p=T.load(self.out);p['itens'][0].update(aprovado=True,audio={'fit':'kept.wav','aprovado':True});T.write(T.plan_path(self.out),p);before=copy.deepcopy(p['itens'])
  s=self.setup_missing()
  with self.assertRaisesRegex(ValueError,'Autorize'):FV.authorize_all(self.out,{'base':s['base']})
  self.assertEqual(T.load(self.out)['itens'],before)
  result=FV.authorize_all(self.out,{'base':s['base'],'autoriza_lote':True});self.assertEqual(result['autorizadas'],1);self.assertEqual(result['pendencias'],[])
  fresh=next(r for r in result['plano']['itens'] if r['origem']=='conferencia_visual');self.assertTrue(fresh['aprovado']);self.assertNotIn('audio',fresh)
  self.assertEqual([r for r in result['plano']['itens'] if r['origem']!='conferencia_visual'],before)
  self.assertEqual(len(list((self.out/'trocas/backups').glob('antes_autorizar_falas_*.json'))),1)
  with self.assertRaisesRegex(ValueError,'mudou'):FV.authorize_all(self.out,{'base':s['base'],'autoriza_lote':True})
  self.assertEqual(len(T.load(self.out)['itens']),3)
  self.assertTrue(next(r for r in T.build(self.out,'Oldbrand')['itens'] if r['origem']=='conferencia_visual')['aprovado'])

 def test_batch_keeps_uncertain_and_discarded_decisions(self):
  s=self.setup_missing('This formula works.');uncertain=copy.deepcopy(s['itens'][0]);uncertain['status']='somente_visual'
  FV.review(self.out,{'id':uncertain['id'],'base':s['base'],'acao':'somente_visual'})
  with patch.object(FV,'view',return_value={'base':'batch','itens':[uncertain,dict(uncertain,id='doubt',status='pendente')]}):
   before=T.plan_path(self.out).read_bytes();result=FV.authorize_all(self.out,{'base':'batch','autoriza_lote':True})
  self.assertEqual(result['autorizadas'],0);self.assertEqual(len(result['pendencias']),1);self.assertEqual(T.plan_path(self.out).read_bytes(),before)
  self.assertEqual(FV.view(self.out)['itens'][0]['status'],'somente_visual')

 def test_batch_rejects_conflicts_and_unknown_speakers_and_keeps_full_sentence(self):
  s=self.setup_missing();r=s['itens'][0]
  candidates=[dict(r,id='unknown',speaker='A_CONFIRMAR'),dict(r,id='overlap',conflito=True),r,dict(r,id='duplicate')]
  with patch.object(FV,'view',return_value={'base':'batch','itens':candidates}):result=FV.authorize_all(self.out,{'base':'batch','autoriza_lote':True})
  self.assertEqual(result['autorizadas'],1);self.assertEqual(len(result['pendencias']),3)
  fresh=next(x for x in T.load(self.out)['itens'] if x['origem']=='conferencia_visual');self.assertEqual(fresh['original'],'Try Oldbrand today.');self.assertEqual(fresh['novo'],'Try Newbrand today.')

 def test_batch_does_not_authorize_usage_pending_or_price_only(self):
  s=self.setup_missing();r=s['itens'][0]
  with patch.object(FV,'view',return_value={'base':'batch','itens':[dict(r,forma_pendente=True)]}):result=FV.authorize_all(self.out,{'base':'batch','autoriza_lote':True})
  self.assertEqual(result['autorizadas'],0);self.assertIn('modo de uso',result['pendencias'][0]['motivo'])
  p=T.load(self.out);p['somente_valores']=True;T.write(T.plan_path(self.out),p);s=FV.view(self.out)
  self.assertEqual(FV.authorize_all(self.out,{'base':s['base'],'autoriza_lote':True})['autorizadas'],0)
