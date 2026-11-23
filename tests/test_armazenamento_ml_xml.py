import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
from plataforma import armazenamento as S,ml_core as M
from plataforma import ml_premiere as XML

class StorageTests(unittest.TestCase):
    def test_switch_reset_and_old_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();legacy={k:root/('old-'+k) for k in S.SUB}
            for d in legacy.values():d.mkdir()
            (legacy['fatiador']/'Trabalho antigo').mkdir();(legacy['montagens']/'old.xml').write_text('old')
            with patch.object(S,'CONFIG',root/'config.json'),patch.object(S,'LEGACY',legacy):
                first=root/'Destino com espaços';S.save(str(first));(S.current('montagens')/'one.xml').write_text('one')
                job=S.current('fatiador')/'Novo trabalho';job.mkdir()
                S.save(str(root/'Outro destino'))
                self.assertEqual(S.resolve('montagens','one.xml'),first/'Montagens/one.xml')
                self.assertEqual(S.resolve('montagens','old.xml'),legacy['montagens']/'old.xml')
                self.assertTrue(S.is_job(S.job_folder('Novo trabalho')))
                self.assertTrue(S.is_job(S.job_folder('Trabalho antigo')))
                S.save('');self.assertEqual(S.current('montagens'),legacy['montagens'])
                self.assertTrue(S.resolve('montagens','one.xml').exists())
                with self.assertRaises(ValueError):S.resolve('fatiador','../segredo')
                with self.assertRaises(ValueError):S.job_folder('/qualquer/coisa')
                with self.assertRaises(ValueError):S.save('pasta-relativa')

class MLXMLTests(unittest.TestCase):
    def test_editable_source_clips_without_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);infos={}
            for key in ('lead','body'):
                folder=root/key;folder.mkdir();shutil.copy('tests/fixtures/auditoria.mp4',folder/'original.mp4')
                info=M.probe(folder/'original.mp4');infos[key]={'probe':info,'arquivo':'original.mp4','nome':key}
            spec={'lead':{'video':'lead','inicio':1,'fim':3},'body':{'video':'body','inicio':5,'fim':8},'opcoes':{'entrega':'xml'}}
            with patch.object(M,'read_meta',side_effect=lambda v:infos[v]),patch.object(M,'vdir',side_effect=lambda v:root/v),patch.object(M,'OUT_DIR',root),patch.object(M,'run_proc') as render:
                result=M.render_job(M.Job('xml','Teste',None),spec)
                self.assertIsNone(result['arquivo']);render.assert_not_called()
                seq=ET.parse(root/result['xml']).find('sequence');fps=infos['body']['probe']['fps']
                clips=seq.findall('./media/video/track/clipitem');audio=seq.findall('./media/audio/track/clipitem')
                self.assertEqual(len(clips),2);self.assertEqual(len(audio),2)
                self.assertEqual(clips[0].findtext('start'),'0');self.assertEqual(clips[1].findtext('start'),str(round(2*fps)))
                self.assertEqual(clips[1].findtext('in'),str(round(5*fps)))
                self.assertEqual(seq.findtext('duration'),str(round(2*fps)+round(3*fps)))
                self.assertIn('/lead/original.mp4',clips[0].findtext('file/pathurl'))
                self.assertIn('/body/original.mp4',clips[1].findtext('file/pathurl'))
                bad=dict(spec,body={'video':'body','inicio':10,'fim':9000})
                with self.assertRaises(ValueError):XML.export(bad,root,'bad',M.vdir)

class StorageHTTPTests(unittest.TestCase):
    def test_live_switch_preserves_old_work_and_refuses_busy(self):
        import threading
        import requests
        from http.server import ThreadingHTTPServer
        import app
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();legacy={k:root/('old-'+k) for k in S.SUB}
            for d in legacy.values():d.mkdir()
            old=legacy['fatiador']/'Antigo';old.mkdir();(old/'resumo.json').write_text('{}');(old/'transcricao_bruta.json').write_text('{}')
            (legacy['montagens']/'antes.xml').write_text('xml antigo')
            with patch.object(S,'CONFIG',root/'config.json'),patch.object(S,'LEGACY',legacy),patch.object(M,'OUT_DIR',legacy['montagens']),patch.object(M,'VID_DIR',legacy['videos']),patch.object(M,'JOBS',{}):
                server=ThreadingHTTPServer(('127.0.0.1',0),app.H);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
                try:
                    job=M.Job('render','Bloqueio de teste',None);M.JOBS[job.id]=job
                    self.assertEqual(requests.post(base+'/api/ajustes',json={'pasta_principal':str(root/'Novo')}).status_code,409)
                    M.JOBS.clear();r=requests.post(base+'/api/ajustes',json={'pasta_principal':str(root/'Novo')});self.assertEqual(r.status_code,200,r.text)
                    self.assertEqual(M.OUT_DIR,root/'Novo/Montagens')
                    self.assertIn('Antigo',requests.get(base+'/fatiador/salvos').json()['pastas'])
                    self.assertEqual(requests.get(base+'/media/out/antes.xml').text,'xml antigo')
                    media = base+'/media/out/antes.xml'
                    suffix = requests.get(media,headers={'Range':'bytes=-3'},timeout=3)
                    self.assertEqual((suffix.status_code,suffix.content,suffix.headers['Content-Range']),
                                     (206,b'igo','bytes 7-9/10'))
                    outside = requests.get(media,headers={'Range':'bytes=12-'},timeout=3)
                    self.assertEqual((outside.status_code,outside.content,outside.headers['Content-Range']),
                                     (416,b'','bytes */10'))
                    multipart = requests.get(media,headers={'Range':'bytes=0-1,8-9'},timeout=3)
                    self.assertEqual((multipart.status_code,multipart.content),(200,b'xml antigo'))
                    self.assertEqual(requests.post(base+'/fatiador/reabrir',json={'folder':'Antigo'}).status_code,200)
                finally:server.shutdown();server.server_close();thread.join()
