import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
from plataforma import recorte_audio as R

class RecorteTests(unittest.TestCase):
    def test_offset_not_doubled(self):
        word={'text':'Golden','start':500,'end':800};raw={'words':[word],'utterances':[{'start':500,'end':1000,'words':[word]}]}
        s={'inicio_ms':60000,'fim_ms':120000,'duracao_original_s':120}
        d=R.restore_times(raw,s)
        self.assertEqual(d['words'][0]['start'],60500)
        self.assertEqual(d['utterances'][0]['words'][0]['start'],60500)
        self.assertEqual(raw['words'][0]['start'],500)
    def test_window_uses_actual_mention(self):
        words=[{'text':text,'start':start,'end':start+300,'speaker':'A'} for text,start in [('Try',61000),('Golden',61500),('Brain.',61900)]]
        phrases,_=app.find_phrases({'words':words,'audio_duration':120},'Golden Brain')
        metrics=R.metrics(phrases,120)
        self.assertEqual(metrics['primeira_mencao_ms'],61500)
        self.assertEqual(metrics['janela_troca_ms'],58500)
        self.assertEqual(R.metrics([],120)['janela_troca_ms'],None)
    def test_full_mode_has_no_offset(self):
        fixture=Path('tests/fixtures/auditoria.mp4')
        if not fixture.exists():self.skipTest('Fixture indisponível')
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'source.mp4';shutil.copy(fixture,src)
            audio,selection=R.prepare(src,app.FFMPEG,app.PLATAFORMA.M.FFPROBE,False)
            self.assertEqual(selection['inicio_ms'],0)
            self.assertEqual(selection['duracao_original_s'],selection['duracao_enviada_s'])
            self.assertTrue(audio.exists())

    def test_half_pipeline_without_paid_transcription(self):
        fixture=Path('tests/fixtures/auditoria.mp4')
        if not fixture.exists():self.skipTest('Fixture indisponível')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'out';out.mkdir();src=root/'input.mp4';shutil.copy(fixture,src)
            jid='test-half';app.JOBS[jid]={'status':'running'}
            def fake_transcribe(jid,path,*args,keyterms=()):
                self.assertEqual(keyterms,['Golden Brain'])
                self.assertEqual(path.suffix,'.mp3')
                media=json.loads(subprocess.check_output([app.PLATAFORMA.M.FFPROBE,'-v','error','-show_format','-show_streams','-of','json',str(path)]))
                self.assertFalse(any(s['codec_type']=='video' for s in media['streams']))
                self.assertLess(float(media['format']['duration']),8)
                words=[{'text':'Golden','start':500,'end':800,'speaker':'A'},{'text':'Brain.','start':900,'end':1200,'speaker':'A'}]
                return {'words':words,'utterances':[{'speaker':'A','start':500,'end':1200,'text':'Golden Brain.','words':words}],'text':'Golden Brain.','language_code':'en','audio_duration':7}
            with patch.object(app.STORAGE,'current',return_value=out),patch.object(app,'transcribe',side_effect=fake_transcribe):
                app.run_job(jid,src,'VSL_TESTE.mp4','en','',0,100,0,{'product':'Golden Brain','novo':'New Product','cut':True},True)
                state=app.JOBS[jid];self.assertEqual(state['status'],'done',state)
                raw=json.loads((out/state['folder']/'transcricao_bruta.json').read_text())
                offset=raw['recorte_transcricao']['inicio_ms']
                self.assertEqual(raw['words'][0]['start'],offset+500)
                self.assertEqual(state['metricas']['primeira_mencao_ms'],offset+500)
                self.assertTrue((out/state['folder']/'_fonte.mp4').exists())
                self.assertFalse(src.exists())
                self.assertFalse((out/(state['folder']+'.zip')).exists())
            app.JOBS.pop(jid,None)

if __name__=='__main__':unittest.main()
