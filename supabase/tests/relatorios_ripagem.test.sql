begin;
create extension if not exists pgtap with schema extensions;
set local search_path to public, extensions;
select plan(13);

select ok(
    (select relrowsecurity from pg_class where oid = 'public.relatorios_ripagem'::regclass),
    'Relatórios protegidos por RLS'
);
select ok(not has_table_privilege('anon', 'public.relatorios_ripagem', 'SELECT'), 'Sem leitura anônima');
select ok(not has_column_privilege('authenticated', 'public.relatorios_ripagem', 'usuario', 'INSERT'), 'A autoria vem de Auth');
select ok(not has_column_privilege('authenticated', 'public.relatorios_ripagem', 'usuario', 'UPDATE'), 'Autoria imutável');

insert into auth.users (id, email) values
    ('0bb5d04f-4afb-4fba-90cb-22d1389d5f00', 'admin-relatorio@exemplo.com'),
    ('0bb5d04f-4afb-4fba-90cb-22d1389d5f01', 'editor-relatorio-1@exemplo.com'),
    ('0bb5d04f-4afb-4fba-90cb-22d1389d5f02', 'editor-relatorio-2@exemplo.com'),
    ('0bb5d04f-4afb-4fba-90cb-22d1389d5f03', 'editor-inativo@exemplo.com');
insert into public.perfis (id, nome, codigo, funcao, ativo) values
    ('0bb5d04f-4afb-4fba-90cb-22d1389d5f00', 'Admin teste', 'QE00', 'administrador', true),
    ('0bb5d04f-4afb-4fba-90cb-22d1389d5f01', 'Editor um', 'QE01', 'editor', true),
    ('0bb5d04f-4afb-4fba-90cb-22d1389d5f02', 'Editor dois', 'QE02', 'editor', true),
    ('0bb5d04f-4afb-4fba-90cb-22d1389d5f03', 'Editor inativo', 'QE03', 'editor', false);

set local role authenticated;
set local request.jwt.claim.sub to '0bb5d04f-4afb-4fba-90cb-22d1389d5f01';
insert into relatorios_ripagem (projeto_id, tempo_ripagem_ms, medicao_completa, revisao, visuais, etapas_ms)
values ('5e532121-8668-49dd-b40d-d668ed1154f1', 56000, true, 1, '{"aprovadas":2}', '{"voz":15000}');
select results_eq(
    $$ select usuario::text from relatorios_ripagem $$,
    $$ values ('0bb5d04f-4afb-4fba-90cb-22d1389d5f01'::text) $$,
    'Servidor vincula o autor à sessão autenticada'
);
insert into relatorios_ripagem (projeto_id, tempo_ripagem_ms, medicao_completa, revisao, falhas)
values ('5e532121-8668-49dd-b40d-d668ed1154f1', 60000, false, 2, 3)
on conflict (projeto_id) do update
set tempo_ripagem_ms = excluded.tempo_ripagem_ms,
    medicao_completa = excluded.medicao_completa,
    revisao = excluded.revisao,
    falhas = excluded.falhas;
select results_eq(
    $$ select tempo_ripagem_ms, medicao_completa, falhas from relatorios_ripagem $$,
    $$ values (56000::bigint, true, 3) $$,
    'Métricas novas preservam o tempo do primeiro XML'
);
update relatorios_ripagem set revisao = 1, falhas = 9;
select results_eq(
    $$ select revisao, falhas from relatorios_ripagem $$, $$ values (2::bigint, 3) $$,
    'Uma retransmissão antiga preserva a revisão atual'
);
select throws_ok(
    $$ update relatorios_ripagem set revisao = 3, etapas_ms = '{"voz":"/Users/teste"}' $$,
    '23514', null, 'Métrica de etapa aceita só números'
);
select throws_ok(
    $$ update relatorios_ripagem set revisao = 3, visuais = '{"caminho":10}' $$,
    '23514', null, 'Métrica visual rejeita chaves fora do contrato'
);

set local request.jwt.claim.sub to '0bb5d04f-4afb-4fba-90cb-22d1389d5f02';
select is((select count(*) from relatorios_ripagem), 0::bigint, 'Editor só lê relatórios próprios');
select throws_ok(
    $$ insert into relatorios_ripagem (projeto_id, revisao) values
       ('5e532121-8668-49dd-b40d-d668ed1154f1', 9)
       on conflict (projeto_id) do update set revisao = excluded.revisao $$,
    '42501', null, 'Editor não toma posse de relatório de outro usuário'
);
set local request.jwt.claim.sub to '0bb5d04f-4afb-4fba-90cb-22d1389d5f03';
select throws_ok(
    $$ insert into relatorios_ripagem (projeto_id) values ('5e532121-8668-49dd-b40d-d668ed1154f2') $$,
    '42501', null, 'Conta inativa não sincroniza'
);
set local request.jwt.claim.sub to '0bb5d04f-4afb-4fba-90cb-22d1389d5f00';
select is((select count(*) from relatorios_ripagem), 1::bigint, 'Admin ativo lê relatórios da equipe');

reset role;
select * from finish();
rollback;
