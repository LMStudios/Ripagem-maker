import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from plataforma import ofertas as O,valores as V
import app

class OfferTests(unittest.TestCase):
 def raw(self,sentences):
  words=[];time=0
  for text,speaker in sentences:
   for token in text.split():
    words.append({'text':token,'start':time,'end':time+150,'speaker':speaker});time+=200
  return {'words':words}
 def detected(self,sentences):return O.blocks(self.raw(sentences),V.RX_PRICE,V.price_key)
 def test_spelled_prices_numeric_and_comparisons(self):
  for text,value in [('sixty-nine dollars per bottle','69'),('sixty nine dollars','69'),('one hundred and seventy-four dollars','174'),('twenty-nine bucks','29'),('$69.50 each','69.50'),('US$1,174 total','1174')]:
   with self.subTest(text=text):self.assertEqual(V.price_key(V.RX_PRICE.search(text)),value)
  self.assertIsNone(V.RX_PRICE.search('sixty-nine people and 2 bottles'))
  self.assertEqual(app.swap_prices('sixty-nine dollars per bottle.',{'69':'39'},{})[0],'39 dollars per bottle.')
 def test_price_detection_includes_sixty_nine(self):
  data=app.detect_prices(self.raw([('That works out to sixty-nine dollars per bottle.','B')]))
  self.assertEqual(data['valores'][0]['valor'],'69')
 def test_requested_matrix_checks_all_unit_totals(self):
  cfg=O.config({'demanda':'Trocar 2/3/6 para 1/3/6 (59/39/29 - 59/117/174)'})
  self.assertEqual([r['total'] for r in cfg['kits']],['59','117','174'])
  for text in ['2/3/6 para 1/3/6 (59/39/29 - 59/118/174)','2/3/6 para 1/3/3 (59/39/29 - 59/117/87)','2/3/6 para 1/3/6']:
   with self.subTest(text=text),self.assertRaises(ValueError):O.config({'demanda':text})
 def test_three_existing_offers_and_different_destinations(self):
  source=self.detected([('Choose a 2-bottle kit.','A'),('That costs $89 per bottle.','A'),('Choose a 3-bottle kit.','B'),('That works out to sixty-nine dollars per bottle.','B'),('Choose a 6-bottle kit.','B'),('That works out to just $49 a bottle.','B')])
  self.assertEqual([r['quantidade'] for r in source],[2,3,6])
  cfg=O.config({'demanda':'2/3/6 para 1/3/6 (59/39/29 - 59/117/174)'})
  outputs=[O.rewritten(b,t,'Brand',None) for b,t in zip(source,cfg['kits'])]
  self.assertIn('1-bottle kit for $59',outputs[0]);self.assertIn('$39 a bottle, for a total of $117',outputs[1]);self.assertIn('$29 a bottle, for a total of $174',outputs[2])
  self.assertNotIn('days',outputs[0])
 def test_three_other_tiers_and_decimal_totals(self):
  cfg=O.config({'demanda':'3/6/12 para 1/3/6 (79,90/49,50/39,25 - 79,90/148,50/235,50)'})
  self.assertEqual([r['quantidade'] for r in cfg['kits']],[1,3,6]);self.assertEqual(cfg['kits'][2]['total'],'235.5')
  cfg=O.config({'demanda':'1/3/6 para 1/2/4 (69/49/29 - 69/98/116)'})
  self.assertEqual(cfg['kits'][2]['quantidade'],4)
 def test_grouped_amounts_work_in_matrix_and_individual_price_changes(self):
  for symbol,large,two,three,expected_currency in [
   ('US$', '1,200.00', '400.00', '200.00', '$'),
   ('R$ ', '1.200,00', '400,00', '200,00', 'R$'),
  ]:
   with self.subTest(symbol=symbol):
    demand = (
        f'2/3/6 → 1/3/6 ({symbol}{large}/{symbol}{two}/{symbol}{three} - '
        f'{symbol}{large}/{symbol}{large}/{symbol}{large})'
    )
    cfg = O.config({'demanda': demand})
    self.assertEqual([r['unitario'] for r in cfg['kits']], ['1200', '400', '200'])
    self.assertEqual([r['total'] for r in cfg['kits']], ['1200'] * 3)
    self.assertEqual(cfg['moeda_informada'], expected_currency)
    self.assertEqual(app.swap_prices(f'{symbol}69', {'69': symbol + large}, {})[0],
                     symbol.strip() + '1200')
  for invalid in ('R$ 1.20,00', '$1,200.001', '1.000.001,00', '-$1,200.00'):
   with self.subTest(invalid=invalid), self.assertRaises(ValueError):
    V.input_amount(invalid)
 def test_pay_and_free_numbers_do_not_become_separate_kits(self):
  data=self.detected([('When you secure the full 6-month supply of Brand, you pay for only 3 bottles.','B'),("They'll cover the other 3.",'B'),('That works out to just $49 a bottle.','B'),('You can start with the three-bottle kit.','B'),("In that case, you pay for only two bottles; they'll cover the third.",'B'),('That works out to sixty-nine dollars per bottle.','B'),("It's not as complete as the full.",'B'),("180-day protocol, but it's still a great option.",'B'),('But listen, this offer ends soon.','B')])
  self.assertEqual([r['quantidade'] for r in data],[6,3])
  tiers=O.config({'demanda':'2/3/6 para 1/3/6 (59/39/29 - 59/117/174)'})['kits']
  six=O.rewritten(data[0],tiers[2],'Brand',None);three=O.rewritten(data[1],tiers[1],'Brand',None)
  self.assertIn('only 3 bottles',six);self.assertIn('cover the other 3',six);self.assertIn('only two bottles',three);self.assertIn('cover the third',three)
  self.assertNotIn('But listen',data[1]['text']);self.assertNotIn('180-day',three)
 def test_duration_is_inferred_only_from_explicit_consistent_day_supply(self):
  source=self.detected([('You can start with the three-bottle kit, covering a ninety-day treatment.','B'),('That costs $69 per bottle.','B')])
  self.assertEqual(O.duration_per_bottle(source),30)
  source.append({'quantidade':6,'antes_preco':'A 120-day treatment.'})
  self.assertIsNone(O.duration_per_bottle(source))
 def test_never_crosses_speaker_or_next_offer_for_price(self):
  self.assertEqual(self.detected([('Choose a 3-bottle kit.','A'),('That costs $69 per bottle.','B')]),[])
  result=self.detected([('Choose a 3-bottle kit.','A'),('Choose a 6-bottle kit.','A'),('That costs $49 per bottle.','A')])
  self.assertEqual([r['quantidade'] for r in result],[6])
 def test_no_price_never_guesses_timecode(self):
  self.assertEqual(self.detected([('Choose a 3-bottle kit.','A'),('There are 69 happy customers.','A')]),[])

 def test_currency_symbols_and_decimal_amounts_in_the_three_kit_request(self):
  for symbol in ('$', 'US$ ', 'R$ '):
   with self.subTest(symbol=symbol):
    prices=lambda values:'/'.join(symbol+value for value in values)
    demand=f"Trocar 2/3/6 para 1/3/6 ({prices(('59,90','39,90','29'))} - {prices(('59,90','119,70','174'))})"
    cfg=O.config({'demanda':demand})
    self.assertEqual([t['total'] for t in cfg['kits']],['59.9','119.7','174'])
  for demand in ('2/3/6 para 1/3/6 (-$59/$39/$29 - $59/$117/$174)',
                 '2/3/6 para 1/3/6 ($59/$39/$29 - $59/$117/$175)',
                 '2/3/6 para 1/3/6 ($59/$39/R$29 - $59/$117/$174)'):
   with self.subTest(demand=demand),self.assertRaises(ValueError):O.config({'demanda':demand})
 def test_currency_symbols_in_individual_prices(self):
  for original,price,value,expected in (
    ('Just sixty-nine dollars per bottle.','69','US$ 39.50','Just 39.50 dollars per bottle.'),
    ('O preço é R$ 1.174,99.','1174.99','R$ 59,90','O preço é R$59,90.'),
    ('O kit custa 69,50 reais.','69.50','R$ 39,25','O kit custa 39,25 reais.')):
   with self.subTest(original=original):self.assertEqual(app.swap_prices(original,{price:value},{})[0],expected)
  with self.assertRaisesRegex(ValueError,'moeda'):app.swap_prices('R$69.',{'69':'$39'},{})
 def test_unit_and_total_are_captured_without_eating_the_next_offer(self):
  source=self.detected([('Choose a 6-bottle kit.','A'),('That costs $49 a bottle.','A'),
                        ('The total is $294.','A'),('Buy three bottles for $207.','A'),
                        ('Your total today is $207.','B')])
  self.assertEqual([r['quantidade'] for r in source],[6,3])
  self.assertEqual(source[0]['precos_detectados'],['49','294'])
  self.assertNotIn('$207',source[0]['text'])
  self.assertNotIn('Your total',source[1]['text'])
 def test_glycowise_saved_offer_excerpt_reproduces_three_kit_request(self):
  fixture=json.loads((Path(__file__).parent/'fixtures/ofertas-glycowise-373.json').read_text())
  source=self.detected([(r['text'],r['speaker']) for r in fixture['blocos']])
  self.assertEqual([r['preco_detectado'] for r in source],['49','69'])
  tiers=O.config(fixture['config'])['kits']
  self.assertIn('$29 a bottle, for a total of $174',O.rewritten(source[0],tiers[2],'GlycoWise',30))
  self.assertIn('$39 a bottle, for a total of $117',O.rewritten(source[1],tiers[1],'GlycoWise',30))

class OfferApplyTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.out=Path(self.temp.name)
  from plataforma import trocas as T,otimizacao as OT
  self.T=T;OT.prepare(self.out,'Brand')
  self.T.write(self.out/'trocas/plano.json',{'produto':'Brand','produto_novo':'Brand','itens':[]})
  self.raw=OfferTests().raw([('When you secure the full 6-month supply of Brand, you pay for only 3 bottles.','B'),("They'll cover the other 3.",'B'),('That works out to just $49 a bottle.','B'),('You can start with the three-bottle kit.','B'),("You pay for only two bottles; they'll cover the third.",'B'),('That works out to sixty-nine dollars per bottle.','B')])
  self.T.write(self.out/'transcricao_bruta.json',self.raw)
 def test_missing_one_is_added_to_last_offer_with_explicit_metadata(self):
  r=O.preview(self.out,{'demanda':'2/3/6 para 1/3/6 (59/39/29 - 59/117/174)','dias_por_frasco':30},V.RX_PRICE,V.price_key)
  self.assertEqual(r['novas_ofertas'],[1]);self.assertEqual(r['blocos'][-1]['ofertas_incluidas'],[3,1]);self.assertIn('1-bottle kit for $59, covering your first 30 days',r['blocos'][-1]['novo'])
 def test_unknown_duration_is_not_invented(self):
  r=O.preview(self.out,{'demanda':'2/3/6 para 1/3/6 (59/39/29 - 59/117/174)'},V.RX_PRICE,V.price_key)
  self.assertNotIn('days of treatment',r['blocos'][-1]['novo'])
 def test_stale_preview_rejected_without_touching_price_file(self):
  r=O.preview(self.out,{'demanda':'2/3/6 para 1/3/6 (59/39/29 - 59/117/174)'},V.RX_PRICE,V.price_key)
  self.raw['words'][0]['text']='Changed';self.T.write(self.out/'transcricao_bruta.json',self.raw)
  with self.assertRaisesRegex(ValueError,'mudou'):O.apply(self.out,r)
  self.assertFalse((self.out/'precos_TROCA.json').exists())

 def test_failed_build_restores_existing_plan_and_price_file(self):
  self.T.write(self.out/'precos_TROCA.json',{'frases':[],'old':True})
  before=self.T.load(self.out)
  r=O.preview(self.out,{'demanda':'2/3/6 para 1/3/6 (59/39/29 - 59/117/174)'},V.RX_PRICE,V.price_key)
  with patch.object(self.T,'build',side_effect=ValueError('Falha de teste')):
   with self.assertRaisesRegex(ValueError,'Falha de teste'):O.apply(self.out,r)
  self.assertEqual(self.T.load(self.out),before)
  self.assertTrue(json.loads((self.out/'precos_TROCA.json').read_text())['old'])

 def test_no_change_does_not_crash_on_apply(self):
  raw=OfferTests().raw([
   ('Choose a 1-bottle kit.','B'),('That works out to $59 a bottle, for a total of $59.','B'),
   ('Choose a 3-bottle kit.','B'),('That works out to $39 a bottle, for a total of $117.','B'),
   ('Choose a 6-bottle kit.','B'),('That works out to $29 a bottle, for a total of $174.','B')])
  self.T.write(self.out/'transcricao_bruta.json',raw)
  self.T.write(self.out/'_fonte.mp4',{})
  with patch.object(self.T,'probe',return_value={'fps':30,'duration':60}):
   result=O.apply(self.out,O.preview(self.out,{'demanda':'1/3/6 para 1/3/6 ($59/$39/$29 - $59/$117/$174)'},V.RX_PRICE,V.price_key))
  self.assertEqual(result['plano']['itens'],[])
  self.assertTrue(all(r['sem_alteracao'] for r in result['blocos']))
 def test_offer_output_preserves_reais(self):
  raw=OfferTests().raw([('Escolha o kit de três frascos.','B'),('Por R$69,90 cada.','B'),('Total de R$209,70.','B')])
  self.T.write(self.out/'transcricao_bruta.json',raw)
  cfg={'demanda':'2/3/6 para 1/3/6 (R$59/R$39,90/R$29 - R$59/R$119,70/R$174)'}
  result=O.preview(self.out,cfg,V.RX_PRICE,V.price_key)
  self.assertEqual(result['config']['moeda'],'R$')
  self.assertIn('R$39,90 por frasco, totalizando R$119,70.',result['blocos'][0]['novo'])
  self.assertEqual(result['blocos'][0]['precos_detectados'],['69.90','209.70'])
