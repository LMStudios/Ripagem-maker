begin;

create table public.perfis (
    id uuid primary key references auth.users(id) on delete cascade,
    nome text not null check (nome = btrim(nome) and char_length(nome) between 1 and 100 and nome !~ '[[:cntrl:]]'),
    codigo text not null unique check (codigo ~ '^[A-Z0-9][A-Z0-9_-]{0,23}$'),
    funcao text not null default 'editor' check (funcao in ('editor', 'administrador')),
    ativo boolean not null default true,
    criado_em timestamptz not null default now()
);

alter table public.perfis enable row level security;

revoke all on public.perfis from public, anon, authenticated, service_role;
grant select on public.perfis to authenticated;
grant select, insert, update on public.perfis to service_role;

create policy perfis_proprio_perfil on public.perfis
    for select to authenticated
    using (id = (select auth.uid()));

commit;
