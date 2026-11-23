begin;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('ripagem-updates', 'ripagem-updates', false, 26214400,
        array['application/json', 'application/zip', 'application/octet-stream']);

create policy ripagem_updates_active_read on storage.objects
for select to authenticated
using (
    bucket_id = 'ripagem-updates'
    and (name = 'latest.json' or name ~ '^Ripagem-Maker-Atualizacao-[0-9]+[.][0-9]+[.][0-9]+[.]zip$')
    and exists (
        select 1 from public.perfis
        where id = (select auth.uid()) and ativo
    )
);

commit;
