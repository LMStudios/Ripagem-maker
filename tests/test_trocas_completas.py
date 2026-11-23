import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import xml.etree.ElementTree as ET
from plataforma import trocas as T,vozes as V,ml_core as M

class FlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.source=cls.root/'source.mp4';cls.tts=cls.root/'tts.mp3'
        subprocess.run([M.FFMPEG,'-y','-v','error','-f','lavfi','-i','color=blue:s=160x90:r=25:d=8','-f','lavfi','-i','sine=frequency=220:duration=8','-c:v','libx264','-c:a','aac','-shortest',str(cls.source)],check=True)
        subprocess.run([M.FFMPEG,'-y','-v','error','-f','lavfi','-i','sine=frequency=1000:duration=2','-c:a','libmp3lame',str(cls.tts)],check=True)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        from plataforma import montagem as MT
        guard=patch.object(MT,'margin_ms',return_value=0);guard.start();self.addCleanup(guard.stop)
        self.case=tempfile.TemporaryDirectory();self.out=Path(self.case.name)
        shutil.copy(self.source,self.out/'_fonte.mp4')
        phrases=[{'n':1,'start':1000,'end':3000,'text':'Oldbrand works.','novo':'Newbrand works.','speaker':'A'},{'n':2,'start':5000,'end':7000,'text':'Try Oldbrand.','novo':'Try Newbrand.','speaker':'B'}]
        (self.out/'frases_TEST.json').write_text(json.dumps({'produto':'Oldbrand','produto_novo':'Newbrand','frases':phrases}))
        raw={'words':[{'text':'Oldbrand','start':1000,'end':1200,'speaker':'A'},{'text':'Oldbrand','start':5000,'end':5200,'speaker':'B'}],'utterances':[{'speaker':'A','start':0,'end':3500},{'speaker':'B','start':4000,'end':8000}]}
        (self.out/'transcricao_bruta.json').write_text(json.dumps(raw))
        self.plan=T.build(self.out,'Oldbrand');self.plan['modo_duracao']='fixo';T.write(T.plan_path(self.out),self.plan)
    def tearDown(self):self.case.cleanup()
    def job(self):return M.Job('teste','Teste',None)
    def approve(self):return T.save(self.out,[{'id':r['id'],'aprovado':True} for r in self.plan['itens']])
    def add_audio(self):
        self.approve();folder=self.out/'trocas'/'raw';folder.mkdir()
        for row in T.load(self.out)['itens']:
            file=folder/(row['id']+'.mp3');shutil.copy(self.tts,file)
            result=T.fit(self.job(),self.out,row,file);self.assertIsNotNone(result['fit'])
            T.record_audio(self.out,row['id'],result);T.approve_audio(self.out,row['id'],result['texto_hash'])
    def test_approval_persistence_and_invalidation(self):
        self.add_audio();p=T.build(self.out,'Oldbrand');self.assertTrue(all(r['audio']['aprovado'] for r in p['itens']))
        rid=p['itens'][0]['id'];p=T.save(self.out,[{'id':rid,'novo':'Edited Newbrand.'}]);self.assertNotIn('audio',p['itens'][0])
        with self.assertRaises(ValueError):T.approved(p,True)
    def test_duration_blocks_overflow(self):
        self.approve();row=self.plan['itens'][0]
        r=T.fit(self.job(),self.out,row,self.out/'_fonte.mp4')
        self.assertEqual(r['status'],'regenerar_longo');self.assertIsNone(r['fit'])
    def test_xml_and_mix_preserve_original(self):
        self.add_audio();exports=T.export_xml(self.out);xml=ET.parse(self.out/exports['xml'])
        tracks=xml.findall('.//sequence/media/audio/track');self.assertEqual(len(tracks),3)
        originals=tracks[0].findall('clipitem');cuts=tracks[1].findall('clipitem');new=tracks[2].findall('clipitem')
        self.assertEqual(len(new),2)
        self.assertEqual([(int(c.findtext('start')),int(c.findtext('end'))) for c in new],[(25,75),(125,175)])
        self.assertEqual([c.findtext('enabled') for c in originals],['TRUE','TRUE','TRUE'])
        self.assertEqual([c.findtext('enabled') for c in cuts],['FALSE','FALSE'])
        self.assertEqual([(int(c.findtext('start')),int(c.findtext('end'))) for c in cuts],[(int(c.findtext('start')),int(c.findtext('end'))) for c in new])
        self.assertTrue(all(c.findtext('enabled')=='TRUE' for c in new))
        self.assertTrue(all(c.findtext('in')=='0' for c in new))
        self.assertTrue((self.out/'_fonte.mp4').exists())
        mixed=T.mix(self.job(),self.out);self.assertAlmostEqual(T.probe(mixed)['duration'],8,delta=.1)
        import numpy as np
        pcm=subprocess.check_output([M.FFMPEG,'-v','error','-ss','1.5','-i',str(mixed),'-t','0.2','-ac','1','-ar','48000','-f','f32le','-'])
        values=np.frombuffer(pcm,dtype=np.float32);peak=np.argmax(abs(np.fft.rfft(values)))*48000/len(values)
        self.assertAlmostEqual(peak,1000,delta=20)
    def test_empty_or_unapproved_cannot_export(self):
        with self.assertRaises(ValueError):T.export_xml(self.out)
        self.approve()
        with self.assertRaises(ValueError):T.export_xml(self.out)
    def test_generation_existing_voices_and_cache(self):
        self.approve();key='TEST_ONLY_SECRET_NEVER_PERSIST'
        response=SimpleNamespace(ok=True,content=self.tts.read_bytes())
        options={'provider':'elevenlabs','model':'eleven_multilingual_v2','voices':{'A':'voice_A','B':'voice_B'},'autofit':True}
        with patch.object(V.requests,'post',return_value=response) as calls:
            result=V.generate(self.job(),str(self.out),options,key)
            self.assertEqual(calls.call_count,2);self.assertTrue(all('erro' not in r for r in result['resultados']))
            V.generate(self.job(),str(self.out),options,key);self.assertEqual(calls.call_count,2)
        self.assertNotIn(key,T.plan_path(self.out).read_text())
        self.assertNotIn(key,json.dumps(self.job().to_dict()))
    def test_correcting_product_spelling_keeps_unchanged_audio_and_approval(self):
        self.add_audio()
        before=T.load(self.out)
        source=next(self.out.glob('frases_*.json'))
        data=json.loads(source.read_text())
        data['produto']='Old brand'
        source.write_text(json.dumps(data))
        after=T.build(self.out,'Old brand')
        self.assertEqual(after['produto'],'Old brand')
        old={r['id']:r for r in before['itens']}
        for row in after['itens']:
            self.assertEqual(row['audio'],old[row['id']]['audio'])
            self.assertEqual(row['aprovado'],old[row['id']]['aprovado'])

    def test_consent_and_verification(self):
        secrets={}
        for name,callback in [('set',lambda p,v:secrets.update({p:v})),('get',lambda p:secrets.get(p)),('delete',lambda p:secrets.pop(p,None))]:
            mock=patch('plataforma.credenciais.store.'+name,side_effect=callback);mock.start();self.addCleanup(mock.stop)
        self.approve();V.configure('elevenlabs','TEST_ONLY')
        with self.assertRaises(ValueError):V.submit(str(self.out),{'provider':'elevenlabs','model':'eleven_multilingual_v2'})
        plan=T.load(self.out);plan['samples']={'A':{'arquivo':'_fonte.mp4','duracao_s':8},'B':{'arquivo':'_fonte.mp4','duracao_s':8}};T.write(T.plan_path(self.out),plan)
        with patch.object(V,'clone',return_value=('created_voice',True)),patch.object(V,'speech') as speech:
            result=V.generate(self.job(),str(self.out),{'provider':'elevenlabs','model':'eleven_multilingual_v2','voices':{}},'TEST_ONLY')
            self.assertFalse(speech.called);self.assertTrue(all('erro' in r for r in result['resultados']))
        V.forget()
    def test_minimax_contract_and_cleanup_only_created(self):
        fake=lambda d:SimpleNamespace(ok=True,json=lambda:d)
        with patch.object(T,'probe',return_value={'duration':12}),patch.object(V.requests,'post',side_effect=[fake({'file':{'file_id':123},'base_resp':{'status_code':0}}),fake({'base_resp':{'status_code':0}}),fake({'base_resp':{'status_code':0},'data':{'audio':'616263'}})]):
            voice,verification=V.clone('minimax','TEST_ONLY',self.tts,'speaker')
            self.assertTrue(voice.startswith('DRStudio'));self.assertFalse(verification)
            self.assertEqual(V.speech('minimax','TEST_ONLY',voice,'Text','speech-2.8-hd'),b'abc')
    def test_cleanup_never_deletes_existing_voice(self):
        self.approve();plan=T.load(self.out);plan['samples']={'B':{'arquivo':'_fonte.mp4'}};T.write(T.plan_path(self.out),plan)
        options={'provider':'elevenlabs','model':'eleven_multilingual_v2','voices':{'A':'existing_A'},'excluir_clones':True}
        with patch.object(V,'clone',return_value=('created_B',False)),patch.object(V,'speech',return_value=self.tts.read_bytes()),patch.object(V,'delete_created') as delete:
            result=V.generate(self.job(),str(self.out),options,'TEST_ONLY')
            self.assertTrue(all('erro' not in r for r in result['resultados']))
            delete.assert_called_once_with('elevenlabs','TEST_ONLY','created_B')

    def test_sequential_names_versions_and_migration(self):
        self.add_audio();p=T.load(self.out)
        self.assertTrue(Path(p['itens'][0]['audio']['fit']).name.startswith('001_Speaker_A_Newbrand_PRONTO'))
        self.assertTrue(Path(p['itens'][1]['audio']['fit']).name.startswith('002_Speaker_B_Newbrand_PRONTO'))
        row=p['itens'][0];again=T.fit(self.job(),self.out,row,self.out/row['audio']['raw'])
        self.assertIn('_V02.wav',again['fit']);self.assertTrue((self.out/row['audio']['fit']).exists())
        original=self.out/row['audio']['raw'];self.assertGreater(T.name_existing_audio(self.out),0)
        self.assertTrue(original.exists());self.assertEqual(T.name_existing_audio(self.out),0)

    def test_generation_reports_counts_and_phase(self):
        self.approve();job=self.job();seen=[]
        def speech(*args):
            seen.append(dict(job.progress));return self.tts.read_bytes()
        options={'provider':'elevenlabs','model':'eleven_multilingual_v2','voices':{'A':'existing_A','B':'existing_B'}}
        with patch.object(V,'speech',side_effect=speech):V.generate(job,str(self.out),options,'TEST_ONLY')
        self.assertEqual([p['processadas'] for p in seen],[0,1]);self.assertEqual(job.progress['processadas'],2)
        self.assertEqual(job.progress['total'],2);self.assertEqual(job.progress['fase'],'Concluído')
        self.assertEqual(job.to_dict()['progresso']['processadas'],2)

    def test_local_review_uses_mix_and_no_remote_calls(self):
        self.add_audio()
        from plataforma import validacao as A
        tr={'words':[{'w':'Newbrand','s':1.,'e':1.4}], 'engine':'test-local'}
        with patch.object(A,'transcribe',return_value=tr),patch.object(V.requests,'post') as remote:
            report=T.review_job(self.job(),self.out);self.assertEqual(report['status'],'nenhuma_mencao_encontrada');self.assertFalse(remote.called)
            before=T.load(self.out)['revisao'];T.save(self.out,[]);self.assertEqual(before,T.load(self.out)['revisao'])

if __name__=='__main__':unittest.main()
