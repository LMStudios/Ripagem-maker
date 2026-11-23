"""Referências do pote, limites das aparições, frestas em V2 e resumo da conferência (3.11)."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from plataforma import deteccao_visual as D, referencias_visuais as RV, trocas as T, ml_core as M

try:
    import cv2
    HAS_CV = hasattr(cv2, 'SIFT_create')
except ImportError:  # pragma: no cover
    HAS_CV = False


def jar(name, color=(40, 120, 200)):
    img = np.full((300, 200, 3), 235, np.uint8)
    cv2.rectangle(img, (20, 40), (180, 290), color, -1)
    cv2.rectangle(img, (60, 5), (140, 40), (30, 30, 30), -1)
    cv2.rectangle(img, (30, 110), (170, 220), (250, 250, 250), -1)
    cv2.putText(img, name, (36, 160), cv2.FONT_HERSHEY_DUPLEX, .78, (20, 20, 120), 2)
    cv2.putText(img, '60 CAPSULES', (48, 195), cv2.FONT_HERSHEY_SIMPLEX, .45, (60, 60, 60), 1)
    cv2.circle(img, (100, 250), 18, (255, 200, 0), -1)
    cv2.line(img, (40, 130), (160, 130), (200, 30, 30), 2)
    return img


def background(seed):
    rng = np.random.default_rng(seed)
    bg = cv2.GaussianBlur((rng.random((540, 960, 3)) * 60 + 90).astype(np.uint8), (0, 0), 6)
    for _ in range(12):
        cv2.circle(bg, (int(rng.integers(0, 960)), int(rng.integers(0, 540))), int(rng.integers(10, 60)),
                   tuple(int(c) for c in rng.integers(0, 255, 3)), -1)
    return bg


def place(bg, img, cx, cy, scale, blur=0, persp=0):
    h, w = img.shape[:2]
    s = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    if persp:
        hh, ww = s.shape[:2]
        src = np.float32([[0, 0], [ww, 0], [ww, hh], [0, hh]])
        dst = np.float32([[0, 0], [ww * (1 - persp), hh * persp * .3], [ww * (1 - persp), hh * (1 - persp * .3)], [0, hh]])
        s = cv2.warpPerspective(s, cv2.getPerspectiveTransform(src, dst), (ww, hh), borderValue=(235, 235, 235))
    if blur:
        s = cv2.GaussianBlur(s, (0, 0), blur)
    out = bg.copy()
    hh, ww = s.shape[:2]
    x, y = int(cx - ww / 2), int(cy - hh / 2)
    out[y:y + hh, x:x + ww] = s
    return out


@unittest.skipUnless(HAS_CV, 'OpenCV com SIFT indisponível')
class AppearanceTests(unittest.TestCase):
    def setUp(self):
        from plataforma.visual_aparencia import RegionReference
        self.ref = RegionReference()
        self.assertTrue(self.ref.add(jar('GELAGEN')))

    def test_finds_small_blurred_and_side_views(self):
        for kwargs in (dict(scale=1), dict(scale=.3), dict(scale=.6, blur=2.2), dict(scale=.7, persp=.35)):
            found = self.ref.match(place(background(1), jar('GELAGEN'), 480, 270, **kwargs))
            self.assertIsNotNone(found, kwargs)
            self.assertAlmostEqual(found['caixa'][0], .5, delta=.05)

    def test_same_model_with_another_name_is_rejected(self):
        for name in ('ROSEDIL', 'JELLYGEN'):
            for scale in (1, .5):
                self.assertIsNone(self.ref.match(place(background(2), jar(name), 480, 270, scale)), (name, scale))

    def test_background_without_jar_is_rejected(self):
        self.assertIsNone(self.ref.match(background(3)))


@unittest.skipUnless(HAS_CV, 'OpenCV com SIFT indisponível')
class BoundaryTests(unittest.TestCase):
    def frames(self, positions, cut_at=None):
        bg, other = background(4), np.full((540, 960, 3), (30, 200, 60), np.uint8)
        result = []
        for i, x in enumerate(positions):
            base = other if cut_at is not None and i >= cut_at else bg
            result.append(place(base, jar('GELAGEN'), x, 270, .6) if x is not None else base.copy())
        return result

    def test_follows_until_the_jar_leaves(self):
        from plataforma.visual_aparencia import Tracker, boundary
        frames = self.frames([480, 470, 460, 450, None, None, None])
        tracker = Tracker(frames[0], [.5, .5, .13, .34])
        index, at_cut = boundary(frames[1:], tracker, start=frames[0])
        self.assertEqual(index, 2)
        self.assertFalse(at_cut)

    def test_stops_at_a_cut_even_right_after_the_edge(self):
        from plataforma.visual_aparencia import Tracker, boundary
        frames = self.frames([480, 480, 480, 480], cut_at=1)
        tracker = Tracker(frames[0], [.5, .5, .13, .34])
        index, at_cut = boundary(frames[1:], tracker, start=frames[0])
        self.assertEqual(index, -1)
        self.assertTrue(at_cut)

    def test_does_not_jump_to_the_background_after_the_jar_leaves(self):
        from plataforma.visual_aparencia import Tracker, boundary
        bg = background(7)
        small = [place(bg, jar('GELAGEN'), 800, 400, .25)] * 3 + [bg.copy() for _ in range(6)]
        tracker = Tracker(small[0], [800 / 960, 400 / 540, .055, .14])
        index, _ = boundary(small[1:], tracker, start=small[0])
        self.assertEqual(index, 1)

    def test_does_not_drift_to_another_object(self):
        from plataforma.visual_aparencia import Tracker, boundary
        bg = background(6)
        frames = [place(bg, jar('GELAGEN'), 480, 270, .6)] + [bg.copy() for _ in range(6)]
        tracker = Tracker(frames[0], [.5, .5, .13, .34])
        index, _ = boundary(frames[1:], tracker, start=frames[0])
        self.assertEqual(index, -1)


class ReviewTests(unittest.TestCase):
    def item(self, a, b, status='sugerido', **extra):
        return {'id': f'{a}-{b}', 'status': status, 'inicio_ms': a, 'fim_ms': b, 'inicio_detectado_ms': a, 'fim_detectado_ms': b, **extra}

    def test_refined_edges_keep_the_review(self):
        merged = D.merge_review([self.item(1000, 2000, 'aprovado')], [self.item(900, 2600)])
        self.assertEqual((merged[0]['id'], merged[0]['status']), ('1000-2000', 'aprovado'))

    def test_joined_reads_in_the_same_shot_keep_approval_and_discard_wins_conflict(self):
        old = [self.item(1000, 2000, 'aprovado'), self.item(2400, 3000, 'aprovado')]
        self.assertEqual(D.merge_review(old, [self.item(900, 3100)])[0]['status'], 'aprovado')
        old[1]['status'] = 'descartado'
        self.assertEqual(D.merge_review(old, [self.item(900, 3100)])[0]['status'], 'sugerido')

    def test_much_larger_area_returns_to_review(self):
        merged = D.merge_review([self.item(1000, 2000, 'aprovado')], [self.item(0, 9000)])[0]
        self.assertEqual(merged['status'], 'sugerido')
        self.assertTrue(merged['ampliada'])

    def test_motives_and_confidence_by_evidence(self):
        appearance = {'evidencias': ['referencia', 'acompanhado'], 'referencia_visual': True, 'texto': 'gelagen', 'nota': 1, 'leituras': 3, 'local': 'imagem'}
        self.assertEqual(D.motives(appearance), ['Parecido com a referência', 'Aparição acompanhada entre quadros'])
        self.assertEqual(D.confidence(appearance), 'revisar')
        self.assertIn('referência marcada pelo editor', D.reason(appearance))
        read = {'evidencias': ['nome_lido'], 'referencia_visual': False, 'texto': 'gelagen', 'nota': 1, 'ocr_confianca': .95, 'leituras': 2, 'local': 'imagem'}
        self.assertEqual(D.motives(read), ['Nome lido no rótulo'])
        self.assertEqual(D.confidence(read), 'alta')

    def test_group_keeps_anchor_box_and_reference_ids(self):
        row = ['gelagen', .82, .5, .1, .4, .2, 'referencia_editor', 'ref1']
        samples = [(0.0, []), (1.0, [row]), (1.5, [row]), (2.0, []), (3.0, [])]
        item = D.group(samples, [], ['gelagen'])[0]
        self.assertEqual((item['referencias'], item['caixa'], item['evidencias']), (['ref1'], [.4, .5, .1, .2], ['referencia']))
        self.assertTrue(item['referencia_visual'])
        self.assertEqual((item['primeiro_s'], item['ultimo_s']), (1.0, 1.5))

    def test_cut_between_positive_reads_separates_appearances(self):
        hit = [['GELAGEN', .95, .4, .2]]
        samples = [(0.0, []), (1.0, hit), (2.0, hit), (3.0, hit), (4.0, [])]
        self.assertEqual(len(D.group(samples, [], ['gelagen'])), 1)
        self.assertEqual(len(D.group(samples, [(2.5, 40.0)], ['gelagen'])), 2)

    def test_coverage_span_applies_margin_except_adjusted(self):
        self.assertEqual(D.coverage_span({'inicio_ms': 1000, 'fim_ms': 2000}, 1500, 2800), (0, 2800))
        self.assertEqual(D.coverage_span({'inicio_ms': 3000, 'fim_ms': 4000, 'ajustado': True}, 1500, 9000), (3000, 4000))
        self.assertEqual(D.coverage_span({'inicio_ms': 3000, 'fim_ms': 4000}, 1500, 9000, floor=2500), (2500, 5500))


class LimitsApplicationTests(unittest.TestCase):
    """O resultado do acompanhamento ajusta bordas, descarta outro nome e une o mesmo plano."""

    def raw(self, a, b, **extra):
        base = {'inicio_ms': a, 'fim_ms': b, 'primeiro_s': a / 1000, 'ultimo_s': b / 1000, 'antes_s': a / 1000 - 1, 'depois_s': b / 1000 + 1,
                'ancora_s': a / 1000, 'caixa': [.5, .5, .1, .2], 'local': 'imagem', 'evidencias': ['nome_lido'], 'referencias': [],
                'referencia_visual': False, 'nota': 1, 'texto': 'gelagen', 'ocr_confianca': .9, 'leituras': 2, 'legenda_ms': []}
        return base | extra

    def run_limits(self, raws, results, changes=()):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        out = Path(temp.name)
        directory = D.folder(out) / 'limites'
        directory.mkdir(parents=True)

        def fake(job, command, total, *args):
            request = json.loads(Path(command[command.index('--limites') + 1]).read_text())
            for group in request['grupos']:
                (directory / f'limite_{group["chave"]}.json').write_text(json.dumps(results[int(group['id'])] | {'chave': group['chave']}))
        with patch.object(D, 'source_key', return_value='k'), patch.object(D.T, 'source', return_value=out / '_fonte.mp4'), \
             patch.object(RV, 'request_items', return_value=[]), patch.object(RV, 'signature', return_value=''), \
             patch.object(D, '_run_tracked', side_effect=fake):
            return D.refine_limits(M.Job('t', 't', None), out, raws, {'width': 960, 'height': 540, 'fps': 25}, ['gelagen'], list(changes))

    def test_edges_conflict_and_join(self):
        raws = [self.raw(1000, 2000), self.raw(2400, 3000), self.raw(6000, 7000, referencia_visual=True, evidencias=['referencia'])]
        results = [{'inicio': .8, 'fim': 2.45, 'acompanhado_s': .65}, {'inicio': 2.4, 'fim': 3.2, 'acompanhado_s': .2},
                   {'inicio': None, 'fim': None, 'conflito': True}]
        items, stats = self.run_limits(raws, results)
        self.assertEqual([(i['inicio_ms'], i['fim_ms']) for i in items], [(800, 3200)])
        self.assertEqual((stats['descartadas_outro_nome'], stats['unidas']), (1, 1))
        self.assertIn('acompanhado', items[0]['evidencias'])

    def test_cut_between_touching_reads_keeps_two_appearances(self):
        raws = [self.raw(1000, 2000), self.raw(2050, 3000)]
        results = [{'inicio': 1.0, 'fim': 2.05}, {'inicio': 2.05, 'fim': 3.0}]
        items, _ = self.run_limits(raws, results, changes=[(2.05, 40.0)])
        self.assertEqual(len(items), 2)

    def test_caption_only_reads_are_not_tracked(self):
        items, stats = self.run_limits([self.raw(1000, 2000, local='legenda')], [{'inicio': 0.0, 'fim': 9.0}])
        self.assertEqual((items[0]['inicio_ms'], items[0]['fim_ms']), (1000, 2000))
        self.assertEqual(stats['ajustadas'], 0)


class ProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.src = Path(cls.temp.name) / 'source.mp4'
        subprocess.run([M.FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=25:duration=12',
                        '-f', 'lavfi', '-i', 'sine=frequency=220:duration=12', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                        '-shortest', str(cls.src)], check=True)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def setUp(self):
        self.case = tempfile.TemporaryDirectory()
        self.out = Path(self.case.name)
        shutil.copy(self.src, self.out / '_fonte.mp4')
        words = [{'text': w, 'start': 8000 + i * 300, 'end': 8250 + i * 300, 'speaker': 'A'} for i, w in enumerate('Then I found Gelagen.'.split())]
        (self.out / 'transcricao_bruta.json').write_text(json.dumps({'words': words, 'audio_duration': 12}))
        (self.out / 'frases_GELAGEN.json').write_text(json.dumps({'produto': 'Gelagen', 'produto_novo': 'Jellygen', 'frases': [
            {'n': 1, 'speaker': 'A', 'start': 8000, 'end': 9200, 'text': 'Then I found Gelagen.', 'novo': 'Then I found Jellygen.'}]}))
        T.build(self.out, 'Gelagen')

    def tearDown(self): self.case.cleanup()

    def test_reference_lifecycle_is_linked_to_the_source_video(self):
        frame = RV.frame(self.out, {'t_ms': 3000})
        self.assertTrue((self.out / frame['arquivo']).is_file())
        view = RV.add(self.out, {'t_ms': 3000, 'caixa': [.5, .5, .2, .3], 'quadro': frame['arquivo']})
        ref = view['itens'][0]
        self.assertEqual((view['validas'], ref['tamanho_px']), (1, [128, 108]))
        self.assertTrue((self.out / ref['arquivo']).is_file() and (self.out / ref['miniatura']).is_file())
        signature = RV.signature(self.out)
        replaced = RV.add(self.out, {'t_ms': 4000, 'caixa': [.4, .5, .2, .3]}, replace=ref['id'])
        self.assertEqual(len(replaced['itens']), 1)
        self.assertNotEqual(RV.signature(self.out), signature)
        self.assertFalse((self.out / ref['arquivo']).exists())
        with self.assertRaisesRegex(ValueError, 'pequena'):
            RV.add(self.out, {'t_ms': 3000, 'caixa': [.5, .5, .005, .3]})
        with self.assertRaisesRegex(ValueError, 'dentro do vídeo'):
            RV.add(self.out, {'t_ms': 99000, 'caixa': [.5, .5, .2, .3]})
        # Vídeo trocado: a referência deixa de valer e pede substituição.
        (self.out / '_fonte.mp4').write_bytes((self.out / '_fonte.mp4').read_bytes() + b'\0')
        view = RV.view(self.out)
        self.assertEqual(view['validas'], 0)
        self.assertIn('substitua', view['itens'][0]['aviso'])
        self.assertEqual(RV.signature(self.out), '')
        RV.remove(self.out, view['itens'][0]['id'])
        self.assertEqual(RV.view(self.out)['itens'], [])

    def test_manual_appearance_is_approved_preserved_and_covered(self):
        result = D.add_manual(self.out, {'inicio_ms': 9500, 'fim_ms': 10500})
        item = next(i for i in result['intervalos'] if i['id'] == result['criado'])
        self.assertEqual((item['status'], item['origem'], item['motivos']), ('aprovado', 'manual', ['Marcada pelo editor']))
        self.assertEqual((item['cobertura_inicio_ms'], item['cobertura_fim_ms']), (8000, 12000))
        self.assertEqual([m['id'] for m in D.approved_markers(self.out)], [item['id']])
        # Uma nova busca não apaga a marcação do editor.
        state = D.load(self.out)
        items, _, _ = D.build(self.out, state, [], [], None, raws=[])
        self.assertIn(item['id'], [i['id'] for i in items])
        with self.assertRaisesRegex(ValueError, 'início deve vir antes'):
            D.add_manual(self.out, {'inicio_ms': 5000, 'fim_ms': 4000})

    def test_new_references_wait_for_the_editor_and_improvements_run_once(self):
        state = D.load(self.out)
        from plataforma.visual_refino import VERSION
        state['analise'] = {'fonte': T.source_identity(T.source(self.out)), 'nomes': D.names(state), 'janela': state['janela'],
                            'refino_versao': VERSION, 'limites_versao': D.LIMITS_VERSION, 'referencias': ''}
        D.write(self.out, state)
        RV.add(self.out, {'t_ms': 3000, 'caixa': [.5, .5, .2, .3]})
        self.assertEqual(D.outdated(self.out, D.load(self.out)), D.REFS_CHANGED)
        with patch.object(M, 'submit') as submit:
            result = D.automatic(self.out)
        submit.assert_not_called()
        self.assertEqual(result['aviso'], D.REFS_CHANGED)
        state = D.load(self.out)
        state['analise'].pop('limites_versao')
        state['analise']['referencias'] = RV.signature(self.out)
        D.write(self.out, state)
        with patch.object(M, 'submit') as submit:
            D.automatic(self.out)
            D.automatic(self.out)
        self.assertEqual(submit.call_count, 1)


class GapTests(unittest.TestCase):
    def run_gaps(self, state, segments, required=None, changes=()):
        from plataforma import visuais as V
        required = required or [{'id': 'produto_antigo_a', 'start': 1000, 'end': 2000}]
        with patch.object(D, 'coverage_rows', return_value=required), patch.object(D, 'approved_markers', return_value=[{'id': 'a', 'inicio_ms': 1000, 'fim_ms': 2000}]), \
             patch.object(V.T, 'source', return_value='source.mp4'), patch.object(V.T, 'probe', return_value={'fps': 25, 'duration': 4}), \
             patch('plataforma.armazenamento.visual_margin_ms', return_value=0), patch.object(V.T, 'load', return_value={'itens': []}), \
             patch('plataforma.montagem.edits', return_value=list(changes)):
            return V.coverage_gaps('unused', state, segments)

    def test_gap_reports_original_and_premiere_times(self):
        changes = [{'a': 0, 'b': 20, 'extra': 10, 'start': 0, 'end': 30}]
        gaps = self.run_gaps({'timeline_final': True}, [{'start_frame': 35, 'end_frame': 50}], changes=changes)
        piece = gaps[0]['frestas'][0]
        self.assertEqual((piece['inicio_ms'], piece['fim_ms'], piece['quadros']), (1600, 2000, 10))
        self.assertEqual((piece['premiere_inicio_s'], piece['premiere_fim_s']), (2.0, 2.4))
        self.assertEqual(piece['aparicoes'], ['a'])

    def test_marked_gap_counts_as_resolved_only_while_current(self):
        from plataforma import visuais as V
        state = {'coverage_policy': {'v': 1}, 'audio_windows': []}
        gap = self.run_gaps(state, [{'start_frame': 25, 'end_frame': 40}])[0]['frestas'][0]
        state['pendencias_visuais'] = [{'id': gap['id'], 'start': gap['inicio_ms'], 'end': gap['fim_ms'],
                                        'token': V.gap_token(state, gap['id'], gap['inicio_ms'], gap['fim_ms'])}]
        self.assertEqual(self.run_gaps(state, [{'start_frame': 25, 'end_frame': 40}]), [])
        state['coverage_policy'] = {'v': 2}
        self.assertEqual(len(self.run_gaps(state, [{'start_frame': 25, 'end_frame': 40}])), 1)


if __name__ == '__main__':
    unittest.main()
