# Ripagem Maker 2.4.2

Adaptação completa de instruções de uso:

- Em Falas → Trocar forma e modo de uso, informe a orientação real do produto novo no idioma da VSL. Não é mais necessário ter uma correspondência exata com a orientação antiga.
- Frases de aplicação são substituídas por inteiro, retirando rota, dose, frequência e duração antigas. Termos de absorção, mecanismo e comparações incompatíveis usam uma descrição confirmada separada.
- Referências próximas com pronomes e sem a marca também podem entrar na busca. Frases sem relação com a troca são preservadas.
- Se falta uma orientação ou explicação necessária, a frase original fica legível para editar, marcada como pendente. O app não produz uma mistura de instruções antigas e novas nem envia essa pendência para gerar voz. É possível editar e confirmar explicitamente cada frase.
- Edições posteriores invalidam a confirmação. Áudios dos textos alterados precisam de nova geração; os arquivos anteriores ficam preservados no histórico.

A busca continua baseada em regras locais de texto. Não faz reescrita semântica livre por IA e não garante identificar todas as referências implícitas. As instruções e descrições confirmadas são utilizadas como texto de substituição; confira a coesão na etapa de revisão antes de aprovar.

Validação: testes de aplicação na pele, posologia antiga, mecanismo transdérmico, modos inversos, contradições com cápsulas, instruções com pronomes, bloqueio de pendências e confirmação persistente. Interface exercitada em servidor isolado no Mac: pendência sem orientação e substituição da frase completa ao informar o novo uso. Nenhum crédito de voz consumido. Windows nativo não executado neste teste.
