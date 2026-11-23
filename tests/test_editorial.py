import copy,json,shutil,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
import test_trocas_completas as base
from plataforma import editorial as E,trocas as T,vozes as V,visuais as VIS,ml_core as M

class EditorialTests(unittest.TestCase):
    setUpClass=classmethod(base.FlowTests.setUpClass.__func__)
    tearDownClass=classmethod(base.FlowTests.tearDownClass.__func__)
    setUp=base.FlowTests.setUp
    tearDown=base.FlowTests.tearDown
    job=base.FlowTests.job
    approve=base.FlowTests.approve
    add_audio=base.FlowTests.add_audio

    def test_missing_and_conflicting_speakers_never_default_to_A(self):
        p={'start':100,'end':500,'speaker':'A'}
        for words in ([{'start':100,'end':500,'text':'X'}],[{'start':100,'end':200,'speaker':'A'},{'start':200,'end':500,'speaker':'B'}],[{'start':100,'end':500,'speaker':'B'}]):
            self.assertEqual(E.speaker_info(p,{'words':words})[:2],(E.UNKNOWN,True))
        plan=T.load(self.out);plan['itens'][0].update(speaker=E.UNKNOWN,speaker_pendente=True,aprovado=True);T.write(T.plan_path(self.out),plan)
        with self.assertRaisesRegex(ValueError,'speaker'):T.approved(plan)
        confirmed=E.assign(self.out,{'ids':[plan['itens'][0]['id']],'speaker':'DEPO_01'})
        self.assertEqual(T.approved(confirmed)[0]['speaker'],'DEPO_01')

    def test_pronunciation_changes_only_affected_audio_and_not_official_text(self):
        self.add_audio();plan=T.load(self.out);plan['itens'][1]['novo']='This formula works.';plan['itens'][1]['audio']['texto_hash']=T.digest([plan['itens'][1]['novo'],'B']);T.write(T.plan_path(self.out),plan);old=copy.deepcopy(plan['itens'][1]['audio'])
        result=E.settings(self.out,{'pronuncia':'Niu brand','aliases':'Old brend'})
        self.assertEqual(result['falas_afetadas'],[plan['itens'][0]['id']]);self.assertEqual(result['plano']['itens'][1]['audio'],old)
        self.assertEqual(result['plano']['itens'][0]['novo'],'Newbrand works.');self.assertEqual(len(result['plano']['itens'][0]['historico_audio']),1)

    def test_generation_sends_pronunciation_without_distant_context(self):
        self.approve();E.settings(self.out,{'pronuncia':'Niu brand'});options={'provider':'elevenlabs','model':'eleven_multilingual_v2','voices':{'A':'voice_A','B':'voice_B'}}
        with patch.object(V,'speech',return_value=self.tts.read_bytes()) as calls:
            r=V.generate(self.job(),self.out,options,'TEST_ONLY')
        self.assertTrue(all('erro' not in a for a in r['resultados']));self.assertEqual(calls.call_args_list[0].args[3],'Niu brand works.');self.assertEqual(len(calls.call_args_list[0].args),5)
        self.assertEqual(T.load(self.out)['itens'][0]['novo'],'Newbrand works.')

    def test_visual_only_suggestions_are_unselected_and_do_not_generate_audio(self):
        raw={'words':[{'text':t,'start':1000+i*100,'end':1090+i*100} for i,t in enumerate('This formula comes in bottles.'.split())]}
        rows=E.visual_references(raw,[]);self.assertEqual(len(rows),1);self.assertFalse(rows[0]['selected']);self.assertTrue(rows[0]['somente_visual']);self.assertIsNone(rows[0]['kit'])
        state=VIS.load(self.out);state['mentions']=rows;VIS.write(self.out,state)
        VIS.save(self.out,{'mentions':[dict(rows[0],selected=True)]})
        self.assertTrue(VIS.load(self.out)['mentions'][0]['selected']);self.assertFalse(any(r['aprovado'] for r in T.load(self.out)['itens']))

    def test_balance_and_no_consecutive_repetition(self):
        state=VIS.load(self.out);state.update(modo_takes='recortes',assets=[{'id':str(i),'name':f'{i}.mp4','kit':1,'kind':'imagem','uso':'produto'} for i in range(4)],mentions=[{'id':'test','start':0,'end':8000,'kit':1,'selected':True}],basis=VIS.basis(self.out),max_clip_s=.5)
        # API accepts 1..30; fixture uses 1 second and 8 slots.
        state['max_clip_s']=1;VIS.write(self.out,state);r=VIS.schedule(self.out,seed=42);d=E.distribution(r)
        self.assertFalse(d['repeticoes_consecutivas']);counts=[a['vezes'] for a in d['materiais']];self.assertEqual(counts,[2,2,2,2])

    def test_tail_repetition_is_suggestion_not_natural_long_audio_error(self):
        words=[{'w':w,'s':i*.3,'e':i*.3+.25} for i,w in enumerate('Get Newbrand today today'.split())]
        self.assertEqual(E.repetitions(words,'Get Newbrand today.')[0]['texto'],'today')
        self.assertFalse(E.repetitions(words,'Get Newbrand today today.'))
        self.assertFalse(E.repetitions(words[:-1],'Get Newbrand today.'))

    def test_trim_is_local_retains_raw_and_only_invalidates_one_approval(self):
        self.add_audio();before=T.load(self.out);row=before['itens'][0];raw=self.out/row['audio']['raw'];original=raw.read_bytes()
        with patch.object(V,'speech') as paid:
            result=E.trim_job(self.job(),self.out,row['id'],0,1200);paid.assert_not_called()
        after=T.load(self.out);self.assertEqual(raw.read_bytes(),original);self.assertEqual(after['itens'][1]['audio'],before['itens'][1]['audio']);self.assertFalse(result['audio']['aprovado']);self.assertEqual(result['audio']['raw'],row['audio']['raw']);self.assertAlmostEqual(T.probe(self.out/result['audio']['fonte_preparo'])['duration'],1.2,delta=.03)
        E.trim_job(self.job(),self.out,row['id'],0,None);self.assertEqual(raw.read_bytes(),original)

    def test_soundtrack_A4_preview_mix_and_signature(self):
        self.add_audio();music=self.out/'music.wav';subprocess.run([M.FFMPEG,'-y','-v','error','-f','lavfi','-i','sine=frequency=550:duration=1','-c:a','pcm_s16le',str(music)],check=True)
        plan=T.load(self.out);plan['trilha']={'arquivo':'music.wav'};T.write(T.plan_path(self.out),plan);signature=T.preview_signature(self.out)
        E.soundtrack(self.out,{'modo':'separada','ganho_db':-24,'repetir':True});self.assertNotEqual(signature,T.preview_signature(self.out))
        result=T.export_xml(self.out);tracks=ET.parse(self.out/result['xml']).findall('.//sequence/media/audio/track');self.assertEqual(len(tracks),4);self.assertEqual(len(tracks[3].findall('clipitem')),8);self.assertAlmostEqual(float(tracks[3].findtext('.//parameter/value')),10**(-24/20))
        mixed=T.mix(self.job(),self.out);self.assertAlmostEqual(T.probe(mixed)['duration'],8,delta=.1)
        preview=T.preview_job(self.job(),self.out);self.assertTrue((self.out/preview['arquivo']).is_file())

    def test_preflight_reports_missing_audio_and_undefined_music(self):
        self.approve();r=E.preflight(self.out);self.assertEqual(r['geradas'],0);self.assertEqual({a['tipo'] for a in r['alertas']},{'audio','aprovacao','trilha'});self.assertFalse(r['entrega'])

    def test_sample_requires_consent_before_any_paid_call(self):
        with patch.object(V,'speech') as paid:
            with self.assertRaisesRegex(ValueError,'créditos'):V.sample(self.out,{'provider':'elevenlabs','model':'eleven_multilingual_v2','voice':'existing'})
            paid.assert_not_called()

    def test_full_audit_uses_assembled_audio_and_aliases(self):
        self.add_audio();E.settings(self.out,{'aliases':'Old brend'})
        from plataforma import validacao
        with patch.object(validacao,'transcribe',return_value={'words':[{'w':'Old','s':.5,'e':.7},{'w':'brend','s':.7,'e':.9}]}) as transcribe:
            result=T.review_job(self.job(),self.out)
        self.assertTrue(result['resquicios']);self.assertTrue(Path(transcribe.call_args.args[1]).is_file());self.assertIn('integral',result['cobertura'])
        E.soundtrack(self.out,{'modo':'sem'});self.assertIsNone(T.load(self.out)['revisao'])

    def test_diagnostics_do_not_invalidate_montage(self):
        self.add_audio();stamp=T.preview_signature(self.out);plan=T.load(self.out);plan['itens'][0]['audio']['analise']={'texto_reconhecido':'test','alertas':[]};T.write(T.plan_path(self.out),plan)
        self.assertEqual(T.preview_signature(self.out),stamp)
