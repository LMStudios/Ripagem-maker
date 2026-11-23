from pathlib import Path
import importlib.util,shutil,subprocess,json,zipfile,sys
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'distribuicao/pacotes/Aplicativo-Windows/Ripagem Maker'
OUT.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('pack',ROOT/'distribuicao/empacotar.py');P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)
files=[(p,p.relative_to(ROOT)) for p in P.files()]
files +=[(ROOT/'distribuicao'/n,Path(n)) for n in ('iniciar.py','requirements.txt')]
files +=[(ROOT/'distribuicao/windows'/n,Path(n)) for n in ('desktop_boot.py','desktop_win.py')]
for source,name in files:
 dest=OUT/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
(OUT/'manifest.json').write_text(json.dumps([str(n).replace('\\','/') for _,n in files]+['manifest.json']))
zig=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/tmp/ripagem-cross-tools/ziglang/zig')
from windows_icon import resource
icon_resource=resource(zig)
subprocess.run([str(zig),'cc','-target','x86_64-windows-gnu','-O2','-municode','-Wl,--subsystem,windows',str(ROOT/'distribuicao/windows/launcher.c'),str(icon_resource),'-o',str(OUT/'Ripagem Maker.exe'),'-luser32','-lshell32','-ladvapi32'],check=True)
(OUT/'LEIA-ME.txt').write_text('''RIPAGEM MAKER — Windows 10/11 de 64 bits (x64)
Extraia TODO o ZIP em uma pasta local com permissão de gravação.
Abra Ripagem Maker.exe. Não mova somente o EXE: os arquivos ao lado são necessários.
Na primeira abertura, clique Abrir ou Usar pasta já instalada para preservar os trabalhos.
Se usar uma pasta anterior, feche a versão antiga antes; somente o código distribuído será atualizado.
Pré-requisitos: Python 3.12 de 64 bits com Tcl/Tk e pip (python.org), FFmpeg com ffprobe,
e Microsoft Edge WebView2 Runtime. A primeira abertura instala dependências pela internet.
FFmpeg: winget install --id Gyan.FFmpeg -e
WebView2: https://developer.microsoft.com/microsoft-edge/webview2/
Configure sua chave em Ajustes → Integrações e APIs.
Ao fechar a janela, os processos iniciados por ela são encerrados. Não feche durante uma tarefa.
O executável não tem assinatura comercial. Compilado no Mac para Windows x64;
a execução e a interface ainda precisam ser validadas em um PC Windows.
Sem chaves, vídeos ou trabalhos do autor. Não é um instalador autossuficiente.
''')
archive=ROOT/'distribuicao/pacotes/Ripagem-Maker-App-Windows.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for name in sorted({n.as_posix() for _,n in files}|{'manifest.json','Ripagem Maker.exe','LEIA-ME.txt'}):
  z.write(OUT/name,'Ripagem Maker/'+name)
print(archive)
