"""Buscador de b-roll por frase e trilha V3 do XML (3.14)."""
import json
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from plataforma import broll as B, trocas as T, ml_core as M


def make_video(path, src='testsrc2', seconds=6, extra=''):
    subprocess.run([M.FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', f'{src}=size=320x180:rate=25' + extra, '-t', str(seconds),
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(path)], check=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.case = tempfile.TemporaryDirectory()
        self.out = Path(self.case.name)
        subprocess.run([M.FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=25:duration=8',
                        '-f', 'lavfi', '-i', 'sine=frequency=220:duration=8', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-shortest', str(self.out / '_fonte.mp4')], check=True)
        text = 'I looked at myself in the bathroom mirror. Then I found Gelagen.'
        words = [{'text': w, 'start': 500 + i * 400, 'end': 850 + i * 400, 'speaker': 'A'} for i, w in enumerate(text.split())]
        (self.out / 'transcricao_bruta.json').write_text(json.dumps({'words': words, 'audio_duration': 8}))
        (self.out / 'frases_GELAGEN.json').write_text(json.dumps({'produto': 'Gelagen', 'produto_novo': 'Jellygen', 'frases': [
            {'n': 1, 'speaker': 'A', 'start': 4100, 'end': 5650, 'text': 'Then I found Gelagen.', 'novo': 'Then I found Jellygen.'}]}))
        T.build(self.out, 'Gelagen')

    def tearDown(self): self.case.cleanup()

    def fake_candidate(self, cid='yt-abc', status='limpo', seconds=2.0, phrase='500'):
        clip = self.out / 'broll' / 'clipes' / f'{cid}.mp4'
        clip.parent.mkdir(parents=True, exist_ok=True)
        make_video(clip, seconds=seconds)
        state = B.load(self.out)
        state['candidatos'][cid] = {'youtube_id': cid[3:], 'titulo': 't', 'canal': '', 'canal_id': '', 'url': '', 'arquivo': f'broll/clipes/{cid}.mp4',
                                    'miniatura': '', 'status': status, 'duracao_s': seconds, 'texto': [], 'marca_dagua': [], 'largura': 320, 'altura': 180}
        state['buscas'].setdefault(phrase, {'consulta': 'x', 'candidatos': []})['candidatos'].append(cid)
        B.save(self.out, state)


class QueryTests(Base):
    def test_query_keeps_visual_words_and_drops_product(self):
        q = B.suggest_query('I went to the bathroom, locked the door, and looked at myself in the mirror.', {'gelagen'})
        self.assertEqual(q, 'bathroom locked door mirror')
        self.assertNotIn('gelagen', B.suggest_query('Then I found Gelagen at the pharmacy.', {'gelagen'}))

    def test_sentences_and_view(self):
        view = B.view(self.out)
        self.assertEqual([r['id'] for r in view['frases']], ['3700'])
        self.assertEqual(view['frases'][0]['inicio_ms'], 4900)
        with self.assertRaisesRegex(ValueError, 'fora da seção do produto'):
            B.require_row(self.out, '500')
        self.assertEqual(view['escolhidos'], 0)

    def test_resellers_long_videos_and_repeats_are_skipped(self):
        entries = [{'id': 'a', 'duration': 12, 'title': 'Woman in mirror', 'channel': 'Free Footage'},
                   {'id': 'b', 'duration': 15, 'title': 'Stock Footage - Woman | VideoHive', 'channel': 'James Gower'},
                   {'id': 'c', 'duration': 900, 'title': 'Knee pain explained', 'channel': 'Physio'},
                   {'id': 'd', 'duration': 10, 'title': 'Mirror', 'channel': 'X'},
                   {'id': 'e', 'duration': 10, 'title': 'Mirror podcast clip', 'channel': 'Y'}]
        keep, skipped = B.pick(entries, {'d'}, 6)
        self.assertEqual([e['id'] for e in keep], ['a'])
        self.assertEqual(skipped, {'revendedor': 1, 'longo': 1, 'repetido': 1, 'fora_do_tema': 1})


class LinkTests(unittest.TestCase):
    def test_only_youtube_tiktok_and_pinterest_links(self):
        self.assertEqual(B.source_of('https://www.tiktok.com/@a/video/123'), 'tt')
        self.assertEqual(B.source_of('https://br.pinterest.com/pin/99/'), 'pin')
        self.assertEqual(B.source_of('https://pin.it/abc'), 'pin')
        self.assertEqual(B.source_of('https://youtu.be/x'), 'yt')
        for bad in ('https://example.com/tiktok.com', 'file:///etc/passwd', 'tiktok.com/x', ''):
            with self.assertRaisesRegex(ValueError, 'YouTube, TikTok ou Pinterest'):
                B.source_of(bad)


class InspectTests(unittest.TestCase):
    def test_static_diagonal_grid_over_moving_scene_is_a_watermark(self):
        import numpy as np, cv2
        def write(path, grid, room=False):
            frames = []
            for t in range(60):
                rng = np.random.default_rng(t)
                img = cv2.resize(rng.integers(0, 255, (5, 8, 3), dtype=np.uint8), (320, 180), interpolation=cv2.INTER_CUBIC)
                if room:  # cena parada com cantos em perspectiva e uma pessoa se mexendo
                    img[:] = 90; [cv2.line(img, (0, y), (320, y + 60), (200, 200, 200), 1) for y in (10, 40, 70)]
                    cv2.circle(img, (60 + t * 3, 120), 25, (30, 30, 30), -1)
                if grid:
                    for k in range(-2, 4):
                        cv2.line(img, (k * 90, 0), (k * 90 + 180, 180), (255, 255, 255), 2)
                        cv2.line(img, (k * 90 + 180, 0), (k * 90, 180), (255, 255, 255), 2)
                frames.append(img)
            proc = subprocess.run([M.FFMPEG, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', '320x180', '-r', '15', '-i', '-',
                                   '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '12', str(path)], input=b''.join(f.tobytes() for f in frames), check=True)
        with tempfile.TemporaryDirectory() as d:
            clean, marked, room = Path(d) / 'limpo.mp4', Path(d) / 'marca.mp4', Path(d) / 'sala.mp4'
            write(clean, False); write(marked, True); write(room, False, True)
            self.assertNotEqual(B.status_of(B.inspect(clean)), 'marca_dagua')
            self.assertNotEqual(B.status_of(B.inspect(room)), 'marca_dagua')
            self.assertEqual(B.status_of(B.inspect(marked)), 'marca_dagua')


class ChoiceAndXmlTests(Base):
    def test_choice_is_limited_to_product_and_sentence(self):
        self.fake_candidate(seconds=2.0, phrase='3700')
        self.fake_candidate('yt-other', phrase='500')
        with self.assertRaisesRegex(ValueError, 'fora da seção do produto'):
            B.choose(self.out, '500', 'yt-other')
        view = B.choose(self.out, '3700', 'yt-abc')
        self.assertEqual(view['escolhidos'], 1)
        choice = B.load(self.out)['escolhas']['3700']
        self.assertEqual((choice['inicio_ms'], choice['fim_ms']), (4900, 5250))
        B.choose(self.out, '3700', '')
        self.assertEqual(B.view(self.out)['escolhidos'], 0)

    def test_library_opens_without_a_project(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual([r['id'] for r in B.view(d, library=True)['frases']], [B.LIBRARY_ROW])
            self.assertEqual(B.approved(d), [])

    def test_xml_gets_v3_only_after_a_choice(self):
        plan = T.load(self.out)
        for row in plan['itens']:
            row['aprovado'] = True
        with patch.object(T, 'approved', return_value=[]), \
             patch('plataforma.conferencia_mencoes.require', return_value={'itens': [], 'pendencias': []}), \
             patch('plataforma.conferencia_mencoes.verify_xml', return_value={}):
            first = T.export_xml(self.out)
            tracks = ET.parse(self.out / first['xml']).getroot().findall('sequence/media/video/track')
            self.assertEqual(len(tracks), 1)
            self.fake_candidate('yt-old', phrase='500')
            state = B.load(self.out)
            state['escolhas']['500'] = {'inicio_ms': 500, 'fim_ms': 2500, 'arquivo': 'broll/clipes/yt-old.mp4'}
            B.save(self.out, state)
            self.fake_candidate(seconds=2.0, phrase='3700')
            B.choose(self.out, '3700', 'yt-abc')
            second = T.export_xml(self.out)
        root = ET.parse(self.out / second['xml']).getroot()
        tracks = root.findall('sequence/media/video/track')
        self.assertEqual(len(tracks), 3)  # V1 original, V2 vazia (sem takes), V3 b-roll
        self.assertEqual(len(tracks[1].findall('clipitem')), 0)
        clip = tracks[2].find('clipitem')
        self.assertEqual((clip.findtext('start'), clip.findtext('end')), (str(round(4.9 * 25)), str(round(5.25 * 25))))
        self.assertIsNone(clip.find('file/media/audio'))
        manifest = json.loads((self.out / second['json']).read_text())
        self.assertEqual(manifest['broll_v3'][0]['frase'], '3700')
        self.assertEqual(second['broll'], 1)


if __name__ == '__main__':
    unittest.main()
