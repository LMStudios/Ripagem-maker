import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
from plataforma import conferencia_mencoes as C,trocas as T,falas_visuais as F
import test_trocas_completas as B

class CoverageTests(unittest.TestCase):
 setUpClass=classmethod(B.FlowTests.setUpClass.__func__)
 tearDownClass=classmethod(B.FlowTests.tearDownClass.__func__)
 setUp=B.FlowTests.setUp
 tearDown=B.FlowTests.tearDown
 job=B.FlowTests.job
 def fixture(self):
  rows=json.loads((Path(__file__).parent/'fixtures/rosedil-resquicios-14.json').read_text())
  p=T.load(self.out);p.update(produto='Rosedil',produto_novo='Briomary Growth',duracao_s=5000,speakers=['A','B']);p['itens']=[]
  for n,r in enumerate(rows):
   if r['status_anterior']=='sem_fala':continue
   new=F.proposed(self.out,p,r['text'])[0]
   p['itens'].append({'id':'old-'+str(n),'inicio_ms':r['inicio_ms'],'fim_ms':r['fim_ms'],'original':r['text'],'novo':new,'base_novo':new,'speaker':r['words'][0]['speaker'],'origem':'conferencia_visual','speaker_confirmado':True,'aprovado':False,'duracao_s':(r['fim_ms']-r['inicio_ms'])/1000})
  T.write(T.plan_path(self.out),p);(self.out/'transcricao_bruta.json').write_text(json.dumps({'words':[w for r in rows for w in r['words']]}));return rows
 def test_all_fourteen_reported_cases_found_without_ocr(self):
  expected=self.fixture();r=C.scan(self.out)
  self.assertEqual(len(r['pendencias']),14)
  self.assertEqual([x['texto'] for x in r['pendencias']],[x['text'] for x in expected])
  self.assertEqual(sum(x['status']=='fora_da_selecao' for x in r['pendencias']),11);self.assertEqual(sum(x['status']=='sem_fala' for x in r['pendencias']),3)
  s=F.view(self.out);probable=[x for x in s['itens'] if x['situacao']=='mencao_provavel'];self.assertEqual(len(probable),14)
  self.assertEqual(sum(bool(x.get('existing_id')) for x in probable),11)
 def test_batch_restores_existing_selection_without_duplicates_and_requires_audio(self):
  self.fixture();p=T.load(self.out);keep=p['itens'][0];keep['audio']={'fit':'existing.mp3','aprovado':True,'texto_hash':T.digest([keep['novo'],keep['speaker']])};(self.out/'existing.mp3').write_bytes(b'audio');T.write(T.plan_path(self.out),p);audio=copy.deepcopy(keep['audio']);s=F.view(self.out)
  result=F.authorize_all(self.out,{'base':s['base'],'autoriza_lote':True});self.assertEqual(result['autorizadas'],14);self.assertEqual(len(result['plano']['itens']),14)
  self.assertEqual(next(x for x in result['plano']['itens'] if x['id']==keep['id'])['audio'],audio)
  self.assertTrue(all(x['aprovado'] for x in result['plano']['itens']));self.assertTrue(C.scan(self.out)['pendencias'])
  with self.assertRaisesRegex(ValueError,'menção'):C.require(self.out)
  p=T.load(self.out)
  for row in p['itens']:row['audio']={'fit':'existing.mp3','aprovado':True,'texto_hash':T.digest([row['novo'],row['speaker']])}
  T.write(T.plan_path(self.out),p);self.assertFalse(C.require(self.out)['pendencias'])
 def test_export_rejects_omitted_mentions_and_preserves_previous_xml(self):
  self.fixture();p=T.load(self.out);row=p['itens'][0];row['aprovado']=True;row['audio']={'fit':'existing.mp3','aprovado':True,'texto_hash':T.digest([row['novo'],row['speaker']])};(self.out/'existing.mp3').write_bytes(b'audio');T.write(T.plan_path(self.out),p)
  old=self.out/'trocas/previous.xml';old.write_text('<previous/>')
  with self.assertRaisesRegex(ValueError,'fora da seleção'):T.export_xml(self.out)
  self.assertEqual(old.read_text(),'<previous/>');self.assertEqual(list((self.out/'trocas').glob('*.xml')),[old])
 def test_quick_export_sends_first_unselected_mention_as_recovery_action(self):
  self.fixture()
  first=C.scan(self.out)['pendencias'][0]
  self.assertEqual(first['status'],'fora_da_selecao')
  job=T.M.Job('entrega','Entrega rápida',None)
  with patch('plataforma.workflow.require_takes'),self.assertRaisesRegex(ValueError,'fora da seleção'):
   T.fast_delivery_job(job,self.out,True)
  self.assertEqual(job.to_dict()['acao_erro'],{'tipo':'revisar_mencao','trecho':{
   key:first[key] for key in ('inicio_ms','fim_ms','status','id_fala')
  }})
  self.assertFalse(list((self.out/'trocas').glob('*.xml')))
 def test_learns_repeated_variants_with_context_without_visual_search(self):
  p=T.load(self.out);p.update(produto='Rosedil',produto_novo='Newbrand',itens=[]);T.write(T.plan_path(self.out),p)
  words=[]
  for n,text in enumerate(['Try Rosedale formula.','Order Rosedale bottles.','Rosedale treatment works.','Rosemary is an ingredient.']):
   for i,t in enumerate(text.split()):words.append({'text':t,'start':n*1500+i*150,'end':n*1500+i*150+100,'speaker':'A'})
  (self.out/'transcricao_bruta.json').write_text(json.dumps({'words':words}));r=C.scan(self.out)
  self.assertEqual(len(r['pendencias']),3);self.assertIn('Rosedale',r['aliases']);self.assertNotIn('Rosemary',r['aliases'])
 def test_does_not_consume_pronoun_after_name(self):
  p={'produto':'Rosedil','produto_novo':'Briomary Growth'}
  value=F.proposed(self.out,p,'When she told me about Rosédeal, I thought it worked.')[0]
  self.assertEqual(value,'When she told me about Briomary Growth, I thought it worked.')
 def test_price_only_does_not_require_product_swap(self):
  self.fixture();p=T.load(self.out);p['somente_valores']=True;T.write(T.plan_path(self.out),p);self.assertFalse(C.require(self.out)['pendencias']);self.assertTrue(C.scan(self.out)['ignorado'])
 def test_explicit_false_positive_is_scoped_and_survives_selection_changes(self):
  rows=self.fixture();r=C.scan(self.out);first=r['pendencias'][0];C.dismiss(self.out,first['frase_inicio_ms'],first['frase_fim_ms'],'Nome de lugar, confirmado pelo usuário')
  self.assertEqual(len(C.scan(self.out)['pendencias']),13)
  p=T.load(self.out);p['itens'][0]['aprovado']=True;T.write(T.plan_path(self.out),p);self.assertEqual(next(x for x in C.scan(self.out)['itens'] if x['id']==first['id'])['status'],'descartada')
  p['produto']='AnotherBrand';T.write(T.plan_path(self.out),p);self.assertNotEqual(C.scan(self.out).get('base'),r['base'])
 def test_current_audio_audit_residue_blocks_even_with_text_coverage(self):
  p=T.load(self.out);p['revisao']={'assinatura':'current','resquicios':[{'termo':'Oldbrand'}]};T.write(T.plan_path(self.out),p)
  with patch.object(C,'scan',return_value={'pendencias':[]}),patch.object(T,'preview_signature',return_value='current'),self.assertRaisesRegex(ValueError,'áudio final'):C.require(self.out)
  with patch.object(C,'scan',return_value={'pendencias':[]}),patch.object(T,'preview_signature',return_value='changed'):self.assertFalse(C.require(self.out)['pendencias'])
 def test_xml_verification_checks_source_frames_after_timeline_shift(self):
  import xml.etree.ElementTree as E
  seq=E.fromstring('<sequence><media><audio><track><clipitem><enabled>TRUE</enabled><start>200</start><end>250</end><in>0</in><out>50</out></clipitem></track></audio></media></sequence>')
  report={'itens':[{'status':'coberta','inicio_ms':1000,'fim_ms':1200}]}
  with self.assertRaisesRegex(ValueError,'áudio original ativo'):C.verify_xml(seq,report,25)
  seq.find('.//out').text='25';self.assertEqual(C.verify_xml(seq,report,25)['mencoes_no_audio_original_ativo'],0)
  seq.find('.//out').text='50';report['itens'][0]['status']='descartada';self.assertEqual(C.verify_xml(seq,report,25)['mencoes_verificadas'],0)
 def test_audit_settings_invalidate_previous_delivery_signature(self):
  original=T.preview_signature(self.out);p=T.load(self.out);p.setdefault('editorial',{})['aliases']='Old brand';T.write(T.plan_path(self.out),p)
  self.assertNotEqual(T.preview_signature(self.out),original)
 def test_compound_brands_and_asr_variants_are_not_rosedil_specific(self):
  for product,variant in [('Memovance Pro','Memovence Pro'),('Breath Zen','Brett Zen')]:
   with self.subTest(product=product):
    p=T.load(self.out);p.update(produto=product,produto_novo='Newbrand',itens=[]);T.write(T.plan_path(self.out),p)
    words=[]
    for n,text in enumerate([f'Try {variant} formula.',f'Order {variant} bottles.',f'Try {variant} treatment.']):
     for i,t in enumerate(text.split()):words.append({'text':t,'start':n*1500+i*150,'end':n*1500+i*150+100,'speaker':'A'})
    (self.out/'transcricao_bruta.json').write_text(json.dumps({'words':words}));self.assertEqual(len(C.scan(self.out)['pendencias']),3)
