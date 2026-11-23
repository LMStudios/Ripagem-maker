"""Modo de uso: o bloco inteiro da instrução antiga sai, inclusive frases sem a palavra da forma."""
import unittest

from plataforma import formas as F


def words(blocks):
    result, t = [], 1000
    for text, speaker in blocks:
        for word in text.split():
            result.append({'text': word, 'start': t, 'end': t + 250, 'speaker': speaker})
            t += 300
        t += 400
    return result


SCRIPT = [("That's why I created Glycowise.", 'A'), ('Just place two drops under your tongue every morning.', 'A'),
          ('Hold it there for thirty seconds.', 'A'), ('Then swallow.', 'A'), ('Do this every day for ninety days.', 'A'),
          ('You will feel the difference.', 'A'), ('My neighbor Mary tried it too.', 'B')]


class UsageBlockTests(unittest.TestCase):
    def setUp(self):
        self.raw = {'words': words(SCRIPT)}
        w = self.raw['words']
        self.product = [{'start': w[0]['start'], 'end': w[4]['end'], 'text': "That's why I created Glycowise.", 'novo': "That's why I created NovaPure."}]

    def test_whole_instruction_block_is_captured_next_to_existing_phrase(self):
        config = F.normalize({'ativo': True, 'origem': 'dropper', 'destino': 'capsule', 'uso_novo': 'Take one capsule a day with water.'})
        rows = F.augment(self.product, self.raw, config, ['Glycowise'], 'NovaPure')
        usage = next(r for r in rows if 'tongue' in r['text'])
        self.assertIn('Then swallow.', usage['text'])
        self.assertIn('Do this every day', usage['text'])
        self.assertEqual(usage['novo'], 'Take one capsule a day with water.')
        self.assertFalse(usage['forma_pendente'])
        self.assertFalse(any('feel the difference' in r['text'] for r in rows))
        self.assertEqual(rows[0]['novo'], "That's why I created NovaPure.")

    def test_without_confirmed_usage_the_block_stays_pending(self):
        config = F.normalize({'ativo': True, 'origem': 'dropper', 'destino': 'capsule'})
        rows = F.augment(self.product, self.raw, config, ['Glycowise'], 'NovaPure')
        usage = next(r for r in rows if 'tongue' in r['text'])
        self.assertTrue(usage['forma_pendente'])
        self.assertIn('Then swallow.', usage['text'])

    def test_leftovers_before_and_after_are_removed_and_unrelated_text_kept(self):
        config = F.normalize({'ativo': True, 'origem': 'dropper', 'destino': 'capsule', 'uso_novo': 'Take one capsule a day with water.'})
        self.assertEqual(F.adapt('Shake the bottle well. Then place two drops under your tongue.', config)[0], 'Take one capsule a day with water.')
        self.assertEqual(F.adapt('Place two drops under your tongue. You will love it.', config)[0], 'Take one capsule a day with water. You will love it.')
        patch = F.normalize({'ativo': True, 'origem': 'patch', 'destino': 'capsule', 'uso_novo': 'Take one capsule a day.'})
        self.assertEqual(F.adapt('Simply stick one patch on your shoulder each morning. Leave it on for 24 hours. It even stays on in the shower.', patch)[0],
                         'Take one capsule a day.')

    def test_a_distant_sentence_is_not_joined_to_the_instructions(self):
        config = F.normalize(dict(ativo=True, origem='dropper', destino='capsule', uso_novo='Take the capsule as directed.'))
        raw = words([('Put the drops under your tongue.', 'A')])
        distant = words([('Swallow.', 'A')])
        for token in distant:
            token['start'] += 11000
            token['end'] += 11000
        result = F.augment([], {'words': raw + distant}, config, [], '')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['text'], 'Put the drops under your tongue.')

    def test_dose_in_words_and_skin_route_without_patch_name(self):
        cfg = F.normalize(dict(ativo=True, origem='patch', destino='capsule', via_uso='oral'))
        for line in ('Two patches.', 'Administrado pela pele.', 'Aplicado a través de la piel.'):
            with self.subTest(line=line):
                self.assertTrue(F.match(line, cfg))
                self.assertTrue(F.pending(F.adapt(line, cfg)[1]))
        dropper = F.normalize(dict(ativo=True, origem='dropper', destino='capsule'))
        self.assertTrue(F.pending(F.adapt('Just two drops.', dropper)[1]))

    def test_checkout_near_use_instructions_is_not_rewritten(self):
        config = F.normalize({
            'ativo': True, 'origem': 'dropper', 'destino': 'capsule',
            'uso_novo': 'Follow the confirmed capsule instructions.',
        })
        call_to_action = 'Use the secure link below to place your order.'
        linked = 'Place two drops under your tongue. ' + call_to_action
        self.assertEqual(F.adapt(linked, config)[0], config['uso_novo'] + ' ' + call_to_action)
        blocks = [('Place two drops under your tongue.', 'A'), (call_to_action, 'A')]
        rows = F.augment([], {'words': words(blocks)}, config, [], '')
        self.assertEqual([row['text'] for row in rows], [blocks[0][0]])
        patch = F.normalize({
            'ativo': True, 'origem': 'patch', 'destino': 'capsule',
            'uso_novo': 'Siga a orientação confirmada da cápsula.',
        })
        call_to_action = 'Aplique o cupom no carrinho.'
        linked = 'Aplique o adesivo na pele. ' + call_to_action
        self.assertEqual(F.adapt(linked, patch)[0], patch['uso_novo'] + ' ' + call_to_action)


if __name__ == '__main__':
    unittest.main()
