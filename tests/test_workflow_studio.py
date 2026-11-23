import copy,io,json,shutil,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
import test_trocas_completas as base
from plataforma import trocas as T,visuais as V,workflow as W,ml_core as M,montagem as MT

class StudioTests(unittest.TestCase):
 setUpClass=classmethod(base.FlowTests.setUpClass.__func__)
 tearDownClass=classmethod(base.FlowTests.tearDownClass.__func__)
 setUp=base.FlowTests.setUp
 tearDown=base.FlowTests.tearDown
 job=base.FlowTests.job
 approve=base.FlowTests.approve
 add_audio=base.FlowTests.add_audio
 def test_takes_cannot_be_reached_by_approving_texts_only(self):
  self.assertFalse(W.state(self.out)['takes_liberados']);self.approve();self.assertEqual(W.state(self.out)['estado'],'pronto_para_gerar')
  with self.assertRaisesRegex(ValueError,'áudio'):W.require_takes(self.out)
  self.add_audio();self.assertTrue(W.require_takes(self.out)['takes_liberados']);p=T.load(self.out);r=p['itens'][0];T.save(self.out,[{'id':r['id'],'novo':'Modified text.'}]);self.assertFalse(W.state(self.out)['takes_liberados'])
 def test_missing_audio_file_revokes_readiness(self):
  self.add_audio();p=T.load(self.out);(self.out/p['itens'][0]['audio']['fit']).unlink();self.assertFalse(W.state(self.out)['takes_liberados'])
 def test_unapproved_audio_goes_to_conference(self):
  self.add_audio();p=T.load(self.out);p['itens'][0]['audio']['aprovado']=False;T.write(T.plan_path(self.out),p);self.assertEqual(W.state(self.out)['estado'],'aguardando_conferencia')
 def test_complexity_requires_both_conditions_and_exact_boundary(self):
  p=T.load(self.out);p['forma']={'ativo':True};T.write(T.plan_path(self.out),p)
  raw={'words':[{'text':'Oldbrand','start':i*100,'end':i*100+90} for i in range(60)]};(self.out/'transcricao_bruta.json').write_text(json.dumps(raw));self.assertEqual(W.state(self.out)['resumo']['complexidade'],'Simples')
  raw['words'].append({'text':'Oldbrand','start':6000,'end':6100});(self.out/'transcricao_bruta.json').write_text(json.dumps(raw));r=W.state(self.out)['resumo'];self.assertEqual(r['mencoes'],61);self.assertEqual(r['frases'],2);self.assertEqual(r['complexidade'],'Complexa')
  p['forma']={'ativo':False};T.write(T.plan_path(self.out),p);self.assertEqual(W.state(self.out)['resumo']['complexidade'],'Simples')
 def setup_full(self,duration=2,window=(1000,3000)):
  self.add_audio();folder=self.out/'materiais';folder.mkdir();video=folder/'1 POTE - V.mp4'
  subprocess.run([M.FFMPEG,'-y','-v','error','-f','lavfi','-i',f'testsrc2=s=90x160:r=24:d={duration}','-an','-c:v','libx264',str(video)],check=True)
  V.scan(self.job(),self.out,folder);V.add(self.out,{'start':window[0],'end':window[1],'kit':1});V.save(self.out,{'incluir':True});return video
 def test_xml_references_full_original_with_source_rate_and_scale(self):
  video=self.setup_full();s=V.schedule(self.out,seed=1);self.assertFalse(s['issues'])
  with patch.object(M,'run_proc') as render:V.prepare(self.job(),self.out);render.assert_not_called()
  prepared=V.valid_prepared(self.out);self.assertEqual(Path(prepared[0]['file']),video.resolve());self.assertTrue(prepared[0]['take_completo'])
  xml=T.export_xml(self.out);c=ET.parse(self.out/xml['xml']).findall('.//sequence/media/video/track')[1].find('clipitem');self.assertEqual(c.findtext('file/pathurl'),video.resolve().as_uri());self.assertEqual(c.findtext('in'),'0');self.assertEqual(c.findtext('out'),'48');self.assertEqual(c.findtext('rate/timebase'),'24');self.assertIsNotNone(c.find('filter/effect/parameter'))
  self.assertFalse(list((self.out/'trocas/visuais').glob('prontos_*')))
 def test_duration_conflict_never_silently_cuts_or_freezes(self):
  video=self.setup_full(window=(1000,1500));s=V.schedule(self.out,seed=1);self.assertTrue(s['issues']);self.assertFalse(s['segments'])
  V.save(self.out,{'ajustar_janela':True});s=V.schedule(self.out,seed=1);self.assertFalse(s['issues']);self.assertEqual(s['segments'][0]['end_frame']-s['segments'][0]['start_frame'],50)
 def test_full_mode_filters_images(self):
  self.setup_full();s=V.load(self.out);s['assets'][0]['kind']='imagem';V.write(self.out,s);s=V.schedule(self.out);self.assertTrue(s['issues']);self.assertFalse(s['segments'])
 def test_real_preview_keeps_video_motion(self):
  self.setup_full();V.schedule(self.out);V.prepare(self.job(),self.out);result=T.preview_job(self.job(),self.out);path=self.out/result['arquivo']
  def frame(at):return subprocess.check_output([M.FFMPEG,'-v','error','-ss',str(at),'-i',str(path),'-frames:v','1','-vf','scale=32:32','-f','rawvideo','-pix_fmt','rgb24','-'])
  self.assertNotEqual(frame(1.2),frame(2.2))
 def test_api_guard_blocks_task_submission(self):
  from plataforma import trocas_api,armazenamento as S
  payload=json.dumps({'folder':self.out.name}).encode()
  class H:
   headers={'Content-Length':str(len(payload))};rfile=io.BytesIO(payload)
   def send(self,status,data):self.status=status;self.data=data
  h=H()
  with patch.object(S,'job_folder',return_value=self.out),patch.object(S,'is_job',return_value=True),patch.object(M,'submit') as submit:
   self.assertTrue(trocas_api.handle(h,'/fatiador/trocas/visual-automatico',self.out.parent));self.assertEqual(h.status,400);submit.assert_not_called()
 def test_existing_approved_audio_does_not_allow_takes_during_regeneration(self):
  self.add_audio();job=M.Job('vozes','Gerar',None,out=str(self.out));job.status='executando'
  with patch.object(M,'JOBS',{job.id:job}):
   self.assertEqual(W.state(self.out)['estado'],'gerando');self.assertFalse(W.state(self.out)['takes_liberados'])
 def test_expanded_audio_keeps_full_take_moving_through_extra_time(self):
  video=self.setup_full(duration=4);p=T.load(self.out);p['modo_duracao']='expandir';T.write(T.plan_path(self.out),p)
  raw=self.out/'long.wav';subprocess.run([M.FFMPEG,'-y','-v','error','-f','lavfi','-i','sine=frequency=900:duration=4','-c:a','pcm_s16le',str(raw)],check=True)
  for index,row in enumerate(p['itens']):
   a=T.fit(self.job(),self.out,row,raw if index==0 else self.out/row['audio']['raw']);T.record_audio(self.out,row['id'],a);T.approve_audio(self.out,row['id'],a['texto_hash'])
  state=V.schedule(self.out);self.assertFalse(state['issues']);V.prepare(self.job(),self.out);result=T.export_xml(self.out)
  v2=ET.parse(self.out/result['xml']).findall('.//sequence/media/video/track')[1].findall('clipitem');self.assertEqual(len(v2),1);self.assertEqual(v2[0].findtext('file/pathurl'),video.resolve().as_uri());self.assertEqual(v2[0].findtext('in'),'0');self.assertEqual(v2[0].findtext('out'),'96');self.assertEqual(v2[0].findtext('end'),'125')
  preview=T.preview_job(self.job(),self.out);path=self.out/preview['arquivo']
  def frame(at):return subprocess.check_output([M.FFMPEG,'-v','error','-ss',str(at),'-i',str(path),'-frames:v','1','-vf','scale=32:32','-f','rawvideo','-pix_fmt','rgb24','-'])
  self.assertNotEqual(frame(3.2),frame(4.2))
 def test_local_tail_batch_reuses_results_and_does_not_approve(self):
  self.add_audio();p=T.load(self.out)
  for r in p['itens']:r['audio']['aprovado']=False
  T.write(T.plan_path(self.out),p)
  from plataforma import editorial as E,validacao as VAL,vozes
  words=[{'w':w,'s':i*.2,'e':i*.2+.15} for i,w in enumerate('Try Newbrand today today'.split())]
  with patch.object(VAL,'transcribe',return_value={'words':words}) as transcribe,patch.object(vozes,'speech') as paid:
   result=E.analyze_batch(self.job(),self.out);self.assertEqual(transcribe.call_count,2);self.assertTrue(all(r['alertas'] for r in result['resultados']));E.analyze_batch(self.job(),self.out);self.assertEqual(transcribe.call_count,2);paid.assert_not_called()
  self.assertTrue(all(not r['audio']['aprovado'] for r in T.load(self.out)['itens']))

 def test_fit_mode_uses_original_without_render_or_freeze(self):
  video=self.setup_full(window=(1000,1500));V.save(self.out,{'modo_takes':'encaixar'});s=V.schedule(self.out,seed=1)
  self.assertFalse(s['issues']);self.assertEqual(len(s['segments']),1);self.assertFalse(s['segments'][0]['take_completo']);self.assertEqual(s['segments'][0]['end_frame']-s['segments'][0]['start_frame'],13)
  with patch.object(M,'run_proc') as render:V.prepare(self.job(),self.out);render.assert_not_called()
  xml=T.export_xml(self.out);c=ET.parse(self.out/xml['xml']).findall('.//sequence/media/video/track')[1].find('clipitem');self.assertEqual(c.findtext('file/pathurl'),video.resolve().as_uri());self.assertEqual(c.findtext('in'),'0');self.assertEqual(c.findtext('out'),'12')
 def test_default_kit_is_explicit_and_never_overrides_named_quantity(self):
  self.setup_full();s=V.load(self.out);s['cobrir_falas']=True;V.write(self.out,s);V.save(self.out,{'modo_takes':'encaixar'});s=V.schedule(self.out,seed=1);self.assertTrue(s['issues']);self.assertTrue(all(i['code']=='variedade' for i in s['issues']))
  V.save(self.out,{'kit_sem_quantidade':'1'});s=V.schedule(self.out,seed=1)
  # Two windows need distinct materials to avoid immediate repeats.
  self.assertNotIn('generico',[i['code'] for i in s['issues']]);self.assertTrue(any(i['code']=='variedade' for i in s['issues']))
  V.add(self.out,{'start':5000,'end':7000,'kit':3});s=V.schedule(self.out,seed=1);self.assertTrue(any(i['code']=='kit' and i['kit']==3 for i in s['issues']))
 def test_fit_mode_can_use_more_than_six_seconds_of_an_original(self):
  video=self.setup_full(duration=7,window=(0,7000));V.save(self.out,{'modo_takes':'encaixar'});s=V.schedule(self.out);self.assertFalse(s['issues']);self.assertEqual(s['segments'][0]['end_frame'],175);V.prepare(self.job(),self.out)
  before=V.signature(V.load(self.out));audio=T.plan_path(self.out).read_bytes();V.save(self.out,{'kit_sem_quantidade':1});self.assertNotEqual(before,V.signature(V.load(self.out)));self.assertIsNone(V.load(self.out)['prepared']);self.assertEqual(audio,T.plan_path(self.out).read_bytes())
 def test_default_kit_rejects_invalid_values(self):
  self.setup_full()
  for bad in (True,-1,'1.5',100,'abc'):
   with self.subTest(bad=bad),self.assertRaises(ValueError):V.save(self.out,{'kit_sem_quantidade':bad})

 def test_unquantified_speech_draws_product_videos_across_kits(self):
  self.setup_full(duration=4);s=V.load(self.out);s['cobrir_falas']=True;s['modo_takes']='encaixar'
  original=s['assets'][0]
  for kit in (3,6):
   asset=copy.deepcopy(original);asset.update(id='product_'+str(kit),kit=kit);s['assets'].append(asset)
  support=copy.deepcopy(original);support.update(id='support',kit=None,uso='apoio');s['assets'].append(support)
  s['mentions']=[];V.write(self.out,s);s=V.schedule(self.out,seed=4)
  self.assertFalse(s['issues']);self.assertEqual(len(s['segments']),2);self.assertTrue(all(r['sorteio_produto'] for r in s['segments']));self.assertNotEqual(s['segments'][0]['asset'],s['segments'][1]['asset']);self.assertNotIn('support',[r['asset'] for r in s['segments']])
  chosen=s['segments'][0];alternative=next(a for a in s['assets'] if a['uso']=='produto' and a['id'] not in {r['asset'] for r in s['segments']})
  changed=V.replace_segment(self.out,{'index':0,'asset':alternative['id']});self.assertEqual(changed['segments'][0]['kit'],alternative['kit']);self.assertTrue(changed['segments'][0]['sorteio_produto'])
 def test_unknown_speech_does_not_use_support_only(self):
  self.setup_full();s=V.load(self.out);s['cobrir_falas']=True;s['modo_takes']='encaixar';s['mentions']=[]
  for a in s['assets']:a['uso']='apoio'
  V.write(self.out,s);s=V.schedule(self.out);self.assertTrue(all(i['code']=='generico' for i in s['issues']));self.assertFalse(s['segments'])

 def test_usage_before_first_product_mention_is_marked_without_pots(self):
  self.setup_full(duration=4);raw=json.loads((self.out/'transcricao_bruta.json').read_text());raw['words']=[{'text':'Apply the patch.','start':1000,'end':1200,'speaker':'A'},{'text':'Oldbrand','start':5000,'end':5200,'speaker':'B'}];(self.out/'transcricao_bruta.json').write_text(json.dumps(raw))
  state=V.load(self.out);state.update(cobrir_falas=True,modo_takes='encaixar',mentions=[],basis=V.basis(self.out));V.write(self.out,state);s=V.schedule(self.out,seed=1)
  self.assertEqual(s['coverage_policy']['primeira_mencao_ms'],5000);self.assertEqual(len(s['coverage_markers']),1);self.assertEqual(s['coverage_markers'][0]['start'],1000);self.assertTrue(all(r['start_frame']>=125 for r in s['segments']));self.assertFalse(s['issues'])
  V.prepare(self.job(),self.out);export=T.export_xml(self.out);markers=ET.parse(self.out/export['xml']).findall('.//sequence/marker');self.assertTrue(any('ADAPTAR MODO DE USO' in m.findtext('name') for m in markers))
 def test_straddling_window_is_clipped_and_aliases_set_first_mention(self):
  self.setup_full();p=T.load(self.out);p['produto_aliases']='Old Brand';T.write(T.plan_path(self.out),p);raw={'words':[{'text':'Old','start':2000,'end':2100},{'text':'Brand','start':2110,'end':2200}]};(self.out/'transcricao_bruta.json').write_text(json.dumps(raw))
  s=V.load(self.out);s.update(cobrir_falas=True,modo_takes='encaixar',basis=V.basis(self.out));V.write(self.out,s);s=V.schedule(self.out,seed=2);self.assertEqual(s['coverage_markers'][0]['end'],2000);self.assertTrue(all(r['start_frame']>=50 for r in s['segments']))
 def test_unknown_product_cannot_be_exported_as_completed_takes(self):
  self.setup_full();(self.out/'transcricao_bruta.json').write_text(json.dumps({'words':[{'text':'Apply patch.','start':1000,'end':1200}]}));s=V.load(self.out);s.update(cobrir_falas=True,modo_takes='encaixar',mentions=[],basis=V.basis(self.out));V.write(self.out,s);s=V.schedule(self.out)
  self.assertIsNone(s['coverage_policy']['primeira_mencao_ms']);self.assertFalse(s['segments']);self.assertEqual(len(s['coverage_markers']),2);V.prepare(self.job(),self.out)
  with self.assertRaisesRegex(ValueError,'primeira menção'):V.valid_prepared(self.out)
  with self.assertRaisesRegex(ValueError,'primeira menção'):T.export_xml(self.out)

 def test_visual_margins_cover_before_after_with_no_overlapping_takes(self):
  from unittest.mock import patch
  self.setup_full();V.scan(self.job(),self.out,Path(__file__).parent/'fixtures/MATERIAIS_POTES_TESTE');state=V.load(self.out);state.update(cobrir_falas=True,modo_takes='encaixar',mentions=[],basis=V.basis(self.out));V.write(self.out,state)
  with patch('plataforma.armazenamento.visual_margin_ms',return_value=1000):
   result=V.schedule(self.out,seed=3)
   self.assertFalse(result['issues']);segments=result['segments'];self.assertTrue(segments)
   rows=V.covered_mentions(self.out,result);first=V.first_product_mention(self.out)
   windows=V.audio_windows(self.out);duration=round(T.probe(T.source(self.out))['duration']*1000)
   for _,a,b in windows:
    if b<=first:continue
    lo=max(first,a-1000);hi=min(duration,b+1000)
    for frame in range(round(lo/1000*25),round(hi/1000*25)):
     self.assertTrue(any(v['start_frame']<=frame<v['end_frame'] for v in segments),frame)
   for a,b in zip(segments,segments[1:]):self.assertLessEqual(a['end_frame'],b['start_frame']);self.assertNotEqual(a['asset'],b['asset'])
   V.prepare(self.job(),self.out);xml=T.export_xml(self.out);tree=ET.parse(self.out/xml['xml']);v2=tree.findall('.//sequence/media/video/track')[1].findall('clipitem')
   self.assertEqual([(int(c.findtext('start')),int(c.findtext('end'))) for c in v2],[(v['start_frame'],v['end_frame']) for v in segments])
  with patch('plataforma.armazenamento.visual_margin_ms',return_value=1500):
   with self.assertRaisesRegex(ValueError,'Prepare os takes novamente'):V.valid_prepared(self.out)
