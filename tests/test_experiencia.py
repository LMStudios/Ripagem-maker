import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from plataforma import experiencia as X,trocas as T,armazenamento as S,identidade_entrega as ID
class ExperienceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.out=Path(self.temp.name)/'Trabalho com espaços';self.out.mkdir();self.cfg=patch.object(S,'CONFIG',Path(self.temp.name)/'settings.json');self.cfg.start();self.addCleanup(self.cfg.stop)
  self.plan={'produto':'Old','produto_novo':'New','speakers':['A'],'itens':[{'id':'one','speaker':'A','aprovado':True,'inicio_ms':0,'fim_ms':1000,'novo':'New'}],'samples':{},'fps':30,'duracao_s':30}
  T.write(T.plan_path(self.out),self.plan)
 def config(self):return {'provider':'elevenlabs','model':'eleven_multilingual_v2','voices':{'A':'authorized-id'},'autoriza_envio':True,'autoriza_clonagem':True,'excluir_clones':False,'autofit':True,'key':'DO-NOT-PERSIST'}
 def test_preferences_persist_without_keys_and_scope_changes_revoke_consent(self):
  X.preferences(self.out,self.config());self.assertTrue(X.preferences(self.out)['autoriza_clonagem']);self.assertNotIn('DO-NOT-PERSIST',T.plan_path(self.out).read_text()+S.CONFIG.read_text())
  p=T.load(self.out);p['itens'][0]['speaker']='B';T.write(T.plan_path(self.out),p);self.assertFalse(X.preferences(self.out)['autoriza_clonagem'])
 def test_changed_sample_requires_new_authorization(self):
  f=self.out/'sample.mp3';f.write_bytes(b'first');p=T.load(self.out);p['samples']={'A':{'arquivo':'sample.mp3'}};T.write(T.plan_path(self.out),p);c=self.config();c['voices']={};X.preferences(self.out,c);self.assertTrue(X.preferences(self.out)['autoriza_clonagem']);f.write_bytes(b'changed');self.assertFalse(X.preferences(self.out)['autoriza_envio'])
 def test_replacing_sample_preserves_previous_file_and_requires_fresh_consent(self):
  from types import SimpleNamespace
  old=self.out/'sample.mp3';old.write_bytes(b'previous')
  incoming=self.out/'uploaded.wav';incoming.write_bytes(b'new')
  plan=T.load(self.out);plan['samples']={'A':{'arquivo':'sample.mp3','duracao_s':20}}
  plan['preferencias_voz']=self.config();T.write(T.plan_path(self.out),plan)
  job=SimpleNamespace(cancel=False,step='')
  def convert(job,cmd):Path(cmd[-1]).write_bytes(b'converted')
  with patch.object(T,'probe',return_value={'duration':30}),patch.object(T.M,'run_proc',side_effect=convert):
   result=T.replace_sample_job(job,self.out,'A',incoming,'outra voz.wav')
  saved=T.load(self.out)
  self.assertEqual((self.out/result['amostra']['arquivo']).read_bytes(),b'converted')
  self.assertEqual(old.read_bytes(),b'previous');self.assertFalse(incoming.exists())
  self.assertFalse(saved['preferencias_voz']['autoriza_clonagem'])
  self.assertNotIn('A',saved['preferencias_voz']['voices'])
  self.assertEqual(saved['itens'],plan['itens'])
 def test_invalid_sample_keeps_current_mapping_and_sample(self):
  from types import SimpleNamespace
  incoming=self.out/'uploaded.wav';incoming.write_bytes(b'invalid')
  before=T.plan_path(self.out).read_bytes()
  with patch.object(T,'probe',return_value={'duration':121}),self.assertRaisesRegex(ValueError,'2 minutos'):
   T.replace_sample_job(SimpleNamespace(cancel=False),self.out,'A',incoming,'long.wav')
  self.assertEqual(T.plan_path(self.out).read_bytes(),before);self.assertFalse(incoming.exists())

 def test_new_work_reuses_model_but_not_consent_or_speaker_voice_ids(self):
  X.preferences(self.out,self.config());p=T.load(self.out);p.pop('preferencias_voz');T.write(T.plan_path(self.out),p);d=X.preferences(self.out);self.assertEqual(d['model'],'eleven_multilingual_v2');self.assertFalse(d['autoriza_clonagem']);self.assertNotIn('voices',d)
 def test_samples_reused_and_no_duplicate_job(self):
  f=self.out/'sample.mp3';f.write_bytes(b'first');p=T.load(self.out);p['samples']={'A':{'arquivo':'sample.mp3'}};T.write(T.plan_path(self.out),p)
  with patch('plataforma.ml_core.submit') as submit:self.assertTrue(X.ensure_samples(self.out)['pronto']);submit.assert_not_called()
 def test_pitch_cached_and_invalidated_on_transcript_change(self):
  words=[{'text':w,'start':10000+i*500,'end':10400+i*500} for i,w in enumerate('Get six bottles for only 29 dollars per bottle.'.split())];raw=self.out/'transcricao_bruta.json';raw.write_text(json.dumps({'words':words}))
  first=X.cached_pitch(self.out);self.assertIsNotNone(first['pitch'])
  with patch('plataforma.validacao.analyze',side_effect=AssertionError('Repeated analysis')):self.assertEqual(first,X.cached_pitch(self.out))
  raw.write_text(json.dumps({'words':[]}));self.assertIsNone(X.cached_pitch(self.out)['pitch'])
 def test_pitch_mapping_uses_ripple_and_does_not_guess_inside_replaced_speech(self):
  p=copy.deepcopy(self.plan);p['pitch_transcricao']={'pitch':{'tempo':10,'valor':'29','status':'contexto_6_potes'}};p['itens'][0]['audio']={'fit':'new.wav'};(self.out/'new.wav').write_bytes(b'test')
  with patch('plataforma.montagem.edits',return_value=[{'a':0,'b':30,'start':0,'end':60,'extra':30}]),patch('plataforma.fechamento.windows',return_value=[(0,6)]):
   self.assertAlmostEqual(X.mapped_pitch(p,self.out)['tempo'],10.8);self.assertEqual(ID.identity(p,self.out)['origem_pitch'],'transcricao_6_potes_mapeado')
  p['pitch_transcricao']['pitch']['tempo']=.5;self.assertTrue(X.mapped_pitch(p,self.out)['confirmar'])
 def test_first_run_requires_folder_and_failed_write_does_not_save(self):
  self.assertFalse(S.status()['configuracao_inicial']);target=Path(self.temp.name)/'Destino';S.save(str(target));self.assertTrue(S.status()['pasta_disponivel']);before=S.CONFIG.read_bytes()
  with patch('plataforma.armazenamento.tempfile.TemporaryFile',side_effect=PermissionError('Sem acesso')):
   with self.assertRaises(PermissionError):S.save(str(Path(self.temp.name)/'Proibida'))
  self.assertEqual(before,S.CONFIG.read_bytes())
