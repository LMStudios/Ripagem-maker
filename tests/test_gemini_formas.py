import copy,json,unittest
from unittest.mock import patch
from types import SimpleNamespace
import test_trocas_completas as B
from plataforma import gemini_formas as G,trocas as T,credenciais as C,ml_core as M
class GeminiTests(unittest.TestCase):
 setUpClass=classmethod(B.FlowTests.setUpClass.__func__)
 tearDownClass=classmethod(B.FlowTests.tearDownClass.__func__)
 tearDown=B.FlowTests.tearDown
 job=B.FlowTests.job
 approve=B.FlowTests.approve
 add_audio=B.FlowTests.add_audio
 def setUp(self):
  B.FlowTests.setUp(self);p=T.load(self.out);p['forma']={'ativo':True,'origem':'patch','destino':'dropper','uso_novo':'Use according to the label.','descricao_nova':'Oral drops.','uso_original':''}
  for r in p['itens']:r['forma_detectada']=True
  T.write(T.plan_path(self.out),p)
 def response(self,*args,**kwargs):
  data=json.loads(kwargs['json']['contents'][0]['parts'][0]['text']);rows=[{'id':r['id'],'texto':'Use Newbrand according to the label.','pendente':False,'motivo':'Instrução confirmada aplicada.'} for r in data['frases']]
  return SimpleNamespace(ok=True,status_code=200,json=lambda:{'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps({'itens':rows})}]}}]})
 def generate(self):
  with patch.object(G.requests,'post',side_effect=self.response) as api:
   result=G.generate(self.job(),self.out,'TEST_ONLY_GEMINI_KEY');return result,api
 def test_suggestions_do_not_change_plan_and_cache_reuses(self):
  before=T.plan_path(self.out).read_bytes();result,api=self.generate();self.assertEqual(before,T.plan_path(self.out).read_bytes());self.assertEqual(len(result['itens']),2)
  self.assertEqual(api.call_args.kwargs['headers'],{'x-goog-api-key':'TEST_ONLY_GEMINI_KEY'});self.assertNotIn('key=',api.call_args.args[0]);self.assertNotIn('TEST_ONLY_GEMINI_KEY',G.path(self.out).read_text())
  prompt=json.loads(api.call_args.kwargs['json']['contents'][0]['parts'][0]['text']);self.assertIn('contexto_posterior',prompt['frases'][0]);self.assertEqual(prompt['forma']['uso_novo'],'Use according to the label.')
  with patch.object(G.requests,'post') as again:G.generate(self.job(),self.out,'TEST_ONLY');again.assert_not_called()
 def test_apply_changes_only_selected_audio_and_requires_review(self):
  self.add_audio();before=T.load(self.out);data,_=self.generate();rid=data['itens'][0]['id'];result=G.apply(self.out,[rid]);row=next(r for r in result['itens'] if r['id']==rid)
  self.assertNotIn('audio',row);self.assertTrue(row['historico_audio']);self.assertTrue(row['forma_pendente']);self.assertFalse(row['forma_confirmada']);self.assertTrue(row['forma_ia_aplicada']);self.assertIn('rascunho',row['forma_avisos'][0]);self.assertEqual(row['inicio_ms'],before['itens'][0]['inicio_ms']);self.assertEqual(result['itens'][1]['audio'],before['itens'][1]['audio'])
 def test_stale_suggestions_cannot_overwrite_edits(self):
  data,_=self.generate();rid=data['itens'][0]['id'];T.save(self.out,[{'id':rid,'novo':'Manual edit.'}]);before=T.plan_path(self.out).read_bytes()
  with self.assertRaisesRegex(ValueError,'desatualizadas'):G.apply(self.out,[rid])
  self.assertEqual(before,T.plan_path(self.out).read_bytes())
 def test_quota_and_network_errors_never_echo_provider_body_or_key(self):
  with patch.object(G.requests,'post',return_value=SimpleNamespace(ok=False,status_code=429,text='TEST_ONLY_GEMINI_KEY')):
   with self.assertRaisesRegex(ValueError,'Cota') as e:G.generate(self.job(),self.out,'TEST_ONLY_GEMINI_KEY')
  self.assertNotIn('TEST_ONLY_GEMINI_KEY',str(e.exception));self.assertFalse(G.path(self.out).exists())
  with patch.object(G.requests,'post',side_effect=G.requests.Timeout('SECRET')):
   with self.assertRaises(ValueError) as e:G.generate(self.job(),self.out,'TEST_ONLY')
  self.assertNotIn('SECRET',str(e.exception))
 def test_invalid_and_pending_response_cannot_apply(self):
  with patch.object(G.requests,'post',return_value=SimpleNamespace(ok=True,status_code=200,json=lambda:{'candidates':[]})):
   with self.assertRaisesRegex(ValueError,'inválida'):G.generate(self.job(),self.out,'TEST_ONLY')
  data,_=self.generate();data['itens'][0].update(pendente=True,texto='');T.write(G.path(self.out),data)
  with self.assertRaisesRegex(ValueError,'pendentes'):G.apply(self.out,[data['itens'][0]['id']])
 def test_cancel_and_concurrent_edits_preserve_texts(self):
  j=self.job();j.cancel=True
  with patch.object(G.requests,'post') as api:
   with self.assertRaises(M.Cancelled):G.generate(j,self.out,'TEST_ONLY')
   api.assert_not_called()
  rid=T.load(self.out)['itens'][0]['id']
  def response(*a,**kw):
   T.save(self.out,[{'id':rid,'novo':'Manual during request.'}]);return self.response(*a,**kw)
  with patch.object(G.requests,'post',side_effect=response):
   with self.assertRaisesRegex(ValueError,'mudaram'):G.generate(self.job(),self.out,'TEST_ONLY')
  self.assertEqual(T.load(self.out)['itens'][0]['novo'],'Manual during request.');self.assertFalse(G.path(self.out).exists())
 def test_submit_requires_consent_and_keeps_key_out_of_params(self):
  with self.assertRaises(ValueError):G.submit(self.out,False)
  with patch.object(C,'key',return_value='TEST_ONLY_SECRET'),patch.object(M,'submit',return_value=SimpleNamespace(to_dict=lambda:{})) as queue:
   G.submit(self.out,True);self.assertEqual(queue.call_args.kwargs['out'],str(self.out));self.assertNotIn('TEST_ONLY_SECRET',str(queue.call_args))

 def test_gemini_key_uses_cofre_and_connection_only_reads_metadata(self):
  values={}
  with patch.object(C.store,'set',side_effect=lambda p,k:values.update({p:k})),patch.object(C.store,'get',side_effect=lambda p:values.get(p)),patch.object(C.store,'delete',side_effect=lambda p:values.pop(p,None)),patch.object(C.requests,'get',return_value=SimpleNamespace(ok=True,status_code=200)) as api:
   self.assertTrue(C.save('TEST_ONLY_GEMINI_KEY','gemini')['configurada']);self.assertEqual(C.key('gemini'),'TEST_ONLY_GEMINI_KEY');result=C.test('gemini');self.assertTrue(result['ok']);self.assertNotIn('TEST_ONLY_GEMINI_KEY',str(result));self.assertEqual(api.call_args.args[0],'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite');self.assertEqual(api.call_args.kwargs['headers'],{'x-goog-api-key':'TEST_ONLY_GEMINI_KEY'});self.assertFalse(C.remove('gemini')['configurada'])
 def test_context_edits_invalidate_suggestions(self):
  self.generate();raw=json.loads((self.out/'transcricao_bruta.json').read_text());raw['words'].append({'text':'Different context.','start':7500,'end':7800});(self.out/'transcricao_bruta.json').write_text(json.dumps(raw));self.assertTrue(G.state(self.out)['desatualizado'])

 def test_old_form_left_by_model_is_not_an_applicable_suggestion(self):
  def response(*a,**kw):
   r=self.response(*a,**kw);data=r.json();items=json.loads(data['candidates'][0]['content']['parts'][0]['text']);items['itens'][0]['texto']='Use the patch.';data['candidates'][0]['content']['parts'][0]['text']=json.dumps(items);return SimpleNamespace(ok=True,status_code=200,json=lambda:data)
  with patch.object(G.requests,'post',side_effect=response):result=G.generate(self.job(),self.out,'TEST_ONLY')
  row=result['itens'][0];self.assertTrue(row['pendente']);self.assertEqual(row['texto'],'')
  with self.assertRaises(ValueError):G.apply(self.out,[row['id']])
 def test_simple_references_can_be_sent_without_dosage_instructions(self):
  p=T.load(self.out);p['forma'].update(uso_novo='',descricao_nova='');T.write(T.plan_path(self.out),p);result,api=self.generate();self.assertTrue(api.called);self.assertEqual(len(result['itens']),2)

 def test_model_not_found_reports_project_availability_without_secret_or_retry(self):
  with patch.object(G.requests,'post',return_value=SimpleNamespace(ok=False,status_code=404,text='PRIVATE_KEY_SERVER_BODY')) as api:
   with self.assertRaisesRegex(ValueError,'chave/projeto') as err:G.generate(self.job(),self.out,'TEST_ONLY_GEMINI_KEY')
  self.assertEqual(api.call_count,1);self.assertNotIn('PRIVATE_KEY_SERVER_BODY',str(err.exception));self.assertNotIn('TEST_ONLY_GEMINI_KEY',str(err.exception));self.assertFalse(G.path(self.out).exists())
 def test_current_model_request_has_no_obsolete_thinking_budget(self):
  _,api=self.generate();self.assertIn('gemini-3.5-flash-lite:generateContent',api.call_args.args[0]);self.assertNotIn('thinkingBudget',str(api.call_args.kwargs['json']));self.assertIn('responseSchema',api.call_args.kwargs['json']['generationConfig'])

 def test_unconfirmed_dose_cannot_be_transferred_to_capsules(self):
  p=T.load(self.out);p['forma'].update(uso_novo='',descricao_nova='');T.write(T.plan_path(self.out),p)
  def response(*a,**kw):
   r=self.response(*a,**kw);d=r.json();items=json.loads(d['candidates'][0]['content']['parts'][0]['text']);items['itens'][0]['texto']='Take 2 capsules per day.';d['candidates'][0]['content']['parts'][0]['text']=json.dumps(items);return SimpleNamespace(ok=True,status_code=200,json=lambda:d)
  with patch.object(G.requests,'post',side_effect=response):result=G.generate(self.job(),self.out,'TEST_ONLY')
  self.assertTrue(result['itens'][0]['pendente']);self.assertEqual(result['itens'][0]['texto'],'')
 def test_neutral_capsule_rewrite_is_allowed_without_dose(self):
  items=[{'id':'dose','original':'Just 2 drops per day.','texto_atual':'Just 2 drops per day.','contexto_anterior':'','contexto_posterior':''}]
  response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps({'itens':[{'id':'dose','texto':'Simply use Newbrand in capsule form.','pendente':False,'motivo':'Dose e frequência retiradas; apresentação adaptada.'}]})}]}}]}
  with patch.object(G.requests,'post',return_value=SimpleNamespace(ok=True,status_code=200,json=lambda:response)):
   result=G.request(items,'Newbrand',{'ativo':True,'origem':'dropper','destino':'capsule','via_uso':'oral','uso_novo':'','descricao_nova':''},'TEST_ONLY')
  self.assertFalse(result[0]['pendente']);self.assertNotIn('drops',result[0]['texto']);self.assertIsNone(__import__('re').search(r'\b2\b|per day',result[0]['texto']))
