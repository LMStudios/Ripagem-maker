import functools
import tempfile
import threading
import unittest
import subprocess
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from plataforma import demandas as D,ml_core as M

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass

class HLSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        subprocess.run([M.FFMPEG,'-y','-v','error','-f','lavfi','-i','color=green:s=160x90:r=25:d=3','-f','lavfi','-i','sine=frequency=400:duration=3','-c:v','libx264','-g','25','-c:a','aac','-shortest','-hls_time','1','-hls_playlist_type','vod','-hls_segment_filename',str(cls.root/'part%03d.ts'),str(cls.root/'main.m3u8')],check=True)
        (cls.root/'master.m3u8').write_text('#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=300000\nmain.m3u8\n')
        (cls.root/'live.m3u8').write_text((cls.root/'main.m3u8').read_text().replace('#EXT-X-ENDLIST',''))
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(cls.root)))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.url=f'http://127.0.0.1:{cls.server.server_port}/'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.tmp.cleanup()
    def test_download_hls_and_master_as_local_mp4(self):
        for manifest in ('main.m3u8','master.m3u8'):
            with self.subTest(manifest=manifest),tempfile.TemporaryDirectory() as tmp,patch.object(M,'vdir',side_effect=lambda vid:Path(tmp)/vid):
                job=M.Job('hls_test','Local HLS',None);vid=D.download(job,self.url+manifest,'VSL base')
                file=Path(tmp)/vid/'original.mp4';self.assertTrue(file.is_file());self.assertAlmostEqual(M.probe(file)['duracao'],3,delta=.15)
                self.assertFalse(list(file.parent.glob('*.partial.mp4')));self.assertTrue((file.parent/'meta.json').exists())
    def test_live_stream_and_cancellation_leave_no_partial_job(self):
        for cancelled in (False,True):
            with tempfile.TemporaryDirectory() as tmp,patch.object(M,'vdir',side_effect=lambda vid:Path(tmp)/vid):
                job=M.Job('hls_test','Local HLS',None);job.cancel=cancelled
                with self.assertRaises(M.Cancelled if cancelled else ValueError):D.download(job,self.url+'live.m3u8')
                self.assertEqual(list(Path(tmp).iterdir()),[])
