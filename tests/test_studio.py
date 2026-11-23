import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from plataforma import studio as S

class StudioTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.out=Path(self.tmp.name);self.config=patch.object(S,'CONFIG',self.out/'prefs.json');self.config.start()
 def tearDown(self):self.config.stop();self.tmp.cleanup()
 def plan(self,count=48):
  return {'forma':{'ativo':True},'itens':[{'id':str(i),'inicio_ms':i*2000,'fim_ms':i*2000+1000,'aprovado':True,'novo':'New','speaker':'A','audio':{}} for i in range(count)]}
 def finish(self,p):
  (self.out/'entrega.xml').write_text('<xmeml/>')
  return S.finish(self.out,{'xml':'entrega.xml'},p)
 def test_example_48_mentions_usage_45_minutes(self):
  with patch.object(S.time,'time',return_value=10000):S.create(self.out,7300);d=self.finish(self.plan())
  self.assertEqual(d['manual_min'],300);self.assertEqual(d['app_min'],45);self.assertEqual(d['economia_min'],255);self.assertEqual(d['percentual'],85)
 def test_old_project_never_gets_invented_savings(self):
  d=self.finish(self.plan());self.assertFalse(d['completa']);self.assertIsNone(d['percentual']);self.assertIsNone(d['economia_min'])
 def test_heartbeat_deduplicates_multiple_windows(self):
  with patch.object(S.time,'time',return_value=100):S.create(self.out)
  with patch.object(S.time,'time',return_value=110):S.heartbeat(self.out);S.heartbeat(self.out)
  self.assertEqual(S.read(self.out/'tempo_studio.json',{})['segundos'],10)
 def test_pause_and_closed_gap_are_excluded(self):
  with patch.object(S.time,'time',return_value=100):S.create(self.out)
  with patch.object(S.time,'time',return_value=110):S.heartbeat(self.out,True)
  with patch.object(S.time,'time',return_value=120):S.heartbeat(self.out,False)
  with patch.object(S.time,'time',return_value=130):S.heartbeat(self.out,closing=True)
  with patch.object(S.time,'time',return_value=135):S.heartbeat(self.out)
  with patch.object(S.time,'time',return_value=500):S.heartbeat(self.out)
  self.assertEqual(S.read(self.out/'tempo_studio.json',{})['segundos'],20)
 def test_missing_xml_cannot_finish(self):
  with self.assertRaises(ValueError):S.finish(self.out,{'xml':'missing.xml'},self.plan())
 def test_external_xml_cannot_finish(self):
  with self.assertRaises(ValueError):S.finish(self.out,{'xml':'../escape.xml'},self.plan())
 def test_changes_invalidate_delivery_and_keep_measurement_closed(self):
  p=self.plan(1)
  with patch.object(S.time,'time',return_value=100):S.create(self.out);self.finish(p)
  p['itens'][0]['novo']='Changed'
  self.assertFalse(S.summary(self.out,p)['entrega_valida'])
  with patch.object(S.time,'time',return_value=110):
   S.heartbeat(self.out,False,p,closing=True)
   S.heartbeat(self.out,plan=p)
  d=S.summary(self.out,p)
  self.assertTrue(d['medicao_encerrada'])
  self.assertEqual(d['app_min'],0)
  self.assertEqual(d['xml_salvo'],'entrega.xml')
 def test_confirmation_of_review_then_delivery_preserves_first_stop(self):
  p=self.plan(1);xml_dir=self.out/'trocas';xml_dir.mkdir()
  p['entrega_revisao']={'xml':'trocas/revisao.xml','revisao_pendencias':True}
  p['entrega']={'xml':'trocas/final.xml'}
  for name in ('revisao.xml','final.xml'):(xml_dir/name).write_text('<xmeml/>')
  with patch.object(S.time,'time',return_value=100):S.create(self.out)
  with patch.object(S.time,'time',return_value=112):
   review=S.confirm_xml_save(self.out,p['entrega_revisao']['xml'],p)
  self.assertTrue(review['medicao_encerrada'])
  self.assertTrue(review['xml_de_revisao'])
  self.assertFalse(review['entrega_valida'])
  before=(self.out/'tempo_studio.json').read_bytes()
  with patch.object(S.time,'time',return_value=122):
   S.heartbeat(self.out,False,p)
   S.confirm_xml_save(self.out,r'trocas\revisao.xml',p)
   self.assertEqual((self.out/'tempo_studio.json').read_bytes(),before)
   final=S.confirm_xml_save(self.out,p['entrega']['xml'],p)
  self.assertEqual(final['app_min'],12/60)
  self.assertTrue(final['medicao_encerrada'])
  self.assertFalse(final['xml_de_revisao'])
  self.assertTrue(final['entrega_valida'])
  self.assertFalse(final['final_completa'])
  self.assertEqual(S.read(self.out/'tempo_studio.json',{})['conclusao']['quando'],112)
 def test_confirmation_only_accepts_assembly_xml(self):
  p=self.plan(1)
  xml_dir=self.out/'trocas';xml_dir.mkdir()
  for name in ('avulso.xml','legenda.srt'):(xml_dir/name).write_text('dados')
  with self.assertRaises(ValueError):S.confirm_xml_save(self.out,'trocas/avulso.xml',p)
  with self.assertRaises(ValueError):S.confirm_xml_save(self.out,'trocas/legenda.srt',p)
  self.assertFalse(S.summary(self.out,p)['medicao_encerrada'])
  assert not (self.out/'tempo_studio.json').exists()
  report={'arquivo':'trocas/avulso.xml','nomenclatura':{},'itens':[],'conferencia_mencoes':{}}
  (xml_dir/'avulso.json').write_text(json.dumps(report))
  self.assertTrue(S.confirm_xml_save(self.out,'trocas/avulso.xml',p)['medicao_encerrada'])
 def test_classic_mac_download_is_confirmed_without_overwriting(self):
  from plataforma import native_files
  plan=self.plan(1)
  copies=self.out/'Downloads';copies.mkdir()
  folder=self.out/'trocas';folder.mkdir()
  xml=folder/'Entrega.xml';xml.write_bytes(b'<xmeml/>')
  package=folder/'Entrega.zip';package.write_bytes(b'faz parte da entrega')
  (folder/'outro.zip').write_bytes(b'outro arquivo')
  plan['entrega']={'xml':'trocas/Entrega.xml','pacote':'trocas/Entrega.zip'}
  (copies/'Entrega.xml').write_bytes(b'original no destino')
  with patch.object(native_files.sys,'platform','darwin'),patch.object(native_files.Path,'home',return_value=self.out):
   with self.assertRaises(ValueError):
    S.confirm_xml_save(self.out,plan['entrega']['xml'],plan,download='trocas/outro.zip')
   self.assertFalse(S.summary(self.out,plan)['medicao_encerrada'])
   data=S.confirm_xml_save(self.out,plan['entrega']['xml'],plan,download=plan['entrega']['xml'])
   self.assertEqual(Path(data['destino']).name,'Entrega (2).xml')
   self.assertEqual(Path(data['destino']).read_bytes(),xml.read_bytes())
   self.assertEqual((copies/'Entrega.xml').read_bytes(),b'original no destino')
   self.assertTrue(data['medicao_encerrada'])
   data=S.confirm_xml_save(self.out,plan['entrega']['xml'],plan,download=plan['entrega']['pacote'])
   self.assertEqual(Path(data['destino']).read_bytes(),package.read_bytes())
  self.assertFalse(list(copies.glob('.ripagem-*')))
 def test_overlapping_and_unselected_mentions_are_not_counted_twice(self):
  p=self.plan(1);p['itens']+=[dict(p['itens'][0],id='dup'),dict(p['itens'][0],id='skip',aprovado=False)]
  self.assertEqual(S.selection(p)[0],1)
 def test_zero_and_negative_savings_are_honest(self):
  p=self.plan(1);p['forma']['ativo']=False
  with patch.object(S.time,'time',return_value=1000):S.create(self.out,40);d=self.finish(p)
  self.assertLess(d['economia_min'],0)
  p=self.plan(0);p['forma']['ativo']=False
  with patch.object(S.time,'time',return_value=1010):
   (self.out/'new.xml').write_text('<xmeml/>')
   d=S.finish(self.out,{'xml':'new.xml'},p)
  self.assertIsNone(d['percentual'])
 def test_preferences_persist_and_reject_bad_values(self):
  self.assertIsNone(S.preferences()['tutorial']);S.preferences({'tutorial':'direto','minutos_por_mencao':4});self.assertEqual(S.preferences()['minutos_por_mencao'],4)
  for value in (float('nan'),float('inf'),-1,True,'invalid'):
   with self.assertRaises(ValueError):S.preferences({'minutos_por_mencao':value})

 def test_corrupted_json_falls_back_without_touching_other_files(self):
  S.CONFIG.write_text('not JSON');self.assertEqual(S.preferences()['minutos_por_mencao'],5)
  S.CONFIG.write_text('[]');self.assertIsNone(S.preferences()['tutorial'])
 def test_montage_change_invalidates_summary(self):
  p=self.plan(1);(self.out/'entrega.xml').write_text('<xmeml/>')
  with patch.object(S.time,'time',return_value=100),patch('plataforma.trocas.preview_signature',return_value='first'):
   S.create(self.out);S.finish(self.out,{'xml':'entrega.xml'},p,montagem='first')
   self.assertTrue(S.summary(self.out,p)['entrega_valida'])
  with patch('plataforma.trocas.preview_signature',return_value='changed'):
   self.assertFalse(S.summary(self.out,p)['entrega_valida'])

 def route(self,body,length=None):
  import io
  from plataforma import api
  class H:
   path='/api/studio/preferencias'
   headers={'Content-Length':str(len(body) if length is None else length)}
   rfile=io.BytesIO(body);wfile=io.BytesIO()
   def send_response(self,status):self.status=status
   def send_header(self,*a):pass
   def end_headers(self):pass
  h=H();self.assertTrue(api.handle(h,'POST'));return h
 def test_invalid_preferences_are_http_400(self):
  h=self.route(b'{"minutos_por_mencao":-1}')
  self.assertEqual(h.status,400);self.assertIn('erro',json.loads(h.wfile.getvalue()))
 def test_oversized_preferences_do_not_read_body(self):
  h=self.route(b'not-read',5000);self.assertEqual(h.status,400);self.assertEqual(h.rfile.tell(),0)
