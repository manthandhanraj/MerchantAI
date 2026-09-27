-- MerchantAI — private storage buckets and their policies
--
-- Both buckets are private. Nothing is ever served from a public URL; the API
-- issues a short-lived signed URL only after it has confirmed ownership.
--
-- Object paths are:
--   merchant-data/{user_id}/{merchant_id}/{upload_id}/source.csv
--   merchant-reports/{user_id}/{merchant_id}/{report_id}/report.pdf
--
-- The first path segment is the owner's user id, which is what every policy
-- below checks. storage.foldername(name) returns the path segments as an array,
-- so [1] is that first segment.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'merchant-data',
  'merchant-data',
  false,
  10485760,                                  -- 10 MB, matching the API's limit
  array['text/csv', 'application/vnd.ms-excel', 'text/plain']
)
on conflict (id) do update
  set public = false,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'merchant-reports',
  'merchant-reports',
  false,
  20971520,                                  -- 20 MB
  array['application/pdf']
)
on conflict (id) do update
  set public = false,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

-- ------------------------------------------------------- merchant-data

drop policy if exists merchant_data_select_own on storage.objects;
create policy merchant_data_select_own on storage.objects
  for select to authenticated
  using (
    bucket_id = 'merchant-data'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists merchant_data_insert_own on storage.objects;
create policy merchant_data_insert_own on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'merchant-data'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists merchant_data_update_own on storage.objects;
create policy merchant_data_update_own on storage.objects
  for update to authenticated
  using (
    bucket_id = 'merchant-data'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists merchant_data_delete_own on storage.objects;
create policy merchant_data_delete_own on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'merchant-data'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

-- ------------------------------------------------------- merchant-reports

drop policy if exists merchant_reports_select_own on storage.objects;
create policy merchant_reports_select_own on storage.objects
  for select to authenticated
  using (
    bucket_id = 'merchant-reports'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists merchant_reports_insert_own on storage.objects;
create policy merchant_reports_insert_own on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'merchant-reports'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists merchant_reports_delete_own on storage.objects;
create policy merchant_reports_delete_own on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'merchant-reports'
    and (storage.foldername(name))[1] = auth.uid()::text
  );
