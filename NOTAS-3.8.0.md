# Ripagem Maker 3.8.0 — versão modular (04/11/2026)

## Backup da versão anterior (3.7.4)
`backups/antes-modular-3.7.4-20261104/` — código, ajustes e metadados dos projetos (JSON/XML/SRT), com SHA256.txt e RESTAURAR.txt (passo a passo). Chaves continuam no cofre do sistema e não foram copiadas nem alteradas. Mídias não foram tocadas.

## O que mudou
**Painel com dois caminhos**: Fluxo completo e Ferramentas avulsas. Cada ferramenta mostra o que recebe, o que entrega, onde salva e se tem custo. As que trabalham sobre um projeto abrem direto na etapa certa, reaproveitando transcrição e áudios (sem nova transcrição, geração ou cobrança). Novas telas: Ferramentas avulsas, Projetos, Tratamento de áudio avulso e Separação de voz e trilha.

**Projetos**: pasta nova com nome do projeto, produto e data (`VSL_14_NovaPure_2026-11-04_090507`); campo “Nome do projeto” na etapa Arquivo; `projeto.json` com favorito e última abertura. Cartão “Projeto” dentro da troca de potes com caminho real, Abrir pasta, Copiar caminho e Mover projeto.

**Segurança e recuperação**
- Arquivos da transcrição gravados de forma atômica (temporário + troca); um arquivo incompleto não substitui o válido.
- Tarefas em curso são registradas; se o app fechar, aparecem como interrompidas no Painel ao reabrir.
- Mudança de pasta interrompida é desfeita ou concluída na próxima abertura.
- O motor só aceita pedidos do próprio app (Host/Origin locais); páginas da internet não conseguem acioná-lo.
- O log de diagnóstico oculta chaves (AssemblyAI, ElevenLabs, MiniMax, Gemini), tokens e e-mails.
- Credenciais seguem no cofre do sistema (Keychain/Gerenciador de Credenciais). O app não tem sistema de usuários; não foi criado um paralelo — o acesso continua restrito ao computador local.
- Ferramentas avulsas nunca sobrescrevem um envio com o mesmo nome; mover projeto recusa destino com pasta homônima.

**Armazenamento e limpeza (Ajustes)**: medição por categoria (projetos, resultados, prévias, temporários, caches, recuperação); conferência com estimativa e seleção item a item; projetos antigos por período só saem se marcados. Protegidos: favoritos, abertos nas últimas 24 h, em processamento, arquivos citados por um projeto ou por XML exportado (inclusive XML de outro projeto ou das Montagens). Tudo vai para a Lixeira (ou para a pasta oculta “.Recuperar Ripagem Maker” se a Lixeira recusar). Limpeza automática começa desligada; quando ligada roda no máximo uma vez por dia, ao abrir, e deixa relatório.

**Local de salvamento**: “Pasta dos novos projetos” (só o destino dos próximos) separada de “Mover projeto” (leva um projeto com os materiais). Mover verifica permissão e espaço, copia, confere cada arquivo por SHA-256, atualiza os caminhos internos, informa quais XMLs precisam ser gerados de novo e só então manda a origem para a Lixeira. Bloqueado enquanto há tarefa no projeto (e edições esperam durante a cópia).

**Tratamento dos áudios gerados** (etapa Falas → “Tratamento dos áudios gerados”, ferramenta avulsa e padrão em Ajustes): apara silêncio excedente só nas bordas, com margens (80 ms antes, 200 ms depois, ajustáveis) e detecção de finais suaves; pausas internas ficam. Redução de ruído suave e ajustável (máx. 18 dB), distinta da separação de voz e música. Mostra duração antes/depois, compara original × tratado, sempre parte do áudio sem tratamento (não reaplica), mantém o original e permite desfazer. A duração nova recalcula o encaixe; montagem, takes e XML usam os novos tempos e prévia/entrega anteriores ficam marcadas como desatualizadas.

**Interface**: componente único de progresso (fase, barra ou animação sem estimativa, cancelar, conclusão/erro, Abrir pasta/Copiar caminho). Proteção contra clique duplo: o botão que disparou o envio fica ocupado até a resposta, sem travar o resto da tela.

**Correção do modo de uso**: a busca passa a ler as frases já captadas e segue o bloco inteiro da instrução antiga (“coloque as gotas… segure… depois engula… repita toda manhã”). As continuações sem a palavra da forma entram na mesma frase e saem junto quando há modo de uso confirmado — sem repetir o modo novo. Projetos já montados: reaplique “Modo de uso / forma” na etapa Falas para refazer a lista.

**Servidor**: fila de conexões maior (a página carrega ~25 scripts de uma vez).

## Testes
Feitos no Mac (macOS 27.2): 336 testes Python (31 novos: tratamento, mudança/recuperação, limpeza, acesso local, log, gravação atômica, tarefas interrompidas, modo de uso), 12 do Electron e 5 de interface. No navegador do app: Painel, Ferramentas avulsas, Ajustes (armazenamento, mover, regras), link direto para Falas com o tratamento num projeto real (só leitura), tratamento avulso real via API, medição e conferência da limpeza num disco real (nada removido), bloqueio de origem externa (403), Lixeira real e pasta de recuperação.

Simulados (não executados no Windows): leitura de caminhos `file:///C:/…` e de rede nos XMLs, comparação sem diferença de maiúsculas, Lixeira do Windows (SHFileOperation), abrir pasta no Explorador, seletor de pasta. Precisa de um teste real no Windows.

## Limitações
- Separação de voz e trilha depende do componente Demucs, que não está no pacote; a ferramenta explica e não envia nada para fora.
- Depois do tratamento, os áudios precisam ser ouvidos e aprovados de novo.
- A mudança de pasta não reescreve XMLs já exportados: gere o XML novamente (o app avisa quais).
- A limpeza automática só remove projetos antigos se essa regra for ligada explicitamente.
- Pacotes Mac/Windows desta versão ainda não foram gerados.
