import unittest
from pathlib import Path
from plataforma import srt_corretor as S

def cue(n,text,start='00:00:01,000',end='00:00:02,000',eol='\n'):
    return eol.join([str(n),start+' --> '+end,text,'',''])

class SrtTests(unittest.TestCase):
    def test_replacements_and_structure(self):
        src='\ufeff'+cue(1,'Golden\r\nBrain and Golden Brain.',eol='\r\n')+cue(2,'Other words.','00:00:03,000','00:00:04,000',eol='\r\n')
        item={'text':'Golden Brain and Golden Brain.','novo':'New Product and New Product.','start':1000,'end':2000}
        out,r=S.correct(src,[item])
        self.assertEqual(r['alterados'],1)
        self.assertTrue(out.startswith('\ufeff'))
        self.assertIn('New\r\nProduct and New Product.',out)
        self.assertEqual([(x['id'],x['tc']) for x in S.parse(src)],[(x['id'],x['tc']) for x in S.parse(out)])
        self.assertIn('Other words.',out)

    def test_cross_cue_and_uncertain(self):
        src=cue(1,'Golden')+cue(2,'Brain.','00:00:02,000','00:00:03,000')
        item={'text':'Golden Brain.','novo':'New Product.','start':1000,'end':3000}
        out,r=S.correct(src,[item]);self.assertEqual(r['alterados'],2)
        self.assertEqual([x['text'] for x in S.parse(out)],['New','Product.'])
        out,r=S.correct(src,[item|{'novo':'Brand.'}]);self.assertEqual(out,src);self.assertTrue(r['pendencias'])
        out,r=S.correct(src,[item|{'status':'revisar'}]);self.assertEqual(out,src)

    def test_scope(self):
        src=cue(1,'Oldbrand works.')+cue(2,'Oldbrand works.','00:00:10,000','00:00:11,000')
        out,r=S.correct(src,[{'text':'Oldbrand works.','novo':'Newbrand works.','start':1000,'end':2000}])
        self.assertEqual([x['text'] for x in S.parse(out)],['Newbrand works.','Oldbrand works.'])

    def test_reference_and_malformed(self):
        src=cue(1,'Golden brain works.')
        ref=cue(1,'Golden Brain works.')
        self.assertEqual(S.correct(src,[],reference=ref)[0],ref)
        with self.assertRaises(ValueError):S.correct(src,[],reference=cue(1,'Golden Brain works.','00:00:03,000'))
        with self.assertRaises(ValueError):S.parse('not an srt')
        with self.assertRaises(ValueError):S.correct(src,[],profile=True)

    def test_user_example_all_135_corrections(self):
        root=Path('/Users/luizmiguelmarques/Downloads')
        a=root/'RIP GOLDEN BRAIN.srt';b=root/'RIP GOLDEN BRAIN-corrigido.srt'
        if not a.exists() or not b.exists():self.skipTest('Exemplo local ausente')
        original=a.read_bytes().decode('utf-8-sig');expected=b.read_bytes().decode('utf-8-sig')
        out,report=S.correct(original,[],profile=True)
        self.assertEqual(report['alterados'],135)
        self.assertEqual([c['text'] for c in S.parse(out)],[c['text'] for c in S.parse(expected)])
        self.assertEqual([(c['id'],c['tc']) for c in S.parse(original)],[(c['id'],c['tc']) for c in S.parse(out)])
        self.assertEqual(report['blocos'],1526)

if __name__=='__main__':unittest.main()
