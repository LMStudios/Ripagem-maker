import json
import shutil
import tempfile
import unittest
from pathlib import Path
import app

class FatiadorPremiereTests(unittest.TestCase):
    def test_existing_transcript_exports_without_transcribing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            words=[{'text':t,'start':i*500,'end':i*500+400,'speaker':'A'} for i,t in enumerate('Golden Brain works. Golden Brain helps.'.split())]
            d={'words':words}
            phrases,_=app.find_phrases(d,'Golden Brain',novo='New Product')
            result=app.export_fatiador_premiere(out,d,phrases,'Golden Brain',fps=30)
            self.assertEqual(len(result['itens']),2)
            self.assertEqual(result['itens'][0]['novo'],'New Product works.')
            self.assertEqual(result['itens'][0]['tl_in'],0)
            self.assertIn('MODE: "CORTAR"',(out/result['exports']['cortes_jsx']).read_text())
            self.assertIn('MODE: "MARCADORES"',(out/result['exports']['jsx']).read_text())
            self.assertNotIn('xml',result['exports'])
            (out/'precos_TROCA.json').write_text(json.dumps({'frases':[{'start':6000,'end':7000,'text':'6 bottles cost 29 dollars','n':1,'speaker':'A','novo':'3 bottles cost 49 dollars'}]}))
            with_prices=app.export_fatiador_premiere(out,d,phrases,'Golden Brain',include_prices=True)
            self.assertEqual(len(with_prices['itens']),3)

    def test_product_aliases_do_not_replace_common_words(self):
        text='Environmental Protection Agency protects tissue. P-Protect works. Pee Protect helps. P Protect works.'
        words=[{'text':t,'start':i*500,'end':i*500+400,'speaker':'B'} for i,t in enumerate(text.split())]
        phrases,_=app.find_phrases({'words':words},'P protect','P-Protect, Pee Protect','Size Fix')
        self.assertEqual(len(phrases),3)
        self.assertTrue(all('Size Fix' in p['novo'] for p in phrases))
        self.assertTrue(all('Agency' not in p['text'] for p in phrases))

    def test_video_exports_xml(self):
        fixture=Path('tests/fixtures/auditoria.mp4')
        if not fixture.exists():self.skipTest('Fixture de vídeo indisponível')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);shutil.copy(fixture,out/'_fonte.mp4')
            phrases=[{'n':1,'start':1000,'end':2000,'text':'Golden Brain works.','speaker':'A'}]
            r=app.export_fatiador_premiere(out,{'words':[]},phrases,'Golden Brain')
            self.assertTrue((out/r['exports']['cortes']).exists())
            self.assertTrue((out/r['exports']['xml']).exists())

if __name__=='__main__':unittest.main()
