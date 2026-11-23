import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

from plataforma import deteccao_visual as D, trocas as T, ml_core as M

HAS_OCR = importlib.util.find_spec('rapidocr') is not None
FONTS = ['/System/Library/Fonts/Supplemental/Arial Bold.ttf', 'C:/Windows/Fonts/arialbd.ttf']


def label(path, text, color):
    img = Image.new('RGB', (420, 300), color)
    draw = ImageDraw.Draw(img)
    font = next((ImageFont.truetype(f, 70) for f in FONTS if Path(f).exists()), None) or ImageFont.load_default(size=70)
    draw.rectangle((15, 20, 405, 280), fill='white', outline='black', width=6)
    for i, line in enumerate(text.split()):
        draw.text((35, 40 + i * 110), line, fill='black', font=font)
    img.save(path)


class PureTests(unittest.TestCase):
    def test_windows_uses_one_visual_worker(self):
        from unittest.mock import patch
        with patch.object(D.sys, 'platform', 'win32'), patch.object(D.os, 'cpu_count', return_value=32):
            self.assertEqual(D.workers(), 1)

    def test_match_tolerates_split_boxes_and_misreads(self):
        score, text, _ = D.match([['GOLDEN', .9, .3, .2], ['NERVES', .9, .4, .2]], ['golden nerves'])
        self.assertGreaterEqual(score, .99)
        self.assertGreaterEqual(D.match([['G0LDEN NERVE5', .9, .3, .2]], ['golden nerves'])[0], .8)
        self.assertLess(D.match([['VITA MAX', .9, .3, .2]], ['golden nerves'])[0], .5)

    def test_place_separates_burned_subtitle_from_label(self):
        self.assertEqual(D.place(['that makes golden nerves different.', .9, .86, .45]), 'legenda')
        self.assertEqual(D.place(['GOLDEN NERVES', .9, .4, .15]), 'imagem')

    def test_group_joins_one_missed_read_and_snaps_to_cut(self):
        hit, miss = [['GOLDEN NERVES', .9, .4, .2]], [['outro texto', .9, .4, .2]]
        samples = [(0.0, miss), (1.0, miss), (2.0, hit), (3.0, miss), (4.0, hit), (5.0, miss), (6.0, miss)]
        changes = [(1.75, 40.0), (4.75, 30.0), (5.5, 30.0)]
        items = D.group(samples, changes, ['golden nerves'])
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0]['inicio_ms'], items[0]['fim_ms']), (1750, 4750))
        self.assertEqual(items[0]['leituras'], 2)

    def test_subtitle_mention_is_seen_even_with_label_visible(self):
        label, caption = ['GOLDEN NERVES', .9, .4, .15], ['We call golden nerves.', .9, .86, .45]
        samples = [(0.0, []), (1.0, [label, caption]), (2.0, [label]), (3.0, [])]
        items = D.group(samples, [], ['golden nerves'])
        self.assertEqual(items[0]['legenda_ms'], [1000])
        self.assertEqual(D.effective_first(5000, items), (1000, 'legenda'))
        self.assertEqual(D.effective_first(500, items), (500, 'transcricao'))
        self.assertEqual(D.effective_first(None, []), (None, None))

    def test_uncovered_and_review_merge(self):
        item = {'inicio_ms': 1000, 'fim_ms': 5000}
        self.assertEqual(D.uncovered_ms(item, [(0, 4500)]), 500)
        old = [{'id': 'a', 'status': 'aprovado', 'inicio_ms': 1200, 'fim_ms': 4800, 'ajustado': True, 'inicio_detectado_ms': 1000, 'fim_detectado_ms': 5000}]
        new = [{'id': 'b', 'status': 'sugerido', 'inicio_ms': 1100, 'fim_ms': 5100, 'inicio_detectado_ms': 1100, 'fim_detectado_ms': 5100}]
        merged = D.merge_review(old, new)[0]
        self.assertEqual((merged['id'], merged['status'], merged['inicio_ms']), ('a', 'aprovado', 1200))


@unittest.skipUnless(HAS_OCR, 'rapidocr indisponível neste Python')
class AnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        label(root / 'old.png', 'GOLDEN BRAIN', (180, 140, 30))
        label(root / 'other.png', 'VITA MAX', (40, 90, 160))
        cls.src = root / 'source.mp4'
        # Rótulo do produto em 4–7 s e 15–18 s; outra marca em 10–12 s.
        graph = ("[2]scale=-1:260[l];[3]scale=-1:260[d];"
                 "[0:v][l]overlay=x='80+10*t':y=180:enable='between(t,4,7)+between(t,15,18)':shortest=1[a];"
                 "[a][d]overlay=x=760:y=200:enable='between(t,10,12)':shortest=1[v]")
        subprocess.run([M.FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=1280x720:rate=25:duration=22',
                        '-f', 'lavfi', '-i', 'sine=frequency=220:duration=22', '-loop', '1', '-i', str(root / 'old.png'),
                        '-loop', '1', '-i', str(root / 'other.png'), '-filter_complex', graph,
                        '-map', '[v]', '-map', '1:a', '-t', '22', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(cls.src)], check=True)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def setUp(self):
        self.case = tempfile.TemporaryDirectory()
        self.out = Path(self.case.name)
        shutil.copy(self.src, self.out / '_fonte.mp4')
        words = [{'text': w, 'start': 19000 + i * 300, 'end': 19250 + i * 300, 'speaker': 'A'} for i, w in enumerate('Then I found Golden Brain.'.split())]
        (self.out / 'transcricao_bruta.json').write_text(json.dumps({'words': words, 'audio_duration': 22}))
        (self.out / 'frases_GOLDEN_BRAIN.json').write_text(json.dumps({'produto': 'Golden Brain', 'produto_novo': 'New Mind', 'frases': [
            {'n': 1, 'speaker': 'A', 'start': 19000, 'end': 20500, 'text': 'Then I found Golden Brain.', 'novo': 'Then I found New Mind.'}]}))
        T.build(self.out, 'Golden Brain')

    def tearDown(self): self.case.cleanup()

    def job(self): return M.Job('deteccao_teste', 'Teste local', None)

    def test_detects_label_ignores_distractor_and_reuses_reading(self):
        state = D.load(self.out)
        self.assertEqual(state['nome'], 'Golden Brain')
        result = D.analyze_job(self.job(), self.out)
        state = D.load(self.out)
        spans = [(i['inicio_ms'], i['fim_ms']) for i in state['intervalos']]
        self.assertEqual(len(spans), 2, spans)
        for (a, b), (ga, gb) in zip(spans, [(4000, 7000), (15000, 18000)]):
            self.assertLessEqual(abs(a - ga), 600)
            self.assertLessEqual(abs(b - gb), 600)
        self.assertTrue(all(len(i['miniaturas']) == 3 and (self.out / i['miniaturas'][1]).is_file() for i in state['intervalos']))
        self.assertEqual(result['intervalos'], 2)
        # Nome novo só recalcula; a leitura dos quadros é reaproveitada.
        D.config(self.out, {'nome': 'Golden Brain', 'aliases': 'GB'})
        self.assertIn('Procure novamente', D.view(self.out)['desatualizado'])
        D.analyze_job(self.job(), self.out)
        analysis = D.load(self.out)['analise']
        self.assertEqual(analysis['minutos_reaproveitados'], analysis['minutos'])

    def test_review_keeps_decisions_and_exports_markers(self):
        D.analyze_job(self.job(), self.out)
        state = D.load(self.out)
        first, second = state['intervalos']
        D.review(self.out, {'itens': [{'id': first['id'], 'status': 'aprovado', 'inicio_ms': 4100, 'fim_ms': 6900}, {'id': second['id'], 'status': 'descartado'}]})
        with self.assertRaises(ValueError):
            D.review(self.out, {'itens': [{'id': first['id'], 'inicio_ms': 9000, 'fim_ms': 8000}]})
        D.analyze_job(self.job(), self.out)
        again = {i['id']: i for i in D.load(self.out)['intervalos']}
        self.assertEqual((again[first['id']]['status'], again[first['id']]['inicio_ms']), ('aprovado', 4100))
        self.assertEqual(again[second['id']]['status'], 'descartado')
        markers = D.approved_markers(self.out)
        self.assertEqual(len(markers), 1)
        self.assertTrue(markers[0]['antes_da_mencao'])
        # Fala aprovada com áudio próprio, como no fluxo real.
        fit = self.out / 'trocas' / 'fala.wav'
        subprocess.run([M.FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=330:duration=1.2', str(fit)], check=True)
        plan = T.load(self.out)
        row = plan['itens'][0]
        row.update(aprovado=True, audio={'fit': 'trocas/fala.wav', 'aprovado': True, 'texto_hash': T.digest([row['novo'], row['speaker']]), 'modo_duracao': plan.get('modo_duracao','fixo')})
        T.write(T.plan_path(self.out), plan)
        xml = self.out / T.export_xml(self.out)['xml']
        names = [m.findtext('name') for m in ET.parse(xml).getroot().iter('marker')]
        self.assertIn('PRODUTO ANTIGO NA IMAGEM · só marcar (antes da 1ª menção)', names)

    def test_changed_source_drops_markers(self):
        D.analyze_job(self.job(), self.out)
        state = D.load(self.out)
        D.review(self.out, {'itens': [{'id': state['intervalos'][0]['id'], 'status': 'aprovado'}]})
        (self.out / '_fonte.mp4').write_bytes((self.out / '_fonte.mp4').read_bytes() + b'\0')
        self.assertEqual(D.approved_markers(self.out), [])
        self.assertIn('vídeo de origem mudou', D.view(self.out)['desatualizado'])


import test_workflow_studio as studio
from unittest.mock import patch
from plataforma import visuais as V, armazenamento as A


class CoverageTests(unittest.TestCase):
    """Aprovados viram takes de Produto só depois da 1ª menção, sem apoio e sem frestas."""
    setUpClass = classmethod(studio.StudioTests.setUpClass.__func__)
    tearDownClass = classmethod(studio.StudioTests.tearDownClass.__func__)
    tearDown = studio.StudioTests.tearDown
    job = studio.StudioTests.job
    approve = studio.StudioTests.approve
    add_audio = studio.StudioTests.add_audio

    def setUp(self):
        studio.StudioTests.setUp(self)
        guard = patch.object(A, 'visual_margin_ms', return_value=0)
        guard.start()
        self.addCleanup(guard.stop)
        self.add_audio()
        folder = self.out / 'materiais'
        folder.mkdir()
        for name, color in (('PRODUTO A.mp4', 'red'), ('PRODUTO B.mp4', 'green'), ('ESTEIRA.mp4', 'yellow'), ('1 POTE.mp4', 'purple'), ('1 POTE B.mp4', 'blue')):
            subprocess.run([M.FFMPEG, '-y', '-v', 'error', '-f', 'lavfi', '-i', f'color={color}:s=90x160:r=25:d=1', '-an', '-c:v', 'libx264', str(folder / name)], check=True)
        V.scan(self.job(), self.out, folder)
        state = V.load(self.out)
        state.update(cobrir_falas=True, mentions=[], incluir=True, modo_takes='encaixar', kit_sem_quantidade=1, basis=V.basis(self.out))
        V.write(self.out, state)

    def detections(self, spans):
        D.write(self.out, {'nome': 'Oldbrand', 'aliases': '', 'janela': 'apos_mencao',
                           'analise': {'chave': D.source_key(self.out), 'nomes': ['oldbrand'], 'janela': 'apos_mencao'},
                           'intervalos': [{'id': f'd{i}', 'inicio_ms': a, 'fim_ms': b, 'status': status, 'motivo': 'teste', 'antes_da_mencao': b <= 1000}
                                          for i, (a, b, status) in enumerate(spans)]})

    def rows(self):
        state = V.refresh_coverage(self.out, V.load(self.out))
        return [(r['start'], r['end'], bool(r.get('produto_antigo'))) for r in V.covered_mentions(self.out, state)]

    def test_no_approved_keeps_policy_and_coverage_unchanged(self):
        before = self.rows()
        self.detections([(3200, 4950, 'sugerido')])
        self.assertEqual(self.rows(), before)
        self.assertNotIn('produto_antigo', V.coverage_policy(self.out))

    def test_windows_fill_gaps_after_first_mention_and_bridge_short_gaps(self):
        self.detections([(300, 900, 'aprovado'), (2500, 4950, 'aprovado'), (7100, 7900, 'aprovado')])
        self.assertEqual(self.rows(), [(1000, 3000, False), (3000, 5000, True), (5000, 7000, False), (7000, 7900, True)])
        state = V.schedule(self.out, seed=2)
        self.assertFalse(state['issues'], state['issues'])
        assets = {a['id']: a for a in state['assets']}
        old = [s for s in state['segments'] if s['mention'].startswith('produto_antigo_')]
        self.assertTrue(old)
        self.assertTrue(all(assets[s['asset']]['uso'] == 'produto' and s['sorteio_produto'] and not s['kit_padrao_aplicado'] for s in old))
        for a, b in zip(state['segments'], state['segments'][1:]):
            self.assertEqual(a['end_frame'], b['start_frame'])
            self.assertNotEqual(a['asset'], b['asset'])

    def test_subtitle_first_mention_allows_earlier_coverage(self):
        self.detections([(300, 900, 'aprovado')])
        self.assertEqual(self.rows()[0], (1000, 3000, False))
        state = D.load(self.out)
        state['primeira_mencao_efetiva_ms'] = 500
        D.write(self.out, state)
        self.assertEqual(self.rows()[0], (500, 1000, True))  # fresta de 0,1 s até a fala fechada

    def test_changing_approvals_invalidates_prepared_takes(self):
        self.detections([(3200, 4950, 'aprovado')])
        V.schedule(self.out, seed=1)
        V.prepare(self.job(), self.out)
        self.assertTrue(V.valid_prepared(self.out, False))
        self.detections([(3200, 4950, 'descartado')])
        with self.assertRaisesRegex(ValueError, 'produto antigo'):
            V.valid_prepared(self.out, False)

    def test_support_never_covers_old_product(self):
        self.detections([(7100, 7900, 'aprovado')])
        state = V.load(self.out)
        for asset in state['assets']:
            if asset['uso'] == 'produto':
                asset['uso'] = 'depoimento'
        state['modo_takes'] = 'recortes'
        V.write(self.out, state)
        issues = V.schedule(self.out, seed=1)['issues']
        self.assertTrue(any('Produto antigo' in i['error'] for i in issues), issues)

if __name__ == '__main__':
    unittest.main()
