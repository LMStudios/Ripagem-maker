import unittest
from app import find_phrases
from plataforma.mencoes import spans


class MentionTests(unittest.TestCase):
    def test_saved_asr_variants_are_reviewable_without_retranscription(self):
        lines = ["Try MemoVance Pro.", "That's why Memo Advance Pro comes with this.",
                 "We launched MemoVents, and people tried it.", "Does Memovance interfere?",
                 "Try Memo Vance Pro.", "Advanced memory works.", "These moments are important."]
        words = [{'text': w, 'start': i * 350, 'end': i * 350 + 250, 'speaker': 'A'}
                 for i, w in enumerate(' '.join(lines).split())]
        found, summary = find_phrases({'words': words, 'recorte_transcricao': {'inicio_ms': 12000}},
                                      'MemoVance Pro', '', 'Brainrecall')
        self.assertEqual(len(found), 5)
        self.assertEqual(sum(bool(r.get('mencoes_revisar')) for r in found), 3)
        self.assertEqual(found[1]['novo'], "That's why Brainrecall comes with this.")
        self.assertIn('Busca parcial', summary)

    def test_short_generic_name_does_not_expand_approximately(self):
        self.assertEqual(spans(['the', 'sizes', 'fit', 'well'], ['Size']), [])
        self.assertEqual(spans(['Size', 'Fix'], ['Size', 'Size Fix']), [(0, 2, 1)])

    @staticmethod
    def transcript(text):
        return {'words': [dict(text=w,start=i*350,end=i*350+250,speaker='A') for i,w in enumerate(text.split())]}

    def test_breath_zen_variants_keep_ordinary_breathing_instructions_intact(self):
        raw=self.transcript("Take a deep breath then hold. Breathe Zen helps. Order Brett Zen now. Breath Zenn works. BreathZen works. Try Breath Sen now. Breath Zen Ultra works. Notice your breath when you run.")
        found,_=find_phrases(raw,'Breath Zen',novo='Breath Zen Ultra')
        self.assertEqual([r['text'] for r in found],['Breathe Zen helps.','Order Brett Zen now.','Breath Zenn works.','BreathZen works.','Try Breath Sen now.'])
        self.assertEqual(sum('mencoes_revisar' in r for r in found),4)

    def test_other_name_shapes(self):
        for product, text, expected in [
            ('Zenvia','Try Zenvya today.',True),
            ('Zenvia','Ordinary Zenvya words.',False),
            ('Neuro Calm','Neuro Kalm works.',True),
            ('P-Protect','The agency protects tissue.',False),
            ('Size Fix','Size Ficks works.',True),
            ('Size Fix','Order size six today.',False),
            ('Nerve Tin','NerveTen works.',True),
            ('Vita Max 2','Vita-Max 2 works.',True),
            ('Vita Max 2','Vita Max 3 works.',False),
        ]:
            with self.subTest(product=product,text=text):
                found,_=find_phrases(self.transcript(text),product,novo='Replacement')
                self.assertEqual(bool(found),expected)

    def test_does_not_glue_across_a_pause_or_two_speakers(self):
        a,b=self.transcript('Breath Zen.')['words']
        b.update(start=2000,end=2250)
        self.assertEqual(find_phrases({'words':[a,b]},'Breath Zen')[0],[])
        b.update(start=350,end=600,speaker='B')
        self.assertEqual(find_phrases({'words':[a,b]},'Breath Zen')[0],[])

    def test_diarized_word_fallback_preserves_speaker_and_time(self):
        words=self.transcript('Try Breath Zen.')['words']
        for w in words:w.pop('speaker')
        found,_=find_phrases({'words':[], 'utterances':[{'speaker':'D','words':words}]},'Breath Zen')
        self.assertEqual((found[0]['speaker'],found[0]['primeira_mencao_ms']),('D',350))

    def test_lowercase_inference_requires_confirmation(self):
        from app import detect_product
        d=detect_product(self.transcript('this is a brand called breath zen. take two bottles of breath zen. a product called breath zen helps.'))
        self.assertEqual(d['product'],'Breath Zen')
        self.assertTrue(d['confirmar'])
        self.assertFalse(d['aliases'])
        self.assertIsNone(detect_product(self.transcript('Take a breath then hold. Take a breath then hold. Take a breath then hold.')))

    def test_common_contractions_never_win_product_detection_without_system_dictionary(self):
        from unittest.mock import patch
        from app import detect_product
        contractions = ["That's", "That’s", "THAT'S", "Thats", "It's", "It’s", "Its",
                        "There's", "There’s", "Theres", "You're", "We’re", "They’ve",
                        "Don't", "Doesn’t", "Haven't", "Let's", "What's", "How's"]
        with patch('app.DICT', set()), patch('app.NAMES', set()):
            for word in contractions:
                with self.subTest(word=word):
                    chatter = ('Well, ' + word + ' why the formula helps. ') * 20
                    brand = 'We recommend Golden Brain today. ' * 4
                    found = detect_product(self.transcript(chatter + brand))
                    self.assertEqual(found['product'], 'Golden Brain')
                    self.assertFalse(any(word.casefold() in a['nome'].casefold() for a in found['alternativas']))

    def test_common_phrases_do_not_become_compound_product_names(self):
        from unittest.mock import patch
        from app import detect_product
        with patch('app.DICT', set()), patch('app.NAMES', set()):
            for phrase in ("That's Why", "It's Just", "There’s Something", "This Really"):
                with self.subTest(phrase=phrase):
                    self.assertIsNone(detect_product(self.transcript(('Well, ' + phrase + ' helpful. ') * 10)))

    def test_contextual_product_inference_also_rejects_contractions(self):
        from app import detect_product
        for token in ("that's", "that’s", "thats", "there's", "theres"):
            with self.subTest(token=token):
                text = (f'It is a product called {token}. Get bottles of {token}. ') * 4
                self.assertIsNone(detect_product(self.transcript(text)))

    def test_brand_possessive_is_not_rejected_as_a_common_contraction(self):
        from unittest.mock import patch
        from app import detect_product
        with patch('app.DICT', set()), patch('app.NAMES', set()):
            result = detect_product(self.transcript("We recommend Nature's Best today. " * 5))
        self.assertEqual(result['product'], "Nature's Best")

    def test_discarding_approximate_match_keeps_exact_match_in_same_phrase(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from plataforma import trocas as T, automatico
        row=find_phrases(self.transcript('Use Breath Zen, not Breathe Zen.'),'Breath Zen',novo='Replacement')[0][0]
        with TemporaryDirectory() as directory:
            out=Path(directory)
            plan={'speakers':['A'],'itens':[{'id':'a','speaker':'A','original':row['text'],'novo':row['novo'],
                  'base_novo':row['novo'],'novo_sem_sugestoes':row['novo_sem_sugestoes'],
                  'mencoes_revisar':row['mencoes_revisar'],'aprovado':False}]}
            T.write(T.plan_path(out),plan)
            plan=T.save(out,[{'id':'a','mencao_descartada':True}])
            self.assertEqual(automatico.candidates(plan)[0]['novo'],'Use Replacement, not Breathe Zen.')
            self.assertTrue(plan['itens'][0]['aprovado'])
            plan=T.save(out,[{'id':'a','mencao_descartada':False}])
            self.assertEqual(plan['itens'][0]['novo'],row['novo'])
            self.assertFalse(plan['itens'][0]['aprovado'])


class SplitNameTests(unittest.TestCase):
    """Avatares falam o nome do produto em partes, com pausas e pontos entre elas."""
    @staticmethod
    def raw(items):
        return {'words': [dict(text=w, start=t, end=t + 300, speaker=s) for w, t, s in items]}

    def test_three_parts_with_periods_and_pauses_are_one_mention(self):
        d = self.raw([('Try', 0, 'A'), ('Gluco.', 400, 'A'), ('Trust.', 1800, 'A'), ('Pro.', 3200, 'A'), ('It', 5000, 'A'), ('works.', 5400, 'A')])
        found, _ = find_phrases(d, 'Gluco Trust Pro', novo='Neuro Calm')
        self.assertEqual([(r['text'], r['novo']) for r in found], [('Try Gluco. Trust. Pro.', 'Try Neuro Calm.')])

    def test_diarization_flip_inside_the_name_keeps_majority_speaker(self):
        d = self.raw([('Gluco', 0, 'A'), ('Trust', 500, 'B'), ('Pro.', 1000, 'A')])
        found, _ = find_phrases(d, 'GlucoTrust Pro', novo='X')
        self.assertEqual([(r['novo'], r['speaker']) for r in found], [('X.', 'A')])

    def test_syllables_of_a_single_word_name(self):
        found, _ = find_phrases(self.raw([('Glu.', 0, 'A'), ('Co.', 900, 'A'), ('Trust.', 1800, 'A')]), 'GlucoTrust', novo='X')
        self.assertEqual([r['novo'] for r in found], ['X.'])

    def test_parts_far_apart_or_only_similar_are_not_joined(self):
        self.assertEqual(find_phrases(self.raw([('Gluco.', 0, 'A'), ('Trust.', 1800, 'A'), ('Pro.', 6000, 'A')]), 'Gluco Trust Pro')[0], [])
        self.assertEqual(find_phrases(self.raw([('Glucose.', 0, 'A'), ('Trust.', 900, 'A'), ('Pro.', 1800, 'A')]), 'Gluco Trust Pro')[0], [])
