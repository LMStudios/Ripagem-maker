from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from plataforma import deteccao_visual as detection


class EarlyVisualCoverageTests(TestCase):
    def test_early_coverage_requires_per_project_choice_and_an_approved_hit(self):
        with TemporaryDirectory() as directory:
            project = Path(directory)
            approved = {'id': 'early', 'inicio_ms': 1100, 'fim_ms': 1600,
                        'status': 'aprovado', 'motivo': 'Rótulo encontrado'}
            suggestion = dict(approved, id='suggestion', inicio_ms=2300, fim_ms=2900, status='sugerido')
            detection.write(project, {'nome': 'Oldbrand', 'janela': 'apos_mencao', 'intervalos': [approved, suggestion]})
            with patch.object(detection, 'outdated', return_value=''), \
                 patch('plataforma.visuais.first_product_mention', return_value=3900), \
                 patch.object(detection, 'view', side_effect=lambda out, state: state):
                previous = detection.coverage_signature(project)
                self.assertEqual(detection.coverage_rows(project), [])
                with self.assertRaises(ValueError):
                    detection.config(project, {'cobrir_antes_da_mencao': 'sim'})
                detection.config(project, {'cobrir_antes_da_mencao': True})
                self.assertNotEqual(detection.coverage_signature(project), previous)
                rows = detection.coverage_rows(project)
                self.assertEqual([(r['start'], r['end']) for r in rows], [(1100, 1600)])
                self.assertEqual(rows[0]['limite_inicio_ms'], 0)
                detection.config(project, {'cobrir_antes_da_mencao': False})
                self.assertEqual(detection.coverage_signature(project), previous)
                self.assertEqual(detection.coverage_rows(project), [])
