"""Empacota o instalador .cmd usando o mesmo fluxo gráfico do instalador EXE."""
from pathlib import Path
import subprocess,zipfile,io,struct,hashlib
ROOT=Path(__file__).resolve().parent.parent
subprocess.run(['python3',str(ROOT/'distribuicao/build_windows_setup.py')],check=True)
exe=(ROOT/'distribuicao/pacotes/Instalar Ripagem Maker Windows.exe').read_bytes()
assert exe[-8:]==b'RMSETUP1'
length=struct.unpack('<Q',exe[-16:-8])[0]
archive=ROOT/'distribuicao/pacotes/Ripagem-Maker-Instalador-CMD-Windows.zip'
with zipfile.ZipFile(io.BytesIO(exe[-16-length:-16])) as source,zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as dest:
 for name in source.namelist():dest.writestr('Instalador Ripagem Maker/'+name,source.read(name))
 launcher=(ROOT/'distribuicao/windows/Instalar Ripagem Maker.cmd').read_text()
 dest.writestr('Instalador Ripagem Maker/Instalar Ripagem Maker.cmd',launcher.replace('\r\n','\n').replace('\n','\r\n'))
 dest.writestr('Instalador Ripagem Maker/COMECE AQUI.txt','''RIPAGEM MAKER — instalação automática no Windows 10/11 x64
1. Extraia TODO o ZIP em uma pasta local.
2. Abra Instalar Ripagem Maker.cmd com dois cliques.
3. Na janela que aparecer, leia a autorização e clique em Instalar tudo.
O instalador prepara Python 3.12, FFmpeg, WebView2 e as dependências Python.
Precisa de internet; o Windows pode solicitar autorização durante a instalação.
Se faltar WinGet, atualize o Instalador de Aplicativo pela Microsoft Store e tente novamente.
Ao terminar, use o atalho Ripagem Maker criado na Área de Trabalho.
A chave do AssemblyAI pode ser configurada em Ajustes → Integrações e APIs.
Feche qualquer versão anterior antes de instalar. Configurações e trabalhos da instalação
no AppData são preservados. Para aproveitar outra pasta, use Usar pasta já instalada no app.
Logs: %LOCALAPPDATA%\\Ripagem Maker Installer
O script não altera permanentemente a política de execução do PowerShell.
Pacote preparado no Mac; a instalação completa ainda precisa ser validada em um PC Windows.
''')
archive.with_suffix('.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
print(archive)
