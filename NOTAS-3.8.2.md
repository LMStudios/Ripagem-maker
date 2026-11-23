# Ripagem Maker 3.8.2 — Legendas antes da entrega

## Fluxo completo
Arquivo → Transcrição → Falas → Takes → Prévia → Legendas → Entrega.

A montagem preparada sem assistir à prévia passa primeiro por Legendas. O XML dessa preparação é um rascunho técnico; a conclusão e a economia de tempo só são apresentadas após a entrega final com SRT atual e conferido. As exportações avulsas continuam independentes.

A etapa Legendas reúne a trilha, geração local de SRT, correção de nomes de SRT enviado e vídeo legendado opcional. A confirmação da legenda é salva e ligada à montagem e ao conteúdo do arquivo. Mudanças em falas, takes, trilha ou legenda exigem nova conferência. O aplicativo não afirma garantir ausência absoluta de erros: a conferência humana continua necessária.

A entrega completa verifica áudios aprovados, takes ou dispensa explícita, trilha definida, busca visual quando habilitada e legenda válida e confirmada. Mostra XML, relatório, SRT e vídeo legendado atual quando existir. Verifica os arquivos no disco. O relatório registra a legenda e sua integridade. Links de entregas antigas não são apresentados como atuais após uma mudança.

## Busca visual automática
Começa em uma fila local separada após a transcrição, quando o produto antigo está disponível. Se a identificação ainda estiver pendente, começa quando o plano com o nome é carregado. Projetos de otimização de preços e arquivos somente de áudio não entram nessa busca.

Ativada por padrão; pode ser desativada no envio ou no próprio projeto. Desativar cancela a tarefa visual desse projeto e preserva o que já foi lido. Análises válidas e tarefas em andamento são reaproveitadas; falhas não provocam repetição automática sem fim. A busca pode ser refeita manualmente. São usados até dois processos de leitura automática, com prioridade reduzida onde o sistema permite. As sugestões continuam em Takes para revisão; não aprovam nem cobrem trechos sozinhas.

## Interface
Cartões da Experiência Studio alinhados e separados por 24 px. Controles da busca com respiro e opção explícita por projeto. Navegação e tutorial mostram Legendas antes de Entrega. Botões e links finais não são reconstruídos a cada consulta de estado, preservando foco e cliques.

## Verificação
- 366 testes Python: sem falhas; 1 ignorado por ausência de um arquivo de exemplo local.
- 33 testes JavaScript/Electron: sem falhas.
- 12 testes novos cobrem confirmação, resíduos do nome antigo, invalidação por montagem/SRT, entrega XML real, tarefas em andamento, cancelamento da confirmação e fila visual automática.
- Mac real: projeto sintético de 8 segundos; busca visual local concluída; bloqueio sem SRT; envio e correção do SRT; confirmação; avanço para Entrega; geração de XML, relatório e legenda com arquivos reais verificados. Verificação visual dos cartões Studio.
- Nenhum crédito de transcrição ou geração de voz foi consumido. Os testes usam sinais sintéticos e simulações de serviços.
- Windows: lógica e ponte cobertas por testes no Mac; janela, diálogos e Premiere no Windows não foram testados em uma máquina Windows nesta rodada.

## Backup
backups/antes-legendas-entrega-3.8.1-20261104-133258/codigo.zip

Para voltar: feche o app, extraia esse ZIP na pasta do projeto substituindo os arquivos incluídos e reabra. Projetos e chaves foram preservados. O backup contém somente código e testes; não deve ser enviado como pacote de atualização.

## Atualização
Use Ripagem-Maker-Atualizacao-3.8.2.zip em Ajustes e atualizações do aplicativo existente. É uma atualização de código comum a Mac e Windows, não um instalador inicial de Python/FFmpeg. Preserva projetos, pasta de saída, configurações e chaves locais; o ZIP não inclui esses dados.
