# Distribuição aos colegas

## Regra permanente de publicação — solicitação de 13/11/2026

Toda versão publicada deve incluir **o aplicativo completo do Mac e o instalador completo do Windows da mesma versão**. O ZIP universal de atualização é adicional e nunca substitui os executáveis. Não considerar a publicação concluída se só o ZIP de código foi enviado.

Preparação padrão no Mac Apple Silicon: `python3 distribuicao/gerar_versao.py`. Os pacotes ficam em `distribuicao/pacotes/Ripagem-Maker-VERSAO`. Enviar essa pasta ao Drive, preservar as versões anteriores e conferir a conclusão do upload. Verificar versão embarcada, integridade e ausência de dados pessoais antes do envio. Identificar claramente a arquitetura suportada; compilação cruzada não equivale a teste nativo no Windows.

Destino informado pelo usuário: [Ripagem Maker](https://drive.google.com/drive/folders/1aC-d_Bp-PMuG9pxSuzPAT5rZx35O3mUM).

Após gerar e validar uma versão, publicar os pacotes limpos nesta pasta, com a versão no nome. Preservar as versões anteriores e as permissões existentes. Incluir instruções de instalação e hashes SHA-256. Nunca enviar ambientes locais, chaves, logs, caches ou trabalhos de usuários.

A publicação exige envio ao Drive e confirmação no destino. Gerar os arquivos localmente não comprova envio. O build atual não faz upload automático.


## Versão 3.3.0 / Electron beta.11 — 30/10/2026
Publicação confirmada pela interface do Google Drive: 1 upload concluído, 6 de 6 arquivos. Subpasta: [Ripagem-Maker-3.3.0](https://drive.google.com/drive/folders/1UFRsKb3XexTx0u2b8SUjC_Vf_1JXAddM). Inclui instaladores Mac arm64 e Windows x64, ZIP de atualização, instruções, novidades e hashes. Arquivos antigos da pasta principal preservados. Envio realizado pelo seletor nativo do Chrome; não exigiu alterar permissões de extensões.

## 3.7.2 — 30/10/2026

Publicado e verificado no Drive (3/3 arquivos; upload 100%):
https://drive.google.com/drive/folders/12g10gnciagOzCOCKZhGCSfcrs9OScTvZ

- Ripagem-Maker-Atualizacao-3.7.2.zip (código universal para app já instalado).
- Ripagem-Maker-Atualizacao-3.7.2.sha256.
- LEIA-ME-3.7.2.txt.

Otimização exclusiva de preços e kits desde o upload; produto e modo de uso não entram na identificação de trechos. Pitch com sublinhado normalizado e erro de nomenclatura sem retorno automático ao Arquivo. Testes automatizados e UI no Mac; teste com transcrição real da GlycoWise, sem ASR/TTS pagos. Matriz 1/3/6 (59/39/29 e 59/117/174) testada com exemplos controlados. Não foi gerada uma VSL final nem validado Windows nativo. Instaladores completos anteriores preservados; esta correção é distribuída como atualização de código.

## 3.7.3 — 30/10/2026 — Ofertas completas

Publicada na pasta principal autorizada, subpasta `Ripagem-Maker-3.7.3`:
https://drive.google.com/drive/folders/1aC-d_Bp-PMuG9pxSuzPAT5rZx35O3mUM

Verificado visualmente: upload concluído, 3/3 arquivos, 100%.
- Ripagem-Maker-Atualizacao-3.7.3.zip.
- Ripagem-Maker-Atualizacao-3.7.3.sha256.
- LEIA-ME-3.7.3.txt.

Entrada única para três ofertas, validação de unitário/total, valores por extenso em inglês, blocos completos preservando o rateio pago/grátis dos kits mantidos. Ofertas faltantes são acrescentadas ao último bloco com espaço na montagem. Testes: 293 Python (4 ignorados) na suíte completa; testes específicos adicionais de duração e estado desatualizado; 21 Node; interface real e motor congelado no Mac. GlycoWise testada sem APIs pagas; Windows nativo não testado. Fonte original e suas 45 menções não foram alteradas nos testes. Atualização requer reabrir o aplicativo em uso para recarregar o servidor Python e a interface.

## 3.9.2 — 06/11/2026

Publicada e conferida no Drive: [Ripagem-Maker-3.9.2](https://drive.google.com/drive/folders/1c718PJE7TPp2Ct48hS8-A2mRzanScZTE).
Cinco arquivos: Mac universal, instalador Windows x64, atualização para instalações existentes, instruções e SHA-256.
Ferramentas avulsas agrupadas, com escolha de projeto e informações sob demanda. Login não ativado.
Interface verificada no Chromium no Mac; binários e conteúdo dos pacotes conferidos. Instalador ainda sem execução no Windows.

## 3.9.3 — 09/11/2026

Atualização Mac e Windows publicada e conferida: [Ripagem-Maker-3.9.3](https://drive.google.com/drive/folders/1SPYuR-8z5yBemjNW4cxFmeWV-8r-he0A). ZIP, instruções e hash.
Busca ampliada com revisão de grafias prováveis. Geração de legenda reaproveita tempos existentes. Entrega inclui ZIP com XML, SRT e relatório. O material do projeto usado no teste não foi distribuído.

## 3.10.0 — 10/11/2026

Atualização para instalações existentes no Mac e Windows publicada e conferida no Drive
em [Ripagem-Maker-3.10.0](https://drive.google.com/drive/folders/1GFdRmDbP1LR-YEag_NcG3lNQh6KYzoeR).
Upload concluído com 3 de 3 arquivos: ZIP, instruções e SHA-256.
Novo fluxo da Troca de potes com entrada separada, revisão por pendências e legenda
antes da entrega. Interface verificada no Chromium com respostas de teste.
A versão anterior permanece na pasta local de pacotes.


## 3.10.13 — 13/11/2026 — Executáveis completos

Publicação confirmada pela interface do Drive: pasta `Ripagem-Maker-3.10.13` presente no destino autorizado e status **1 upload concluído**. O seletor confirmou o envio de cinco arquivos:

- Ripagem-Maker-3.10.13-Mac-arm64.zip (Mac com chip Apple, 333.935.329 bytes).
- Ripagem-Maker-3.10.13-Windows-x64.exe (Windows 64 bits, 338.746.421 bytes).
- Ripagem-Maker-Atualizacao-3.10.13.zip.
- LEIA-ME.txt.
- SHA256SUMS.txt.

Python e FFmpeg incluídos nos dois pacotes completos. Código embarcado conferido contra o manifesto da atualização. Assinatura local do Mac verificada; motor congelado iniciou e serviu a interface em teste isolado. Windows: 3.138 hashes de conteúdo conferidos (marcador vazio .gitkeep excluído pelo empacotador), binários principais x64 e compilação do instalador concluída. Não houve instalação ou execução em PC Windows. Os pacotes não contêm projetos ou credenciais. As versões antigas e as permissões foram preservadas.

O fluxo padrão `gerar_versao.py` passa a exigir os dois pacotes completos; upload e confirmação continuam sendo etapas explícitas de cada publicação.


## 3.10.14 — 13/11/2026 — Espaço antes do envio

Pasta Ripagem-Maker-3.10.14 publicada no destino autorizado. Verificação visual: 5 de 5 arquivos concluídos. Aplicativo Mac arm64, instalador Windows x64, atualização ZIP, LEIA-ME e SHA-256. Versões anteriores preservadas.

Consulta de espaço antes do upload, valores explícitos de arquivo/espaço livre/mínimo, tratamento de conexão e envio interrompido. O servidor ativo do caso relatado estava acessível; o vídeo de 5,96 GB não cabia nos 3,86 GB livres. Após limpeza informada pelo usuário foram medidos 40,34 GB.

Validação: 462 testes Python (461 passaram, um ignorado), 45 JavaScript; HTTP real no motor congelado Mac com falta de espaço simulada e nenhuma transcrição criada. Código embarcado conferido contra o manifesto; assinatura local Mac e integridade/x64 Windows conferidas. Sem execução nativa em Windows.


## 3.10.15 — 13/11/2026 — Refinamento da imagem e cobertura

Publicação confirmada na pasta autorizada: Ripagem-Maker-3.10.15, 5 de 5 arquivos concluídos. Aplicativo Mac arm64, instalador Windows x64, atualização ZIP, LEIA-ME e SHA-256. Os executáveis incluem Python e FFmpeg.

Segunda leitura local de rótulos e bordas, proteção contra fragmentos genéricos, reaproveitamento de cache e revisão das sugestões. Corrige cobertura subtraída por falas que viram apenas marcadores e sobras de um quadro; verifica cobertura real dos intervalos aprovados antes do XML e preserva exceções manuais válidas.

Teste em cópias isoladas: Rosedil passou de 5 lacunas no plano preparado para 0 após novo agendamento; VapoBrain manteve 0. Suíte: 480 testes Python (479 passaram, um ignorado) e 45 JavaScript/Electron. Motor empacotado Mac validado com vídeo sintético, rótulo curto e cache. Integridade dos dois pacotes conferida. Não houve teste nativo em Windows ou importação no Premiere. Projetos do usuário e XMLs anteriores não foram regravados. Detalhes em relatorios/refino-visual-3.10.15.md.


## 3.10.16 — 16/11/2026 — Reprodução de áudio sem controles nativos em cada frase

Publicação confirmada visualmente na pasta autorizada: `Ripagem-Maker-3.10.16`, **1 upload concluído, 5 de 5 arquivos**. Inclui aplicativo Mac arm64 (333.945.016 bytes), instalador Windows x64, atualização ZIP, LEIA-ME e SHA-256. O tamanho exato e os hashes dos pacotes estão em `relatorios/player-audio-3.10.16/pacotes-verificados.json`. Versões anteriores e permissões preservadas.

Player compartilhado sob demanda na revisão, amostras e áudios tratados. Pausa ao alternar/ocultar, cancelamento, busca e erros visíveis. 480 testes Python (479 passaram, um ignorado), 53 JavaScript/Electron aprovados. Teste nativo WKWebView com MP3/WAV reais e 300 controles: dez inícios em 143–264 ms, sem congelar. Original e fala pronta também conferidos na tela real de Falas em aba separada. Não houve execução em PC Windows.

106 arquivos de código Mac/Windows conferidos contra o manifesto da atualização. Integridade do runtime Windows e arquitetura x64 conferidas; assinatura local Mac verificada. Projetos, arquivos e aprovações existentes preservados. Detalhes em `relatorios/player-audio-3.10.16.md`.


## 3.10.17 — 16/11/2026 — Pronta localmente; publicação adiada

Regeneração individual pelo botão Regenerar áudio em Falas. Confirmação de créditos, escopo de uma frase, histórico, nova aprovação e permanência na revisão. Corrige o restauro dos IDs de voz.

Mac arm64, instalador Windows x64, atualização ZIP, LEIA-ME e SHA-256 preparados em `distribuicao/pacotes/Ripagem-Maker-3.10.17/`. Integridade e código embarcado conferidos. Detalhes e hashes em `relatorios/regeneracao-individual-3.10.17.md`.

**Publicação não realizada:** o usuário pediu para concluir o envio depois, pois está utilizando o Chrome. Respeitar essa solicitação e não afirmar que a 3.10.17 está no Drive até enviar e verificar os cinco arquivos. O destino autorizado continua o mesmo.


## 3.10.18 - 17/11/2026 - Pronta localmente; envio adiado

Correção da exigência de primeira menção na otimização e restrição dos takes às falas de preços/kits selecionadas. 491 testes Python (490 passaram, um ignorado), 60 JavaScript/Electron. Teste em cópia do projeto: XML com 7 falas e 9 takes, usando extensão de janela autorizada apenas no teste.

Aplicativo Mac arm64, instalador Windows x64, ZIP de atualização, instruções e hashes estão em distribuicao/pacotes/Ripagem-Maker-3.10.18/. Integridade conferida. Não houve teste nativo em Windows. **Ainda não publicado no Drive**, respeitando a solicitação do usuário de concluir o envio depois.


## 3.10.19 - 17/11/2026 - Pronta localmente; sem permissão na pasta compartilhada

Corrige painel com entrega nula e IDs antigos na lista de takes; oferece extensão explícita para vídeos completos. 493 testes Python (492 passaram, um ignorado), 64 JavaScript/Electron. Mac arm64, instalador Windows x64, atualização, instruções e hashes conferidos em distribuicao/pacotes/Ripagem-Maker-3.10.19/. Sem teste nativo em PC Windows.

O Drive foi conectado para criar o relatório, mas criar a subpasta de publicação no destino autorizado retornou 403 insufficientParentPermissions. Não houve upload dos pacotes. Publicação permanece pendente; não afirmar que esta versão está no Drive. Chrome não foi usado.


## 3.10.20 — 19/11/2026 — Pronta localmente; sem permissão na pasta compartilhada

Interface mais limpa, entradas diretas Nova ripagem/Continuar projeto, nomenclatura recolhida e Mais filtros na revisão. 64 testes JavaScript/Electron aprovados; conferência visual Mac e projeto temporário isolado. Motor Mac conferido; Windows compilado e verificado, sem teste nativo em PC. Pacotes em distribuicao/pacotes/Ripagem-Maker-3.10.20/.

Tentativa de criar a subpasta no destino autorizado recusada: 403 insufficientParentPermissions. Nenhum pacote publicado no Drive. Detalhes em relatorios/interface-3.10.20.md.
