"""Publicação completa: app Mac arm64, instalador Windows x64 e atualização opcional.
Executar no Mac Apple Silicon com o ambiente Electron instalado.
"""
import hashlib,json,platform,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def main():
    if platform.system()!='Darwin' or platform.machine()!='arm64':
        raise SystemExit('Prepare o app Mac completo em um Mac Apple Silicon. O Windows pode ser gerado separadamente com npm run build:windows em electron.')
    version=(ROOT/'VERSION').read_text().strip();shell=ROOT/'electron';packages=ROOT/'distribuicao/pacotes';dest=packages/('Ripagem-Maker-'+version)
    package=shell/'package.json';settings=json.loads(package.read_text());settings['build']['artifactName']='Ripagem-Maker-'+version+'-Mac-${arch}.${ext}';package.write_text(json.dumps(settings,ensure_ascii=False,indent=2)+'\n')
    # Somente a cópia de código gerada é recriada. O runtime e os dados do usuário são preservados.
    code=shell/'engine/code'
    if code.exists():shutil.rmtree(code)
    prepare=[sys.executable,str(shell/'scripts/prepare_engine.py')]
    if not (shell/'engine/bin/ripagem-engine/ripagem-engine').is_file():prepare+=['--freeze']
    subprocess.run(prepare,cwd=ROOT,check=True)
    subprocess.run(['npm','run','build:mac'],cwd=shell,check=True)
    subprocess.run(['npm','run','build:windows'],cwd=shell,check=True)
    subprocess.run([sys.executable,str(ROOT/'distribuicao/gerar_atualizacao.py')],cwd=ROOT,check=True)
    wanted=[packages/'Electron'/f'Ripagem-Maker-{version}-Mac-arm64.zip',packages/'Electron'/f'Ripagem-Maker-{version}-Windows-x64.exe',packages/f'Ripagem-Maker-Atualizacao-{version}.zip']
    if any(not p.is_file() or not p.stat().st_size for p in wanted):raise RuntimeError('Publicação incompleta: é obrigatório ter os dois executáveis da mesma versão.')
    dest.mkdir(exist_ok=True)
    for f in wanted:shutil.copy2(f,dest/f.name)
    shutil.copy2(wanted[2].with_suffix('.latest.json'),dest/'latest.json')
    (dest/'LEIA-ME.txt').write_text(instructions(version))
    (dest/'SHA256SUMS.txt').write_text(''.join(hashlib.file_digest(f.open('rb'),'sha256').hexdigest()+'  '+f.name+'\n' for f in sorted(dest.iterdir()) if f.is_file() and f.name!='SHA256SUMS.txt'))
    print('Pacotes completos preparados em '+str(dest)+'. Ainda é necessário enviar ao Drive e confirmar o upload.')

def instructions(version):
    return f'''Ripagem Maker {version}

MAC COM CHIP APPLE (M1, M2, M3, M4 ou posterior / arm64)
Descompacte Ripagem-Maker-{version}-Mac-arm64.zip e arraste Ripagem Maker Electron.app para Aplicativos. Feche a versão anterior antes de abrir a nova.

WINDOWS 10/11 DE 64 BITS (x64)
Execute Ripagem-Maker-{version}-Windows-x64.exe e siga o instalador.

Os dois pacotes completos incluem o motor Python e FFmpeg. Os modelos de transcrição local são baixados no primeiro uso. No Windows, o componente oficial do Microsoft Visual C++ pode ser solicitado se ainda não estiver instalado.

ATUALIZAÇÃO OPCIONAL PARA QUEM JÁ TEM O APP
Use Ripagem-Maker-Atualizacao-{version}.zip em Ajustes → Atualizações. Esse ZIP é uma alternativa aos instaladores completos.

Os dados e as chaves existentes são preservados. Cada colega configura suas próprias integrações em Ajustes. Os pacotes não incluem projetos, vídeos ou chaves do autor.
A edição Mac deste pacote é para chip Apple; não é uma edição Intel. Os aplicativos têm assinatura local no Mac e não possuem assinatura comercial/notarização.

Validação: verificação do conteúdo dos pacotes e abertura do motor incluído no Mac. O instalador Windows foi compilado no Mac; instalação e execução em Windows real ainda precisam de homologação.
'''

if __name__=='__main__':main()
