import json
import unittest

import test_workflow_studio as studio
from plataforma import otimizacao as OT, trocas as T


class OptimizationTests(unittest.TestCase):
    setUpClass = classmethod(studio.StudioTests.setUpClass.__func__)
    tearDownClass = classmethod(studio.StudioTests.tearDownClass.__func__)
    setUp = studio.StudioTests.setUp
    tearDown = studio.StudioTests.tearDown

    def prices(self):
        phrase = {'n': 1, 'speaker': 'B', 'start': 4000, 'end': 4800, 'text': 'Each bottle is $59.', 'novo': 'Each bottle is $49.'}
        (self.out / 'precos_TROCA.json').write_text(json.dumps({'frases': [phrase], 'mapa_precos': {'59': '49'}, 'mapa_qtd': {}}))

    def same_product(self):
        data = json.loads((self.out / 'frases_TEST.json').read_text())
        data['produto_novo'] = ''
        (self.out / 'frases_TEST.json').write_text(json.dumps(data))

    def test_mode_requires_true_or_false(self):
        for value in ('talvez', 1, None):
            with self.assertRaises(ValueError):
                OT.state(self.out, {'ativar': value})
        self.assertFalse(OT.active(self.out))

    def test_mode_is_saved_per_job_and_can_be_turned_off(self):
        self.assertFalse(OT.state(self.out)['ativo'])
        self.assertTrue(OT.state(self.out, {'ativar': True})['ativo'])
        self.assertTrue(OT.active(self.out))
        self.assertFalse(OT.state(self.out, {'ativar': False})['ativo'])

    def test_same_product_keeps_only_price_phrases(self):
        self.prices()
        self.same_product()
        OT.state(self.out, {'ativar': True})
        self.assertTrue(OT.state(self.out)['somente_valores'])
        plan = T.build(self.out, 'Oldbrand', True, only_prices=OT.active(self.out) and OT.same_product(self.out))
        self.assertEqual([r['origem'] for r in plan['itens']], ['preco_kit'])
        self.assertEqual(plan['itens'][0]['novo'], 'Each bottle is $49.')

    def test_product_metadata_cannot_enable_product_replacements(self):
        self.prices()
        OT.state(self.out, {'ativar': True})
        self.assertFalse(OT.same_product(self.out))
        plan = T.build(self.out, 'Oldbrand', True, only_prices=False)
        self.assertEqual([r['origem'] for r in plan['itens']], ['preco_kit'])
        self.assertEqual(plan['produto_novo'],'Oldbrand')

    def test_only_prices_before_values_has_empty_plan_not_product_mentions(self):
        OT.state(self.out, {'ativar': True})
        plan=T.build(self.out, 'Oldbrand')
        self.assertTrue(plan['somente_valores'])
        self.assertEqual(plan['itens'],[])

    def test_mode_skips_usage_augmentation_and_preserves_previous_plan_backup(self):
        from unittest.mock import patch
        from plataforma import formas
        self.prices()
        previous=T.load(self.out)
        OT.state(self.out, {'ativar': True})
        with patch.object(formas,'augment',side_effect=AssertionError('Must not adapt usage')):
            plan=T.build(self.out,'Oldbrand',form_config={'ativo':True,'origem':'patch','destino':'dropper'})
        self.assertEqual(len(plan['itens']),1)
        backups=list((self.out/'trocas').glob('plano_antes_escopo_*.json'))
        self.assertEqual(len(backups),1)
        self.assertEqual(json.loads(backups[0].read_text())['itens'],previous['itens'])

    def test_fresh_optimization_needs_no_product_search_results(self):
        for file in self.out.glob('frases_*.json'):file.unlink()
        OT.prepare(self.out,'GlycoWise')
        self.assertEqual(T.build(self.out,'GlycoWise')['itens'],[])
        self.prices()
        self.assertEqual(len(T.build(self.out,'GlycoWise')['itens']),1)

    def test_unchanged_price_rows_are_not_revoiced(self):
        self.prices()
        file=self.out/'precos_TROCA.json';data=json.loads(file.read_text());data['frases'][0]['novo']=data['frases'][0]['text'];file.write_text(json.dumps(data))
        OT.state(self.out, {'ativar': True})
        self.assertEqual(T.build(self.out,'Oldbrand')['itens'],[])


    def test_normal_flow_unchanged(self):
        self.prices()
        plan = T.build(self.out, 'Oldbrand', False)
        self.assertEqual([r['origem'] for r in plan['itens']], ['produto', 'produto'])


if __name__ == '__main__':
    unittest.main()
