begin;
create extension if not exists pgtap with schema extensions;
set local search_path to public, extensions;
select plan(8);

select has_table('public', 'perfis', 'A tabela de perfis existe');
select ok(
    (select relrowsecurity from pg_class where oid = 'public.perfis'::regclass),
    'A tabela tem RLS'
);
select ok(not has_table_privilege('anon', 'public.perfis', 'SELECT'), 'Anônimos não leem perfis');
select ok(not has_table_privilege('authenticated', 'public.perfis', 'UPDATE'), 'Cliente não promove conta nem altera código');
select ok(not has_table_privilege('authenticated', 'public.perfis', 'INSERT'), 'Cliente não cria perfis');
select ok(not has_table_privilege('authenticated', 'public.perfis', 'DELETE'), 'Cliente não apaga perfis');

insert into auth.users (id, email) values
    ('84092a71-cd28-48d9-9890-8568e5db16a0', 'editor-teste-1@exemplo.com'),
    ('84092a71-cd28-48d9-9890-8568e5db16a1', 'editor-teste-2@exemplo.com');
insert into public.perfis (id, nome, codigo) values
    ('84092a71-cd28-48d9-9890-8568e5db16a0', 'Primeiro editor', 'QA01'),
    ('84092a71-cd28-48d9-9890-8568e5db16a1', 'Segundo editor', 'QA02');

set local role authenticated;
set local request.jwt.claim.sub to '84092a71-cd28-48d9-9890-8568e5db16a0';
select results_eq(
    $$ select codigo::text from public.perfis $$,
    $$ values ('QA01'::text) $$,
    'O editor só enxerga o próprio perfil'
);
set local request.jwt.claim.sub to '84092a71-cd28-48d9-9890-8568e5db16a1';
select results_eq(
    $$ select codigo::text from public.perfis $$,
    $$ values ('QA02'::text) $$,
    'A leitura se isola ao trocar de identidade'
);

reset role;
select * from finish();
rollback;
