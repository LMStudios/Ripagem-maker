import sys,unittest
from plataforma import ml_core as M
class ProcessDiagnosticTests(unittest.TestCase):
 def test_missing_module_reports_real_cause_instead_of_bootloader(self):
  text="Traceback:\nModuleNotFoundError: No module named 'wave'\n[PYI-25851:ERROR] Failed to execute script 'engine_entry' due to unhandled exception!"
  self.assertIn('wave',M.process_error(text,1));self.assertNotIn('PYI-',M.process_error(text,1))
 def test_flooded_stderr_does_not_deadlock_stdout(self):
  j=M.Job('test','test',None);lines=[]
  code="import sys;sys.stderr.write('warning\\n'*30000);sys.stderr.flush();print('PROGRESS 1',flush=True)"
  errors=M.run_proc(j,[sys.executable,'-c',code],lines.append)
  self.assertEqual(lines,['PROGRESS 1']);self.assertLessEqual(len(errors.splitlines()),80);self.assertIsNone(j.proc)
 def test_process_exception_retains_diagnostic_log(self):
  j=M.Job('test','test',None)
  with self.assertRaisesRegex(RuntimeError,'wave'):
   M.run_proc(j,[sys.executable,'-c',"import sys;sys.stderr.write(\"ModuleNotFoundError: No module named 'wave'\\n[PYI-1:ERROR] Failed\\n\");sys.exit(1)"])
  self.assertTrue(any('ModuleNotFoundError' in line for line in j.log));self.assertIsNone(j.proc)
 def test_non_frozen_error_remains_understandable(self):
  self.assertEqual(M.process_error('RuntimeError: arquivo inválido\n',1),'RuntimeError: arquivo inválido')
