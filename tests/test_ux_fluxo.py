import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_trocas_completas as base
from plataforma import trocas as T,vozes as V,perfis as P

class UXTests(unittest.TestCase):
    setUpClass=classmethod(base.FlowTests.setUpClass.__func__)
    tearDownClass=classmethod(base.FlowTests.tearDownClass.__func__)
    setUp=base.FlowTests.setUp
    tearDown=base.FlowTests.tearDown
    job=base.FlowTests.job
    approve=base.FlowTests.approve
    add_audio=base.FlowTests.add_audio
    # Exercita o fluxo novo com mídia real e provedor simulado.
    def test_pending_generation_preserves_ready_and_approval(self):
        self.add_audio();p=T.load(self.out);bad=p['itens'][1];bad['audio']['fit']=None;bad['audio']['aprovado']=False;bad['audio']['status']='regenerar_longo';T.write(T.plan_path(self.out),p)
        options={'provider':'elevenlabs','model':'eleven_multilingual_v2','voices':{'A':'voice_A','B':'voice_B'},'somente_pendentes':True}
        self.assertEqual([r['id'] for r in V.selected_rows(p,options)],[bad['id']])
        before=p['itens'][0]['audio']
        with patch.object(V,'speech',return_value=self.tts.read_bytes()) as speech:
            V.generate(self.job(),self.out,options,'TEST_ONLY');self.assertEqual(speech.call_count,1)
        self.assertEqual(T.load(self.out)['itens'][0]['audio'],before)
        with self.assertRaises(ValueError):V.selected_rows(T.load(self.out),options)
    def test_preview_context_audio_and_no_approval(self):
        self.add_audio();p=T.load(self.out);p['itens'][0]['audio']['aprovado']=False;p['itens'][1].pop('audio');T.write(T.plan_path(self.out),p)
        result=T.preview_job(self.job(),self.out)
        self.assertEqual(result['trechos'],1);self.assertEqual(result['pendentes'],1)
        self.assertAlmostEqual(T.probe(self.out/result['arquivo'])['duration'],5,delta=.15)
        self.assertFalse(T.load(self.out)['itens'][0]['audio']['aprovado'])
        T.save(self.out,[{'id':p['itens'][0]['id'],'novo':'Changed name.'}]);self.assertNotIn('previa',T.load(self.out))
    def test_profiles_allowlist_no_credentials(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(P,'PATH',Path(tmp)/'profiles.json'):
            row=P.save({'nome':'Produto teste','dados':{'produto':'Old','novo':'New','key':'SECRET','autoriza_envio':True,'vozes':{'A':'existing_voice'},'kits':{'6|frascos':'3'},'precos':{'49':'29'}}})
            self.assertNotIn('SECRET',P.PATH.read_text());self.assertNotIn('autoriza_envio',row['dados']);self.assertEqual(row['dados']['vozes']['A'],'existing_voice')
            self.assertEqual(len(P.read()),1)
            with self.assertRaises(ValueError):P.save({'nome':' '})
    def test_preview_includes_prepared_visuals(self):
        from plataforma import visuais as VIS
        self.add_audio();assets=Path(__file__).parent/'fixtures/MATERIAIS_POTES_TESTE'
        VIS.scan(self.job(),self.out,assets);VIS.add(self.out,{'start':1000,'end':3000,'kit':1})
        s=VIS.load(self.out);s['modo_takes']='recortes';s['max_clip_s']=.5;s['incluir']=True;VIS.write(self.out,s);VIS.schedule(self.out,seed=3);VIS.prepare(self.job(),self.out)
        result=T.preview_job(self.job(),self.out);self.assertTrue(result['visuais'])
        import subprocess
        from plataforma import ml_core as M
        rgb=subprocess.check_output([M.FFMPEG,'-v','error','-ss','1.1','-i',str(self.out/result['arquivo']),'-frames:v','1','-vf','scale=1:1','-f','rawvideo','-pix_fmt','rgb24','-'])
        self.assertLess(rgb[2],max(rgb[0],rgb[1]))
    def test_preview_audio_only_and_cancel(self):
        import subprocess
        from plataforma import ml_core as M
        self.add_audio();subprocess.run([M.FFMPEG,'-y','-v','error','-i',str(self.out/'_fonte.mp4'),'-vn',str(self.out/'audio.m4a')],check=True)
        (self.out/'_fonte.mp4').unlink();(self.out/'audio.m4a').rename(self.out/'_fonte.m4a')
        result=T.preview_job(self.job(),self.out);self.assertFalse(result['video']);self.assertTrue((self.out/result['arquivo']).exists())
        job=self.job();job.cancel=True
        with self.assertRaises(M.Cancelled):T.preview_job(job,self.out)
    def test_reviewed_delivery_rejects_changed_montage(self):
        self.add_audio();preview=T.preview_job(self.job(),self.out);result=T.export_reviewed(self.out,preview['assinatura']);self.assertTrue((self.out/result['xml']).exists());self.assertTrue(T.flow_state(self.out)['entrega_atual']);T.build(self.out,'Oldbrand');self.assertTrue(T.flow_state(self.out)['entrega_atual'])
        p=T.load(self.out);T.save(self.out,[{'id':p['itens'][0]['id'],'aprovado':False}])
        self.assertFalse(T.flow_state(self.out)['entrega_atual'])
        with self.assertRaisesRegex(ValueError,'montagem mudou'):T.export_reviewed(self.out,preview['assinatura'])
