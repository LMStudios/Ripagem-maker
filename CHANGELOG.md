# Notas de versão

## 3.16.0

- Nova aparência: paleta, tipografia, botões, campos, abas, avisos e diálogos seguem um único sistema visual no painel e na Troca de potes.
- Barra lateral organizada em grupos (Criar, Utilitários, Sistema) com ícones, e pode ser recolhida; a escolha fica salva.
- Busca rápida (Ctrl/⌘ K ou /) para ir a qualquer tela, começar uma ripagem ou reabrir um projeto recente, também dentro da Troca de potes.
- Em telas estreitas, a navegação vira uma faixa única com ícones, sem rolar a página para os lados.
- Os arquivos da interface são revalidados por ETag e ficam em memória no app local: reaberturas não baixam de novo o que não mudou.

## 3.15.6

- Comparação de quadros da detecção visual usa menos memória temporária e processamento, mantendo a leitura do OCR na resolução original da análise.

## 3.15.5

- Detecção visual no Windows usa um processo de OCR por vez e limita o paralelismo interno da leitura e das miniaturas.
- Configuração inicial de login no Windows para o projeto da equipe, com convite por código dentro do aplicativo.

## 3.15.4

- O XML do Premiere declara takes e B-rolls das faixas de sobreposição apenas como vídeo, evitando divergências de áudio ao vincular esses arquivos no Windows.

- O XML explicita o formato mono ou estéreo das falas e os caminhos locais com letras de unidade no Windows.

## 3.15.3

- A geração manual processa as falas prontas mesmo quando outras ainda precisam de revisão do modo de uso.

## 3.15.2

- Busca e instalação de atualizações do código dentro do app para usuários com login de equipe.
- O app aguarda o término das tarefas, verifica o pacote e reabre após instalar na edição Electron atualizada.

## 3.15.1

- Caçar B-rolls está disponível em Ferramentas avulsas, com busca, prévia e download sem precisar abrir um projeto.
- Na Troca de Potes, as sugestões começam na primeira menção ao produto. Os clipes escolhidos entram na faixa V3 do XML.
- Busca, cartões e botões se reorganizam em janelas estreitas.

## 3.15.0

- Busca de B-rolls no TikTok e no Pinterest pelo aplicativo instalado, com detecção de texto na tela e marca-d’água.
- Clipes já baixados podem ser reutilizados em outras falas.

As notas das versões anteriores estão no [histórico de versões](https://github.com/LMStudios/Ripagem-maker/tree/442d4eb5744b0a4dc46f4df47eea62f92fbec6dd).
