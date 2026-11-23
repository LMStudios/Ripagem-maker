# Ativação do login da equipe

O Ripagem Maker usa o Supabase Free para autenticar os usuários, ler os perfis e reunir os resumos de ripagem. Sessões de uso do aplicativo, eventos detalhados, mídias e o relatório completo ficam nos computadores.

## Preparar o Supabase

1. Em um projeto **Free** de homologação aprovado para o Ripagem Maker, aplique as migrações em `migrations/` na ordem dos nomes. A leitura de perfis fica restrita ao próprio usuário e a gravação passa pela função administrativa. Os resumos de ripagem são gravados com a identidade autenticada e apenas administradores ativos podem consultar toda a equipe.
2. Em **Authentication**, habilite o provedor de e-mail, mantenha a confirmação de e-mail e desabilite cadastro aberto e login anônimo. Configure senha mínima de oito caracteres e códigos de e-mail de seis dígitos. O `config.toml` registra essas opções para o ambiente local.
3. Em **Email Templates**, use `templates/convite.html` para **Invite user** e `templates/recuperacao.html` para **Reset password**. Os modelos enviam `{{ .Token }}`. O editor usa o código no próprio aplicativo. [Configuração de modelos de e-mail](https://supabase.com/docs/guides/auth/auth-email-templates)
4. Configure o SMTP aprovado pela equipe para enviar convites e códigos a editores fora da organização do projeto Supabase. O SMTP padrão atende testes com membros da organização. Escolha o remetente e confirme a entrega do convite e da recuperação antes de liberar o login à equipe. [SMTP do Supabase](https://supabase.com/docs/guides/auth/auth-smtp)
5. Publique a Edge Function `equipe-admin` no projeto aprovado quando a tela de administração for liberada. Mantenha `verify_jwt = true`. A função valida o token no Auth e lê o perfil ativo do próprio solicitante antes de executar operações administrativas. O Supabase injeta as chaves como variáveis da função. [Configuração de Edge Functions](https://supabase.com/docs/guides/functions/function-configuration) · [Variáveis das Edge Functions](https://supabase.com/docs/guides/functions/secrets)

### Primeiro administrador

Convide o administrador pelo painel **Authentication → Users**. Depois de o usuário aparecer nessa tela, use o ID de Auth exibido para criar seu perfil no SQL Editor. Substitua os três valores abaixo pelos dados aprovados.

```sql
insert into public.perfis (id, nome, codigo, funcao, ativo)
values ('<UUID do usuário>', '<Nome>', '<Código do editor>', 'administrador', true);
```

O administrador abre o Ripagem Maker, escolhe **Ativar convite** e confirma o código recebido. Funções e permissões são controladas pelo perfil no banco. A operação **Desativar** da função administrativa se aplica a editores.

## Configurar o aplicativo

Use apenas a URL HTTPS do projeto Supabase e sua **chave publicável**. Insira as duas na configuração local do backend por um destes meios.

- Arquivo `plataforma/workspace/equipe_auth.json` conforme o exemplo abaixo. Esse arquivo é uma configuração da máquina.
- Variáveis `RIPAGEM_SUPABASE_URL` e `RIPAGEM_SUPABASE_CHAVE_PUBLICA` fornecidas ao processo do aplicativo.

```json
{
  "url": "https://REFERENCIA.supabase.co",
  "chave_publica": "sb_publishable_SUA_CHAVE"
}
```

Reabra o aplicativo após configurar. Valide o login com o primeiro administrador. Use a opção de SMTP aprovada para testar o convite e a recuperação com um endereço usado na homologação.

## Validação local

- Deno, com respostas simuladas de Auth e PostgREST: `deno test supabase/functions/equipe-admin/index_test.ts`.
- Com o ambiente local do Supabase em execução: `supabase test db`. Os testes de RLS rodam em transação e usam perfis fictícios.
- Na homologação, confira a ativação do convite, a recuperação de senha, a leitura do próprio perfil e a recusa do editor em chamar a ação de administrador. Desative um editor e confirme que ele deixa de ter acesso aos novos projetos.
