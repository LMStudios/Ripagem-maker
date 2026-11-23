import io
import json
import unittest
from unittest.mock import patch

import test_workflow_studio as studio
from plataforma import ml_core as M, visuais as V, trocas_api as TA, armazenamento as S
import shutil
import tempfile
import unicodedata
from pathlib import Path
from plataforma import trocas as T, deteccao_visual as D, legendas as L


class FriendlyErrorTests(unittest.TestCase):
    def test_user_messages_pass_and_unexpected_errors_become_clear(self):
        job = M.Job('teste', 'Teste', None)
        self.assertEqual(M.friendly_error(ValueError('Prepare os takes.'), job), 'Prepare os takes.')
        self.assertEqual(M.friendly_error(RuntimeError('Falha do FFmpeg.'), job), 'Falha do FFmpeg.')
        try:
            None.get('x')
        except AttributeError as error:
            message = M.friendly_error(error, job)
        self.assertIn('Erro inesperado', message)
        self.assertNotIn('NoneType', message)
        self.assertTrue(any('AttributeError' in line for line in job.log))
        self.assertIn('espaço em disco', M.friendly_error(OSError(28, 'No space left on device')))


class FakeHandler:
    def __init__(self, body):
        raw = json.dumps(body).encode()
        self.rfile, self.headers, self.out = io.BytesIO(raw), {'Content-Length': str(len(raw))}, None

    def send(self, code, data, *a):
        self.out = (code, data)


class MalformedRequestTests(unittest.TestCase):
    setUpClass = classmethod(studio.StudioTests.setUpClass.__func__)
    tearDownClass = classmethod(studio.StudioTests.tearDownClass.__func__)
    setUp = studio.StudioTests.setUp
    tearDown = studio.StudioTests.tearDown

    def call(self, path, body):
        h = FakeHandler(dict(body, folder=self.out.name))
        with patch.object(S, 'job_folder', return_value=self.out), patch.object(S, 'is_job', return_value=True):
            TA.handle(h, path, self.out.parent)
        return h.out

    def test_wrong_types_are_refused_with_portuguese_message(self):
        for path, body in (('/fatiador/trocas/salvar', {'itens': ['x', None]}), ('/fatiador/trocas/visual-salvar', {'assets': 'x'}),
                           ('/fatiador/trocas/plano', {'product': None, 'rebuild': True}), ('/fatiador/trocas/deteccao-revisar', {'itens': [None]})):
            code, data = self.call(path, body)
            self.assertEqual(code, 400, (path, data))
            self.assertNotIn('object has no attribute', data['erro'])

    def test_take_preview_without_preparation_asks_to_prepare(self):
        state = V.load(self.out)
        state['prepared'] = None
        V.write(self.out, state)
        with self.assertRaises(ValueError):
            V.preview(M.Job('t', 't', None), self.out, 'qualquer')


def current_versions():
    """Análise feita pela versão atual da busca (refino e limites)."""
    from plataforma import visual_refino as R, deteccao_visual as DV
    return {'refino_versao': R.VERSION, 'limites_versao': DV.LIMITS_VERSION}


class MovedFolderTests(unittest.TestCase):
    """Mover a pasta ou receber o caminho com acentos em outra forma Unicode não invalida o trabalho."""
    setUpClass = classmethod(studio.StudioTests.setUpClass.__func__)
    tearDownClass = classmethod(studio.StudioTests.tearDownClass.__func__)
    setUp = studio.StudioTests.setUp
    tearDown = studio.StudioTests.tearDown
    add_audio = studio.StudioTests.add_audio
    approve = studio.StudioTests.approve
    job = studio.StudioTests.job

    def moved(self):
        target = Path(tempfile.mkdtemp()) / 'EDIÇÃO DE VÍDEOS movida'
        shutil.copytree(self.out, target, copy_function=shutil.copy2)
        self.addCleanup(shutil.rmtree, target.parent, True)
        return target

    def test_signatures_survive_moving_the_folder(self):
        self.add_audio()
        before = (V.basis(self.out), D.source_key(self.out), L.audio_signature(self.out))
        moved = self.moved()
        self.assertEqual((V.basis(moved), D.source_key(moved), L.audio_signature(moved)), before)

    def test_values_saved_by_previous_versions_are_still_valid(self):
        self.add_audio()
        src = T.source(self.out)
        stat = src.stat()
        raw, kits, months = V._basis_parts(self.out)
        for form in ('NFC', 'NFD'):
            text = unicodedata.normalize(form, str(src.resolve()))
            old_basis = T.digest([raw, kits, text, stat.st_size, stat.st_mtime_ns] + months)
            self.assertTrue(V.basis_ok(self.out, old_basis))
            old_key = T.digest([D.VERSION, text, stat.st_size, stat.st_mtime_ns, D.WIDTH])
            self.assertIn(old_key, D.legacy_keys(self.out))
        self.assertFalse(V.basis_ok(self.out, 'outra-base'))
        # Leitura de quadros gravada com a chave antiga é reaproveitada.
        old_dir = D.folder(self.out) / ('ocr_' + D.legacy_keys(self.out)[0])
        old_dir.mkdir(parents=True)
        (old_dir / 'unidade_00000.000.jsonl').write_text('{}\n')
        self.assertTrue((D.cache(self.out) / 'unidade_00000.000.jsonl').exists())
        # Transcrição do áudio final gravada com a chave antiga também.
        old_audio = L.folder(self.out) / f"audio_final_{T.digest(['audio-final-1', *L._audio_parts(self.out), str(src.resolve()), stat.st_size, stat.st_mtime_ns])}.json"
        old_audio.parent.mkdir(parents=True, exist_ok=True)
        old_audio.write_text(json.dumps({'words': [{'w': 'oi', 's': 0, 'e': .2}]}))
        self.assertEqual(L.heard_words(self.job(), self.out), [{'w': 'oi', 's': 0, 'e': .2}])


    def test_old_analysis_survives_until_the_video_is_replaced(self):
        import os, time
        self.add_audio()
        old = D.folder(self.out) / 'ocr_chave-antiga-qualquer'
        old.mkdir(parents=True)
        D.write(self.out, {'nome': 'Oldbrand', 'aliases': '', 'janela': 'apos_mencao', 'intervalos': [],
                           'analise': {'chave': 'chave-antiga-qualquer', 'nomes': ['oldbrand'], 'janela': 'apos_mencao', **current_versions()}})
        self.assertEqual(D.outdated(self.out, D.load(self.out)), '')
        self.assertTrue(D.cache(self.out).is_dir())
        # Vídeo trocado depois da leitura: fica mais novo que ela e a análise deixa de valer.
        D.write(self.out, dict(D.load(self.out), analise={'chave': 'outra-chave', 'nomes': ['oldbrand'], 'janela': 'apos_mencao', **current_versions()}))
        stale = D.folder(self.out) / 'ocr_outra-chave'
        stale.mkdir()
        os.utime(stale, ns=(1, 1))
        D.cache(self.out).rename(D.folder(self.out) / 'ocr_sem-uso')
        self.assertIn('mudou', D.outdated(self.out, D.load(self.out)))

    def test_new_analysis_compares_source_identity(self):
        self.add_audio()
        D.write(self.out, {'nome': 'Oldbrand', 'aliases': '', 'janela': 'apos_mencao', 'intervalos': [],
                           'analise': {'chave': 'x', 'fonte': T.source_identity(T.source(self.out)), 'nomes': ['oldbrand'], 'janela': 'apos_mencao', **current_versions()}})
        self.assertEqual(D.outdated(self.out, D.load(self.out)), '')
        D.write(self.out, dict(D.load(self.out), analise=dict(D.load(self.out)['analise'], fonte=[1, 2])))
        self.assertIn('mudou', D.outdated(self.out, D.load(self.out)))


class ParallelProbeTests(unittest.TestCase):
    def test_prefetch_reads_each_file_once_and_in_parallel(self):
        import threading, time, subprocess as sp
        from plataforma import media_cache as MC
        folder = Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree, folder, True)
        files = [folder / f'm{i}.mp4' for i in range(6)]
        for f in files:f.write_bytes(b'x')
        calls, active, peak, lock = [], [0], [0], threading.Lock()
        def fake_run(cmd, **kw):
            with lock:
                calls.append(cmd[-1]);active[0] += 1;peak[0] = max(peak[0], active[0])
            time.sleep(.05)
            with lock:active[0] -= 1
            return sp.CompletedProcess(cmd, 0, '{"format": {}, "streams": []}', '')
        with patch.object(MC.subprocess, 'run', fake_run):
            MC.prefetch(files + files, 'ffprobe-teste')
            MC.metadata(files[0], 'ffprobe-teste')
        self.assertEqual(sorted(calls), sorted(str(f.resolve()) for f in files))
        self.assertGreater(peak[0], 1)
        self.assertEqual(MC._PENDING, {})


if __name__ == '__main__':
    unittest.main()
