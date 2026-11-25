"""Conferência de voz: aponta fala atribuída à pessoa errada e a deixa fora da amostra do clone."""
import json, shutil, tempfile, unittest, wave
from pathlib import Path

import numpy as np

from plataforma import ml_core as M, perfil_voz as P, trocas as T

SR = 16000
VOICES = {'A': (210, [(800, 90), (1500, 110), (2800, 160)]),   # mulher principal
          'B': (225, [(450, 70), (2200, 120), (3300, 180)]),   # outra mulher, tom parecido
          'C': (115, [(600, 80), (1100, 100), (2500, 150)])}   # homem


def synth(path, order, seed=1):
    rng = np.random.default_rng(seed); parts, labels, t = [], [], 0
    for real, label in order:
        f0, formants = VOICES[real]; f0 *= rng.uniform(.95, 1.05)
        x = np.arange(3 * SR) / SR
        phase = 2 * np.pi * np.cumsum(f0 * (1 + .06 * np.sin(2 * np.pi * .7 * x))) / SR
        sig = sum(np.sin(k * phase) / k for k in range(1, 40))
        freq = np.fft.rfftfreq(len(sig), 1 / SR)
        gain = sum(1 / (1 + ((freq - F) / bw) ** 2) for F, bw in formants)
        sig = np.fft.irfft(np.fft.rfft(sig) * gain, len(sig)) * (np.sin(2 * np.pi * 2.5 * x) > -.6)
        parts += [.3 * sig / np.abs(sig).max(), np.zeros(int(.4 * SR))]
        labels.append((label, t, t + 3000, real)); t += 3400
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.concatenate(parts) * 32767).astype('<i2').tobytes())
    return labels


class VoiceCheckTests(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.out)

    def job(self):
        return type('Job', (), {'cancel': False, 'step': '', 'pct': 0})()

    def project(self, order):
        labels = synth(self.out / '_fonte.wav', order)
        utts = [{'speaker': l, 'start': a, 'end': b, 'text': 'x', 'words': [{'text': 'x', 'start': a, 'end': b, 'speaker': l}]} for l, a, b, _ in labels]
        (self.out / 'transcricao_bruta.json').write_text(json.dumps({'utterances': utts, 'words': [w for u in utts for w in u['words']]}))
        rows = [{'id': f'r{i}', 'inicio_ms': a, 'fim_ms': b, 'speaker': l, 'duracao_s': 3, 'novo': 'x', 'original': 'x', 'aprovado': True}
                for i, (l, a, b, _) in enumerate(labels)]
        (self.out / 'trocas').mkdir(); T.write(T.plan_path(self.out), {'speakers': sorted(VOICES), 'itens': rows, 'samples': {}})
        return labels

    def test_misattributed_similar_female_voice_is_flagged_and_left_out_of_the_sample(self):
        order = [('A', 'A'), ('B', 'B'), ('A', 'A'), ('C', 'C'), ('B', 'B'), ('A', 'A'), ('C', 'C'), ('B', 'B'), ('A', 'A'), ('C', 'C'), ('B', 'A'), ('A', 'A'), ('B', 'B')]
        self.project(order)
        result = T.sample_job(self.job(), self.out)
        self.assertEqual(result['vozes_a_conferir'], {'r10': 'B'})
        row = T.load(self.out)['itens'][10]
        self.assertTrue(row['speaker_pendente']); self.assertEqual(row['speaker_sugerido'], 'B')
        with self.assertRaises(ValueError):
            T.approved(T.load(self.out))
        # Cinco falas reais da A (3 s cada) — a fala da B marcada como A fica fora da amostra.
        self.assertAlmostEqual(result['samples']['A']['duracao_s'], 5 * 3.15, delta=.4)
        # Salvar outra coisa não apaga o aviso; confirmar explicitamente, sim.
        T.save(self.out, [{'id': 'r10', 'novo': 'y', 'speaker': 'A', 'aprovado': True}])
        self.assertTrue(T.load(self.out)['itens'][10]['speaker_pendente'])
        T.save(self.out, [{'id': 'r10', 'novo': 'y', 'speaker': 'A', 'aprovado': True, 'confirmar_speaker': True}])
        row = T.load(self.out)['itens'][10]
        self.assertFalse(row['speaker_pendente']); self.assertTrue(row['speaker_confirmado']); self.assertNotIn('speaker_sugerido', row)
        # Já conferida: uma nova preparação não volta a marcar.
        self.assertEqual(T.sample_job(self.job(), self.out)['vozes_a_conferir'], {})

    def test_correct_attribution_raises_no_warning(self):
        self.project([('A', 'A'), ('C', 'C'), ('A', 'A'), ('C', 'C'), ('A', 'A'), ('C', 'C'), ('A', 'A')])
        self.assertEqual(T.sample_job(self.job(), self.out)['vozes_a_conferir'], {})
        self.assertFalse(any(r.get('speaker_pendente') for r in T.load(self.out)['itens']))

    def test_unreadable_audio_is_no_evidence(self):
        self.assertIsNone(P.features(P.decode(M.FFMPEG, self.out / 'ausente.wav', 0, 3)))
        self.assertFalse(P.Profiles({'A': [None, None]}).ok)


if __name__ == '__main__':
    unittest.main()
