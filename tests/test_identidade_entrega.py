import json,tempfile,unittest,copy
from pathlib import Path
import xml.etree.ElementTree as ET
from plataforma import identidade_entrega as N,trocas as T
import test_trocas_completas as B
class IdentityUnitTests(unittest.TestCase):
 def test_requested_pattern_uses_new_product_and_confirmed_final_pitch(self):
  p={'produto':'Old','produto_novo':'Nervelin','nomenclatura':{'numero_vsl':'1','copy':'C46','editor':'EV8'},'revisao':{'pitch':{'tempo':3494.02,'status':'contexto_6_potes'}}}
  r=N.identity(p);self.assertEqual(r['nome_sequencia'],'FUNIL VSL 01 MOD - NERVELIN - C46 - EV8 - PITCH 58:14');self.assertEqual(r['origem_pitch'],'audio_final_6_potes')
 def test_unidentified_pitch_is_explicit_no_delay_or_raw_price_guess(self):
  p={'produto_novo':'New','delay':'58:40','pitch':29,'revisao':{'pitch':{'tempo':99,'status':'revisar'}}}
  r=N.identity(p);self.assertEqual(r['pitch'],'A IDENTIFICAR');self.assertIn('VSL XX MOD',r['nome_sequencia']);self.assertIn('COPY A DEFINIR',r['nome_sequencia'])
 def test_manual_time_is_explicit_and_converted_to_total_minutes(self):
  r=N.identity({'produto_novo':'New','nomenclatura':{'pitch_manual':'1:02:03'}});self.assertEqual(r['pitch'],'62:03');self.assertEqual(r['origem_pitch'],'manual_confirmado')
 def test_filename_pitch_separator_is_accepted(self):
  self.assertEqual(N.normalize({'pitch_manual':'52_22'})['pitch_manual'],'52:22')
  self.assertEqual(N.normalize({'pitch_manual':'1_02_03'})['pitch_manual'],'62:03')
 def test_bad_metadata_rejected(self):
  for cfg in ({'numero_vsl':'0'},{'numero_vsl':'1000'},{'copy':'a\nb'},{'editor':'x'*81},{'pitch_manual':'01:99'}):
   with self.assertRaises(ValueError):N.normalize(cfg)
 def test_model_pitch_invalid_values_stay_pending(self):
  for v in (float('nan'),-1,True,'29'):
   self.assertEqual(N.identity({'revisao':{'pitch':{'tempo':v,'status':'contexto_6_potes'}}})['origem_pitch'],'pendente')
class IdentityExportTests(unittest.TestCase):
 setUpClass=classmethod(B.FlowTests.setUpClass.__func__)
 tearDownClass=classmethod(B.FlowTests.tearDownClass.__func__)
 setUp=B.FlowTests.setUp
 tearDown=B.FlowTests.tearDown
 approve=B.FlowTests.approve
 add_audio=B.FlowTests.add_audio
 job=B.FlowTests.job
 def test_xml_sequence_matches_requested_pattern_and_filename_is_windows_safe(self):
  self.add_audio();N.save(self.out,{'numero_vsl':'2','copy':'João & Ana','editor':'EV8','pitch_manual':'00:05'})
  result=T.export_xml(self.out);xml=self.out/result['xml'];name=ET.parse(xml).findtext('./sequence/name')
  self.assertEqual(name,'FUNIL VSL 02 MOD - NEWBRAND - JOÃO & ANA - EV8 - PITCH 00:05');self.assertNotIn(':',xml.name);self.assertIn('V01',xml.name)
  result2=T.export_xml(self.out);self.assertNotEqual(result['xml'],result2['xml']);self.assertIn('V02',result2['xml'])
 def test_metadata_change_preserves_voice_preview_and_review(self):
  self.add_audio();p=T.load(self.out);p['revisao']={'pitch':{'tempo':5,'status':'contexto_6_potes'}};T.write(T.plan_path(self.out),p)
  before=copy.deepcopy(p);signature=T.preview_signature(self.out);N.save(self.out,{'numero_vsl':'9','copy':'C20','editor':'EV11'})
  after=T.load(self.out);self.assertEqual(after['itens'],before['itens']);self.assertEqual(after['revisao'],before['revisao']);self.assertEqual(T.preview_signature(self.out),signature)
 def test_settings_survive_rebuild(self):
  N.save(self.out,{'numero_vsl':'11','copy':'C47','editor':'EV8'});p=T.build(self.out,'Oldbrand');self.assertEqual(p['nomenclatura']['numero_vsl'],'11')
 def test_metadata_saved_before_plan_is_used_when_plan_is_created(self):
  T.plan_path(self.out).unlink();N.save(self.out,{'numero_vsl':'3','copy':'C50','editor':'EV10'});p=T.build(self.out,'Oldbrand');self.assertEqual(p['nomenclatura']['copy'],'C50')
 def test_rename_marks_existing_delivery_stale_without_deleting_it(self):
  self.add_audio();result=T.export_xml(self.out);p=T.load(self.out);p['entrega']=result|{'assinatura':T.preview_signature(self.out)};T.write(T.plan_path(self.out),p)
  self.assertTrue(T.flow_state(self.out)['entrega_atual']);N.save(self.out,{'numero_vsl':'9','copy':'C20','editor':'EV11'});self.assertFalse(T.flow_state(self.out)['entrega_atual']);self.assertTrue((self.out/result['xml']).is_file())

 def test_rename_xml_only_keeps_media_and_old_export(self):
  self.add_audio();first=T.export_xml(self.out);p=T.load(self.out);p['entrega']=first|{'assinatura':T.preview_signature(self.out)};T.write(T.plan_path(self.out),p)
  old=self.out/first['xml'];original=old.read_bytes();clips=[ET.tostring(x) for x in ET.parse(old).findall('.//clipitem')];rows=copy.deepcopy(p['itens'])
  N.save(self.out,{'numero_vsl':'5','copy':'C46','editor':'EV8','pitch_manual':'00:05'});result=T.rename_delivery(self.out)
  self.assertNotEqual(first['xml'],result['xml']);self.assertEqual(old.read_bytes(),original);self.assertEqual(clips,[ET.tostring(x) for x in ET.parse(self.out/result['xml']).findall('.//clipitem')]);self.assertEqual(T.load(self.out)['itens'],rows);self.assertTrue(T.flow_state(self.out)['entrega_atual']);self.assertIn('FUNIL VSL 05 MOD',ET.parse(self.out/result['xml']).findtext('./sequence/name'))

 def test_fast_delivery_preserves_detected_pitch_if_approvals_did_not_change(self):
  from unittest.mock import patch
  self.add_audio();p=T.load(self.out);p['revisao']={'pitch':{'tempo':5,'status':'contexto_6_potes'}};T.write(T.plan_path(self.out),p)
  with patch('plataforma.workflow.require_takes'),patch('plataforma.visuais.load',return_value={'sem_takes':True}):result=T.fast_delivery_job(self.job(),self.out,True)
  self.assertEqual(T.load(self.out)['revisao']['pitch']['tempo'],5);self.assertIn('PITCH 00:05',result['nome_sequencia'])
