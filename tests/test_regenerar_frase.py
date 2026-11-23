import copy
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import test_trocas_completas as base
from plataforma import trocas as T,vozes as V

class RegenerateTests(unittest.TestCase):
    setUpClass=classmethod(base.FlowTests.setUpClass.__func__)
    tearDownClass=classmethod(base.FlowTests.tearDownClass.__func__)
    setUp=base.FlowTests.setUp
    tearDown=base.FlowTests.tearDown
    job=base.FlowTests.job
    approve=base.FlowTests.approve
    add_audio=base.FlowTests.add_audio
    def options(self,rid):
        return dict(provider='elevenlabs',model='eleven_multilingual_v2',voices={'A':'voice_A'},autoriza_envio=True,row_ids=[rid],regenerar=True)
    def test_one_audio_replaced_history_retained_and_other_untouched(self):
        self.add_audio();before=T.load(self.out);first,second=before['itens'];old=copy.deepcopy(first['audio']);old_bytes=(self.out/old['fit']).read_bytes()
        before['previa']={'arquivo':'old-preview.mp4'};T.write(T.plan_path(self.out),before)
        with patch.object(V,'speech',return_value=self.tts.read_bytes()) as speech:
            result=V.generate(self.job(),self.out,self.options(first['id']),'TEST_ONLY')
        after=T.load(self.out);self.assertEqual(speech.call_count,1);self.assertEqual([r['id'] for r in result['resultados']],[first['id']])
        self.assertEqual(after['itens'][1],second);new=after['itens'][0];self.assertNotEqual(new['audio']['fit'],old['fit']);self.assertFalse(new['audio']['aprovado']);self.assertEqual(new['historico_audio'][-1],old)
        self.assertEqual((self.out/old['fit']).read_bytes(),old_bytes);self.assertNotIn('previa',after)
    def test_provider_failure_preserves_approved_audio(self):
        self.add_audio();before=T.load(self.out);rid=before['itens'][0]['id']
        with patch.object(V,'speech',side_effect=ValueError('Serviço indisponível')):
            result=V.generate(self.job(),self.out,self.options(rid),'TEST_ONLY')
        self.assertIn('erro',result['resultados'][0]);self.assertEqual(T.load(self.out),before)
    def test_invalid_scope_never_defaults_to_whole_batch(self):
        p=self.approve()
        for value in [[],None,'all',['missing'],[p['itens'][0]['id']]*2,[123]]:
            with self.subTest(value=value),self.assertRaises(ValueError):V.selected_rows(p,{'row_ids':value})
        p['itens'][0]['aprovado']=False
        with self.assertRaisesRegex(ValueError,'aprove o texto'):V.selected_rows(p,self.options(p['itens'][0]['id']))
    def test_only_target_requires_form_and_speaker_validation(self):
        p=self.approve();p['itens'][1].update(forma_pendente=True,forma_confirmada=False,speaker_pendente=True)
        self.assertEqual([r['id'] for r in V.selected_rows(p,self.options(p['itens'][0]['id']))],[p['itens'][0]['id']])
        p['itens'][0]['forma_pendente']=True
        with self.assertRaisesRegex(ValueError,'modo de uso'):V.selected_rows(p,self.options(p['itens'][0]['id']))
    def test_changed_while_queued_fails_before_paid_request(self):
        p=self.approve();rid=p['itens'][0]['id'];captured={}
        def submit(*args,**kwargs):captured['run']=args[2];return SimpleNamespace(id='fake')
        with patch.object(V.C,'key',return_value='TEST_ONLY'),patch.object(V.M,'submit',side_effect=submit):V.submit(self.out,self.options(rid))
        T.save(self.out,[{'id':rid,'novo':'Changed while queued.'}])
        with patch.object(V,'speech') as speech,self.assertRaisesRegex(ValueError,'mudou enquanto aguardava'):captured['run'](self.job())
        speech.assert_not_called()
    def test_route_cannot_expand_single_request_to_other_rows(self):
        import io,json
        from plataforma import trocas_api as API
        p=self.approve();rid=p['itens'][0]['id'];received=[]
        raw=json.dumps({'folder':'qa','id':rid,'options':{'row_ids':[r['id'] for r in p['itens']],'regenerar':False,'somente_pendentes':True}}).encode()
        h=SimpleNamespace(headers={'Content-Length':str(len(raw))},rfile=io.BytesIO(raw),send=lambda status,result:received.append((status,result)))
        fake=SimpleNamespace(to_dict=lambda:{'id':'fake'})
        with patch.object(API.S,'job_folder',return_value=self.out),patch.object(API.S,'is_job',return_value=True),patch.object(API.V,'submit',return_value=fake) as submit:
            API.handle(h,'/fatiador/trocas/regenerar-frase',self.out.parent)
        self.assertEqual(received[0][0],200);opts=submit.call_args.args[1];self.assertEqual(opts['row_ids'],[rid]);self.assertTrue(opts['regenerar']);self.assertFalse(opts['somente_pendentes'])
