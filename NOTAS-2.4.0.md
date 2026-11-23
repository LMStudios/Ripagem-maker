# Ripagem Maker 2.4.0

Melhorias editoriais a partir do uso da equipe:

- Takes distribuídos pelo número de usos e tempo em tela, mantendo a regra de não repetir em sequência. Associação por kit preservada. Classificação editável em produto, apoio ou depoimento; resumo da distribuição na conferência da entrega.
- Sugestões visuais para referências à apresentação, fórmula e pedido, mesmo sem o nome da marca. Começam desmarcadas e não criam trocas de áudio. A busca usa a transcrição; não lê potes ou textos que aparecem somente na imagem.
- Speaker ausente/conflitante fica “A_CONFIRMAR”. É possível ouvir o original, confirmar um novo speaker ou atribuir a várias frases pelos números. Áudio externo continua disponível por frase.
- Pronúncia separada da grafia oficial. Teste curto com ID de voz existente e autorização explícita de créditos. Alterar a pronúncia afeta somente as frases cujo texto enviado muda. A geração deixou de enviar frases selecionadas distantes como contexto.
- Análise local de possível repetição ao final e recorte manual em milissegundos. O bruto é preservado. Falas naturalmente maiores continuam aceitas no modo de abrir espaço; maior duração não é considerada repetição.
- Escolha explícita da trilha: manter o som original, adicionar arquivo em A4 com volume/repetição ou seguir sem trilha separada. A trilha participa da prévia e da conferência integral. Não separa voz e música já misturadas.
- Conferência da entrega com resumo, pendências, distribuição dos takes e caminho confirmado do XML. A revisão integral procura a marca antiga e grafias alternativas na montagem de áudio; imagens e mudanças posteriores no Premiere exigem conferência própria.

## Validação

137 testes Python concluídos, 1 ignorado por condição do ambiente. Oito verificações JavaScript de concorrência de salvamento e ciclo da geração. FFmpeg executado no Mac para recorte, mixagem, prévia e XML com A4. Interface exercitada em servidor isolado com dados sintéticos: salvar pronúncia, alterar speaker, extrair original, escolher trilha e exibir pendências.

Chamadas de voz foram simuladas nos testes: não foram consumidos créditos. O arquivo real com a palavra final duplicada não foi disponibilizado, portanto a causa desse caso específico não foi comprovada. Alertas de ASR são sugestões e podem errar.

Os testes de caminhos, UTF-8 e ponte de arquivos do Windows são simulações no Mac. Instaladores foram compilados para Windows; abertura nativa no Windows e importação deste novo XML no Premiere precisam de validação nesses aplicativos.

Credenciais, trabalhos e mídias não entram nos pacotes. A atualização universal preserva dados e pede reabertura do aplicativo.
