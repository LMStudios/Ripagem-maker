# Ripagem Maker 3.11.0 — Referências do pote, limites das aparições e cobertura real

Base: 3.10.24, conferida por hash contra o ZIP de atualização 3.10.24 antes de editar (113 arquivos iguais, sem alterações locais).

## 1. Referências visuais do pote antigo
Em Takes → Produto antigo na imagem → Referências do pote antigo:
- **Abrir o vídeo original**, pausar e **Usar este quadro como referência**. O quadro aparece em tamanho grande para o editor arrastar um retângulo sobre o pote e **Confirmar seleção**.
- Várias referências (até 12), de ângulos e tamanhos diferentes, com miniatura, horário no original, **Substituir** e **Remover**. Ficam na pasta do projeto e ligadas à versão do vídeo original: se o vídeo mudar, a referência é marcada para substituição e deixa de ser usada.
- **Buscar com estas referências** usa a mesma busca local (OCR, comparação de rótulos e cache por minuto) e acrescenta a comparação com a região marcada. A decisão compara o desenho fino dos detalhes da região (letras do rótulo), depois de alinhar o quadro à referência, inclusive com perspectiva para o pote de lado. Cor e formato do pote, sozinhos, não bastam.
- Cada card mostra o motivo: **Nome lido no rótulo**, **Nome na legenda gravada**, **Parecido com a referência**, **Parecido com o rótulo lido em outro quadro**, **Aparição acompanhada entre quadros**, **Marcada pelo editor**. Correspondência só por aparência entra como “revisar com atenção” e fica fora do “Aprovar todos de confiança alta”.
- Busca automática após a transcrição e **Varrer o vídeo inteiro** mantidas. Segundo plano com progresso por fase, cancelamento e reaproveitamento do que já foi lido. Referências novas não disparam a busca sozinhas: o editor pede a busca.

## 2. Limites da aparição
- Depois de achar um candidato, o app analisa 12 quadros por segundo perto da entrada e da saída e acompanha o pote quadro a quadro até ele sair, até um corte de cena ou até 12 s além da última leitura.
- Cortes e quadros sem o pote separam aparições distintas; duas leituras do mesmo plano que se encontram viram uma aparição só. Se o acompanhamento se perde (pote girando), o app tenta reencontrar o pote pelo nome ou pela referência antes de desistir.
- Legenda gravada não é acompanhada como se fosse o pote.
- Intervalo detectado e intervalo de cobertura aparecem no card. A margem visual configurada (padrão 1,5 s) vale sobre a aparição, respeitando o começo e o fim do vídeo e os tempos ajustados pelo editor.
- Revisões preservadas: bordas refinadas e leituras unidas mantêm a aprovação. Se a nova área for muito maior que a revisada, volta para revisão com o aviso “aparição ampliada”.
- Mantida a escolha do projeto de cobrir aparições aprovadas antes da 1ª menção. Aparições só visuais ficam em Takes; a sugestão de nova fala continua dependendo da legenda gravada/áudio.
- Pote encontrado só pela aparência, mas com outro nome legível no rótulo, é descartado.

## 3. Cobertura real antes do XML
Em Takes → **Conferir cobertura do produto antigo**: compara as aparições aprovadas com os takes que ficarão em V2, no tempo final da sequência (expansões de áudio e fechamentos de margem). Cada fresta mostra início e fim no vídeo original e no Premiere, com:
- **Ajustar take** — abre a revisão lado a lado da aparição, com Trocar take;
- **Repreparar este intervalo** — refaz só os takes das janelas com fresta e reaproveita o restante;
- **Marcar para revisão no Premiere** — o XML recebe o marcador **PENDÊNCIA VISUAL · produto antigo**, falas aprovadas e takes preparados ficam como estão, e o relatório registra os intervalos marcados (pode ser desfeito).
Quando o editor autorizou vídeos inteiros e eles não cabem, as opções do projeto continuam aparecendo antes de qualquer mudança de duração, corte ou posição.

## 4. Extras
1. **Lado a lado**: trecho original e take escolhido juntos, com Reproduzir juntos, Trocar take e Usar este quadro como referência. Atalhos ← Anterior, → Próximo, A Aprovar, D Descartar, Espaço reproduz, Esc fecha. Ao voltar, filtro, seleção e posição da lista são mantidos.
2. **Marcar aparição que ficou de fora**: Marcar início e Marcar fim no player do original, Enviar aparição para os takes. Entra aprovada, sobrevive a novas buscas e pode virar referência.
3. **Continuar de onde parou**: ao reabrir, uma ação principal (Revisar N aparições, Resolver N frestas, Preparar os takes, Salvar XML). Reaproveita áudios, busca e takes que ainda correspondem à montagem.
4. **Resumo na Entrega**: aparições aprovadas, cobertas, marcadas para o Premiere, frestas abertas e ainda para revisar. O cronômetro continua encerrando no primeiro salvamento confirmado do XML. A busca longa avisa ao terminar pelas notificações de tarefas já existentes.

## Resultados medidos

### Vídeo sintético com gabarito exato (bench/referencias_visuais/medir.py)
72 s, 11 aparições: antes da 1ª menção, rótulo grande, rótulo pequeno, desfocado, de lado, curta (0,6 s), duas separadas por um corte, entrando pelo canto, zoom, pequeno e desfocado; mais um pote igual com o nome ROSEDIL.

| | 3.10.24 | 3.11 sem referência | 3.11 com 2 referências |
|---|---|---|---|
| Aparições encontradas | 11/11 | 11/11 | 11/11 |
| Falsos positivos | 0 | 0 | 0 |
| Pote ROSEDIL | rejeitado | rejeitado | rejeitado |
| Aparições do corte separadas | não (uma só) | sim | sim |
| Erro médio nas bordas | 0,57 s | 0,12 s | 0,03 s |
| Quadros do pote sem take (margem 1,5 s) | 32 | 13 | 0 |
| Busca sem cache / com cache | 41 s / 0 s | 68 s / 0 s | 71 s / 0 s |

Comparação por aparência isolada (12 fundos diferentes): 0 falsos positivos em 144 casos de potes do mesmo modelo com outro nome (ROSEDIL, JELLYGEN, GELATIN, VITAMAX) e 0 em quadros sem pote. Encontrou 12/12 em tamanho normal, 35%, 25%, desfocado e de lado; 0/12 no pote pequeno e desfocado ao mesmo tempo.

### VSL real disponível: FUNIL VSL 01 MOD · Gelagen → Jellygen (64 min)
Única VSL original ainda no disco; as 10 VSLs anteriores não estão mais disponíveis, então a amostra de regressão foi esta. Cópia isolada; o projeto real não foi alterado.
- Bordas refinadas: entrada e saída acompanhadas em 80 de 95 leituras; bordas conferidas em quadros extraídos (cortes em 2381, 2487, 2813, 3038, 3060 s corretos).
- Quadros do pote sem take em V2: preparo com os intervalos da 3.10.24 = 17 quadros (2 aparições); com a 3.11 = 0. Na medição intermediária, contando também a extensão 2571–2585 s (que agora volta para revisão como “aparição ampliada”), eram 100 quadros na 3.10.24.
- Revisões preservadas: 45 aprovações do editor mantidas; partes divididas por corte herdam a aprovação; a área ampliada pede nova conferência.
- Referências: os potes desta VSL são renderizados de forma diferente em cada cena; a referência achou a própria cena (sem falsos positivos em 24 quadros conferidos).
- Tempo: busca completa com OCR em cache 4 min 14 s (refino 2 min 35 s, que a 3.10.24 também fazia; limites ~1,5 min); comparação com 1 referência ~3 min a mais com 4 processos; segunda rodada com cache 2 s. Cancelar e retomar reaproveitou os minutos já lidos.

### Testes
543 testes Python (1 ignorado por ausência de material local), 12 do Electron e 12 arquivos de interface, sem falhas. 23 testes novos (referências, aparência, acompanhamento com corte e salto, revisão preservada, limites, aparição manual, frestas com tempo do Premiere e marcação). Quatro testes antigos atualizados: três já falhavam na 3.10.24 por causa da margem de 1,5 s e da versão do refino; um mudou de regra (partes de uma aparição aprovada divididas por corte herdam a aprovação).
Interface conferida no navegador com cópia isolada: referência marcada no quadro, lado a lado com atalhos (←, →, A, D, Esc), filtro e posição mantidos, marcação manual, frestas (marcar, desfazer, repreparar), ação ao reabrir e resumo na Entrega. XML de revisão gerado com o marcador PENDÊNCIA VISUAL e o intervalo no relatório.

## Limitações conhecidas
- Rótulos com uma ou duas letras de diferença no mesmo modelo de pote (ex.: GELAGEN × GELAGON, COLAGEN) não são separados pela aparência; o OCR também os aceita como grafia próxima.
- Pote pequeno e desfocado ao mesmo tempo raramente é confirmado pela aparência: depende do acompanhamento a partir de um quadro nítido ou de uma referência daquele tamanho.
- Em VSLs com potes gerados por IA, cada cena desenha o rótulo de um jeito; a referência encontra a mesma filmagem e cenas reaproveitadas, não outra renderização. Marque uma referência por visual diferente do pote.
- Windows: lógica coberta por testes no Mac; instalação e uso em um PC Windows real ainda precisam de homologação.

## Backup
`backups/antes-referencias-visuais-3.10.24-20261120-074333/` — código, testes e o ZIP de atualização 3.10.24, com SHA256.txt e RESTAURAR.txt. Para voltar: feche o app e aplique `Ripagem-Maker-Atualizacao-3.10.24.zip` em Ajustes → Atualizações, ou extraia `codigo.zip` na pasta do app. Projetos, mídias e chaves não estão no backup e não foram alterados.

Projetos analisados antes desta versão recebem uma única atualização automática da busca (reaproveita o OCR já lido e preserva as revisões). Depois disso, prepare os takes de novo se o aviso aparecer.
