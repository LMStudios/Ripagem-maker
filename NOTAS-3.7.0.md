# Ripagem Maker 3.7.0

## Vídeo com legendas na imagem (etapa 7)
- Renderiza a montagem final (V1 com extensões, V2, falas novas e margens removidas) com o áudio final e as legendas do SRT da montagem aplicadas na imagem.
- Estilo: fonte, tamanho, cor e cor de destaque, negrito, itálico, maiúsculas, contorno, sombra, caixa de fundo com opacidade, posição, alinhamento e margens. Medidas relativas ao vídeo (servem para 16:9, 9:16 e 1:1).
- Exibição por frase, frase com a palavra falada em destaque (só com alinhamento por palavra ≥ 90%; senão volta para frase com aviso) ou poucas palavras por vez.
- Presets: quatro padrões e presets próprios reutilizáveis em outras VSLs.
- Prévia de 15 s antes do vídeo inteiro; render completo em blocos de 1 minuto, cancelável sem perder os blocos prontos. Blocos são apagados quando o vídeo fica pronto.
- Com legendas gravadas no original, a legenda nova entra só onde a imagem foi coberta por takes.
- Teste real (Mac M4, Glycozen Pro): prévia em 96 s na primeira vez (inclui o áudio final); vídeo completo de 72 min em 5,4 min, 4.301,08 s (montagem: 4.301,13 s), idêntico à prévia quadro a quadro, sem saltos nas emendas.
- Fontes: as do sistema. Fontes livres embutidas ainda não incluídas.
