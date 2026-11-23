"""Recurso de ícone nativo compartilhado pelo launcher e pelo instalador Windows."""
from pathlib import Path
import shutil,subprocess
ROOT=Path(__file__).resolve().parent.parent
def resource(zig):
 build=ROOT/'distribuicao/build-windows';build.mkdir(exist_ok=True)
 shutil.copy2(ROOT/'design/logo/RipagemMaker.ico',build/'app.ico')
 (build/'app-icon.rc').write_text('1 ICON "app.ico"\n')
 obj=build/'app-icon.obj'
 subprocess.run([str(zig),'rc','/:output-format','coff','/:target','X64','/fo',obj.name,'--','app-icon.rc'],cwd=build,check=True)
 return obj
