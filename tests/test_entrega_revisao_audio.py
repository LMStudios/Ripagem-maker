import json
import math
import shutil
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from plataforma import montagem as MT, trocas as T, visuais as V
import test_trocas_completas as fixtures


class AudioReviewDeliveryTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.FlowTests.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.FlowTests.tearDownClass.__func__)
    setUp = fixtures.FlowTests.setUp
    tearDown = fixtures.FlowTests.tearDown
    job = fixtures.FlowTests.job

    def setup_review(self, *, selected=False, mode='fixo'):
        plan = T.load(self.out)
        ready, pending = plan['itens']
        self.assertNotEqual(ready['id'], pending['id'])
        shutil.copy(self.tts, self.out / 'ready.mp3')
        if mode == 'expandir':
            ready['fim_ms'] = 2000
        ready.update(aprovado=True, audio={
            'raw': 'ready.mp3', 'fit': 'ready.mp3', 'aprovado': True,
            'texto_hash': T.digest([ready['novo'], ready['speaker']]), 'modo_duracao': mode,
        })
        pending['aprovado'] = selected
        plan['modo_duracao'] = mode
        plan['entrega'] = {'xml': 'trocas/final.xml'}
        T.write(T.plan_path(self.out), plan)
        (self.out / 'trocas/final.xml').write_text('<final/>')
        V.save(self.out, {'sem_takes': True})
        return ready, pending

    def test_explicit_review_is_separate_and_marks_original_audio(self):
        ready, pending = self.setup_review()
        with self.assertRaisesRegex(ValueError, 'fora da seleção'):
            T.fast_delivery_job(self.job(), self.out, True)
        with self.assertRaisesRegex(ValueError, 'Autorize explicitamente'):
            T.fast_delivery_job(self.job(), self.out, revisao_pendencias=True)
        result = T.fast_delivery_job(self.job(), self.out, True, revisao_pendencias=True)
        self.assertEqual(result['total_pendencias'], 1)
        self.assertTrue(result['revisao_pendencias'])
        self.assertFalse(result['completa'])
        self.assertEqual(result['pendencias'][0]['id_fala'], pending['id'])
        seq = ET.parse(self.out / result['xml']).find('sequence')
        self.assertTrue(seq.findtext('name').startswith('REVISÃO DE ÁUDIO'))
        markers = [m for m in seq.findall('marker') if 'PENDÊNCIA DE ÁUDIO' in m.findtext('name')]
        self.assertEqual([(m.findtext('in'), m.findtext('out')) for m in markers], [('125', '175')])
        a1, _, a3 = seq.findall('media/audio/track')
        clip = next(c for c in a1.findall('clipitem') if 'PENDÊNCIA DE ÁUDIO' in c.findtext('name'))
        self.assertEqual((clip.findtext('enabled'), clip.findtext('in'), clip.findtext('out')), ('TRUE', '125', '175'))
        self.assertEqual([c.findtext('name') for c in a3.findall('clipitem')], ['ready.mp3'])
        data = json.loads((self.out / result['json']).read_text())
        self.assertEqual(data['pendencias'], result['pendencias'])
        self.assertEqual(data['conferencia_mencoes']['verificacao_xml']['mencoes_verificadas'], 1)
        self.assertEqual((self.out / 'trocas/final.xml').read_text(), '<final/>')
        state = T.flow_state(self.out)
        self.assertTrue(state['entrega_revisao_atual'])
        self.assertEqual(state['entrega_revisao']['xml'], result['xml'])
        self.assertEqual(state['entrega']['xml'], 'trocas/final.xml')
        self.assertEqual(T.load(self.out)['itens'], [ready, pending])

    def test_selected_missing_audio_and_no_persistence(self):
        _, pending = self.setup_review(selected=True)
        before = T.plan_path(self.out).read_bytes()
        result = T.fast_delivery_job(self.job(), self.out, True, persist=False, revisao_pendencias=True)
        self.assertEqual(result['pendencias'][0]['id_fala'], pending['id'])
        self.assertEqual(result['pendencias'][0]['status'], 'sem_audio')
        self.assertEqual(T.plan_path(self.out).read_bytes(), before)

    def test_multiple_mentions_in_same_pending_phrase_share_marker(self):
        self.setup_review()
        transcript = self.out / 'transcricao_bruta.json'
        raw = json.loads(transcript.read_text())
        raw['words'].append({'text': 'Oldbrand.', 'start': 5300, 'end': 5500, 'speaker': 'B'})
        transcript.write_text(json.dumps(raw))
        result = T.fast_delivery_job(self.job(), self.out, True, revisao_pendencias=True)
        self.assertEqual(result['total_pendencias'], 2)
        seq = ET.parse(self.out / result['xml']).find('sequence')
        markers = [m for m in seq.findall('marker') if 'PENDÊNCIA DE ÁUDIO' in m.findtext('name')]
        self.assertEqual(len(markers), 1)

    def test_review_marker_follows_montage_expansion_and_closed_margin(self):
        self.setup_review(mode='expandir')
        with patch.object(MT, 'margin_ms', return_value=200):
            result = T.fast_delivery_job(self.job(), self.out, True, revisao_pendencias=True)
        seq = ET.parse(self.out / result['xml']).find('sequence')
        marker = next(m for m in seq.findall('marker') if 'PENDÊNCIA DE ÁUDIO' in m.findtext('name'))
        expansion = math.ceil(T.probe(self.out / 'ready.mp3')['duration'] * 25 - 1e-3) - 25
        self.assertEqual(int(marker.findtext('in')), 125 + expansion - 5)
        self.assertEqual(result['pendencias'][0]['inicio_timeline_frame'], int(marker.findtext('in')))

    def test_review_preserves_prepared_takes_and_never_prepares_them_again(self):
        self.setup_review()
        state = V.load(self.out)
        shutil.copy(self.source, self.out / 'take.mp4')
        segments = [{'file': 'take.mp4', 'start_frame': 30, 'end_frame': 75, 'timeline_final': True}]
        state.update(incluir=True, sem_takes=False, basis=V.basis(self.out))
        state['prepared'] = {'signature': V.signature(state), 'segments': segments}
        V.write(self.out, state)
        before = V.path(self.out).read_bytes()
        with patch.object(V, 'automatic', side_effect=AssertionError('não recalcular os takes')):
            result = T.fast_delivery_job(self.job(), self.out, True, revisao_pendencias=True)
        seq = ET.parse(self.out / result['xml']).find('sequence')
        v2 = seq.findall('media/video/track')[1].find('clipitem')
        self.assertEqual((v2.findtext('name'), v2.findtext('start'), v2.findtext('end')), ('take.mp4', '30', '75'))
        self.assertEqual(V.path(self.out).read_bytes(), before)
