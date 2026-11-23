import json
import unittest
from unittest.mock import patch

import test_legendas as base
from plataforma import legendas as L, legendas_video as LV, trocas as T, ml_core as M


class StyleTests(unittest.TestCase):
    def cue(self):
        words = [{'texto': t, 'inicio': 1 + i * .5, 'fim': 1.4 + i * .5} for i, t in enumerate(['Ação', 'com', 'Glycozen', 'Pro', '{x}'])]
        return {'inicio': 1.0, 'fim': 3.6, 'palavras': words, 'linhas': ['Ação com Glycozen', 'Pro {x}']}

    def test_ass_header_scales_with_resolution_and_box(self):
        text = LV.ass([self.cue()], LV.clean_style({'fundo': True, 'tamanho': 5, 'posicao': 'superior', 'alinhamento': 'esquerda'}), 1080, 1920)
        self.assertIn('PlayResX: 1080', text)
        self.assertIn('PlayResY: 1920', text)
        style = next(line for line in text.splitlines() if line.startswith('Style:')).split(',')
        self.assertEqual(style[2], '96')            # 5% de 1920
        self.assertEqual(style[15], '3')            # caixa de fundo
        self.assertEqual(style[18], '7')            # superior à esquerda
        self.assertIn('Ação com Glycozen\\NPro (x)', text)

    def test_highlight_creates_one_event_per_word(self):
        text = LV.ass([self.cue()], LV.clean_style({'exibicao': 'destaque', 'cor_destaque': '#FFD400'}), 1280, 720)
        events = [line for line in text.splitlines() if line.startswith('Dialogue:')]
        self.assertEqual(len(events), 5)
        self.assertIn('{\\c&H00D4FF&}Glycozen{\\r}', events[2])
        self.assertEqual(events[0].split(',')[1], '0:00:01.00')

    def test_invalid_style_is_rejected(self):
        for bad in ({'cor': 'red'}, {'tamanho': 40}, {'exibicao': 'karaoke'}, {'linhas': 5}, {'tamanho': 'abc'}, {'contorno': None}):
            with self.assertRaises(ValueError) as error:
                LV.clean_style(bad)
            self.assertNotIn('could not convert', str(error.exception))

    def test_one_broken_saved_preset_does_not_hide_the_others(self):
        file = Path(self.tmp.name) / 'p.json'
        file.write_text(json.dumps({'Bom': {'cor': '#00FF00'}, 'Antigo': {'tamanho': 99}, 'Lixo': 5}))
        with patch.object(LV, 'presets_path', return_value=file):
            self.assertEqual(list(LV.presets()['meus']), ['Bom'])
            file.write_text('{quebrado')
            self.assertEqual(LV.presets()['meus'], {})

    def test_presets_keep_builtins_and_save_user(self):
        with patch.object(LV, 'presets_path', return_value=Path(self.tmp.name) / 'p.json'):
            with self.assertRaises(ValueError):
                LV.save_preset('Caixa escura', {})
            data = LV.save_preset('Meu amarelo', {'cor': '#FFFF00'})
            self.assertEqual(data['meus']['Meu amarelo']['cor'], '#FFFF00')
            self.assertIn('Caixa escura', data['padrao'])
            self.assertNotIn('Meu amarelo', LV.delete_preset('Meu amarelo')['meus'])

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)


from pathlib import Path


class RenderTests(unittest.TestCase):
    setUpClass = classmethod(base.MontageTests.setUpClass.__func__)
    tearDownClass = classmethod(base.MontageTests.tearDownClass.__func__)
    setUp = base.MontageTests.setUp
    tearDown = base.MontageTests.tearDown
    job = base.MontageTests.job
    approve = base.MontageTests.approve
    add_audio = base.MontageTests.add_audio
    transcript = base.MontageTests.transcript
    heard = base.MontageTests.heard

    def prepare(self):
        self.transcript()
        self.add_audio()
        tmap = L.TimeMap(self.out)
        with patch.object(L, 'heard_words', return_value=self.heard(tmap)), patch.object(L, 'burned_subtitles', return_value={'detectado': False}):
            L.generate_job(self.job(), self.out, base.CONFIG)

    def test_requires_current_subtitles(self):
        self.transcript()
        self.add_audio()
        with self.assertRaisesRegex(ValueError, 'Gere primeiro o SRT'):
            LV.preview_job(self.job(), self.out)

    def test_preview_and_chunked_render_match_montage(self):
        self.prepare()
        preview = LV.preview_job(self.job(), self.out, inicio=0)
        meta = T.probe(self.out / preview['arquivo'])
        self.assertTrue(meta['has_audio'])
        self.assertAlmostEqual(meta['duration'], 8.0, delta=.2)
        with patch.object(LV, 'CHUNK_S', 3):
            result = LV.render_job(self.job(), self.out, {'exibicao': 'destaque'})
        self.assertEqual(result['blocos'], 3)
        meta = T.probe(self.out / result['arquivo'])
        self.assertAlmostEqual(meta['duration'], LV.Montage(self.job(), self.out).frames / meta['fps'], delta=.15)
        self.assertTrue(meta['has_audio'])
        self.assertFalse(list((LV.folder(self.out) / 'blocos').glob('*.mp4')))
        # Cancelado no 2º bloco: o 1º fica guardado e é reaproveitado na nova tentativa.
        real, calls = M.run_proc, []
        def cancel_second(job, cmd, *a, **k):
            calls.append(1)
            if len(calls) == 2:
                raise M.Cancelled()
            return real(job, cmd, *a, **k)
        with patch.object(LV, 'CHUNK_S', 3), patch.object(M, 'run_proc', side_effect=cancel_second):
            with self.assertRaises(M.Cancelled):
                LV.render_job(self.job(), self.out, {'exibicao': 'frase'})
        with patch.object(LV, 'CHUNK_S', 3):
            again = LV.render_job(self.job(), self.out, {'exibicao': 'frase'})
        self.assertEqual(again['blocos_reaproveitados'], 1)
        view = LV.view(self.out)
        self.assertTrue(view['final']['atual'])
        LV.save_style(self.out, {'exibicao': 'frase', 'cor': '#00FF00'})
        self.assertFalse(LV.view(self.out)['final']['atual'])

    def test_ranges_follow_removed_margins(self):
        self.prepare()
        montage = LV.Montage(self.job(), self.out)
        total = sum(b - a for a, b in montage.ranges(0, montage.frames))
        self.assertEqual(total, montage.frames)


if __name__ == '__main__':
    unittest.main()
