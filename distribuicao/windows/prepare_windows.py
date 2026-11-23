"""Prepara dependências sem abrir o app; chamado pelo instalador gráfico."""
import importlib.util,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('starter',root/'iniciar.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
s.ensure_runtime()
marker=s.ENV/'desktop-instalado-v1'
if not s.dependencies_ready(marker,desktop=True):
 subprocess.run([str(s.PY),'-m','pip','install','-r',str(root/'requirements.txt'),'pywebview>=5,<7'],check=True,creationflags=subprocess.CREATE_NO_WINDOW)
marker.write_text(s.dependency_fingerprint(desktop=True))
