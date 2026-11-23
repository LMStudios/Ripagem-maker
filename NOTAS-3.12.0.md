# Ripagem Maker 3.12.0 — Interface de estúdio

Base: 3.11.1 (código local idêntico ao pacote 3.11.1). Só apresentação: transcrição, vozes, busca visual, takes, XML, login e relatórios continuam com a mesma lógica.

## O que mudou
- **Troca de potes em layout de estúdio:** etapas na coluna esquerda com o ✓ de etapa preparada; cabeçalho de uma linha (produto, "Continuar de onde parou", tempo, Como usar, Pasta do projeto, Ferramentas da etapa, Ajustes); barra inferior fixa com Voltar, o resumo do que falta e **uma** ação principal.
- **Ação principal por etapa:** Começar ripagem · Aprovar textos / Continuar para Takes (conforme a subetapa) · Preparar takes ou Continuar para Entrega · Aprovar prévia e gerar XML · Confirmar legenda · Gerar XML para o Premiere. Os demais botões ficam com aparência secundária.
- **Gaveta "Ferramentas da etapa":** resumo e pitch, forma e modo de uso, extras de preços e arquivos, tratamento de áudio e busca automática (Falas); configurações e entrega rápida (Takes); exportações avulsas, identificação do XML e legenda opcional (Entrega); vídeo com legendas (Legendas). "Pasta do projeto" abre na gaveta.
- **Takes em abas:** Preparar takes · Produto antigo · Cobertura, com contadores de pendências.
- **Falas:** a lista rola por dentro e termina acima da barra; caminhos longos em uma linha, com o caminho completo ao passar o mouse.
- **Ajustes em abas:** Fluxo e notificações · Integrações · Takes e áudio · Pastas e armazenamento · Versão e atualizações.
- **Correções:** ordem das etapas (Legendas 6 antes de Entrega 7); "null/null" e caminho completo em Nova ripagem; "Etapa N de 7" repetido nos títulos.

## Medido (projeto real, cópia isolada)
| Tela | Antes 1366×768 | Depois 1366×768 | Antes 1440×900 | Depois 1440×900 | Ações principais |
|---|---|---|---|---|---|
| Nova ripagem | 1,2 telas | 1,0 | — | — | 1 |
| Falas | 4,5 | 1,9 | 3,9 | 1,35 | 11 → 1 |
| Takes | 3,0 | 1,2–1,4 | 2,6 | 1,3 | 6 → 1 |
| Prévia | 1,6 | 1,0 | 1,3 | 1,0 | 1 |
| Legendas | 3,7 | 2,45 | 3,1 | 2,1 | 5 → 1 |
| Entrega | 2,6 | 1,5 | 2,2 | 1,3 | 5 → 1 |
| Ajustes | 7,2 | 1,0–3,1 por aba | 6,1 | — | 21 → por aba |
O conteúdo da etapa começa logo abaixo do cabeçalho (antes: 515 px do topo em 1440×900).

## Testes
Testes Python, 12 do Electron e os de interface sem falhas, mais `tests/test_layout_312.cjs` (ordem de carregamento, ordem das etapas, "null", todas as seções de Ajustes em alguma aba, layout sem chamadas ao servidor). Conferência visual no app em 1366×768 e 1440×900, modo guiado incluído; console sem erros.

## Ainda falta
- Falas e Legendas ainda rolam um pouco (1,4–2,5 telas): o conteúdo interno de cada subetapa continua o original e pode ser compactado numa próxima rodada.
- Teste de uso com um editor novo (do zero até o XML) e medição de cliques e tempo.
- Windows real, zoom de 125% e 1920×1080 não conferidos visualmente.

Backup: `backups/antes-redesenho-3.11.1-20261120-123152/`. Para voltar, aplique `Ripagem-Maker-Atualizacao-3.11.1.zip` em Ajustes → Atualizações.
