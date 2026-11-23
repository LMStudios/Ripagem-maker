# Ripagem Maker 3.6.0

## Legendas da montagem final (etapa 7)
- "Gerar SRT da montagem": SRT novo no tempo da montagem, com falas novas, extensões e margens removidas. O SRT original e o corretor de nomes (que preserva timecodes) continuam separados.
- Texto: transcrição original fora das trocas + texto aprovado das falas novas; grafia do produto novo padronizada. O tempo da fala antiga nunca é reaproveitado.
- Tempos: áudio final da montagem transcrito localmente (MLX/Faster Whisper), guardado para as próximas gerações.
- Detecta legendas gravadas no vídeo original; nesse caso, por padrão, legenda só onde a imagem foi coberta por takes (V2). Opção "vídeo inteiro".
- Blocos com limite de caracteres por linha, linhas e duração; o nome do produto nunca é quebrado; sem sobreposições.
- Avisos: fala nova que não bate com o texto aprovado e nome antigo ainda falado.
- Teste real (Mac, Glycozen Pro, 72 min): legendas gravadas detectadas (23/24 quadros); 356 blocos só nas 90 coberturas; 96,5% das palavras com tempo do áudio final; sem avisos.

## Otimização · trocar valores dos kits (etapa 1)
- Botão próprio para partir da VSL finalizada: troca preços e quantidades dos kits e, opcionalmente, o produto.
- O trabalho fica marcado como otimização; na etapa Falas, "Preços e kits" abre no topo com detecção automática.
- Sem produto novo, só as frases de preço e kit entram na lista (menções ao produto não geram vozes). Com produto novo, ambos.
- Ao gerar as frases com os valores novos, a lista de trocas é refeita. Takes seguem as quantidades novas.
