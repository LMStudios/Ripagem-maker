# Ripagem Maker 3.0.1

Em Falas, o bloco Adaptações de modo de uso oferece Aprovar todos os modos de uso. O botão informa quantas confirmações faltam e inclui todas as adaptações identificadas, mesmo fora do filtro ou ainda não selecionadas para gerar áudio.

A confirmação salva os textos atuais como aprovados para a adaptação de uso. Não seleciona novos textos para geração, não chama o serviço de voz e não aprova áudios. As aprovações de áudio, prévias e revisões existentes são preservadas quando não há alteração de conteúdo.

Uma edição posterior do texto exige nova confirmação somente daquela frase. A aprovação do lote verifica os textos no servidor e é atômica: se uma frase mudou durante a operação, o lote não é parcialmente aplicado.

Verificação: testes de confirmação em lote, preservação de áudio/seleção/prévia, concorrência e reaprovação após edição. Interface testada no Mac com duas adaptações e filtro mostrando apenas uma: ambas foram aprovadas. Ao editar uma delas, a contagem voltou para 1 de 2. Nenhum crédito consumido.
