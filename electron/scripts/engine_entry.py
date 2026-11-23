"""Entry point congelado: código e dados ficam fora do executável, permitindo atualização."""
import os,sys,runpy
from pathlib import Path
if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1].endswith('.py'):
  script=Path(sys.argv[1]).resolve();sys.argv=sys.argv[1:];sys.path.insert(0,str(script.parent.parent));runpy.run_path(str(script),run_name='__main__');raise SystemExit()
 root=Path(sys.argv[1]).resolve()
 if not (root/'app.py').is_file():raise SystemExit('Pasta do aplicativo inválida.')
 os.chdir(root);sys.path.insert(0,str(root));sys.argv=[str(root/'app.py')]
 runpy.run_path(str(root/'app.py'),run_name='__main__')
