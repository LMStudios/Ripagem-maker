"""A publicação padrão sempre inclui os executáveis completos de Mac e Windows."""
import subprocess,sys
from pathlib import Path
subprocess.run([sys.executable,str(Path(__file__).with_name('gerar_executaveis.py'))],check=True)
