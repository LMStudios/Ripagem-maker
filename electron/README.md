# Ripagem Maker Electron — edição de teste, em paralelo ao app atual

O aplicativo nativo anterior permanece instalado. O Electron tem ID próprio `local.ripagemmaker.electron`, nome próprio e não sobrescreve o app antigo. O backup de código e app anterior está em `Backups Ripagem Maker/Antes-Electron_*`, ao lado do projeto.

## Abrir

Na pasta `electron`, execute `npm ci`, `npx install-electron`, `npm start` (Node 22.12 ou superior). Em desenvolvimento usa o projeto atual. Feche o outro Ripagem Maker antes, pois ambos utilizam a porta 8765. Para testar isoladamente use `RIPAGEM_ELECTRON_PORT=18767 RIPAGEM_ENGINE_ROOT=/caminho/isolado npm start`.

A primeira instalação prepara automaticamente o código no perfil do Electron e abre a configuração da pasta principal dos materiais. Perfis existentes continuam usando a pasta de código já escolhida, preservando os trabalhos anteriores. Os dados ficam fora do bundle. As chaves continuam no mesmo cofre do sistema, serviço `Ripagem Maker`; o sistema pode pedir acesso ao novo executável. Nenhuma chave é incorporada ao instalador.

## Empacotar

macOS: instale as dependências de `../distribuicao/requirements.txt` e PyInstaller, execute `python3 scripts/prepare_engine.py --freeze` e depois `npm run build:mac`, no Mac da arquitetura alvo.

Windows x64: execute `npm run build:windows` na pasta `electron`. Pode ser empacotado no Mac ou Windows. O script prepara separadamente `engine-windows`: CPython 3.13 embeddable oficial, wheels Windows amd64, FFmpeg/ffprobe e instalador oficial do Microsoft Visual C++. As versões dos principais pacotes ficam em `windows-runtime-constraints.txt`; o runtime e os hashes ficam em runtime.json/manifest.json. O NSIS inclui essas dependências; nenhum Python local é exigido do colega. Na primeira abertura, se o componente Microsoft estiver ausente, o app oferece instalá-lo com a confirmação nativa do Windows. Compilação cruzada não substitui teste de abertura, transcrição, takes e XML em Windows real.

Modelos Whisper são baixados separadamente na primeira utilização. MLX é opcional e não está incluído; use Faster Whisper (CPU) ou AssemblyAI. O build inclui apenas código permitido pela allowlist, nunca `.env`, chaves, mídia ou workspace.

Windows: NSIS por usuário, com seleção do destino. macOS: ZIP com `.app`. Não há certificado de assinatura/notarização configurado; os sistemas podem mostrar aviso ao abrir. A atualização do instalador preserva o perfil do Electron e as credenciais do sistema. Cada colega configura suas próprias chaves.

## Arquitetura e manutenção

Electron controla janela, diálogos e downloads; Python mantém transcrição, trocas, takes e XML. Renderer isolado, sandbox ligado, sem Node. IPC aceita somente o frame principal local. Links externos HTTP(S) abrem no navegador. Ao fechar com tarefas ativas, pede confirmação. Outro servidor na porta não é encerrado nem reutilizado silenciosamente.

Atualizações do código continuam em Ajustes do app. O shell Electron deve ser atualizado pelo novo instalador. Atualização automática do shell não está habilitada: requer endpoint de releases e assinatura. O Drive é destino de downloads manuais, não um serviço de auto-update.
