# Ripagem Maker 3.7.1

- Produto antigo na imagem: atalho na etapa Falas ("Procurar em segundo plano"). A busca roda numa fila própria e não atrasa amostras de voz nem renders.
- 1ª menção: se a legenda gravada mostra o nome antes do ponto achado pela transcrição, essa passa a valer para as regras dos takes (antes dela, só marcação).
- "Nome falado sem troca?": trechos em que a legenda gravada mostra o nome fora das falas trocadas são destacados para conferência.
- Legendas da montagem: o aviso de nome antigo agora usa o áudio final inteiro, pegando menções fora do trecho transcrito (ex.: transcrição só da 2ª metade).
- Trabalhos com trechos aprovados pedem para preparar os takes de novo após atualizar; os demais não mudam.
- Teste real (Glycozen, transcrição só da 2ª metade): 1ª menção 36:00 → 34:41 pela legenda gravada; avisos do nome antigo falado sem troca em 34:41, 34:42 e 35:14; 5 takes a mais a partir de 34:41, sem pendências.
- A transcrição do áudio final (legendas) só é refeita quando o áudio muda: preparar takes de novo não a invalida. Usa o idioma da transcrição original, o que permite o modelo local menor no app instalado.
