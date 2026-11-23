# Ripagem Maker 3.14.0 — Buscador de b-roll por frase

Base: 3.13.0.

## Novo
- **Takes → aba B-roll.** Lista as frases da transcrição com uma busca sugerida (palavras visuais da frase, sem o nome do produto), editável. Filtros: texto da fala, frases com fresta visual, já buscadas, com b-roll escolhido; "Só clipes limpos".
- **YouTube automático:** "Buscar" procura vídeos curtos (até 3 min, com "stock footage" na busca), pula revendedores de banco pago, vídeos longos, aulas e podcasts, e baixa só ~10 s de cada candidato, em H.264 sem áudio.
- **TikTok e Pinterest pelo link:** a frase tem "Procurar no TikTok ↗" e "Procurar no Pinterest ↗" (abrem a busca no navegador com as palavras da frase); cole o link do vídeo escolhido e clique em Adicionar. A busca automática nesses dois sites não funciona sem navegador logado (TikTok recusa, Pinterest devolve 404).
- **Conferência de cada clipe neste computador:** texto na tela (OCR) e marca d'água. A marca d'água em grade de linhas finas (Motion Array, Envato etc. revendidos) é achada pelas bordas que ficam paradas enquanto a cena se mexe; logos e textos fixos pela mediana dos quadros. Canal com marca d'água é bloqueado nas buscas seguintes do projeto.
- **Nada entra sem escolha:** "Usar nesta frase" põe o clipe em **V3** do XML, a partir do início da frase, até o fim da frase ou do clipe; sem áudio. Não deixa dois b-rolls no mesmo trecho. O manifesto do XML lista o b-roll (`broll_v3`).
- Arquivos no projeto: `broll/clipes`, `broll/miniaturas`, `broll/estado.json`.

## Testado
- JELLYGEN (cópia isolada): busca "woman looking in bathroom mirror" → 5–6 candidatos relevantes em ~45 s; 2 clipes com grade de marca d'água revendida (título sem nome de banco) marcados corretamente, 1 com texto na tela, 1 logotipo de produto. TikTok e Pinterest pelo link: baixados e conferidos (vídeos verticais).
- Escolha pela tela → XML com V3 no quadro certo (7:00, 2,9 s).
- 8 testes novos; bateria Python, Electron e interface sem falhas.

## Limites
- Confira a licença de cada vídeo antes de entregar ao cliente.
- A prévia renderizada não mostra o b-roll; ele aparece no Premiere.
- Vídeo vertical (TikTok/Pinterest) entra preenchendo o quadro 16:9, com corte em cima e embaixo.
- Muitas buscas seguidas no YouTube podem pedir "confirme que não é robô"; o app para a busca e mantém o que já baixou.
- A atualização pelo ZIP instala o componente de busca (yt-dlp) na próxima abertura.
