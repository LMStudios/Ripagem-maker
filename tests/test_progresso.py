import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from plataforma.progresso import DownloadProgress
from plataforma import demandas as D

class ProgressTests(unittest.TestCase):
    def job(self):return SimpleNamespace(cancel=False,pct=0,progress=None,step='')
    def test_known_total(self):
        job=self.job();p=DownloadProgress(job,'VSL base',{'Content-Length':'10485760'})
        p.add(5242880);p.update(force=True)
        self.assertEqual(job.pct,.5)
        self.assertFalse(job.progress['indeterminado'])
        self.assertEqual(job.progress['bytes_recebidos'],5242880)
        self.assertIn('5.00 MB de 10.00 MB',job.step)
    def test_unknown_or_compressed(self):
        for headers in ({},{'Content-Length':'bad'},{'Content-Length':'100','Content-Encoding':'gzip'},{'Content-Length':'100','Transfer-Encoding':'chunked'}):
            job=self.job();p=DownloadProgress(job,'ML da variação 2 de 2',headers);p.add(10);p.update(force=True)
            self.assertTrue(job.progress['indeterminado'])
            self.assertIsNone(job.progress['bytes_total'])
            self.assertIn('tamanho total não informado',job.step)
    def test_updates_are_throttled(self):
        with patch('plataforma.progresso.time.monotonic',return_value=10):
            job=self.job();p=DownloadProgress(job,'VSL',{});p.add(100)
            self.assertEqual(job.progress['bytes_recebidos'],0)
            p.update(force=True);self.assertEqual(job.progress['bytes_recebidos'],100)
    def test_download_stream_with_and_without_length(self):
        for headers in ({'Content-Length':'6'},{}):
            class Response:
                def __init__(self):self.headers=headers
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def raise_for_status(self):pass
                def iter_content(self,size):yield b'abc';yield b'def'
            response=Response();session=SimpleNamespace(get=lambda *a,**k:response)
            class Session:
                def __enter__(self):return session
                def __exit__(self,*args):pass
            with tempfile.TemporaryDirectory() as tmp,patch.object(D.requests,'Session',Session),patch.object(D.M,'VID_DIR',Path(tmp)),patch.object(D.M,'probe',return_value={'duracao':1}):
                vid=D.download(self.job(),'https://example.com/video.mp4','VSL base')
                self.assertEqual((Path(tmp)/vid/'original.mp4').read_bytes(),b'abcdef')
    def test_cancel_cleans_partial(self):
        class Response:
            headers={}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def raise_for_status(self):pass
            def iter_content(self,size):yield b'partial'
        class Session:
            def __enter__(self):return SimpleNamespace(get=lambda *a,**k:Response())
            def __exit__(self,*args):pass
        job=self.job();job.cancel=True
        with tempfile.TemporaryDirectory() as tmp,patch.object(D.requests,'Session',Session),patch.object(D.M,'VID_DIR',Path(tmp)):
            with self.assertRaises(D.M.Cancelled):D.download(job,'https://example.com/video.mp4')
            self.assertEqual(list(Path(tmp).iterdir()),[])
    def test_ui_no_false_zero_percent(self):
        source=Path('plataforma/static/demandas.js').read_text();fn=source[source.index('function progressHTML('):source.index('async function demandaJobs(')]
        script='const esc=s=>String(s??" ");'+fn+'''
let html=progressHTML({status:'executando',step:'Baixando VSL · 5 MB',pct:0,progresso:{fase:'download',rotulo:'VSL base',indeterminado:true}});
if(html.includes('0%')||!html.includes('unknown'))throw Error('Percentual ficticio');
html=progressHTML({status:'executando',step:'Baixando ML · 5 MB de 10 MB',pct:.5,progresso:{fase:'download',rotulo:'ML da variação 2',indeterminado:false}});
if(!html.includes('50% desta etapa')||!html.includes('aria-valuenow="50"'))throw Error('Progresso conhecido ausente');
if(progressHTML({status:'concluido',step:'Pronto'}).includes('job-spinner'))throw Error('Spinner apos concluir');
'''
        subprocess.run(['node','-e',script],check=True)

if __name__=='__main__':unittest.main()
