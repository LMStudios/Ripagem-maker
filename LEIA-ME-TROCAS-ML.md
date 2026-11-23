# Trocas de ML e nomenclatura VTurb

Abra o Ripagem Maker normalmente. No menu, use **Troca por demanda**.

1. Cole a solicitação inteira e clique em **Interpretar demanda**.
2. Confira VSL base, fim da lead original e o fim de cada ML. É possível preencher manualmente.
3. Pitch é o instante da primeira menção ao valor da oferta de 6 potes. Valores como 29 e 49 ajudam a localizar, mas exigem contexto. Informe esse tempo na VSL original; DELAY fica separado e não define o pitch automaticamente. O ajuste de duração vem marcado por padrão. A conta é pitch original − duração removida + duração inserida. O HTML não é alterado.
4. Opcionalmente abra a nomenclatura, preencha produto/copywriter e identifique cada ML. EV8 é o editor padrão. Sem esses dados, os arquivos usam título + número de variação.
5. Clique em **Baixar e gerar todas as versões**. Os vídeos são montados com corte exato, áudio original e sem fade. Acompanhe a fila e use Assistir/Baixar.

O arquivo JSON do resultado mantém a nomenclatura com dois-pontos e barras. O nome físico substitui esses caracteres por hífens e acrescenta um identificador para evitar sobrescrever versões.

O gerador separado **Nomenclatura VTurb** cobre VSL, alterações, ML, MOD, MOD + ML, upsell com fluxo opcional e novos closes com o sufixo 1/3/6.

## Limites atuais

- A interpretação é por regras e tempos explícitos, sem enviar a demanda a uma IA. Solicitações em outros formatos podem precisar de ajustes manuais.
- Downloads: arquivos compartilhados do Google Drive e links HTTP/HTTPS diretos. Links com login, páginas de players e playlists HLS/DASH não são suportados nesta versão.
- Os downloads ficam na biblioteca local, sem transcrição automática. Para usar as sugestões de corte do módulo antigo, mande reanalisar o vídeo.
- A fila é mantida em memória enquanto o servidor está aberto. Os vídeos e relatórios concluídos ficam em `plataforma/workspace/saidas` mesmo após fechar o aplicativo. Não feche durante downloads/renders.
- Foram usados vídeos sintéticos na verificação completa de download/montagem. Os vídeos reais da demanda não foram baixados/renderizados durante a implementação.

## Verificação

`python3 -m unittest discover -s tests -v`

Com o servidor aberto, `python3 tests/smoke_demanda.py` testa download HTTP, duas montagens, duração, sincronismo e cores antes/depois da emenda. Gera arquivos pequenos de teste na pasta de saídas.

Backup dos arquivos anteriores: `.backup_ml_20261024`.

Com a validação desativada, o pitch é informado manualmente ou por `PITCH: mm:ss` na demanda. Com a validação ativada, ele é buscado na transcrição do vídeo final.

## Validação de produto e pitch

Na **Troca por demanda**, a opção de validar cada vídeo final vem marcada. Informe o nome antigo e grafias alternativas separados por vírgula. O app renderiza, transcreve o vídeo resultante com Whisper local, procura esses termos e localiza o pitch. Sem termos, realiza apenas a busca do pitch. Falhas de transcrição deixam um aviso e preservam a saída para análise avulsa.

O menu **Validar produto e pitch** aceita um arquivo do computador, um vídeo da biblioteca ou um link. Use somente uma fonte de cada vez. Serve também para analisar trabalhos já finalizados.

- Termos exatos encontrados e grafias parecidas aparecem separados. Grafias parecidas exigem revisão.
- O pitch usa o timestamp da primeira palavra do valor, com contexto próximo da oferta de 6 potes. Valores 29/49, também por extenso em inglês/português/espanhol, ajudam a encontrar candidatos. Idades, prazos e quantidades não contam como preços. Contextos ambíguos ficam pendentes.
- Quando a validação está ativa, o pitch manual é substituído pelo detectado no vídeo final. A nomenclatura fica `PITCH PENDENTE` até a detecção; se o pitch for encontrado, o nome é atualizado. Revise o contexto antes de publicar.
- A transcrição pode errar nomes e números. “Nenhuma menção encontrada” significa somente que os termos não foram localizados na transcrição, não uma garantia de ausência no áudio ou no conteúdo visual.

### Premiere

Cada validação gera três arquivos na pasta de saídas:

1. **JSON:** transcrição, trechos, início/fim, contexto dos preços, pitch, FPS e arquivo de origem.
2. **XML (FCP7/xmeml):** importe via Arquivo > Importar no Premiere. Cria uma sequência nova com o vídeo integral e os marcadores `TROCAR`, `REVISAR` e `PITCH`. Mantém a mídia vinculada ao arquivo local; se mover os arquivos, será necessário relinkar.
3. **JSX:** execute em um host ExtendScript/CEP disponível na sua instalação do Premiere. O arquivo mostra a sequência ativa e pergunta a posição, em segundos, em que o vídeo analisado começa nela. Cria somente marcadores com duração, sem cortar nem substituir mídia. Reexecutar o mesmo relatório na mesma posição não duplica os marcadores.

JSON não é importado diretamente como marcadores pelo Premiere; use o XML ou o JSX. Os tempos são relativos ao início do vídeo analisado, não ao timecode embutido da mídia. O JSX pressupõe vídeo contínuo na sequência. Não mapeia automaticamente cortes, mudanças de velocidade ou reorganizações de uma montagem existente. Para esse caso, use a sequência nova do XML ou o alinhamento de timeline do Fatiador existente.

Referências: [amostra oficial de marcadores da Adobe](https://github.com/Adobe-CEP/Samples/blob/master/PProPanel/jsx/PPRO/Premiere.jsx), [importação de XML no Premiere](https://helpx.adobe.com/premiere/desktop/organize-media/import-files/migrate-from-final-cut-pro-x.html).

Verificação em 24/10/2026: o XML foi importado no Adobe Premiere Pro 2026 em um projeto de teste separado. Foram conferidos os marcadores de duas menções ao produto e do pitch, com vídeo e áudio vinculados e dimensões preservadas. O JSX foi validado com uma simulação da API de marcadores (offset e prevenção de duplicatas); não foi executado no host ExtendScript do Premiere.

## Cortes automáticos para troca

Cada nova validação também gera **XML com cortes automáticos** (`validacao_*_cortes.xml`). Importe no Premiere para abrir a sequência `DR Cortes` com áudio e vídeo divididos no início e no fim das frases com menções exatas ao produto antigo. O conteúdo é integralmente preservado, sem remoção nem ripple. Os cortes seguem os timestamps da transcrição, arredondados para fora ao quadro. Frases sobrepostas são unidas para não gerar cortes redundantes. Os pares áudio/vídeo são vinculados no XML.

Grafias parecidas e candidatos de pitch ficam somente marcados para revisão. A ferramenta não escolhe nem insere uma nova locução. Confira os limites no áudio antes de substituir. Caso não encontre menções exatas, a sequência permanece sem divisões adicionais.

O XML com cortes foi importado e conferido no Premiere Pro 2026 em 24/10/2026: dois trechos de troca, cinco segmentos contínuos em cada trilha e duração total preservada. Para análises antigas, faça uma nova validação para obter a nova exportação.

## Fluxo principal no Fatiador e troca de potes

A identificação dos trechos para substituir e as exportações do Premiere estão no próprio **Fatiador e troca de potes**, dentro de **Frases com o nome do produto → Trechos para trocar no Premiere**.

Depois de identificar o produto e as frases, clique em **Gerar JSON, marcadores e cortes para Premiere**. Não usa a tela de revisão nem chama uma nova transcrição. Pode incluir as trocas de preços e kits já geradas. Para continuar um trabalho anterior, use **Reabrir trabalho salvo** no topo do Fatiador.

- JSON: frases originais/novas, speakers e tempos em milissegundos desde o início da fonte.
- JSX de marcadores: marca os trechos na sequência correspondente.
- JSX de cortes: usa o mecanismo QE já existente do Fatiador para dividir o áudio em A1. Confira a sequência/trilha e salve uma cópia antes de executá-lo. Não remove conteúdo nem insere a nova locução. Grafias aproximadas ficam para revisão.
- Se a fonte salva tem vídeo: também disponibiliza XML de marcadores e XML de cortes em vídeo e áudio.
- Para timelines já editadas: o módulo de alinhamento por SRT continua disponível logo abaixo. Não aplique os tempos originais a uma sequência reorganizada sem alinhamento.

A revisão de produto/pitch continua disponível como conferência final e análise avulsa.

## Fluxo guiado e correção final do SRT

O Fatiador agora tem cinco etapas: **Escolher arquivo → Transcrever → Conferir trocas → Enviar ao Premiere → Corrigir SRT**. Trabalhos salvos entram direto na conferência, sem pagar outra transcrição. Ajustes avançados ficam recolhidos.

Na etapa 5, envie o SRT final exportado do Premiere e escolha:

- Somente trocas confirmadas de produto/preços: aplica as diferenças entre texto original e novo nos intervalos marcados.
- SRT revisado de referência: copia correções de linguagem do mesmo vídeo, exigindo blocos e timecodes iguais.
- Exemplo Golden Brain: reproduz as 135 correções dos dois SRTs fornecidos pelo usuário, somente com a mesma estrutura e textos correspondentes. Não é um dicionário global para outros produtos.

Se o SRT vem de uma timeline com cortes, selecione a opção de alinhar antes de corrigir. Alinhamentos incertos, inserções/remoções e trocas que deixariam blocos vazios ficam pendentes. Não há reescrita livre por IA, nem nova análise do áudio nesta etapa. Para erros de linguagem que não estão nas trocas definidas, é necessária uma referência revisada.

A ferramenta preserva os números dos blocos, cada linha de timecode e a quantidade de linhas de legenda; não retima nem renumera. Gera um SRT novo e um relatório JSON de antes/depois e pendências. O arquivo enviado não é sobrescrito. Na interface, confira o antes/depois e baixe o SRT para importar no Premiere.

Teste com o exemplo fornecido: 1.526 blocos, 135 textos corrigidos, todos os timecodes preservados. Também há testes de troca entre blocos, CRLF, BOM, texto fora do intervalo e alinhamento incerto.

### Regra atual da etapa 5 (nome do produto)

A etapa final agora corrige **somente o nome do produto**, em todo o SRT. Usa o nome antigo e aliases da etapa 3, substitui pela grafia final editável (ex.: `Golden Brain`) e padroniza menções existentes ao produto novo, independentemente de maiúsculas/minúsculas. Mostra quantas menções antigas encontrou e se restam resquícios. Não corrige gramática, termos técnicos, preços, kits nem pontuação. Referências revisadas e o perfil Golden Brain não são usados nessa etapa. Blocos, timecodes e quebras de linha permanecem iguais. Se a troca deixaria um bloco vazio, fica pendente.

## Indicadores de progresso

Os downloads agora informam VSL base ou ML da variação, volume recebido em MB e total quando o servidor fornece um tamanho confiável. Sem tamanho total, há animação de atividade e MB recebidos, sem percentual fictício. O percentual exibido é sempre da etapa atual, não da demanda inteira. Renderização, extração de áudio, transcrição, análise e conferência têm identificação própria. As atualizações de download são limitadas a duas por segundo.

A melhoria foi testada com downloads HTTP com e sem Content-Length, cancelamento, total inválido/compressão, renderização de fontes sintéticas e interface em um servidor de teste separado. A sessão em produção não foi reiniciada, preservando os resultados em tela; o backend novo será carregado na próxima abertura do Ripagem Maker.app.

## Áudio leve e segunda metade da VSL

Na etapa 2, **Segunda metade** é a opção padrão do trocador. O vídeo é recebido localmente e o app extrai um MP3 mono de 64 kbps apenas dessa metade para enviar ao AssemblyAI. Você pode escolher **Vídeo inteiro**. Não é enviado o vídeo ao serviço de transcrição.

A transcrição recebe o deslocamento da metade removida: frases, legendas, preços e marcadores continuam usando tempos desde o início da VSL completa. O WAV temporário para fatiar também usa somente o trecho analisado. A fonte integral continua salva localmente para exportar os XMLs de vídeo e áudio. O SRT gerado nessa transcrição contém apenas o trecho analisado, nos tempos originais.

Na etapa 3, o resumo visual mostra:

- primeira menção encontrada (início do nome, quando disponível);
- janela de troca = fim da VSL menos primeira menção;
- soma das durações das frases a substituir (não é estimativa de horas de trabalho).

A duração da janela considera o trecho analisado. Não afirma que não existem menções na metade que não foi transcrita. Se não encontrar o produto, confira a grafia/aliases ou escolha o vídeo inteiro.

As opções de preços/kits, alinhamento de timeline e arquivos completos ficam recolhidas para simplificar o uso. Os resultados concluídos de Microlead/Body e demandas passam a ficar salvos em `plataforma/workspace/tarefas_concluidas.json` e são restaurados ao reabrir o app; tarefas em andamento não são retomadas automaticamente.

Verificação: extração e cortes com ffmpeg real e transcrição simulada, sem consumir créditos de AssemblyAI, cobrindo metade/inteiro, deslocamento aplicado uma vez e janela calculada desde a menção real.


## Fluxo completo de troca de potes

No Fatiador, a etapa 3 reúne frases originais/novas, speaker, duração, reprodução e aprovação. Prepare as trocas de preços/kits antes de marcar “Incluir também” e atualizar a lista. Frases sobrepostas precisam ser resolvidas na seleção antes de montar. Mudanças de texto ou speaker invalidam o áudio anterior.

É possível importar gravações de até 50 MB por frase sem usar APIs, ou configurar ElevenLabs/MiniMax. A chave fica somente na memória do servidor até fechar o app ou clicar em Esquecer chaves; não é guardada no navegador, plano ou histórico. A confirmação de chave é local: permissões e créditos são verificados pelo serviço ao gerar. As chamadas reais dos provedores dependem da chave/conta e não foram executadas na validação desta entrega; contratos e falhas foram testados com respostas simuladas.

Para clonar, prepare e ouça as amostras locais e confirme autorização dos speakers. Um ID existente evita criar outro clone. MiniMax exige amostra de pelo menos 10 segundos; o app prepara até 60 segundos por speaker sem sobreposição detectada. ElevenLabs pode exigir verificação adicional na conta. A opção de excluir clones afeta somente vozes criadas naquela geração; nunca IDs existentes. Sem essa opção, os clones ficam na conta, e o resultado informa os IDs. Geração e clonagem podem consumir créditos; regenerar também.

Cada áudio é medido e precisa de aprovação. Ajustes de velocidade são limitados a 10%; áudios abaixo de 75% do espaço são sinalizados para revisão/regeneração. Diferenças pequenas recebem silêncio no final. A geração reutiliza áudios com o mesmo texto, speaker e configuração quando possível, sem repetir chamadas automaticamente em falhas.

Na etapa 4, “Gerar montagem pronta para Premiere” produz XML e plano JSON. Importe o XML com Arquivo → Importar (⌘I) e abra “DR Trocas aprovadas”. V1 mantém o vídeo; A1 preserva o original com os intervalos substituídos desativados; A2 recebe os áudios aprovados. A montagem usa a fonte contínua original: confira alinhamento se sua sequência tem cortes/retiming. Se A1 mistura fala e música, o trecho inteiro dessa mistura é desativado durante a substituição; não há separação automática de música.

Na etapa 5, a conferência mistura o áudio integral e usa Whisper local para procurar menções antigas. Não valida uma exportação posterior editada manualmente no Premiere. A revisão por transcrição pode perder nomes mal reconhecidos; o relatório mantém essa ressalva. O corretor SRT continua limitado a nomes de produtos, preservando os timecodes e sem reescrever outras frases.

Validação: suíte de 34 testes; importação/encaixe/aprovação/exportação pela interface; XML aberto no Premiere em projeto de teste; transcrição local de áudio M4A com fala sintética. Não houve envio de amostras aos serviços de voz nem consumo de créditos nesses testes.


Atualização de progresso/nomenclatura: o botão Gerar exibe imediatamente um indicador abaixo dele; durante o lote mostra fase, frase, speaker, contagem, percentual de frases processadas, reutilizações e erros, com cancelamento. O percentual não estima o tempo da chamada atual. Arquivos usam número da frase na lista, speaker, produto e GERADO/PRONTO; regenerações recebem V02, V03 etc., preservando versões. Cópias legíveis dos áudios existentes foram criadas sem remover caminhos antigos usados em XMLs. Validação: 37 testes e lote simulado pela interface, sem chamadas de voz externas.


Montagem XML atual: V1 contínuo; A1 com o restante original; A2 com os trechos originais separados e desativados; A3 com cada fala nova aprovada, já posicionada no mesmo intervalo do trecho correspondente. XMLs exportados anteriormente mantêm a organização antiga: gere um XML novo para aplicar esta mudança.


## Pasta principal e XML de ML

Ajustes → Escolher pasta → Salvar pasta principal. Os novos trabalhos usam Fatiador, Montagens e Biblioteca dentro da pasta escolhida. Os arquivos antigos não são movidos, e continuam disponíveis ao reabrir trabalhos, acessar a biblioteca e baixar saídas. A troca fica bloqueada enquanto há tarefas na fila ou executando. Usar pastas padrão reverte o destino dos próximos trabalhos sem remover os arquivos de outros destinos. Downloads feitos pelo navegador/app continuam em Downloads; os arquivos originais de trabalho seguem o destino configurado. A configuração fica em plataforma/workspace/ajustes.json.

Em Troca por demanda, Microlead + Body e Lote há entrega em vídeo, somente XML ou ambos. XML de ML contém duas fontes locais, ML e body, com vídeo/áudio separados na sequência DR ML + Body. Importar no Premiere com ⌘I. Mantém cortes secos e as mídias locais: não aplica os fades da renderização nem renderiza vídeo na opção somente XML. A conferência do vídeo final só fica disponível nas entregas com vídeo.

Validação: 40 testes passando, troca de pasta via HTTP/interface, renderização de exemplo de 8 s e XML do exemplo importado no Premiere. O seletor nativo de pasta foi verificado no Ripagem Maker.app após o usuário autorizar novamente o acesso a Documentos. O aplicativo abre normalmente; a página Ajustes ficou aberta sem alterar o destino escolhido pelo usuário.

### Sobreposições de potes por menção

Na etapa 3 do Fatiador, abra “Sobrepor os potes por menção”. Escolha a pasta dos materiais e leia a biblioteca. Subpastas ou nomes como `1 pote`, `kit 3` e `6 bottles` sugerem a quantidade; confira e ajuste as associações. A biblioteca aceita vídeos e imagens, sem mover os originais.

Detecte as menções, confira quantidade e intervalo de cada uma e salve. A detecção usa quantidades explícitas junto a nomes de potes/kits, considerando o mapa de quantidades já configurado. Não infere quantidade a partir de preço ou meses de tratamento. É possível adicionar intervalos manualmente.

“Sortear materiais” alterna aleatoriamente materiais da quantidade correspondente, sem repetir o mesmo arquivo imediatamente (cópias idênticas também contam como o mesmo material). Intervalos longos recebem vários materiais, respeitando a duração máxima configurada. Se não houver variedade suficiente para evitar repetição, o intervalo fica pendente: adicione materiais ou ajuste a duração.

Prepare os clipes e confira as prévias. A imagem ocupa a tela inteira, mantém a proporção e recorta as bordas quando necessário. Os clipes são silenciosos; a prévia usa o áudio original para conferir o momento da menção. Na etapa 4, exporte o XML só com V2 ou inclua os visuais na montagem com as falas aprovadas. O XML mantém V1 original, sobreposições em V2 e, na montagem completa, os cortes originais em A2 desativados e as falas aprovadas em A3.

Validação em 25/10/2026: 50 testes passando, fluxo pela interface e XML importado no Premiere em projeto separado. Conferidos V2, preenchimento da tela, tempos e taxa de quadros. Os materiais sintéticos de teste não foram associados ao trabalho do usuário.

### Revisão por pendências e perfis (25/10/2026)

O Fatiador agora apresenta resumo fixo do trabalho e filtros “Só pendências”, “Precisam de geração”, “Para ouvir”, “Aprovados” e “Todos”, além de busca por frase. A lista fica ao lado do trecho selecionado em telas largas; em telas menores fica acima. O áudio pronto fica em destaque e o áudio bruto permanece em detalhes. Alterações de texto, speaker e seleção são salvas automaticamente após uma pausa, com indicação de salvamento/erro. Editar texto ou speaker invalida o áudio anterior para aquela frase. A cópia antiga permanece no disco.

Em “Configurar vozes e gerar falas”, “Gerar somente pendentes” envia apenas frases selecionadas sem áudio pronto válido, mostra quantidade/caracteres e mantém as aprovações dos trechos prontos. Não garante que uma nova tentativa vá caber: confira a duração e ouça antes de aprovar. As autorizações e a chave da sessão continuam necessárias.

Os perfis do produto, disponíveis nas etapas 2 e 3, guardam nomes/grafias, valores/kits preenchidos, pasta dos materiais e IDs informados de vozes existentes. São salvos localmente em plataforma/workspace/perfis.json. Não guardam segredos, consentimentos ou aprovações. Ao carregar em um trabalho já transcrito, use “Buscar de novo” para aplicar os nomes às frases; leia a pasta dos materiais e confira os speakers. Valores de perfil preenchem as linhas correspondentes quando a análise de preços aparece, sem aplicá-los silenciosamente.

“Prévia das trocas com contexto” monta localmente os áudios prontos com dois segundos de contexto de cada lado. Os trechos sem áudio pronto são contados e omitidos. A prévia não aprova falas. Quando os visuais preparados estiverem incluídos, também aparecem em V2. A montagem completa continua exigindo todos os áudios selecionados aprovados.

A etapa 4 inicia pela escolha da entrega: montagem com falas (e V2 opcional), somente visuais, ou edição manual por marcações/cortes. Pastas e tutoriais ficam em detalhes. Validação: 55 testes passando, incluindo preservação de aprovações na geração seletiva, perfis sem credenciais e prévias de vídeo/áudio/V2/cancelamento; salvamento, filtros, perfis e prévia conferidos pela interface em servidor separado, sem chamadas aos serviços de voz.

### Fluxo principal com takes (25/10/2026)

As etapas passam a ser: **1 Arquivo → 2 Transcrição → 3 Falas → 4 Takes → 5 Prévia → 6 Premiere → 7 Legendas**. Escolher o arquivo abre a configuração da transcrição; ao terminar, a lista de falas aparece. A geração de voz continua dependendo das autorizações e aprovações explícitas do usuário.

Na etapa 4, escolha a pasta e use **Preparar takes automaticamente**: leitura da biblioteca quando necessária, detecção de menções se ainda não houver intervalos, sorteio sem repetição seguida e preparação dos clipes em V2. Os intervalos ajustados e os takes preparados são reaproveitados quando válidos. Kits desconhecidos, falta de variedade ou alterações na transcrição pausam o preparo com mensagem. Cada take pode ser selecionado ou sorteado individualmente, preservando os demais e respeitando kit, duração e vizinhos. Trocar um take exige prepará-lo novamente; os arquivos anteriores permanecem salvos.

A opção explícita “Esta entrega não precisa de takes” é salva no trabalho e mantém somente V1. Caso contrário, a prévia exige os takes preparados e incluídos. Ao entrar na etapa 5 com falas aprovadas e takes prontos, a prévia local começa automaticamente. Ela reúne os trechos com dois segundos de contexto, com áudio novo e V2. Confira a prévia e use **Aprovar prévia e preparar XML**: o XML completo é gerado e disponibilizado na etapa 6, mantendo V1, V2, cortes originais desativados em A2 e novas falas em A3. A entrega verifica no servidor a assinatura da montagem conferida. Alterações posteriores exigem nova prévia. Prévia e última entrega válidas são recuperadas ao reabrir o trabalho. Exportações parciais continuam em opções avançadas.

A etapa 7 recebe o SRT exportado da versão final para corrigir somente os nomes sem mudar timecodes. A importação do XML no Premiere é feita pelo usuário em Arquivo → Importar; não há controle remoto do Premiere. Verificação: 60 testes, fluxo automático dos takes e prévia/exportação pela interface com materiais sintéticos, sem créditos de voz.

### Limpeza segura em Ajustes

Em **Ajustes → Limpeza segura de materiais**, use **Analisar espaço** e depois **Executar limpeza segura**. A análise compara por SHA-256 as mídias acima de 10 MB, incluindo os destinos atuais e anteriores configurados no app. O botão informa cópias novas, espaço de duplicação, caches e cópias já otimizadas. O ganho real depende do compartilhamento de blocos do APFS.

A execução usa clones APFS com cópia na escrita: preserva nomes, caminhos, datas e conteúdo, verificando o hash antes de substituir atomicamente a cópia redundante. Alterações futuras em uma cópia não alteram a outra. Em volumes que não permitem a operação, o arquivo original é mantido e o resultado informa o aviso. A limpeza apaga apenas .pyc em caches conhecidos do projeto e artefatos conhecidos da compilação nativa; nunca remove mídias, XMLs, transcrições, áudios, ZIPs ou trabalhos antigos por idade ou nome.

Há progresso, cancelamento e retomada do acompanhamento ao voltar aos Ajustes. A análise e a execução exigem o app sem trabalhos ativos; durante a operação, novos trabalhos ficam bloqueados. Arquivos alterados após a análise exigem nova análise. O catálogo evita otimizar novamente cópias inalteradas e reconhece a consolidação inicial já feita neste projeto. Registros ficam em plataforma/workspace/limpeza. Não é necessário configurar uma automação agendada.

Verificação: 68 testes, incluindo clones independentes, hash inválido, alteração após análise, volumes incompatíveis, caminhos externos, cancelamento e bloqueio de novos trabalhos; análise, execução e segunda análise pela interface com arquivos sintéticos.

A geração de voz passou a ser a subetapa **3.2 · Gerar falas por speaker**, sempre expandida e destacada dentro de Falas, entre a conferência dos textos e as opções secundárias. A navegação de Falas mostra **3.1 Conferir textos → 3.2 Gerar falas por speaker → 3.3 Ouvir e aprovar áudios**. Os atalhos levam diretamente à seção correspondente. Sem textos selecionados, a geração fica desabilitada e orienta concluir 3.1. A mudança é de interface; não gera falas nem consome créditos automaticamente.

Aprovação em lote: os botões “Aprovar todos os textos”, “Desmarcar todos” e “Aprovar todos os áudios” ficam visíveis no topo da revisão. O texto de apoio informa quantos textos estão selecionados e esclarece que áudios só podem ser aprovados depois de gerados e encaixados. A aprovação de textos considera a lista inteira, inclusive fora do filtro atual.

Nomenclatura dos takes: o leitor reconhece “[QUANTIDADE] POTE/POTES - V/H”, “[QUANTIDADE] PRODUTO/UGC - V/H” e pastas KIT X. Sufixos de diferenciação existentes são tolerados sem virarem quantidade. ESTEIRA, ESTOQUE, SETA e UGC sem quantidade ficam como apoio, fora do sorteio por kit, sem bloquear materiais numerados. Uma associação manual continua possível. O preparo verifica mudanças de nomes, arquivos e datas na pasta e relê a biblioteca quando necessário, preservando associações manuais. A nomenclatura dos arquivos originais não é alterada.

A conferência da prévia separa faltantes, fora da duração e prontos para ouvir, com atalhos para resolver. A confirmação só aparece quando uma prévia válida existe; antes disso, a tela informa as pendências. Quantidades de meses na oferta continuam exigindo confirmação de correspondência com potes, sem associação implícita. Validação: 72 testes, mais conferência da pasta real SIZEFIX (33 materiais, 28 com quantidade e 5 de apoio).

Correspondência de ofertas por duração: na etapa Takes, “Minha oferta fala em meses · associar aos potes” permite declarar 1/3/6 meses → quantidade de potes. O mapeamento fica restrito ao trabalho e é usado somente em referências explícitas a pacotes, planos, tratamentos ou protocolos; duração de estudo isolada continua ignorada. A regra precisa ser informada pelo usuário. Alterá-la limpa as sugestões para identificar e preparar os intervalos novamente. Confirmado neste trabalho Pee Protect → SizeFix: 1/3/6 meses = 1/3/6 potes. Validação da atualização: 74 testes.

### Falas maiores e entrega rápida

Novos trabalhos usam **Abrir espaço para falas maiores · velocidade natural**. Uma fala longa é aceita sem aceleração: o restante da timeline avança pelo acréscimo. V1 preserva todo o vídeo original e usa a última imagem no espaço adicional; V2 acompanha os deslocamentos e estende sua última imagem quando cobre esse intervalo. A1 e os cortes originais desativados em A2 avançam junto; A3 recebe a fala completa. Marcadores e relatório usam os tempos finais. A prévia e a conferência de áudio também refletem os acréscimos. As legendas finais devem vir da sequência resultante no Premiere.

Em **Falas → Duração das falas na timeline**, “Aplicar e preparar áudios já gerados” reaproveita os arquivos locais sem novos créditos de voz. O modo antigo de manter a duração continua disponível. Versões antigas são preservadas; aprovações só são mantidas quando o áudio pronto é idêntico byte a byte.

Na etapa 4, **Autorizar tudo e gerar XML sem prévia** autoriza em lote os áudios das frases selecionadas e os takes, preparando os materiais locais quando necessário e seguindo diretamente à entrega. Não gera novas falas nem chama serviços de voz; se faltar um áudio, mostra a pendência. O relatório registra explicitamente que a conferência da prévia foi dispensada. Conferir a prévia permanece uma alternativa. Validação: 81 testes, incluindo áudio natural, deslocamentos de V1/V2/A1/A2/A3, duração da prévia, sinal de áudio após os deslocamentos e entrega rápida sem chamadas de voz; conversão local e entrega rápida verificadas pela interface com mídia sintética.
