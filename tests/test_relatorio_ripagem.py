from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from plataforma import projetos, relatorio_ripagem as reports


class ReportTests(unittest.TestCase):
    def test_time_owner_and_revision_preserved_and_sensitive_feedback_local(self):
        with TemporaryDirectory() as root:
            out = Path(root) / 'projeto'
            out.mkdir()
            owner = {'id': str(uuid4()), 'funcao': 'editor'}
            colleague = {'id': str(uuid4()), 'funcao': 'editor'}
            project_id = str(uuid4())
            projetos.write_meta(out, projeto_id=project_id)
            report = {'medicao_encerrada': True, 'completa': True, 'app_min': 6,
                      'xml_de_revisao': True, 'xml_salvo': 'trocas/Review.xml'}
            queue = Path(root) / 'outbox'
            with patch.object(reports, 'OUTBOX', queue), patch.object(reports, 'schedule_sync'), \
                 patch.object(reports, '_visuals', return_value=({'manuais': 3}, 1)):
                reports.saved(out, owner, report, 'EV08')
                reports.saved(out, colleague, dict(report, xml_de_revisao=False, app_min=20,
                                                   xml_salvo='trocas/Final.xml'), 'EV08')
                changed = reports.feedback(out, owner, {'etapa': 'voz', 'minutos': 12, 'comentario': '/pessoal/arquivo.wav'})
                self.assertEqual(changed['resumo']['revisao'], 3)
                self.assertEqual(changed['resumo']['tempo_ripagem_ms'], 360000)
                self.assertEqual(changed['resumo']['usuario'], owner['id'])
                self.assertEqual(changed['ultimo_salvamento']['usuario'], colleague['id'])
                self.assertEqual(changed['resumo']['fora_app_ms'], 720000)
                self.assertIsNone(changed['resumo']['espera_ms'])
                self.assertIn('/pessoal/arquivo.wav', (out/reports.REPORT).read_text())
                self.assertNotIn('/pessoal/arquivo.wav', (queue/owner['id']/(project_id+'.json')).read_text())
                self.assertEqual(len(list(queue.rglob('*.json'))), 1)
                with self.assertRaises(PermissionError):
                    reports.read(out, colleague)

    def test_measured_regenerations_do_not_count_parallel_time_twice(self):
        with TemporaryDirectory() as root:
            out = Path(root)
            with patch.object(reports.armazenamento, 'is_job', return_value=True):
                reports.record_operation(out, '1', 'vozes', 'concluido', 5, inicio=100, repeticao=True)
                reports.record_operation(out, '2', 'vozes', 'erro', 5, inicio=103, repeticao=True)
                reports.record_operation(out, '3', 'visual_automatico', 'concluido', 4, inicio=103)
            stages, errors, count, rework = reports._metrics(out)
            self.assertEqual(stages, {'voz': 10000, 'takes': 4000})
            self.assertEqual(errors, {'voz': 1})
            self.assertEqual(rework, 8000)
            self.assertEqual(count, 3)
