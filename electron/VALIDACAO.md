# Validação — 4.0.0-beta.1 (28/10/2026)

- Backup anterior ao Electron: pasta `Backups Ripagem Maker/Antes-Electron_2026-10-28_12-19-40`, com ZIP do código, ZIP do aplicativo anterior e SHA-256. Trabalhos, credenciais e ambientes existentes não foram movidos.
- Suite Python: 198 testes, todos aprovados, 1 ignorado. Foram emitidos avisos de recursos não fechados dos testes existentes.
- Electron/Node: 5 testes aprovados (origem IPC, downloads locais, travessia de caminhos, protocolos externos, preload restrito).
- macOS arm64: abertura do Electron de desenvolvimento e do `.app` empacotado, com código de teste isolado em `/tmp/ripagem-electron-qa`, porta 18767. Nenhum serviço pago foi chamado.
- Seletor de pastas abriu o diálogo nativo; cancelar retornou à interface sem modificar as configurações.
- Link de XML abriu o diálogo nativo de salvamento; a interface mostrou o destino. Cópias salvas pelo desenvolvimento e pacote foram comparadas byte a byte ao XML original (11.520 bytes). Arquivos de teste removidos de Downloads após validação.
- Motor congelado iniciou o servidor sem Python instalado no PATH de teste; FFmpeg/ffprobe incluídos leram a mídia sintética (8 segundos). Worker em subprocesso importou requests, numpy, keyring e faster_whisper sem recorrer ao Python do sistema. Modelos ASR não foram baixados neste teste.
- Pacote ZIP verificado: integridade, presença de motor/FFprobe/interface, ausência de `.env` e de trabalhos/workspace de usuários. SHA-256 registrado no diretório de entrega.

## Limites

Windows: configuração NSIS e roteiro de build nativo prontos, mas instalador não foi gerado/executado no Windows neste Mac. O build recusa motor de outro sistema/arquitetura. Roteiro de CI em `ci/build.yml`, ainda não executado num repositório remoto.

Mac Intel: exige build x64 com motor correspondente; este pacote é somente Apple Silicon (arm64).

Sem assinatura Developer ID/notarização nem atualização automática do shell. O app antigo permanece como opção de retorno. As atualizações de código podem continuar pelo mecanismo já existente, mas atualização do shell exige novo pacote. MLX opcional não foi incluído; usar Faster Whisper (CPU) ou AssemblyAI.

Drive: destino de distribuição registrado em `distribuicao/PUBLICACAO-DRIVE.md`. Upload pendente da permissão de acesso a arquivos locais da extensão Chrome; nenhum envio desta beta foi confirmado.

## Revisão beta.2 — confirmação manual do arquivo

14 testes de seleção, arrastar e navegação passaram. No Electron instalado, a escolha de um vídeo pelo diálogo nativo manteve a etapa 1, exibiu nome/tamanho e habilitou Continuar. A etapa 2 só abriu após clicar em Continuar; nenhuma transcrição foi iniciada. Arrastar foi exercitado por eventos simulados com FileList e DataTransferItem; não houve verificação de um arrasto físico do Finder neste teste. A confirmação final mostra nome e tamanho, sem player embutido (o codec do vídeo sintético não abriu no Chromium). O aplicativo instalado foi comparado ao build beta.2: 1.847 arquivos regulares e todos os links correspondem.

## Revisão beta.3 — Gemini (28/10/2026)

Reprodução real: models.list HTTP 200; generateContent do 2.5 Flash HTTP 404 com recusa de acesso a novos usuários. Integração atualizada explicitamente para gemini-3.5-flash-lite, sem fallback. Um pedido real com frase sintética e resposta estruturada foi aceito e validado; nenhum texto do trabalho foi aplicado nem voz gerada. Documentação oficial confirma faixa gratuita sujeita à cota/projeto. Testar conexão continua sem gerar conteúdo e agora explica que metadata não garante acesso à geração. HTTP 404 tem mensagem específica, sem expor o corpo do serviço/chave. Suite completa: 200 testes, 1 ignorado. Trabalho Nervelin e metadados preservados em backup no perfil antes de reiniciar; reinício somente com zero tarefas ativas.

## Revisão beta.4 — adaptação sem equivalência de dose

O prompt Gemini agora exige reescrita neutra quando faltar a dose nova, retirando quantidade/frequência antigas. Acrescentada validação contra doses novas sem orientação confirmada. Teste real produziu três sugestões para o trabalho: apresentação em cápsulas e duas frases sem a dose de gotas. Aplicar sugestão marca o texto como rascunho para revisão e remove o aviso antigo de texto ainda não adaptado; confirmação do usuário continua necessária. Alterações de texto preservam áudios anteriores no histórico e invalidam somente as falas alteradas. Suite: 202 testes, 1 ignorado; após ajustes de apresentação, 15 testes específicos Gemini aprovados.

Aplicação ao trabalho Nervelin: aguardou a tarefa de vozes 87716d711c terminar antes de fechar o app. Três rascunhos aplicados; as outras 75 linhas foram comparadas integralmente e preservadas. Tempos e speakers das três linhas preservados; áudios anteriores guardados em historico_audio e confirmação de modo de uso reiniciada apenas nas linhas alteradas.

## Revisão beta.5 — transcrição empacotada e pitch

Reprodução antes da correção: executar o asr_worker.py pelo motor congelado falhava com ModuleNotFoundError: wave, ocultado pela última linha genérica do PyInstaller. O build agora inclui o worker como hidden import, analisando suas dependências. Novo motor congelado executou --help do worker e uma transcrição real offline com faster-whisper small.en já em cache. A validação extraiu o áudio sintetizado localmente, reconheceu 8 palavras ('Get 6 bottles for only $29 per bottle.') e localizou pitch $29 em 1,3 s com contexto de seis potes. Nenhuma API paga foi chamada. Teste curto não equivale a revisar toda a VSL do usuário. O executor agora drena stderr em paralelo, limita o buffer e registra a causa real; 4 testes cobrem módulo ausente, volume alto de stderr, diagnóstico e erro normal.


## 4.0.0-beta.6 — Identificação da entrega
Campos desde Arquivo e na entrega: número VSL, produto novo, copy, editor, pitch manual opcional. XML usa pitch validado da oferta de seis potes. Renomeação cria cópia preservando montagem. Validação: 220 testes Python (1 skip), 19 Node; UI local e XML sintético com pitch 00:05 verificados. Sem teste nativo Windows nesta versão.


## 4.0.0-beta.7 — Margens de cobertura
Áudio padrão 200 ms; remove fragmentos até 120 ms entre trocas próximas, sem mover A3. Visual padrão 1000 ms antes/depois, limitado pela primeira menção e duração, sem sobreposição. UI Ajustes testada para salvar ambas as margens. Cópia do trabalho Nervelin: 78 falas, 135 takes, zero pendências; XML verificado. Testes de silêncio PCM, sequência XML e margens/limites. Sem teste nativo Windows nesta versão.


## 4.0.0-beta.8 — Fechamento das margens
A margem esquerda é removida com ripple em V1/V2/A1/A2/A3 e trilha, em vez de gerar silêncio. Tempos dos marcadores e duração atualizados. Áudios novos preservam in/out e duração. Mix integral e prévia usam o mesmo fechamento. 227 testes Python (1 skip), 21 Node passaram. Cópia do trabalho com 78 falas: união de A1+A3 contínua do primeiro ao último frame; V1 contínuo e V2 sem sobreposições. Sem validação nativa no Premiere/Windows nesta versão.


## 4.0.0-beta.9 — Potes aleatórios nas pendências
Aviso e botão exigem autorização explícita. Preenche somente janelas pendentes, mantém takes resolvidos, não altera kit detectado/texto/voz. Usa apenas vídeos classificados Produto; respeita primeira menção e não repetição consecutiva. Autorizações vinculadas ao conteúdo/tempo/kit da janela. 231 testes Python (1 skip) e 21 Node passaram; UI com kit 94 preencheu e preparou sem pendências. Sem teste nativo Windows nesta versão.


## 4.0.0-beta.10 — Tela de takes mais leve
Players e seletores de takes são criados somente ao abrir os detalhes. Biblioteca mostra botão Ver material, sem instanciar 44 players. Aviso de pendências não é reconstruído em eventos idênticos. UI com cópia ALPHASODA de 44 materiais e 101 segmentos: zero players/seletores dos takes ao abrir etapa; abrir um trecho cria 1 player/1 seletor. 23 Node e 9 testes UX Python passaram. Temporários próprios de cross-compilação foram removidos para aliviar disco. Sem teste nativo Windows nesta versão.


## Windows x64 — instalador beta.10 (29/10/2026)
NSIS gerado no Mac com Electron 45.1.0 e electron-builder 26.18.0. Motor Windows separado: CPython embeddable 3.13.17, 33 wheels Windows/any, FFmpeg/ffprobe e redistribuível oficial Microsoft. Primeira auditoria identificou concatenação de extraResources incluindo o motor Mac; configuração separada por plataforma, diretório de build removido e instalador refeito. Auditoria final: 139 DLLs/PYDs/executáveis AMD64; 2.556 hashes do manifest conferidos; wave.pyc, dependências ASR e backend de credenciais Windows presentes; sem dylibs Mac, .env ou saídas pessoais. Nove testes Node passaram (seleção do motor, rejeição de plataforma/arquitetura, políticas IPC/download). Instalador sem assinatura. Não foi executado em Windows real; não há confirmação de transcrição, takes ou importação no Premiere nesse sistema. App e dados reais do usuário não foram reiniciados nem alterados para este empacotamento.


## 4.0.0-beta.11 / código 3.3.0 — Fluxo simplificado (30/10/2026)
Backup de código anterior em Backups Ripagem Maker/Antes-UX-simplificado-2026-10-30.zip. Configuração inicial compartilhada, pasta validada por gravação, resumo visível de forma/uso, amostras locais automáticas com reaproveitamento, preferências sem chaves e consentimento vinculado a serviço/speakers/amostras. Lote parcial exige confirmação na tela e retira apenas as falas sem áudio da seleção, preservando textos/arquivos. Takes detalhados recolhidos em Configurações. Pasta de áudios e XML mostram caminhos reais. Pitch analisado uma vez na transcrição, invalidado se ela mudar, e mapeado pelas expansões e cortes; se cair dentro de uma fala regravada, exige confirmação do horário. Validação do nome movida para o SRT, com timecodes preservados. Trilha visível abaixo da entrega. Instalador atualiza código anterior com rollback e preserva dados/chaves; nunca faz downgrade.

Validação: 238 testes Python, 1 ignorado; 30 testes Node. UI em servidor isolado com mídia sintética: pasta inicial salva e persistida após recarregar, trabalho reaberto, avanço dos textos para geração, amostras locais preparadas sem API de voz, pasta aberta, configurações de takes recolhidas, XML gerado e baixado via HTTP 200, SRT corrigido mantendo timecodes. Lote parcial exibido corretamente; diálogo confirm foi substituído por confirmação inline após bloquear o navegador do teste. Sessão macOS bloqueada impediu concluir a conferência da janela Electron e o último clique da confirmação inline. Nenhuma API paga foi chamada para os testes. Windows: pacote x64 e código validados estruturalmente; sem execução nativa Windows ou Premiere nesta revisão. Trabalhos reais e credenciais preservados; não houve reinício forçado do app em uso.

Auditoria final do Mac: assinatura ad hoc do bundle foi corrigida, verificada com codesign --verify --deep --strict e incluída no ZIP. Configuração mac.identity agora é explícita para builds futuras. Não há certificado de distribuição/notarização. Aplicativo Electron instalado atualizado para beta.11, com o anterior preservado. Conferência da janela nativa continua pendente por sessão bloqueada.


Conferência nativa concluída após desbloqueio (30/10/2026): aplicativo Electron beta.11 instalado iniciou com motor congelado na porta isolada 18768; trabalho sintético reaberto; seleção parcial confirmada na própria tela avançou automaticamente para Takes, preservando a fala excluída da entrega; botão Gerar XML sem assistir à prévia gerou V02; Salvar uma cópia abriu o diálogo nativo, salvou entrega-qa.xml em /tmp/ripagem-ux-preview e exibiu o destino. Arquivo XML de 9.331 bytes confirmado no disco e parseado com sequência válida. Nenhuma geração paga foi chamada. Evidência local: tests/fixtures/ux-electron-330-confirmacao.png. Teste nativo Windows continua pendente.

Publicação confirmada em 30/10/2026: seis arquivos no Drive, pasta https://drive.google.com/drive/folders/1UFRsKb3XexTx0u2b8SUjC_Vf_1JXAddM. Teste Electron isolado encerrado; aplicativo real na porta 8765 preservado.
