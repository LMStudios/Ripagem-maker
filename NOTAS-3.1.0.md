# Ripagem Maker 3.1.0

- Gemini 2.5 Flash para sugestões de adaptação completa do modo de uso, com contexto anterior/posterior e instruções confirmadas do produto novo.
- Chave própria em Ajustes → Integrações e APIs, salva no cofre do sistema; teste de conexão consulta metadados sem geração.
- Autorização explícita de envio de textos ao Google; áudio e vídeo não são enviados por esta integração.
- Revisão lado a lado, aplicação seletiva e confirmação posterior em Falas. Não aprova textos/áudios nem gera voz automaticamente.
- Frases editadas durante a análise não são sobrescritas. Cache por conteúdo reaproveita lotes concluídos; cancelar ou atingir cota preserva sugestões salvas.
- Erros de cota sem troca automática de modelo. O app não verifica o plano de faturamento da chave: use projeto sem faturamento ativo para a faixa gratuita.
- Testes automatizados com respostas simuladas e interface local no Mac. Sem chave real fornecida, não houve validação ao vivo do Gemini, nem teste nativo no Windows.
