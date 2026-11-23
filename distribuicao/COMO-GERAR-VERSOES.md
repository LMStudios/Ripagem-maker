# Ripagem Maker: uma base para Mac e Windows

## Próximas versões

1. Atualize o código, rode os testes e aumente VERSION.
2. Execute `python3 distribuicao/gerar_versao.py` no Mac Apple Silicon.
3. Confira os pacotes completos Mac arm64 e Windows x64 e o ZIP de atualização, todos da mesma versão.
4. Envie a pasta `distribuicao/pacotes/Ripagem-Maker-VERSAO` ao Drive e confirme a conclusão do upload.

**Os executáveis completos são obrigatórios em toda publicação.** O ZIP de atualização é apenas uma alternativa para quem já tem o aplicativo. Para gerar somente essa alternativa durante testes, use `python3 distribuicao/gerar_atualizacao.py`; isso não conclui uma publicação.

O atualizador verifica hashes, bloqueia tarefas ativas, permite apenas código e guarda
backup em .atualizacoes/antes-.... Não inclui ou substitui chaves, mídias, trabalhos,
configurações ou .runtime. Hashes detectam corrupção, não autenticam o publicador:
use apenas pacotes recebidos de quem mantém o aplicativo.

Se requirements.txt mudar, os iniciadores preparam dependências na próxima abertura.
Mudanças nos iniciadores nativos C/Swift exigem um novo pacote de instalação; o ZIP
universal atualiza Python e interface, não os binários nativos.
Não há hospedagem ou checagem automática de releases; o ZIP é selecionado manualmente.

## Primeira migração

Versões anteriores não têm atualizador. Instale uma vez o pacote 2.2.0 do seu sistema.
No Windows, use o atalho instalado. No Mac, selecione a pasta da versão anterior.
O iniciador Mac 2.2.0 preserva código mais novo, sem sobrescrevê-lo com a cópia do bundle.
Não apague a pasta de dados escolhida.

## Todos os pacotes

No Mac Apple Silicon com Node e Python, execute `python3 distribuicao/gerar_versao.py`.
Gera aplicativo Electron Mac arm64 com runtime incluído, instalador Windows x64 com runtime incluído e ZIP de atualização universal.
Os scripts nativos antigos permanecem disponíveis separadamente para compatibilidade.
O Mac tem assinatura local, sem notarização. Windows não tem assinatura comercial.
Compilação cruzada não substitui testes no Windows.


## Credenciais e arquivos na versão 2.3

AssemblyAI e ElevenLabs são configurados em Ajustes → Integrações e APIs.
As credenciais são guardadas pelo keyring no cofre do sistema e não fazem parte dos
pacotes. A chave antiga do AssemblyAI no .env é migrada quando o cofre está disponível;
se estiver bloqueado, a configuração antiga é preservada. Chaves de voz que só existiam
na memória da versão antiga devem ser salvas uma vez no novo painel.
No Windows, use a janela do aplicativo atualizada para ter diálogos nativos de pasta e
Salvar uma cópia. No navegador normal, a seleção de pasta local pode exigir colar o caminho.
A entrega só é apresentada como atual se o XML estiver presente e não vazio; o caminho
completo aparece na tela. Os XMLs continuam dependendo das mídias nos caminhos originais.
