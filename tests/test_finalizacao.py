import json
import zipfile
from pathlib import Path
from unittest.mock import patch
import unittest
import test_trocas_completas as base
from plataforma import trocas as T, deteccao_visual as D, ml_core as M, finalizacao as F, visuais as V, editorial as E, studio as ST

class CompleteTests(unittest.TestCase):
 setUpClass=classmethod(base.FlowTests.setUpClass.__func__)
 tearDownClass=classmethod(base.FlowTests.tearDownClass.__func__)
 setUp=base.FlowTests.setUp
 tearDown=base.FlowTests.tearDown
 job=base.FlowTests.job
 approve=base.FlowTests.approve
 add_audio=base.FlowTests.add_audio
 def ready(self):
  self.add_audio();E.soundtrack(self.out,{'modo':'original'});V.save(self.out,{'sem_takes':True,'incluir':False});D.write(self.out,D.load(self.out)|{'automatico':False})
 def subtitle(self,text='Newbrand works.'):
  path=self.out/'legenda_final.srt';path.write_text('1\n00:00:01,000 --> 00:00:03,000\n'+text+'\n')
  plan=T.load(self.out);plan['validacao_srt']={'arquivo':path.name,'resquicios':[],'montagem_assinatura':T.preview_signature(self.out)};T.write(T.plan_path(self.out),plan)
 def test_missing_caption_blocks_delivery_before_render(self):
  self.ready()
  with patch.object(T,'fast_delivery_job') as render,self.assertRaisesRegex(ValueError,'legenda'):
   F.deliver(self.job(),self.out,sem_previa=True)
  render.assert_not_called()
 def test_caption_must_be_explicitly_reviewed(self):
  self.ready();self.subtitle();self.assertFalse(F.state(self.out)['pronto']);F.confirm(self.out,True);self.assertTrue(F.state(self.out)['pronto'])
 def test_missing_soundtrack_is_reported_even_with_confirmed_caption(self):
  self.ready();E.soundtrack(self.out,{'modo':'nao_definida'});self.subtitle();F.confirm(self.out,True)
  state=F.state(self.out)
  self.assertTrue(state['legenda_conferida']);self.assertTrue(state['trilha_pendente']);self.assertFalse(state['pronto'])
  E.soundtrack(self.out,{'modo':'original'})
  self.assertFalse(F.state(self.out)['trilha_pendente'])
 def test_residual_old_name_blocks_confirmation(self):
  self.ready();self.subtitle('Oldbrand works.');self.assertTrue(any('produto antigo' in x for x in F.state(self.out)['pendencias']))
  with self.assertRaisesRegex(ValueError,'produto antigo'):F.confirm(self.out,True)
 def test_montage_change_invalidates_subtitle_confirmation(self):
  self.ready();self.subtitle();F.confirm(self.out,True);E.soundtrack(self.out,{'modo':'original','ganho_db':-12});self.assertFalse(F.state(self.out)['pronto'])
 def test_only_saving_real_xml_delivery_stops_clock(self):
  self.ready();self.subtitle();F.confirm(self.out,True);ST.create(self.out)
  result=F.deliver(self.job(),self.out,sem_previa=True)
  self.assertTrue(result['completa']);self.assertTrue(result['xml_existe']);self.assertEqual(result['legenda'],'legenda_final.srt')
  self.assertFalse(ST.summary(self.out,T.load(self.out))['medicao_encerrada'])
  saved=ST.confirm_xml_save(self.out,result['xml'],T.load(self.out))
  self.assertTrue(saved['medicao_encerrada']);self.assertTrue(saved['final_completa'])
  self.assertEqual((self.out/result['legenda_entrega']).read_bytes(),(self.out/result['legenda']).read_bytes())
  with zipfile.ZipFile(self.out/result['pacote']) as archive:
   self.assertEqual(set(archive.namelist()), {Path(result[k]).name for k in ('xml','json','legenda_entrega')}|{'IMPORTAR NO PREMIERE.txt'})
   self.assertEqual(archive.read(Path(result['legenda_entrega']).name),(self.out/result['legenda']).read_bytes())
  (self.out/'legenda_final.srt').write_text('changed')
  after_srt_change=ST.summary(self.out,T.load(self.out))
  self.assertFalse(after_srt_change['final_completa'])
  self.assertTrue(after_srt_change['entrega_valida'])
  self.assertTrue(after_srt_change['medicao_encerrada'])
 def test_ocr_automatic_only_enqueues_once_and_uses_own_queue(self):
  with patch.object(M,'JOBS',{}),patch.object(M,'submit') as submit:
   job=M.Job('deteccao_visual','test',D.analyze_job,out=str(self.out));job.status='na_fila';submit.return_value=job
   D.automatic(self.out);D.automatic(self.out)
   self.assertEqual(submit.call_count,1);self.assertEqual(submit.call_args.args[3],'visual');self.assertTrue(submit.call_args.kwargs['automatico'])
 def test_ocr_disabled_does_not_enqueue_and_preserves_cache(self):
  marker=D.folder(self.out)/'read-cache';marker.parent.mkdir(parents=True);marker.write_text('preserve')
  with patch.object(M,'submit') as submit:D.automatic(self.out,False);D.automatic(self.out)
  submit.assert_not_called();self.assertEqual(marker.read_text(),'preserve');self.assertFalse(D.load(self.out)['automatico'])
 def test_ocr_skips_audio_only_and_price_only(self):
  with patch.object(T,'probe',return_value={'video':False}),patch.object(M,'submit') as submit:
   self.assertEqual(D.automatic(self.out)['situacao'],'somente_audio')
  submit.assert_not_called()
  plan=T.load(self.out);plan['somente_valores']=True;T.write(T.plan_path(self.out),plan)
  with patch.object(M,'submit') as submit:self.assertEqual(D.automatic(self.out)['situacao'],'somente_valores')
  submit.assert_not_called()
 def test_finished_valid_ocr_is_reused(self):
  from plataforma.visual_refino import VERSION
  state=D.load(self.out);state['analise']={'fonte':T.source_identity(T.source(self.out)),'nomes':D.names(state),'janela':state['janela'],'refino_versao':VERSION,'limites_versao':D.LIMITS_VERSION};D.write(self.out,state)
  with patch.object(M,'submit') as submit:self.assertEqual(D.automatic(self.out)['situacao'],'concluido')
  submit.assert_not_called()

 def test_old_visual_scan_gets_one_refinement_without_deleting_base_cache(self):
  state=D.load(self.out);state['analise']={'fonte':T.source_identity(T.source(self.out)),'nomes':D.names(state),'janela':state['janela']};D.write(self.out,state)
  marker=D.folder(self.out)/'old-ocr-cache';marker.write_text('preserve')
  with patch.object(M,'JOBS',{}),patch.object(M,'submit') as submit:
   job=M.Job('deteccao_visual','test',D.analyze_job,out=str(self.out));job.status='na_fila';submit.return_value=job
   D.automatic(self.out);D.automatic(self.out)
   self.assertEqual(submit.call_count,1)
  self.assertEqual(marker.read_text(),'preserve')

 def test_revoking_caption_blocks_delivery(self):
  self.ready();self.subtitle();F.confirm(self.out,True);F.confirm(self.out,False)
  self.assertFalse(F.state(self.out)['pronto'])
 def test_background_render_blocks_delivery(self):
  self.ready();self.subtitle();F.confirm(self.out,True)
  job=M.Job('legendas_video','render',lambda:None,out=str(self.out));job.status='executando'
  with patch.object(M,'JOBS',{'render':job}):self.assertFalse(F.state(self.out)['pronto'])
 def test_saved_delivery_becomes_stale_when_caption_changes(self):
  self.ready();self.subtitle();F.confirm(self.out,True);F.deliver(self.job(),self.out,sem_previa=True)
  self.assertTrue(F.state(self.out)['entrega']['atual'])
  self.subtitle('Newbrand is here.');F.confirm(self.out,True)
  self.assertFalse(F.state(self.out)['entrega']['atual'])

 def test_failed_package_keeps_previous_delivery_current(self):
  self.ready();self.subtitle();F.confirm(self.out,True)
  previous=F.deliver(self.job(),self.out,sem_previa=True)
  with patch.object(F,'package',side_effect=OSError('disco cheio')),self.assertRaises(OSError):
   F.deliver(self.job(),self.out,sem_previa=True)
  delivery=F.state(self.out)['entrega']
  self.assertEqual(delivery['xml'],previous['xml'])
  self.assertTrue(delivery['atual'])
