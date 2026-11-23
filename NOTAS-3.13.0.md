# Ripagem Maker 3.13.0 — Conferência final e relatório de entrega

Base: 3.12.0 (interface de estúdio).

## Novo
- **Entrega → Conferência final do vídeo exportado.** Depois de exportar no Premiere, clique em "Conferir vídeo exportado…" e escolha o vídeo pronto (seletor nativo no app; no navegador, cole o caminho). O vídeo é lido no lugar, sem cópia.
- O app transcreve o áudio e lê o texto dos quadros **neste computador** e procura:
  - o nome do produto antigo e as grafias cadastradas no projeto, no áudio, na imagem e na legenda gravada;
  - os valores antigos, quando o projeto tem troca de preços.
- **Relatório de entrega para o cliente:** página única (HTML, com os quadros embutidos), com veredito ("Conferência aprovada" ou "N pontos para conferir"), falas substituídas, aparições cobertas, tabela de pontos com tempo, trecho e quadro, e a explicação do método. Salvo em `entregas/conferencia_final/<data>/` no projeto; "Abrir relatório de entrega", "Mostrar no Finder" e "Copiar caminho".
- Refazer a conferência do mesmo vídeo reaproveita a transcrição e a leitura dos quadros.
- Electron: seletor nativo de vídeo (`files:choose-video`).

## Testado em vídeo real
VSL final exportada do JELLYGEN (64 min), numa cópia isolada do projeto:
- 1ª rodada 12 min (transcrição + leitura de 64 min de imagem); refazer: 5,5 min com a imagem em cache.
- A lista automática de grafias incluía "gelatin", palavra comum da copy, e gerou 115 pontos falsos. Corrigido: a conferência usa só o nome do produto e as grafias cadastradas, e na imagem só leituras muito próximas do nome.
- Resultado final: **2 pontos no áudio** — 36:17 "Because Gelagen cannot cost…" (encontrado) e 54:32 "she recommends Gelogen…" (possível). Nenhum na imagem nem na legenda. Os dois trechos ainda precisam ser ouvidos para confirmar.

## Testes
Testes Python (6 novos da conferência final), Electron e interface sem falhas. Cartão e relatório conferidos no navegador.

## Limites
- Erros de reconhecimento podem ocultar ou sugerir ocorrências; a conferência humana continua necessária.
- Windows real não testado.
