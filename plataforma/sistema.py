"""Ações locais equivalentes em Windows e macOS."""
import os,sys,subprocess
from pathlib import Path
def abrir(path,revelar=False):
 path=Path(path).resolve()
 if os.name=='nt':
  if revelar and path.is_file():subprocess.Popen(['explorer.exe','/select,',str(path)])
  else:os.startfile(str(path))
 elif sys.platform=='darwin':subprocess.run(['open','-R',str(path)] if revelar and path.is_file() else ['open',str(path)],check=True)
 else:subprocess.Popen(['xdg-open',str(path.parent if revelar and path.is_file() else path)])

def revelar_entrega(out,relative):
 root=Path(out).resolve();path=(root/str(relative)).resolve()
 if not path.is_relative_to(root) or path.suffix.lower() not in ('.xml','.json') or not path.is_file():raise ValueError('Arquivo de entrega não encontrado neste trabalho.')
 abrir(path,revelar=True)
 return {'ok':True,'arquivo':str(path)}

def localizar_entrega(out,relative):
 root=Path(out).resolve();path=(root/str(relative)).resolve()
 if not path.is_relative_to(root) or path.suffix.lower() not in ('.xml','.json'):raise ValueError('Caminho de entrega inválido.')
 return {'arquivo':str(path),'pasta':str(path.parent),'nome':path.name,'existe':path.is_file() and path.stat().st_size>0}
