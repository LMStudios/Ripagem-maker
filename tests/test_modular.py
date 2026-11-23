"""Versão modular: tratamento de áudio, projetos (mudança de pasta e recuperação), limpeza segura e acesso local."""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_trocas_completas as B
from plataforma import armazenamento as S
from plataforma import diagnostico as D
from plataforma import lixeira
from plataforma import limpeza as L
from plataforma import ml_core as M
from plataforma import projetos as P
from plataforma import trocas as T
from plataforma import tratamento_audio as TA


def fake_trash(bin_dir):
    def move(path):
        path = Path(path)
        target = Path(bin_dir) / (path.name + '_' + str(time.time_ns()))
        shutil.move(str(path), str(target))
        return {'caminho': str(path), 'destino': 'lixeira'}
    return move


class Isolated(unittest.TestCase):
    """Ajustes, diário de mudanças e Lixeira em pastas temporárias: nada toca a configuração real."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        legacy = {k: self.base / 'legacy' / k for k in S.LEGACY}
        for v in legacy.values():
            v.mkdir(parents=True)
        self.bin = self.base / 'lixeira'
        self.bin.mkdir()
        for p in (patch.object(S, 'CONFIG', self.base / 'ajustes.json'), patch.object(S, 'LEGACY', legacy),
                  patch.object(P, 'JOURNAL', self.base / 'movimentos.json'), patch.object(L, 'HOME', self.base / 'limpeza'),
                  patch.object(lixeira, 'to_trash', fake_trash(self.bin)), patch.object(L, '_loose_temp_folders', lambda: [])):
            p.start()
            self.addCleanup(p.stop)
        self.root = legacy['fatiador']

    def project(self, name='VSL_01_NovaPure_2026-01-01_120000', with_media=True):
        out = self.root / name
        (out / 'trocas/encaixados').mkdir(parents=True)
        (out / 'transcricao_bruta.json').write_text('{"words": []}')
        (out / '_fonte.mp4').write_bytes(b'video' * 1000)
        (out / 'trocas/encaixados/001_PRONTO.wav').write_bytes(b'audio' * 500)
        plan = {'produto': 'Old', 'produto_novo': 'NovaPure', 'itens': [], 'entrega': {'xml_absoluto': str(out / 'trocas/x.xml'), 'xml': 'trocas/x.xml'},
                'previa': {'arquivo': 'trocas/previa_atual/previa.mp4'}}
        T.write(out / 'trocas/plano.json', plan)
        url = 'file://' + str((out / 'trocas/encaixados/001_PRONTO.wav').resolve()).replace(' ', '%20')
        (out / 'trocas/x.xml').write_text(f'<xmeml><pathurl>{url}</pathurl></xmeml>')
        return out

    def job(self):
        return M.Job('teste', 'Teste', None)


class NamingAndSecurityTests(unittest.TestCase):
    def test_folder_name_has_project_product_and_date(self):
        from datetime import datetime
        self.assertEqual(P.folder_name('VSL 14 – Funil A', 'NovaPure', datetime(2026, 11, 4, 9, 5, 7)), 'VSL_14_Funil_A_NovaPure_2026-11-04_090507')
        self.assertEqual(P.folder_name('NovaPure VSL', 'NovaPure', datetime(2026, 1, 2, 3, 4, 5)), 'NovaPure_VSL_2026-01-02_030405')

    def test_only_local_pages_reach_the_engine(self):
        self.assertTrue(D.local_request({'Host': '127.0.0.1:8765'}, 8765))
        self.assertTrue(D.local_request({'Host': 'localhost:8765', 'Origin': 'http://localhost:8765'}, 8765))
        self.assertFalse(D.local_request({'Host': 'evil.example:8765'}, 8765))
        self.assertFalse(D.local_request({'Host': '127.0.0.1:8765', 'Origin': 'https://evil.example'}, 8765))
        self.assertFalse(D.local_request({'Host': '127.0.0.1:8765', 'Sec-Fetch-Site': 'cross-site'}, 8765))

    def test_xml_paths_on_windows_and_mac(self):
        text = '<pathurl>file:///C:/Users/Ana/Fatiador/P1/_fonte.mp4</pathurl><pathurl>file://localhost/C:/Users/Ana/a%20b.wav</pathurl><pathurl>file://servidor/v/x.mp4</pathurl>'
        self.assertEqual(P.pathurls(text, True), {'C:\\Users\\Ana\\Fatiador\\P1\\_fonte.mp4', 'C:\\Users\\Ana\\a b.wav', '\\\\servidor\\v\\x.mp4'})
        self.assertEqual(P.pathurls('<pathurl>file:///Users/a/EDI%C3%87%C3%83O/x.wav</pathurl>'), {'/Users/a/EDIÇÃO/x.wav'})

    def test_logs_hide_keys_and_emails(self):
        text = D.redact('xi-api-key: sk_abcdefghijklmnop1234 Authorization: Bearer eyJabcdefghijkl.mnopqrstuvwxyz assembly 0123456789abcdef0123456789abcdef pessoa@exemplo.com AIzaSyA12345678901234567890')
        for secret in ('sk_abcdefghijklmnop1234', 'eyJabcdefghijkl', '0123456789abcdef0123456789abcdef', 'pessoa@exemplo.com', 'AIzaSyA1234'):
            self.assertNotIn(secret, text)

    def test_atomic_write_keeps_previous_version_on_failure(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'plano.json'
            D.atomic_text(target, 'versão válida')
            with patch('os.fsync', side_effect=OSError('disco cheio')):
                with self.assertRaises(OSError):
                    D.atomic_text(target, 'incompleto')
            self.assertEqual(target.read_text(encoding='utf-8'), 'versão válida')
            self.assertEqual([p.name for p in Path(d).iterdir()], ['plano.json'])


class TreatmentTests(B.FlowTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 0,5 s de silêncio + 1 s de voz simulada + final suave + 0,4 s de silêncio, com ruído leve.
        cls.padded = cls.root / 'padded.wav'
        subprocess.run([M.FFMPEG, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'anoisesrc=d=2:c=pink:a=0.002', '-f', 'lavfi', '-i',
                        'sine=frequency=300:duration=1.1', '-filter_complex', '[1:a]afade=t=out:st=0.9:d=0.2,adelay=500|500,apad=whole_dur=2[v];[0:a][v]amix=inputs=2:normalize=0',
                        '-ar', '48000', str(cls.padded)], check=True)

    def add_padded_audio(self):
        self.approve()
        folder = self.out / 'trocas' / 'raw'
        folder.mkdir()
        for row in T.load(self.out)['itens']:
            file = folder / (row['id'] + '.wav')
            shutil.copy(self.padded, file)
            result = T.fit(self.job(), self.out, row, file)
            T.record_audio(self.out, row['id'], result)
            T.approve_audio(self.out, row['id'], result['texto_hash'])

    def test_treatment_trims_edges_keeps_original_resets_approval_and_can_be_undone(self):
        self.add_padded_audio()
        before_signature = T.preview_signature(self.out)
        rid = T.load(self.out)['itens'][0]['id']
        raw_before = T.load(self.out)['itens'][0]['audio']['raw']
        result = TA.treat_rows(self.job(), self.out, [rid], {'silencio': True, 'ruido': True, 'intensidade': 30})
        self.assertEqual(len(result['tratados']), 1)
        audio = T.load(self.out)['itens'][0]['audio']
        report = audio['tratamento']
        self.assertGreater(report['removido_inicio_ms'], 300)
        self.assertLess(report['duracao_depois_s'], report['duracao_antes_s'])
        self.assertGreater(report['duracao_depois_s'], 1.1)  # voz e final suave preservados
        self.assertEqual(audio['raw'], raw_before)
        self.assertTrue((self.out / raw_before).is_file())
        self.assertFalse(audio['aprovado'])
        self.assertNotEqual(T.preview_signature(self.out), before_signature)  # prévia/entrega ficam desatualizadas
        again = TA.treat_rows(self.job(), self.out, [rid], {'silencio': True, 'ruido': True, 'intensidade': 30})
        self.assertEqual(again['tratados'], [])
        self.assertEqual(again['ignorados'][0]['motivo'], 'Já tratado com estas opções.')
        stronger = TA.treat_rows(self.job(), self.out, [rid], {'silencio': True, 'ruido': True, 'intensidade': 60})
        self.assertEqual(stronger['tratados'][0]['tratamento']['origem'], raw_before)  # nunca trata o já tratado
        TA.undo_row(self.job(), self.out, rid)
        audio = T.load(self.out)['itens'][0]['audio']
        self.assertNotIn('tratamento', audio)
        self.assertNotIn('fonte_preparo', audio)
        self.assertEqual(audio['raw'], raw_before)

    def test_xml_uses_treated_audio_and_stays_in_sync(self):
        self.add_padded_audio()
        ids = [r['id'] for r in T.load(self.out)['itens']]
        TA.treat_rows(self.job(), self.out, ids, {'silencio': True, 'ruido': False})
        for row in T.load(self.out)['itens']:
            T.approve_audio(self.out, row['id'], row['audio']['texto_hash'])
        exported = T.export_xml(self.out)
        xml = (self.out / exported['xml']).read_text()
        for row in T.load(self.out)['itens']:
            self.assertIn(Path(row['audio']['fit']).name, xml)
            self.assertEqual(T.probe(self.out / row['audio']['fit'])['duration'], T.probe(self.out / row['audio']['fit'])['duration'])
            self.assertAlmostEqual(T.probe(self.out / row['audio']['fit'])['duration'], row['audio']['alvo_s'], delta=0.05)

    def test_internal_pauses_are_not_removed(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d) / 'a.wav', Path(d) / 'b.wav'
            subprocess.run([M.FFMPEG, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=300:duration=0.5', '-f', 'lavfi', '-i', 'sine=frequency=300:duration=0.5',
                            '-filter_complex', '[0:a]adelay=300|300[a];[1:a]adelay=1600|1600[b];[a][b]amix=inputs=2:normalize=0,apad=whole_dur=2.6', '-ar', '48000', str(src)], check=True)
            report = TA.process(None, src, dst, {'silencio': True})
            # Fala de 0,3 a 2,1 s com pausa de 0,8 s no meio: a pausa interna fica.
            self.assertGreater(report['duracao_depois_s'], 1.75)
            self.assertLess(report['duracao_depois_s'], 2.35)


class MoveTests(Isolated):
    def test_move_copies_verifies_updates_references_and_trashes_origin(self):
        out = self.project()
        dest = self.base / 'Outro disco'
        result = P.move_job(self.job(), out.name, str(dest))
        final = (dest / out.name).resolve()
        self.assertTrue((final / '_fonte.mp4').is_file())
        self.assertFalse(out.exists())
        plan = json.loads((final / 'trocas/plano.json').read_text())
        self.assertEqual(plan['entrega']['xml_absoluto'], str(final / 'trocas/x.xml'))
        self.assertEqual(result['xmls_a_refazer'], ['trocas/x.xml'])
        self.assertIn(str(dest.resolve()), [str(Path(p)) for p in S.read()['pastas_projetos']])
        self.assertEqual(P.find(out.name).resolve(), final.resolve())
        self.assertEqual(json.loads(P.JOURNAL.read_text())[-1]['etapa'], 'concluido')

    def test_refuses_without_space_inside_project_or_while_busy(self):
        out = self.project()
        with self.assertRaisesRegex(ValueError, 'fora do próprio projeto'):
            P.check_destination(out.name, str(out / 'sub'))
        with patch('shutil.disk_usage', return_value=SimpleNamespace(free=10)):
            with self.assertRaisesRegex(ValueError, 'Espaço insuficiente'):
                P.check_destination(out.name, str(self.base / 'x'))
        busy = M.Job('render', 'Render', None, out=str(out))
        busy.status = 'executando'
        M.JOBS[busy.id] = busy
        self.addCleanup(M.JOBS.pop, busy.id, None)
        with self.assertRaisesRegex(ValueError, 'tarefa usando este projeto'):
            P.check_destination(out.name, str(self.base / 'x'))

    def test_failed_copy_check_keeps_origin_intact(self):
        out = self.project()
        with patch.object(P, '_digest', side_effect=['a', 'b'] * 10):
            with self.assertRaisesRegex(RuntimeError, 'não confere'):
                P.move_job(self.job(), out.name, str(self.base / 'dest'))
        self.assertTrue((out / '_fonte.mp4').is_file())
        self.assertFalse((self.base / 'dest' / out.name).exists())
        self.assertFalse(any((self.base / 'dest').iterdir()))

    def test_recovery_after_interruption(self):
        out = self.project('A_2026-01-01_000000')
        partial = self.base / 'dest' / ('.' + out.name + '.copiando')
        (partial / 'trocas').mkdir(parents=True)
        other = self.project('B_2026-01-01_000000')
        final = self.base / 'dest2' / other.name
        shutil.copytree(other, final)
        P._save_journal([{'id': '1', 'origem': str(out), 'destino': str(self.base / 'dest' / out.name), 'parcial': str(partial), 'etapa': 'copiando'},
                         {'id': '2', 'origem': str(other), 'destino': str(final), 'parcial': '', 'etapa': 'copiado'}])
        report = P.recover_moves()
        self.assertFalse(partial.exists())
        self.assertTrue(out.exists())  # cópia interrompida: o original fica
        self.assertFalse(other.exists())  # cópia já conferida: conclui e manda a origem para a Lixeira
        self.assertTrue(final.is_dir())
        self.assertEqual(len(report), 2)


class CleanupTests(Isolated):
    def test_plan_protects_referenced_favorites_and_recent(self):
        out = self.project().resolve()
        old_preview = out / 'trocas/previa_antiga'
        old_preview.mkdir()
        (old_preview / 'previa.mp4').write_bytes(b'x' * 100)
        current = out / 'trocas/previa_atual'
        current.mkdir()
        (current / 'previa.mp4').write_bytes(b'x' * 100)
        (out / 'trocas/mix-abc').mkdir()
        (out / 'trocas/mix-abc/lote0.wav').write_bytes(b'x' * 50)
        plan = L.build_plan(self.job(), {'categorias': ['previas', 'temporarios'], 'dias': 90})
        paths = {i['caminho'] for i in plan['itens']}
        self.assertIn(str(old_preview), paths)
        self.assertIn(str(out / 'trocas/mix-abc'), paths)
        self.assertNotIn(str(current), paths)
        self.assertTrue(any(p['caminho'] == str(current) for p in plan['protegidos']))
        report = L.run_plan(self.job(), plan['token'], [str(old_preview)])
        self.assertFalse(old_preview.exists())
        self.assertTrue((out / 'trocas/mix-abc').exists())  # não marcado: fica
        self.assertTrue(current.exists())
        self.assertEqual(len(report['removidos']), 1)

    def test_old_projects_need_selection_and_respect_protection(self):
        old = self.project('Antigo_2025-01-01_000000')
        fav = self.project('Favorito_2025-01-01_000000')
        P.write_meta(fav, favorito=True)
        past = time.time() - 400 * 86400
        for out in (old, fav):
            for f in out.rglob('*'):
                os.utime(f, (past, past))
        plan = L.build_plan(self.job(), {'categorias': ['projetos_antigos'], 'dias': 90})
        self.assertEqual(plan['itens'], [])  # antigo não basta: precisa ser escolhido
        listed = {o['pasta']: o['protecao'] for o in plan['projetos_antigos']}
        self.assertEqual(listed[fav.name], 'Favorito')
        plan = L.build_plan(self.job(), {'categorias': ['projetos_antigos'], 'dias': 90, 'projetos': [old.name, fav.name]})
        self.assertEqual([Path(i['caminho']).name for i in plan['itens']], [old.name])
        L.run_plan(self.job(), plan['token'], [i['caminho'] for i in plan['itens']])
        self.assertFalse(old.exists())
        self.assertTrue(fav.exists())

    def test_file_changed_after_review_is_kept(self):
        out = self.project().resolve()
        preview = out / 'trocas/previa_x'
        preview.mkdir()
        (preview / 'a.mp4').write_bytes(b'1')
        plan = L.build_plan(self.job(), {'categorias': ['previas'], 'dias': 90})
        os.utime(preview, (time.time() + 50, time.time() + 50))
        report = L.run_plan(self.job(), plan['token'], [str(preview)])
        self.assertTrue(preview.exists())
        self.assertEqual(report['ignorados'][0]['motivo'], 'Mudou desde a conferência')

    def test_project_referenced_by_another_xml_is_protected(self):
        old = self.project('Base_2025-01-01_000000')
        other = self.project('Usa_base_2026-01-01_000000')
        (other / 'trocas/y.xml').write_text('<xmeml><pathurl>file://' + str((old / '_fonte.mp4').resolve()) + '</pathurl></xmeml>')
        past = time.time() - 400 * 86400
        for f in old.rglob('*'):
            os.utime(f, (past, past))
        plan = L.build_plan(self.job(), {'categorias': ['projetos_antigos'], 'dias': 90, 'projetos': [old.name]})
        self.assertEqual(plan['itens'], [])
        self.assertIn('Citado em XML', next(o for o in plan['projetos_antigos'] if o['pasta'] == old.name)['protecao'])

    def test_automatic_cleanup_starts_disabled(self):
        self.assertFalse(S.cleanup_settings()['ativa'])
        self.assertIsNone(L.auto_cleanup())


class InterruptedJobsTests(unittest.TestCase):
    def test_running_job_is_reported_after_restart(self):
        with tempfile.TemporaryDirectory() as d:
            active = Path(d) / 'ativas.json'
            active.write_text(json.dumps([{'id': 'abc123', 'kind': 'render', 'title': 'Prévia', 'params': {'out': '/x'}, 'step': 'Renderizando'}]))
            with patch.object(M, 'ACTIVE', active), patch.object(M, 'HISTORY', Path(d) / 'hist.json'):
                restored = M.restore_interrupted_jobs()
                self.addCleanup(M.JOBS.pop, 'abc123', None)
                self.assertEqual(restored[0]['id'], 'abc123')
                self.assertEqual(M.JOBS['abc123'].status, 'erro')
                self.assertIn('fechado durante esta tarefa', M.JOBS['abc123'].error)


if __name__ == '__main__':
    unittest.main()
