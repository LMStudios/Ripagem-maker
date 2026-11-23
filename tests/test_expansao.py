import json,subprocess,unittest
from pathlib import Path
import xml.etree.ElementTree as ET
import test_trocas_completas as base
from plataforma import trocas as T,montagem as MT,ml_core as M,visuais as VIS

class ExpandTests(unittest.TestCase):
 setUpClass=classmethod(base.FlowTests.setUpClass.__func__)
 tearDownClass=classmethod(base.FlowTests.tearDownClass.__func__)
 setUp=base.FlowTests.setUp
 tearDown=base.FlowTests.tearDown
 job=base.FlowTests.job
 def audio(self):
  p=T.load(self.out);p['modo_duracao']='expandir';T.write(T.plan_path(self.out),p)
  T.save(self.out,[{'id':r['id'],'aprovado':True} for r in p['itens']]);folder=self.out/'trocas/raw';folder.mkdir()
  for i,row in enumerate(T.load(self.out)['itens']):
   path=folder/f'{i}.wav';subprocess.run([M.FFMPEG,'-y','-v','error','-f','lavfi','-i',f'sine=frequency={1000 if i==0 else 2000}:duration={4 if i==0 else 1}',str(path)],check=True)
   a=T.fit(self.job(),self.out,row,path);T.record_audio(self.out,row['id'],a);T.approve_audio(self.out,row['id'],a['texto_hash'])
 def test_left_margin_closes_gap_and_ripples_all_tracks(self):
  from unittest.mock import patch
  import numpy as np
  self.audio()
  with patch.object(MT,'margin_ms',return_value=200):
   result=T.export_xml(self.out);tree=ET.parse(self.out/result['xml']);tracks=tree.findall('.//sequence/media/audio/track')
   self.assertEqual(int(tracks[0].find('clipitem/end').text),20)
   self.assertEqual(int(tracks[2].find('clipitem/start').text),20)
   path=T.mix(self.job(),self.out)
   pcm=subprocess.check_output([M.FFMPEG,'-v','error','-ss','0.84','-i',str(path),'-t','0.1','-ac','1','-ar','48000','-f','f32le','-'])
   self.assertGreater(float(np.max(abs(np.frombuffer(pcm,dtype=np.float32)))),.01)
   self.assertAlmostEqual(T.probe(path)['duration'],9.6,delta=.12)
   preview=T.preview_job(self.job(),self.out);self.assertTrue((self.out/preview['arquivo']).is_file())
   for track in [tree.findall('.//sequence/media/video/track')[0],tracks[0]]:
    if track is tracks[0]:continue
    clips=track.findall('clipitem');self.assertEqual(int(clips[0].findtext('start')),0)
    for a,b in zip(clips,clips[1:]):self.assertEqual(a.findtext('end'),b.findtext('start'))
 def test_natural_audio_and_ripple_xml(self):
  self.audio();p=T.load(self.out);self.assertEqual(p['itens'][0]['audio']['status'],'espaco_ampliado');self.assertAlmostEqual(T.probe(self.out/p['itens'][0]['audio']['fit'])['duration'],4,delta=.001)
  result=T.export_xml(self.out);tree=ET.parse(self.out/result['xml']);self.assertEqual(int(tree.findtext('.//sequence/duration')),250)
  tracks=tree.findall('.//sequence/media/audio/track');self.assertEqual([(int(c.findtext('start')),int(c.findtext('end'))) for c in tracks[2].findall('clipitem')],[(25,125),(175,225)])
  self.assertTrue(all(c.findtext('enabled')=='FALSE' for c in tracks[1].findall('clipitem')))
  v=tree.findall('.//sequence/media/video/track')[0].findall('clipitem');self.assertEqual([(int(c.findtext('start')),int(c.findtext('end'))) for c in v],[(0,75),(75,125),(125,250)])
  self.assertEqual(result['acrescimo_s'],2)
 def test_mix_preserves_long_voice_and_following_audio(self):
  self.audio();path=T.mix(self.job(),self.out);self.assertAlmostEqual(T.probe(path)['duration'],10,delta=.12)
  import numpy as np
  for at,expected in [(4,1000),(6,220),(7.3,2000),(9.4,220)]:
   pcm=subprocess.check_output([M.FFMPEG,'-v','error','-ss',str(at),'-i',str(path),'-t','0.15','-ac','1','-ar','48000','-f','f32le','-']);values=np.frombuffer(pcm,dtype=np.float32);peak=np.argmax(abs(np.fft.rfft(values)))*48000/len(values);self.assertAlmostEqual(peak,expected,delta=20)
 def test_preview_with_expansion_and_visuals(self):
  self.audio();VIS.scan(self.job(),self.out,Path(__file__).parent/'fixtures/MATERIAIS_POTES_TESTE');VIS.add(self.out,{'start':2000,'end':4000,'kit':1});s=VIS.load(self.out);s['modo_takes']='recortes';s['max_clip_s']=1;s['incluir']=True;VIS.write(self.out,s);VIS.schedule(self.out,seed=7);VIS.prepare(self.job(),self.out)
  result=T.preview_job(self.job(),self.out);self.assertAlmostEqual(T.probe(self.out/result['arquivo'])['duration'],12,delta=.15)
  xml=T.export_xml(self.out);tree=ET.parse(self.out/xml['xml']);v2=tree.findall('.//sequence/media/video/track')[1].findall('clipitem');intervals=[(int(c.findtext('start')),int(c.findtext('end'))) for c in v2];self.assertEqual(intervals[0][0],50);self.assertEqual(intervals[-1][1],150)
  for first,second in zip(intervals,intervals[1:]):self.assertEqual(first[1],second[0])
 def test_duration_change_is_local_and_preserves_old_files(self):
  self.audio();old=[self.out/r['audio']['fit'] for r in T.load(self.out)['itens']];result=T.duration_job(self.job(),self.out,'expandir');self.assertTrue(result['local']);self.assertTrue(all(p.exists() for p in old));self.assertTrue(all(r['audio']['fit'] for r in T.load(self.out)['itens']))
 def test_new_work_defaults_to_expansion(self):
  T.plan_path(self.out).unlink();self.assertEqual(T.build(self.out,'Oldbrand')['modo_duracao'],'expandir')
 def test_fast_delivery_without_preview_is_explicit_and_local(self):
  from unittest.mock import patch
  from plataforma import vozes as V
  self.audio();VIS.save(self.out,{'sem_takes':True});p=T.load(self.out)
  for r in p['itens']:r['audio']['aprovado']=False
  T.write(T.plan_path(self.out),p)
  with patch.object(V,'speech') as speech,patch.object(V,'clone') as clone:
   with self.assertRaisesRegex(ValueError,'Ouça e aprove'):T.fast_delivery_job(self.job(),self.out,True)
   for row in p['itens']:T.approve_audio(self.out,row['id'],row['audio']['texto_hash'])
   result=T.fast_delivery_job(self.job(),self.out,True);speech.assert_not_called();clone.assert_not_called()
  self.assertTrue(result['sem_previa']);self.assertTrue(T.flow_state(self.out)['entrega_atual']);self.assertFalse(T.load(self.out).get('previa'));self.assertTrue(all(r['audio']['aprovado'] for r in T.load(self.out)['itens']))
 def test_fast_delivery_rejects_missing_audio_and_no_authorization(self):
  self.audio();VIS.save(self.out,{'sem_takes':True})
  with self.assertRaises(ValueError):T.fast_delivery_job(self.job(),self.out)
  p=T.load(self.out);p['itens'][1].pop('audio');T.write(T.plan_path(self.out),p)
  with self.assertRaisesRegex(ValueError,'Gere ou importe'):T.fast_delivery_job(self.job(),self.out,True)
 def test_reapplying_same_duration_keeps_files_approvals_and_delivery(self):
  from unittest.mock import patch
  self.audio();p=T.load(self.out);p['entrega']={'arquivo':'existing.xml'};T.write(T.plan_path(self.out),p);before=T.plan_path(self.out).read_bytes()
  with patch.object(T,'fit',side_effect=AssertionError('Ready audios must be reused')):
   result=T.duration_job(self.job(),self.out,'expandir')
  self.assertEqual(result['reutilizados'],2);self.assertEqual(result['resultados'],[]);self.assertEqual(T.plan_path(self.out).read_bytes(),before)
 def test_duration_only_repairs_missing_file_and_preserves_other_approval(self):
  self.audio();p=T.load(self.out);first=p['itens'][0];second=p['itens'][1];(self.out/second['audio']['fit']).unlink();original=first['audio'].copy()
  result=T.duration_job(self.job(),self.out,'expandir');after=T.load(self.out)
  self.assertEqual(result['reutilizados'],1);self.assertEqual(len(result['resultados']),1);self.assertEqual(after['itens'][0]['audio'],original);self.assertTrue((self.out/after['itens'][1]['audio']['fit']).exists())
