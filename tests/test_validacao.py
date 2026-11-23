import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
from plataforma import validacao as V

def words(text,start=0):
    return [{'w':w,'s':start+i*.5,'e':start+i*.5+.4} for i,w in enumerate(text.split())]

class ValidationTests(unittest.TestCase):
    def test_exact_alias_and_fuzzy(self):
        r=V.analyze(words('Nerve Tin works. NerveTen works. Nervetin works.'), 'Nerve Tin, Nervetin')
        self.assertEqual([h['tipo'] for h in r['resquicios']],['produto_antigo','produto_possivel','produto_antigo'])
        self.assertEqual(r['resquicios'][0]['mencao_inicio'],0)
        self.assertEqual(V.analyze(words('New Product works.'),'Nervetin')['validacao_produto'],'nenhuma_mencao_encontrada')
        self.assertEqual(V.analyze(words('New Product works.'),'')['validacao_produto'],'nao_configurada')

    def test_pitch_first_contextual_price(self):
        text='I am 49 years old. Get six bottles for only twenty nine dollars per bottle. Later six bottles cost 49 dollars each.'
        r=V.analyze(words(text),'')
        self.assertIsNotNone(r['pitch'])
        self.assertEqual(r['pitch']['valor'],'twenty nine')
        self.assertEqual(r['pitch']['tempo'],5.0)
        self.assertEqual(V.analyze(words('Com seis potes voce paga 29 reais por pote.'),'')['pitch']['valor'],'29')

    def test_wrong_kit_and_ambiguous(self):
        r=V.analyze(words('Three bottles cost 49 dollars each.'),'')
        self.assertIsNone(r['pitch'])
        self.assertIsNone(V.analyze(words('Only 29 dollars today.'),'')['pitch'])
        early=words('Only 29 dollars today.')
        later=words('Get six bottles for 49 dollars per bottle.',start=90)
        self.assertIsNone(V.analyze(early+later,'')['pitch'])
        self.assertIsNone(V.analyze(words('Get six bottles for a total of six months.'),'')['pitch'])

    def test_exports_and_jsx_idempotence(self):
        r=V.analyze(words('Oldbrand works. Get six bottles for 29 dollars per bottle.'),'Oldbrand')
        with tempfile.TemporaryDirectory() as tmp, patch.object(V.M,'OUT_DIR',Path(tmp)):
            info={'fps':29.97,'duracao':20,'tem_audio':True,'largura':1920,'altura':1080,'sample_rate':48000}
            result=V.export(r,Path(tmp)/'My Video.mp4',info,'test')
            root=ET.parse(Path(tmp)/result['exports']['xml'])
            self.assertEqual(root.findtext('.//sequence/rate/ntsc'),'TRUE')
            self.assertEqual(root.findtext('.//sequence/media/video/format/samplecharacteristics/width'),'1920')
            self.assertEqual(len(root.findall('.//sequence/marker')),len(result['marcadores']))
            self.assertIn('My%20Video',root.findtext('.//file/pathurl'))
            data=json.loads((Path(tmp)/result['exports']['json']).read_text())
            self.assertEqual(data['origem_tempos'],result['origem_tempos'])
            script=(Path(tmp)/result['exports']['jsx']).read_text()
            harness='''const vm=require('vm');let items=[];const markers={createMarker(s){const m={start:s};items.push(m);return m},getFirstMarker(){return items[0]},getNextMarker(m){return items[items.indexOf(m)+1]}};
const sandbox={app:{project:{activeSequence:{name:'Teste',markers}}},prompt:()=>"10",alert:()=>{},Time:function(){}};
'''+f'const script={json.dumps(script)};'+'''vm.runInNewContext(script,sandbox);let count=items.length;vm.runInNewContext(script,sandbox);if(items.length!==count||items[0].start!==10)throw Error('Marcadores duplicados ou offset incorreto');'''
            subprocess.run(['node','-e',harness],check=True)

    def test_automatic_cuts_preserve_audio_video(self):
        report=V.analyze(words('Oldbrand works. Oldbrand is useful. Oldbrend works.'),'Oldbrand')
        with tempfile.TemporaryDirectory() as tmp, patch.object(V.M,'OUT_DIR',Path(tmp)):
            info={'fps':30,'duracao':12,'tem_audio':True,'largura':320,'altura':180,'sample_rate':48000}
            result=V.export(report,Path(tmp)/'video.mp4',info,'cuttest')
            root=ET.parse(Path(tmp)/result['exports']['cortes'])
            intervals=[]
            for track in root.findall('.//sequence/media/video/track')+root.findall('.//sequence/media/audio/track'):
                clips=track.findall('clipitem')
                pairs=[(int(c.findtext('start')),int(c.findtext('end'))) for c in clips]
                self.assertEqual(pairs[0][0],0)
                self.assertEqual(pairs[-1][1],360)
                self.assertTrue(all(a[1]==b[0] for a,b in zip(pairs,pairs[1:])))
                self.assertEqual(sum(b-a for a,b in pairs),360)
                for clip,(a,b) in zip(clips,pairs):
                    self.assertEqual((int(clip.findtext('in')),int(clip.findtext('out'))),(a,b))
                    self.assertEqual(len(clip.findall('link')),2)
                intervals.append(pairs)
            self.assertEqual(intervals[0],intervals[1])
            self.assertEqual(result['cortes_automaticos']['trechos'],2)
            self.assertFalse(result['cortes_automaticos']['conteudo_removido'])

if __name__=='__main__':unittest.main()
