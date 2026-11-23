import json
import re
import unittest
from unittest.mock import patch

import test_workflow_studio as studio
from plataforma import legendas as L, trocas as T

CONFIG = dict(L.DEFAULTS, modo='video_inteiro', conferencia_integral=True)


def parse(text):
    blocks = []
    for chunk in text.strip().split('\n\n'):
        _, times, *lines = chunk.split('\n')
        a, b = [sum(float(x) * f for x, f in zip(re.split('[:,]', t), (3600, 60, 1, .001))) for t in times.split(' --> ')]
        blocks.append((a, b, ' '.join(lines)))
    return blocks


class PureTests(unittest.TestCase):
    def words(self, text, start=0.0, step=.3, speaker='A'):
        return [{'texto': w, 'inicio': start + i * step, 'fim': start + i * step + .25, 'origem': 'original', 'speaker': speaker} for i, w in enumerate(text.split())]

    def test_standardize_new_name_keeps_punctuation(self):
        out = L.standardize(self.words('try GLYCOZEN pro, today'), 'Glycozen Pro')
        self.assertEqual([w['texto'] for w in out], ['try', 'Glycozen', 'Pro,', 'today'])

    def test_align_takes_heard_times_and_interpolates_gaps(self):
        words = self.words('the new formula works fast')
        heard = [{'w': ' the', 's': 1.0, 'e': 1.2}, {'w': ' new', 's': 1.3, 'e': 1.5}, {'w': ' works', 's': 2.0, 'e': 2.3}, {'w': ' fast', 's': 2.4, 'e': 2.7}]
        out = L.align(words, heard)
        self.assertEqual((out[0]['inicio'], out[3]['inicio']), (1.0, 2.0))
        self.assertTrue(out[2].get('estimado'))
        self.assertTrue(1.5 <= out[2]['inicio'] < out[2]['fim'] <= 2.0)

    def test_cues_respect_limits_pause_speaker_and_product_name(self):
        words = self.words('this is a long sentence that keeps going and going until it needs a break now. Golden Nerves helps')
        words += self.words('second speaker talks', start=words[-1]['fim'] + .1, speaker='B')
        cues = L.cues(words, dict(CONFIG, caracteres_linha=20, linhas=2), ['golden nerves'])
        for cue in cues:
            self.assertTrue(all(len(line) <= 20 or len(line.split()) == 1 for line in cue['linhas']), cue['linhas'])
            self.assertLessEqual(len(cue['linhas']), 2)
            self.assertNotIn('Golden\n', '\n'.join(cue['linhas']) + '\n')
        self.assertTrue(any(c['palavras'][0]['speaker'] == 'B' for c in cues))
        for a, b in zip(cues, cues[1:]):
            self.assertLessEqual(a['fim'], b['inicio'] + 1e-9)

    def test_product_name_counts_as_one_unit_when_fitting_lines(self):
        words = self.words('secure the 6-bottle package of Golden Nerves will receive an investment back for')
        cues = L.cues(words, dict(CONFIG, caracteres_linha=42, linhas=2), ['golden nerves'])
        for cue in cues:
            self.assertTrue(all(len(line) <= 42 for line in cue['linhas']), cue['linhas'])
            self.assertFalse(any(line.endswith('Golden') for line in cue['linhas']))
            self.assertLessEqual(cue['fim'] - cue['inicio'], CONFIG['duracao_max_s'] + 1e-9)

    def test_cues_only_inside_coverage_windows(self):
        words = self.words('one two three four five six seven eight', step=1.0)
        cues = L.cues(words, CONFIG, [], windows=[(2.0, 4.5)])
        text = ' '.join(' '.join(c['linhas']) for c in cues)
        self.assertEqual(text, 'three four five')
        self.assertTrue(all(2.0 <= c['inicio'] and c['fim'] <= 4.5 for c in cues))

    def test_product_name_does_not_merge_separate_coverage_windows(self):
        words = self.words('Golden Nerves', start=.15, step=2)
        result = L.cues(words, CONFIG, ['golden nerves'], windows=[(0,1),(2,3)])
        self.assertEqual([c['linhas'] for c in result], [['Golden'], ['Nerves']])
        self.assertEqual([c['janela'] for c in result], [0,1])

    def test_out_of_order_heard_times_never_overlap(self):
        words = self.words('one two three four five six seven eight nine ten', step=.4)
        words[5].update(inicio=1.0, fim=1.3)
        cues = L.cues(words, dict(CONFIG, caracteres_linha=12, linhas=1), [])
        for a, b in zip(cues, cues[1:]):
            self.assertLessEqual(a['fim'], b['inicio'] + 1e-9)

    def test_align_never_goes_back_across_chunks(self):
        words = self.words('click the button for you now are my nerves damaged for this to work', start=10.0, step=.4)
        heard = [{'w': ' ' + w['texto'], 's': w['inicio'] + .05, 'e': w['fim']} for w in words]
        out = L.align([dict(w) for w in words], heard, chunk=11)
        times = [w['inicio'] for w in out]
        self.assertEqual(times, sorted(times))

    def test_srt_format(self):
        text = L.srt([{'inicio': 1.0, 'fim': 2.5, 'linhas': ['olá', 'mundo']}])
        self.assertEqual(text, '1\n00:00:01,000 --> 00:00:02,500\nolá\nmundo\n\n')


class MontageTests(unittest.TestCase):
    setUpClass = classmethod(studio.StudioTests.setUpClass.__func__)
    tearDownClass = classmethod(studio.StudioTests.tearDownClass.__func__)
    setUp = studio.StudioTests.setUp
    tearDown = studio.StudioTests.tearDown
    job = studio.StudioTests.job
    approve = studio.StudioTests.approve
    add_audio = studio.StudioTests.add_audio

    def transcript(self):
        words = [('Hello', 200), ('there.', 500), ('Oldbrand', 1000), ('works.', 1500), ('Middle', 3500), ('words', 3900), ('here.', 4300),
                 ('Try', 5000), ('Oldbrand.', 5600), ('The', 7300), ('end.', 7600)]
        raw = {'words': [{'text': t, 'start': s, 'end': s + 250, 'speaker': 'A' if s < 4000 else 'B'} for t, s in words]}
        (self.out / 'transcricao_bruta.json').write_text(json.dumps(raw))

    def heard(self, tmap):
        """Simula o áudio final: palavras originais nos tempos mapeados e falas novas onde o áudio novo toca."""
        words = []
        for w in L.expected(self.out, tmap):
            words.append({'w': ' ' + w['texto'], 's': round(w['inicio'] + .02, 3), 'e': round(w['fim'] - .02, 3)})
        return words

    def test_map_drops_replaced_audio_and_keeps_other_times(self):
        self.transcript()
        self.add_audio()
        tmap = L.TimeMap(self.out)
        self.assertAlmostEqual(tmap.source_s(.5), .5, delta=1 / tmap.fps)
        self.assertIsNone(tmap.source_s(1.5))
        self.assertAlmostEqual(tmap.source_s(4.0), 4.0, delta=1 / tmap.fps)
        texts = [w['texto'] for w in L.expected(self.out, tmap)]
        self.assertIn('Newbrand', texts)
        self.assertNotIn('Oldbrand', texts)
        self.assertNotIn('Oldbrand.', texts)

    def test_generates_srt_with_approved_text_and_monotonic_times(self):
        self.transcript()
        self.add_audio()
        tmap = L.TimeMap(self.out)
        heard = self.heard(tmap)
        with patch.object(L, 'heard_words', return_value=heard), patch.object(L, 'burned_subtitles', return_value={'detectado': False}):
            result = L.generate_job(self.job(), self.out, CONFIG)
        blocks = parse((self.out / result['arquivo']).read_text())
        text = ' '.join(b[2] for b in blocks)
        self.assertIn('Newbrand works.', text)
        self.assertIn('Try Newbrand.', text)
        self.assertNotIn('Oldbrand', text)
        for a, b in zip(blocks, blocks[1:]):
            self.assertLessEqual(a[1], b[0] + 1e-6)
        self.assertTrue(all(b[1] > b[0] for b in blocks))
        self.assertEqual(result['modo_usado'], 'video_inteiro')
        self.assertGreaterEqual(result['alinhadas_pct'], 90)
        self.assertEqual(L.view(self.out)['desatualizado'], '')
        T.save(self.out, [{'id': T.load(self.out)['itens'][0]['id'], 'novo': 'Newbrand works well.'}])
        self.assertIn('Gere as legendas novamente', L.view(self.out)['desatualizado'])

    def test_divergent_audio_is_reported(self):
        self.transcript()
        self.add_audio()
        tmap = L.TimeMap(self.out)
        heard = [h for h in self.heard(tmap) if not (1.0 <= h['s'] < 3.0)] + [{'w': ' banana', 's': 1.2, 'e': 1.6}, {'w': ' split', 's': 1.7, 'e': 2.0}]
        heard.sort(key=lambda h: h['s'])
        with patch.object(L, 'heard_words', return_value=heard), patch.object(L, 'burned_subtitles', return_value={'detectado': False}):
            result = L.generate_job(self.job(), self.out, CONFIG)
        self.assertTrue(any(a['tipo'] == 'divergencia' and 'banana' in a['ouvido'] for a in result['avisos']))

    def test_old_name_heard_outside_swaps_is_reported(self):
        self.transcript()
        self.add_audio()
        tmap = L.TimeMap(self.out)
        heard = self.heard(tmap) + [{'w': ' Oldbrand', 's': 4.05, 'e': 4.3}]
        heard.sort(key=lambda h: h['s'])
        with patch.object(L, 'heard_words', return_value=heard), patch.object(L, 'burned_subtitles', return_value={'detectado': False}):
            result = L.generate_job(self.job(), self.out, CONFIG)
        old = [a for a in result['avisos'] if a['tipo'] == 'nome_antigo']
        self.assertEqual([round(a['inicio'], 2) for a in old], [4.05])

    def test_edit_during_generation_rejects_obsolete_caption(self):
        from plataforma import editorial as E
        self.transcript()
        self.add_audio()
        heard = self.heard(L.TimeMap(self.out))
        def change_soundtrack(*args):
            E.soundtrack(self.out, {'modo':'original','ganho_db':-10})
            return heard
        with patch.object(L, 'heard_words', side_effect=change_soundtrack), self.assertRaisesRegex(ValueError,'mudou'):
            L.generate_job(self.job(), self.out, CONFIG)
        self.assertFalse(L.view(self.out).get('resultado'))

    def test_fast_path_reuses_original_times_and_aligns_only_new_speech(self):
        self.transcript()
        self.add_audio()
        tmap = L.TimeMap(self.out)
        clips = [[{'w': w['texto'], 's': w['inicio'], 'e': w['fim']} for w in L.expected(self.out, tmap)
                  if w.get('fala') == item['row']['id']] for item in tmap.replaced()]
        with patch.object(L, 'clip_words', return_value=clips), patch.object(L, 'heard_words') as integral, patch.object(L, 'burned_subtitles') as ocr:
            result = L.generate_job(self.job(), self.out, {'modo':'video_inteiro'})
        integral.assert_not_called()
        ocr.assert_not_called()
        self.assertEqual(result['conferencia'], 'falas_novas')
        self.assertEqual(result['avisos'], [])
        self.assertIn('Hello there.', (self.out / result['arquivo']).read_text())

    def test_full_mode_recovers_text_before_a_partial_source_transcript(self):
        self.transcript()
        self.add_audio()
        tmap = L.TimeMap(self.out)
        heard = self.heard(tmap)
        path = self.out / 'transcricao_bruta.json'
        raw = json.loads(path.read_text())
        raw['recorte_transcricao'] = {'inicio_ms': 900}
        partial = dict(raw, words=[w for w in raw['words'] if w['start'] >= 900])
        path.write_text(json.dumps(partial))
        clips = [[w for w in heard if item['inicio'] <= w['s'] < item['fim']] for item in tmap.replaced()]
        with patch.object(L, 'missing_source_words', return_value=raw) as recover, patch.object(L, 'clip_words', return_value=clips), patch.object(L, 'heard_words') as integral:
            result = L.generate_job(self.job(), self.out, {'modo':'video_inteiro'})
        recover.assert_called_once()
        integral.assert_not_called()
        self.assertIn('Hello there.', (self.out / result['arquivo']).read_text())

    def test_audio_cache_ignores_takes_and_uses_known_language(self):
        from plataforma import visuais as V
        self.transcript()
        self.add_audio()
        raw = json.loads((self.out / 'transcricao_bruta.json').read_text())
        raw['language_code'] = 'en_us'
        (self.out / 'transcricao_bruta.json').write_text(json.dumps(raw))
        self.assertEqual(L.language(self.out), 'en')
        before = L.audio_signature(self.out)
        V.write(self.out, dict(V.load(self.out), incluir=True, prepared={'signature': 'outra'}))
        self.assertEqual(L.audio_signature(self.out), before)
        T.save(self.out, [{'id': T.load(self.out)['itens'][0]['id'], 'novo': 'Newbrand works well.'}])
        self.assertNotEqual(L.audio_signature(self.out), before)

    def test_coverage_mode_requires_prepared_takes(self):
        self.transcript()
        self.add_audio()
        with patch.object(L, 'burned_subtitles', return_value={'detectado': True}):
            with self.assertRaisesRegex(ValueError, 'prepare os takes'):
                L.generate_job(self.job(), self.out, dict(L.DEFAULTS, modo='auto'))


if __name__ == '__main__':
    unittest.main()
