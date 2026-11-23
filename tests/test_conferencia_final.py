"""Conferência final do vídeo exportado e relatório de entrega (3.13)."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plataforma import conferencia_final as CF, trocas as T, ml_core as M


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.video = Path(cls.temp.name) / 'final.mp4'
        subprocess.run([M.FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=25:duration=6',
                        '-f', 'lavfi', '-i', 'sine=frequency=220:duration=6', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-shortest', str(cls.video)], check=True)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def setUp(self):
        self.case = tempfile.TemporaryDirectory()
        self.out = Path(self.case.name)
        shutil.copy(self.video, self.out / '_fonte.mp4')
        words = [{'text': w, 'start': 1000 + i * 300, 'end': 1250 + i * 300, 'speaker': 'A'} for i, w in enumerate('Then I found Gelagen.'.split())]
        (self.out / 'transcricao_bruta.json').write_text(json.dumps({'words': words, 'audio_duration': 6}))
        (self.out / 'frases_GELAGEN.json').write_text(json.dumps({'produto': 'Gelagen', 'produto_novo': 'Jellygen', 'frases': [
            {'n': 1, 'speaker': 'A', 'start': 1000, 'end': 2200, 'text': 'Then I found Gelagen.', 'novo': 'Then I found Jellygen.'}]}))
        T.build(self.out, 'Gelagen')

    def tearDown(self): self.case.cleanup()

    def job(self): return M.Job('conferencia_final', 'teste', None)


class PathAndPriceTests(Base):
    def test_only_existing_videos_are_accepted(self):
        self.assertEqual(CF.check_path(str(self.video)), self.video.resolve())
        with self.assertRaisesRegex(ValueError, 'Escolha o vídeo'):
            CF.check_path('relativo.mp4')
        text = self.out / 'nota.txt'; text.write_text('x')
        with self.assertRaisesRegex(ValueError, 'Escolha um vídeo'):
            CF.check_path(str(text))

    def test_terms_are_the_product_and_registered_spellings_only(self):
        plan = T.load(self.out); plan['produto_aliases'] = 'Gelogen; Gel Agen'
        self.assertEqual(CF.names(self.out, plan), ['Gelagen', 'Gelogen', 'Gel Agen'])

    def test_old_prices_come_from_the_price_swap(self):
        (self.out / 'precos_TROCA.json').write_text(json.dumps({'mapa_precos': {'$49': '$39', '29': '29', '$69.00': '$59'}}))
        self.assertEqual(CF.old_prices(self.out), ['69.00', '49'])
        (self.out / 'precos_TROCA.json').unlink()
        self.assertEqual(CF.old_prices(self.out), [])


class ReportTests(Base):
    def run_check(self, audio, image):
        with patch.object(CF, '_audio', return_value=(audio, {'motor': 'teste', 'palavras': 10})), \
             patch.object(CF, '_ocr', return_value=(image, {'minutos': 1, 'minutos_reaproveitados': 0, 'quadros_lidos': 6})):
            return CF.check_job(self.job(), self.out, str(self.video))

    def test_clean_video_is_approved_and_saved_in_the_project(self):
        summary = self.run_check([], [])
        self.assertTrue(summary['aprovado'])
        page = (self.out / summary['relatorio']).read_text()
        self.assertIn('Conferência aprovada', page)
        self.assertIn('Gelagen → Jellygen', page)
        self.assertEqual(CF.view(self.out)['ultima']['relatorio'], summary['relatorio'])
        self.assertTrue(CF.view(self.out)['ultima']['existe'])

    def test_points_are_listed_with_time_and_embedded_frame(self):
        audio = [{'tipo': 'produto', 'inicio_s': 2.0, 'fim_s': 2.4, 'termo': 'Gelagen', 'certeza': 'encontrado', 'contexto': 'Then I found Gelagen'}]
        image = [{'tipo': 'produto', 'local': 'imagem', 'inicio_s': 3.0, 'fim_s': 4.0, 'termo': 'gelagen', 'certeza': 'possivel', 'leituras': 2},
                 {'tipo': 'produto', 'local': 'legenda', 'inicio_s': 4.5, 'fim_s': 5.0, 'termo': 'gelagen', 'certeza': 'encontrado', 'leituras': 1}]
        summary = self.run_check(audio, image)
        self.assertFalse(summary['aprovado'])
        self.assertEqual(summary['pontos'], 3)
        report = json.loads((self.out / summary['json']).read_text())
        self.assertEqual((len(report['audio']), len(report['imagem']), len(report['legenda'])), (1, 1, 1))
        page = (self.out / summary['relatorio']).read_text()
        self.assertIn('3 ponto(s) para conferir', page)
        self.assertIn('00:02', page)
        self.assertIn('data:image/jpeg;base64,', page)  # quadros embutidos: a página pode ir ao cliente como está

    def test_requires_product_or_old_prices(self):
        plan = T.load(self.out); plan['produto'] = ''; plan['produto_aliases'] = ''
        with patch.object(CF, 'names', return_value=[]), patch.object(T, 'load', return_value=plan):
            with self.assertRaisesRegex(ValueError, 'produto antigo'):
                CF.check_job(self.job(), self.out, str(self.video))


if __name__ == '__main__':
    unittest.main()
