begin;

create schema ripagem_privado;
revoke all on schema ripagem_privado from public, anon, authenticated, service_role;
grant usage on schema ripagem_privado to authenticated;

create function ripagem_privado.numeros_validos(dados jsonb, chaves text[], limite numeric)
returns boolean language sql immutable strict set search_path = ''
as $$
    select case
        when pg_catalog.jsonb_typeof(dados) <> 'object' or dados - chaves <> '{}'::jsonb then false
        else not exists (
            select 1 from pg_catalog.jsonb_each(dados) as campo(chave, valor)
            where not case when pg_catalog.jsonb_typeof(valor) = 'number' then
                (valor #>> '{}')::numeric between 0 and limite
                and pg_catalog.trunc((valor #>> '{}')::numeric) = (valor #>> '{}')::numeric
            else false end
        )
    end
$$;

revoke all on function ripagem_privado.numeros_validos(jsonb, text[], numeric)
    from public, anon, authenticated, service_role;
grant execute on function ripagem_privado.numeros_validos(jsonb, text[], numeric) to authenticated;

create table public.relatorios_ripagem (
    projeto_id uuid primary key,
    usuario uuid not null default auth.uid() references public.perfis(id),
    tempo_ripagem_ms bigint check (tempo_ripagem_ms between 0 and 2592000000),
    espera_ms bigint check (espera_ms between 0 and 2592000000),
    retrabalho_ms bigint check (retrabalho_ms between 0 and 2592000000),
    fora_app_ms bigint check (fora_app_ms between 0 and 2592000000),
    medicao_completa boolean not null default false,
    xml_revisao boolean not null default false,
    pendencias_visuais integer not null default 0 check (pendencias_visuais between 0 and 100000),
    tentativas integer not null default 0 check (tentativas between 0 and 100000),
    falhas integer not null default 0 check (falhas between 0 and 100000),
    versao_app text check (versao_app ~ '^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}$'),
    sistema text check (sistema in ('macOS', 'Windows', 'Linux', 'Outro')),
    etapas_ms jsonb not null default '{}'::jsonb check (ripagem_privado.numeros_validos(
        etapas_ms, array['transcricao', 'voz', 'busca_visual', 'takes', 'exportacao'], 2592000000
    )),
    visuais jsonb not null default '{}'::jsonb check (ripagem_privado.numeros_validos(
        visuais, array['sugeridas', 'aprovadas', 'descartadas', 'manuais', 'marcadas'], 100000
    )),
    feedback_etapa text check (feedback_etapa in (
        'transcricao', 'voz', 'busca_visual', 'takes', 'exportacao', 'legenda', 'outro'
    )),
    revisao bigint not null default 1 check (revisao between 1 and 9007199254740991),
    criado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now()
);

create index relatorios_ripagem_usuario_atualizacao on public.relatorios_ripagem
    (usuario, atualizado_em desc, projeto_id);
create index relatorios_ripagem_atualizacao on public.relatorios_ripagem
    (atualizado_em desc, projeto_id);

create function ripagem_privado.preservar_relatorio()
returns trigger language plpgsql set search_path = ''
as $$
begin
    if new.usuario is distinct from old.usuario or new.projeto_id is distinct from old.projeto_id then
        raise exception 'O projeto e seu autor são imutáveis.' using errcode = '23514';
    end if;
    if new.revisao <= old.revisao then
        return old;
    end if;
    new.tempo_ripagem_ms := old.tempo_ripagem_ms;
    new.medicao_completa := old.medicao_completa;
    new.atualizado_em := pg_catalog.clock_timestamp();
    return new;
end;
$$;

revoke all on function ripagem_privado.preservar_relatorio()
    from public, anon, authenticated, service_role;

create trigger preservar_relatorio before update on public.relatorios_ripagem
    for each row execute function ripagem_privado.preservar_relatorio();

alter table public.relatorios_ripagem enable row level security;
revoke all on public.relatorios_ripagem from public, anon, authenticated, service_role;
grant select on public.relatorios_ripagem to authenticated;
grant insert (
    projeto_id, tempo_ripagem_ms, espera_ms, retrabalho_ms, fora_app_ms, medicao_completa,
    xml_revisao, pendencias_visuais, tentativas, falhas, versao_app, sistema, etapas_ms,
    visuais, feedback_etapa, revisao
) on public.relatorios_ripagem to authenticated;
grant update (
    projeto_id, tempo_ripagem_ms, espera_ms, retrabalho_ms, fora_app_ms, medicao_completa,
    xml_revisao, pendencias_visuais, tentativas, falhas, versao_app, sistema, etapas_ms,
    visuais, feedback_etapa, revisao
) on public.relatorios_ripagem to authenticated;

create policy relatorios_ripagem_leitura on public.relatorios_ripagem
    for select to authenticated using (exists (
        select 1 from public.perfis p
        where p.id = (select auth.uid()) and p.ativo
          and (p.funcao = 'administrador' or p.id = usuario)
    ));

create policy relatorios_ripagem_insercao on public.relatorios_ripagem
    for insert to authenticated with check (usuario = (select auth.uid()) and exists (
        select 1 from public.perfis p where p.id = (select auth.uid()) and p.ativo
    ));

create policy relatorios_ripagem_atualizacao on public.relatorios_ripagem
    for update to authenticated
    using (usuario = (select auth.uid()) and exists (
        select 1 from public.perfis p where p.id = (select auth.uid()) and p.ativo
    ))
    with check (usuario = (select auth.uid()) and exists (
        select 1 from public.perfis p where p.id = (select auth.uid()) and p.ativo
    ));

commit;
