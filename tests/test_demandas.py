import unittest
from plataforma import demandas as D

class DemandasTests(unittest.TestCase):
    def test_request(self):
        p=D.parse('''Solicitação de TROCA DE LEAD
FUNIL VSL 01 MOD - EREHONEY (2/3/6)
VSL: [link](https://drive.google.com/file/d/base/view)
DELAY: 58:40
HTML: https://drive.google.com/file/d/html/view
1. https://drive.google.com/file/d/one/view (pegar essa ML q está até 1:32 e trocar pela da VSL acima que termina em 1:57)
2. https://cdn.example.com/two.mp4 (pegar essa ML q está até 2:27 e trocar a da VSL acima que termina em 1:57)''')
        self.assertEqual(p['corte_original'],'1:57')
        self.assertEqual([i['fim'] for i in p['variacoes']],['1:32','2:27'])
        self.assertEqual(p['avisos'],[])
        self.assertEqual(p['delay'],'58:40')
        self.assertEqual(p['pitch'],'')
        p['pitch']='58:40'
        p['ajustar_pitch']=True
        p['nomenclatura']={'produto':'EREHONEY','tipo':'mod_ml','vsl':'1','copy':'C50','editor':'EV8'}
        for i,v in enumerate(p['variacoes']): v['ml']=str(45+i)
        names=D.validate(p)
        self.assertTrue(names[0].endswith('ML 45 - PITCH 58:15'))
        self.assertTrue(names[1].endswith('ML 46 - PITCH 59:10'))

    def test_inline_rippagem_direction_overrides_donor_header(self):
        donor='https://cdn.example.com/donor/main.m3u8';body='https://cdn.example.com/body/main.m3u8'
        text=f"""**Requisição rippagem ML**
**Produto:** Nervetin MOD11
**Link da VSL a ser rippada:** [{donor}]({donor})
**Link da página:** https://example.com/page/
**Nicho:** Neuropatia
**Explicação:**
Pegar essa ML até 3:28 [{donor}]({donor}) e plugar nessa VSL cortando em 3:32 [{body}]({body})
**Prazo:** Hoje"""
        plan=D.parse(text)
        self.assertEqual(plan['base_url'],body);self.assertEqual(plan['corte_original'],'3:32')
        self.assertEqual(plan['variacoes'],[{'url':donor,'fim':'3:28','corte_original':'3:32','ml':''}])
        self.assertEqual(plan['titulo'],'Nervetin MOD11');self.assertEqual(plan['nicho'],'Neuropatia');self.assertEqual(plan['prazo'],'Hoje')
        self.assertEqual(plan['avisos'],[]);self.assertTrue(plan['observacoes'])
        plan.update(ajustar_pitch=False,entrega='xml');self.assertEqual(len(D.validate(plan)),1)

    def test_names(self):
        b={'produto':'NERVETIN','vsl':'1','lead':'2','versao':'1','ml':'45','copy':'C20','editor':'EV11','pitch':'58:40'}
        self.assertEqual(D.name(b|{'tipo':'ml'}),'NERVETIN VSL 01 - LEAD 02 - V1 - ML45 - C20 - EV11 - PITCH 58:40')
        self.assertEqual(D.name(b|{'tipo':'vsl','versao':'2','alteracao':'DROP'}),'NERVETIN VSL 01 - LEAD 02 - V2 - DROP - C20 - EV11 - PITCH 58:40')
        self.assertEqual(D.name(b|{'tipo':'upsell','upsell':'1','fluxo':'2'}),'NERVETIN - UPSELL 01 - V1 - CONTROLE - C20 - EV11 - FLUXO 02 - PITCH 58:40')
        self.assertEqual(D.name({'tipo':'close','original':'MEU VÍDEO'}),'MEU VÍDEO - 1/3/6')

    def test_missing_and_conflicting_cuts(self):
        p=D.parse('VSL: https://example.com/base.mp4\n1. https://example.com/one.mp4 (até 1:32 termina em 1:57)\n2. https://example.com/two.mp4 (até 2:27 termina em 2:00)')
        self.assertEqual(p['corte_original'],'')
        with self.assertRaises(ValueError): D.validate(p)
        for t in ('1:99','abc',-1,float('nan')):
            with self.assertRaises(ValueError): D.seconds(t)
        D.check_url('https://example.com/video.m3u8?token=test')
        with self.assertRaises(ValueError):D.check_url('https://example.com/video.mpd')

if __name__=='__main__': unittest.main()
