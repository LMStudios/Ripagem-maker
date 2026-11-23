# Ripagem Maker 3.0.0

## Experiência de trabalho

Painel simplificado: Troca de potes, Microlead’s, Nomenclatura VTurb e Ajustes. A validação de produto e pitch passou para a entrega de Troca de potes. Regras de corte ficam em Ajustes → Transcrição e cortes. Rotas antigas e trabalhos existentes continuam acessíveis; nenhuma biblioteca foi apagada.

Arquivo prioriza o envio e apresenta os trabalhos recentes em um segundo bloco. Transcrição destaca o novo produto. Falas reúne resumo, quantidade de menções, duração e andamento; configurações auxiliares ficam em Extras. “Complexa” exige alteração de modo de uso e mais de 60 menções na transcrição disponível; transcrição parcial fica identificada.

Aprovar textos abre a geração. Geração tem uma tela própria com andamento e cancelamento. Depois abre a conferência dos áudios; após aprovação completa, libera Takes. Navegação e API verificam mídia existente, texto/speaker atualizados, duração preparada, adaptação de uso confirmada e aprovação. Uma regeneração em andamento também bloqueia o avanço.

Na conferência, filtros de erros/alertas e modo de uso priorizam os pontos de atenção. É possível voltar à frase selecionada para corrigir. Conferência local dos finais sugere repetições; reaproveita análises atuais, não corta nem aprova automaticamente. Não foi consumido crédito nos testes.

## Takes e XML

Novos trabalhos usam vídeos completos. O XML referencia os arquivos originais, conserva seu frame rate e aplica escala separada. V2 mantém movimento durante o espaço extra das falas, sem congelar os takes. A imagem base de V1 ainda pode ser estendida atrás da cobertura quando a timeline abre espaço para áudio maior.

Se não existe combinação de vídeos inteiros que caiba na janela, o app informa a pendência. Pode-se ajustar os tempos ou permitir explicitamente estender a cobertura até o próximo intervalo. Não inventa uma equivalência de kit e não substitui material de produto por ESTEIRA/ESTOQUE silenciosamente. Takes sem quantidade precisam ser classificados como Produto.

O modo de recortes/imagens permanece como opção explícita de compatibilidade. XMLs já gerados não são alterados. Trabalhos antigos podem exigir preparar novamente os takes ao mudar para o modo completo. As mídias originais devem permanecer no lugar depois da importação.

## Verificação

Interface percorrida em servidor isolado no Mac: arquivos/recentes, dashboard, aprovação dos textos, geração simulada de voz, aprovação dos áudios, liberação automática de Takes, planejamento de vídeos completos, prévia real via FFmpeg, geração e download HTTP do XML. Confirmados in=0/out=48 em mídias de 24 fps e 2 segundos. Testes também verificam movimento durante áudio expandido e diferentes resoluções, concorrência de salvamento e bloqueio dos endpoints.

Vozes e transcrições externas foram simuladas. A análise semântica de modo de uso continua por regras e exige instruções confirmadas. A revisão de áudio não examina imagens/legendas visuais. Windows nativo e importação do novo efeito de escala no Premiere não foram executados: a compatibilidade estrutural do XML e da ponte Windows foi testada no Mac.

## Backup e retorno

Foi criado um backup privado do código 2.4.2 e do aplicativo Mac antes das alterações. Feche o app e execute o restaurador .command para voltar ao código anterior, mantendo mídias, trabalhos e credenciais no lugar. Se também substituir o aplicativo nativo pela nova distribuição, a cópia do aplicativo antigo está no ZIP do backup e pode ser recolocada no local original.
