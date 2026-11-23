"""Casos adversos sem serviços pagos ou arquivos reais de trabalho."""
import io,random,tempfile,unittest
from pathlib import Path
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from plataforma import trocas_api as API,armazenamento as S,trocas as T,ml_core as M,projetos as PR,ofertas as O,fechamento as F
class UploadStressTests(unittest.TestCase):
 def request(self,out,size=10,data=b'partial',**headers):
  h=SimpleNamespace(headers={'Content-Length':str(size),'X-Folder':out.name,'X-Row':'one','X-Filename':'take.wav',**headers},rfile=io.BytesIO(data))
  h.send=lambda status,result:setattr(h,'result',(status,result))
  return h
 def invoke(self,out,h,**patches):
  with patch.object(S,'job_folder',return_value=out),patch.object(S,'is_job',return_value=True),patch.object(T,'load',return_value={'itens':[{'id':'one'}]}),patch.object(PR,'moving',return_value=patches.get('moving',False)),patch.dict(M.JOBS,patches.get('jobs',{}),clear=True),patch.object(API.AUTO,'active',return_value=False):
   API.handle(h,'/fatiador/trocas/audio-upload',out.parent)
  return h.result
 def test_interrupted_upload_never_queues_and_leaves_no_file(self):
  with tempfile.TemporaryDirectory() as d,patch.object(M,'submit') as submit:
   out=Path(d);status,result=self.invoke(out,self.request(out));self.assertEqual(status,400);submit.assert_not_called();self.assertFalse(list(out.rglob('*.*')))
 def test_busy_or_moving_project_never_consumes_audio(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)
   for args in [{'moving':True},{'jobs':{'j':SimpleNamespace(kind='vozes',status='executando',params={'out':str(out)})}}]:
    h=self.request(out);self.assertEqual(self.invoke(out,h,**args)[0],400);self.assertEqual(h.rfile.tell(),0)
 def test_simultaneous_upload_is_rejected_without_clearing_the_other_lease(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d);key=str(out.resolve());API._UPLOADS.add(key)
   try:
    h=self.request(out);self.assertEqual(self.invoke(out,h)[0],400);self.assertEqual(h.rfile.tell(),0);self.assertIn(key,API._UPLOADS)
   finally:API._UPLOADS.discard(key)
 def test_queue_failure_cleans_new_upload(self):
  with tempfile.TemporaryDirectory() as d,patch.object(M,'submit',side_effect=ValueError('Fila indisponível')):
   out=Path(d);self.assertEqual(self.invoke(out,self.request(out,3,b'123'))[0],400);self.assertFalse(list(out.rglob('*.wav')))
 def test_rejected_decoding_keeps_old_record_and_cleans_upload(self):
  with tempfile.TemporaryDirectory() as d,patch.object(M,'submit') as submit,patch.object(T,'record_audio') as record:
   out=Path(d);submit.return_value=SimpleNamespace(to_dict=lambda:{'id':'job'})
   self.assertEqual(self.invoke(out,self.request(out,3,b'123'))[0],200)
   fn=submit.call_args.args[2]
   with patch.object(T,'fit',side_effect=ValueError('Áudio inválido')):
    with self.assertRaises(ValueError):fn(None,str(out))
   record.assert_not_called();self.assertFalse(list(out.rglob('*.wav')))
class PropertyStressTests(unittest.TestCase):
 def test_500_three_kit_currency_requests_and_inconsistent_totals(self):
  rng=random.Random(880)
  for i in range(500):
   units=[rng.randrange(100,10000) for _ in range(3)];totals=[u*q for u,q in zip(units,(1,3,6))]
   def prices(values):return '/'.join('$'+format(Decimal(v)/100,'.2f') for v in values)
   demand='2/3/6 para 1/3/6 ('+prices(units)+' - '+prices(totals)+')'
   cfg=O.config({'demanda':demand});self.assertEqual([Decimal(k['total']) for k in cfg['kits']],[Decimal(v)/100 for v in totals])
   totals[1]+=1
   with self.assertRaises(ValueError):O.config({'demanda':'2/3/6 para 1/3/6 ('+prices(units)+' - '+prices(totals)+')'})
 def test_2000_final_intervals_keep_all_source_frames_across_audio_closures(self):
  rng=random.Random(29)
  for _ in range(2000):
   cuts=[];cursor=0
   for _ in range(rng.randrange(1,12)):
    a=cursor+rng.randrange(1,70);b=a+rng.randrange(1,10);cuts.append((a,b));cursor=b
   start=rng.randrange(0,600);end=start+rng.randrange(1,300);parts=F.expand(start,end,cuts)
   self.assertEqual(sum(b-a for a,b,offset in parts),end-start)
   self.assertEqual(parts[0][2],0)
   for a,b,offset in parts:self.assertEqual(F.position(a,cuts),start+offset);self.assertEqual(F.position(b,cuts),start+offset+b-a)
