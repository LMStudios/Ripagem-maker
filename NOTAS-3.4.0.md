# Ripagem Maker 3.4.0

- Etapa Takes → "Produto antigo na imagem": procura o nome do produto antigo escrito nos quadros (rótulos, telas e legendas gravadas), inclusive onde o narrador não fala dele. Leitura local (RapidOCR / PP-OCRv6, Apache-2.0), sem API e sem envio de arquivos.
- Por padrão analisa a partir de 2 min antes da 1ª menção falada; "vídeo inteiro" fica nos ajustes. Quatro processos em paralelo; cancelar preserva os minutos já lidos, e mudar nome ou janela reaproveita a leitura.
- Cada trecho é sugestão até aprovação: miniaturas, início/fim, motivo e confiança qualitativa. Aprovar, descartar, ajustar tempos e ver o trecho com áudio original, individualmente ou em lote. Trechos colados em falas trocadas ficam agrupados como já cobertos.
- Aprovados entram no XML como marcadores "PRODUTO ANTIGO NA IMAGEM", acompanhando extensões e margens removidas. Antes da 1ª menção: "só marcar". Nesta versão não há takes automáticos nessas áreas; imagem e áudio originais não mudam.
- Medição local (Mac M4): 32/32 aparições silenciosas numa VSL de conta-gotas em 4,4 min; 14/15 (a restante detectada parcialmente) numa VSL de potes em 3,2 min. Windows não medido.
- Instaladores incluem o motor de leitura (+~80 MB de pacotes no Windows).
