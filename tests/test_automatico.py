import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET

import test_trocas_completas as base
from plataforma import (
    automatico as A, deteccao_visual as D, finalizacao as F, legendas as L, ml_core as M,
    trocas as T, visuais as VIS, vozes as V,
)


class AutomaticFlowTests(unittest.TestCase):
    setUpClass = classmethod(base.FlowTests.setUpClass.__func__)
    tearDownClass = classmethod(base.FlowTests.tearDownClass.__func__)
    tearDown = base.FlowTests.tearDown

    def setUp(self):
        base.FlowTests.setUp(self)
        self.library = self.out / 'takes'
        self.library.mkdir()
        shutil.copy2(self.source, self.library / 'PRODUTO.mp4')
        subprocess.run([M.FFMPEG, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=red:s=160x90:r=25:d=8',
                        '-c:v', 'libx264', str(self.library / 'PRODUTO LATERAL.mp4')], check=True)
        self.config = A.validate({'pasta': str(self.library), 'autoriza': True,
                                  'vozes': {'A': 'voice_a', 'B': 'voice_b'}}, False)
        T.write(A.path(self.out), {'config': self.config, 'produto': 'Oldbrand',
                                  'estado': 'preparando', 'fase': 'textos', 'mensagem': '', 'textos': False})
        D.write(self.out, D.load(self.out) | {'automatico': False})
        VIS.save(self.out, {'modo_takes': 'recortes'})
        # A fala original preservada, fora das janelas trocadas, também entra no SRT.
        raw_path = self.out / 'transcricao_bruta.json'
        raw = json.loads(raw_path.read_text())
        raw['words'].append({'text': 'Today.', 'start': 7500, 'end': 7800, 'speaker': 'B'})
        T.write(raw_path, raw)

    def job(self):
        job = M.Job(A.KIND, 'Teste automático', A.run, out=str(self.out))
        job.status = 'executando'
        return job

    def voice(self, job, out, options, key):
        for row in V.selected_rows(T.load(out), options, out):
            target = T.audio_path(out, row, 'TESTE', '.mp3')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.tts, target)
            T.record_audio(out, row['id'], T.fit(job, out, row, target))
        return {'resultados': []}

    def heard(self, job, out):
        # Recognition of generated synthetic tones is mocked; assembly and export are real.
        return [[{'w': word, 's': start, 'e': start + .2} for word, start in line]
                for line in [[('Newbrand', 1.05), ('works.', 1.45)], [('Try', 5.1), ('Newbrand.', 5.5)]]]

    def test_one_job_prepares_real_takes_subtitles_and_xml(self):
        job = self.job()
        with patch.object(M, 'JOBS', {job.id: job}), patch.object(V, 'validate', return_value='TEST_ONLY'), \
             patch.object(V, 'generate', side_effect=self.voice), patch.object(L, 'clip_words', side_effect=lambda job,out,tmap: self.heard(job,out)):
            result = A.run(job, self.out)
        self.assertEqual(A.load(self.out)['estado'], 'concluido', result)
        self.assertTrue(result['completa'])
        self.assertTrue((self.out / result['legenda']).is_file())
        xml = ET.parse(self.out / result['xml'])
        self.assertEqual(len(xml.findall('.//sequence/media/audio/track')[2].findall('clipitem')), 2)
        self.assertTrue(VIS.valid_prepared(self.out))
        report = json.loads((self.out / result['json']).read_text())['entrega_final']
        self.assertTrue(report['conferencia_automatica'])
        self.assertEqual(report['falas_aprovadas_automaticamente'], 2)
        self.assertEqual(A.view(self.out)['entrega']['xml'], result['xml'])

    def test_ambiguous_usage_pauses_before_voices_and_keeps_manual_edit(self):
        plan = T.load(self.out)
        row = plan['itens'][0]
        row.update(forma_detectada=True, forma_pendente=True, forma_confirmada=False)
        T.write(T.plan_path(self.out), plan)
        with patch.object(V, 'generate') as generate:
            result = A.run(self.job(), self.out)
        self.assertEqual(result['fase'], 'textos')
        self.assertIn('modo de uso', result['pendencia'])
        generate.assert_not_called()
        T.save(self.out, [{'id': row['id'], 'novo': 'Edited Newbrand text.', 'forma_confirmada': True}])
        with patch.object(V, 'validate', side_effect=ValueError('Chave de voz ausente.')):
            result = A.run(self.job(), self.out)
        self.assertEqual(result['fase'], 'vozes')
        self.assertEqual(T.load(self.out)['itens'][0]['novo'], 'Edited Newbrand text.')

    def test_missing_voice_does_not_request_credits(self):
        state = A.load(self.out)
        state['config']['vozes'] = {'A': 'voice_a'}
        T.write(A.path(self.out), state)
        with patch.object(V, 'validate') as validate, patch.object(T, 'sample_job') as samples:
            result = A.run(self.job(), self.out)
        self.assertEqual(result['fase'], 'vozes')
        self.assertIn('speaker B', result['pendencia'])
        validate.assert_not_called()
        samples.assert_called_once()

    def test_interrupt_and_deduplicate(self):
        job = self.job()
        with patch.object(M, 'JOBS', {job.id: job}), patch.object(M, 'submit') as enqueue:
            self.assertIs(A.submit(self.out), job)
            enqueue.assert_not_called()
        job.cancel = True
        with self.assertRaises(M.Cancelled):
            A.run(job, self.out)
        self.assertEqual(A.view(self.out)['estado'], 'pausado')

    def test_configuration_validates_consent_and_kit_arithmetic(self):
        with self.assertRaisesRegex(ValueError, 'Autorize'):
            A.validate({'pasta': str(self.library)}, False)
        with self.assertRaisesRegex(ValueError, 'deve ser igual'):
            A.validate({'pasta': str(self.library), 'autoriza': True,
                        'demanda': '2/3/6 para 1/3/6 ($59/$39/$29 - $59/$117/$175)'}, True)

    def test_saved_resolution_requeues_but_manual_pause_does_not(self):
        state = A.load(self.out)
        state.update(estado='pausado', fase='vozes')
        T.write(A.path(self.out), state)
        with patch.object(A, 'submit') as submit:
            A.resume_on_edit(self.out, 'preferencias-voz-salvar')
            submit.assert_called_once_with(self.out)
            state['pausa_manual'] = True
            T.write(A.path(self.out), state)
            A.resume_on_edit(self.out, 'preferencias-voz-salvar')
            self.assertEqual(submit.call_count, 1)

    def test_offer_audio_pauses_when_one_price_is_wrong(self):
        from types import SimpleNamespace
        item = {'inicio': 60, 'fim': 65, 'row': {'novo': '$39 per bottle. The total is $117.'}}
        def heard(total):
            return [{'w': '$39', 's': 61}, {'w': total, 's': 63}]
        with (
            patch.object(L, 'TimeMap', return_value=SimpleNamespace(replaced=lambda: [item])),
            patch.object(L, 'clip_words', side_effect=[[heard('$177')], [heard('$117')]]),
        ):
            with self.assertRaisesRegex(ValueError, '01:00'):
                A.verify_offer_audio(self.job(), self.out)
            A.verify_offer_audio(self.job(), self.out)

    def test_caption_confirmation_resumes_without_reshuffling_coverage(self):
        job = self.job()
        with (
            patch.object(M, 'JOBS', {job.id: job}),
            patch.object(V, 'validate', return_value='TEST_ONLY'),
            patch.object(V, 'generate', side_effect=self.voice) as generate,
            patch.object(L, 'clip_words', return_value=[[], []]),
        ):
            paused = A.run(job, self.out)
            self.assertEqual(paused['fase'], 'legendas')
            self.assertIn('alertas', paused['pendencia'])
            F.confirm(self.out, True, automatic_job=job)
            signature = VIS.load(self.out)['prepared']['signature']
            result = A.run(job, self.out)
            self.assertTrue(result.get('completa'), result)
            self.assertEqual(VIS.load(self.out)['prepared']['signature'], signature)
            generate.assert_called_once()
