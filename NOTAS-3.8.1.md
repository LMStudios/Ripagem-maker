# Ripagem Maker 3.8.1 — Studio Grafite

Base: versão modular 3.8.0 atualizada pelo Claude em 04/11/2026. A edição de segurança/homologação anterior não foi usada como base nem substituída.

## Interface

Tema grafite consistente no painel, ferramentas e Troca de potes; azul/violeta na ação principal; estados de foco e cliques, animações de 180 ms e respeito a movimento reduzido. Projetos recentes se reorganizam em janelas menores, mantendo Continuar, Abrir pasta e Copiar caminho acessíveis. O envio do arquivo volta a ocupar o primeiro bloco; otimização de preços fica abaixo. A localização do projeto permanece disponível num bloco recolhível.

Primeira entrada em Troca de potes oferece Quero ser guiado ou Começar direto. Como usar reabre a escolha; o guia acompanha a etapa e as subetapas de falas, sem cobrir controles, aprovar textos ou iniciar operações. Experiência Studio, no painel, permite reabrir o tutorial e ajustar parâmetros da economia.

## Tempo por projeto

Novos projetos: medição desde a seleção do arquivo nesta versão, incluindo envio, processamento e revisão. Sem cabeçalho de seleção (outros clientes), começa no início da transcrição. O relógio usa atualizações a cada 10 s, agrega janelas sem duplicar o tempo, salva pausas e descarta lacunas longas sem contato. Fechamento normal registra o último intervalo; em encerramentos abruptos pode perder até um intervalo de medição. Não é um rastreador de atividade humana: o tempo com o projeto aberto conta até o usuário pausar ou concluir.

Projetos antigos são identificados como medição parcial; não recebem percentual inventado. A entrega encerra o relógio somente com XML confirmado no disco. Mudanças nas falas, aprovação, trilha ou assinatura da montagem invalidam o resumo e retomam a medição.

Fórmula padrão: trechos únicos selecionados × 5 min + 60 min por projeto com adaptação de modo de uso. Intervalos sobrepostos não contam em dobro. Economia = manual estimado − tempo no app. Percentual = economia/manual × 100. Resultados negativos e referência zero são tratados sem inventar economia. Exemplo validado: 48 trechos + modo de uso, 45 min no app → 5 h manuais, 4h15 e 85% de economia estimada.

## Robustez e armazenamento

Envios do fatiador e da biblioteca agora são recebidos por blocos em arquivo parcial; só um envio completo é publicado. Upload vazio, interrompido, maior que 20 GB ou sem espaço suficiente é recusado antes de iniciar o processamento. Falhas removem só o temporário da operação. Um arquivo existente não é substituído.

As ferramentas avulsas, limpeza recuperável, movimentação verificada de projetos, credenciais no cofre e tratamento de silêncio/ruído da versão 3.8.0 foram preservados e incluídos na regressão. Nenhuma limpeza de projetos do usuário foi executada.

## Verificação

- 354 testes Python, sem falhas; 1 ignorado por ausência de material de exemplo local.
- 33 testes JavaScript/Electron, sem falhas.
- Mac: painel real, escolha guiada, tutorial contextual, reabertura de projeto sintético, navegação, resumo da entrega, XML real, abrir pasta no Finder e salvar cópia (hash idêntico).
- Projeto sintético TESTE_STUDIO_GRAFITE: 8 segundos de imagem e sinais de teste, sem fala real, sem ASR/TTS pago. O percentual mostrado nesse projeto é de teste, não evidência de produtividade real.
- Contrastes dos tokens: texto principal 15,67:1; secundário 8,41:1; branco nos extremos do degradê principal 5,65:1 e 7,29:1. Não equivale a uma auditoria completa de acessibilidade.
- APIs locais, 5 amostras: medianas entre 0,6 e 2,8 ms antes/depois. Variações são ruído de medição; não se reivindica ganho percentual de velocidade. Não foi feito benchmark de uma VSL longa nesta rodada.

Windows: testes de lógica, caminhos, UTF-8 e ponte Electron executados no Mac/simulados. A interface, os diálogos e a importação no Premiere em Windows precisam de validação real nesse sistema. Não foram consumidos créditos de APIs; transcrição e voz externas foram simuladas nos testes.

## Backup e restauração

`backups/antes-studio-grafite-3.8.0-20261104-080900/codigo-e-configuracoes.zip`

Backup conferido por integridade ZIP e SHA-256. Contém código e configurações anteriores; mídias e chaves do cofre não foram copiadas nem alteradas. Feche o app, extraia o ZIP na pasta do projeto, substituindo os arquivos incluídos, e reabra pelo iniciador habitual. O ZIP inclui RESTAURAR.txt. Arquivos novos sem referência não são executados pela versão restaurada.

## Atualização para os colegas

`distribuicao/pacotes/Ripagem-Maker-Atualizacao-3.8.1.zip` é o pacote de atualização de código comum ao Mac e Windows. Instale pelo mecanismo de atualização do aplicativo existente; ele não é um instalador completo do Python/FFmpeg. O pacote não contém projetos, credenciais, backups ou ambientes Python. Separação de voz/trilha mantém a dependência opcional de Demucs, conforme a versão 3.8.0.
