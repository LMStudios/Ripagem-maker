import base64
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from plataforma import armazenamento as S, ml_core as M, notificacoes as N


class NotificationTests(unittest.TestCase):
    def test_opt_in_persists_and_preserves_other_settings(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(S, 'CONFIG', Path(folder) / 'ajustes.json'):
            S.write_config({'pasta_principal': '/originais'})
            self.assertFalse(N.settings()['ativo'])
            self.assertFalse(N.enqueue('Notificação desativada'))
            self.assertTrue(N.settings(True)['ativo'])
            self.assertEqual(S.read()['pasta_principal'], '/originais')
            with self.assertRaises(ValueError):
                N.settings('false')
            self.assertTrue(N.settings()['ativo'])
            self.assertFalse(N.settings(False)['ativo'])

    def test_short_and_cancelled_tasks_are_quiet(self):
        with patch.object(N, 'enqueue') as send:
            N.finished('Prévia', 'concluido', N.MIN_SECONDS - .1)
            N.finished('Prévia', 'cancelado', 60)
            send.assert_not_called()

    def test_pending_and_failed_tasks_are_not_announced_as_success(self):
        with patch.object(N, 'enqueue') as send:
            N.finished('Ripagem automática', 'concluido', 30, {'pendencia': 'Detalhe sensível'})
            self.assertIn('precisa de atenção', send.call_args.args[0])
            self.assertNotIn('Detalhe sensível', send.call_args.args[0])
            N.finished('Vozes', 'concluido', 20, {'resultados': [{'erro': 'Teste'}]})
            self.assertIn('precisa de atenção', send.call_args.args[0])
            N.finished('XML', 'erro', 10)
            self.assertIn('interrompida por um erro', send.call_args.args[0])

    def test_ripagem_notifies_even_when_a_resumed_job_finishes_fast(self):
        job = M.Job('ripagem_automatica', 'Ripagem automática', None)
        job.finished = job.created + .1
        job.status = 'concluido'
        with patch.object(N, 'enqueue') as send:
            N.queued_job(job)
            self.assertIn('Tarefa concluída', send.call_args.args[0])

    def test_long_job_uses_completion_hook_even_without_browser_polling(self):
        ready = threading.Event()
        release = threading.Event()
        notice = threading.Event()

        def task(job):
            ready.set()
            release.wait(2)

        def sent(message):
            self.assertIn('Renderização de montagem', message)
            self.assertNotIn('nome-do-cliente.mp4', message)
            notice.set()

        with patch.object(M, 'save_finished_jobs'), patch.object(M, 'save_active_jobs'), patch.object(N, 'enqueue', side_effect=sent):
            job = M.submit('render', 'nome-do-cliente.mp4', task, 'render')
            self.assertTrue(ready.wait(2))
            job.created -= N.MIN_SECONDS
            release.set()
            self.assertTrue(notice.wait(2))

    def test_message_is_passed_as_data_on_both_platforms(self):
        message = 'Preço de áudio: R$ 59,90 "teste"'
        with patch.object(N.sys, 'platform', 'darwin'):
            argv, _ = N.command(message)
            self.assertEqual(argv[-1], message)
            self.assertNotIn(message, argv[2])
        with patch.object(N.sys, 'platform', 'win32'):
            argv, kwargs = N.command(message)
            self.assertIn('ShowBalloonTip', base64.b64decode(argv[-1]).decode('utf-16-le'))
            self.assertEqual(json.loads(kwargs['input']), message)
            self.assertNotIn(message, argv)
