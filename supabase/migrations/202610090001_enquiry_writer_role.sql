-- Review-only migration for the existing public.enquiries table.
-- This migration does not create, alter, truncate, or delete table data.
-- Run only after reviewing the PUBLIC and role ACL checks called out in the
-- launch checklist. It intentionally fails if the inspected table/policy state
-- has changed or if the dedicated role already exists.

begin;

do $$
declare
  table_oid oid;
  column_total integer;
  policy_total integer;
begin
  table_oid := to_regclass('public.enquiries');
  if table_oid is null then
    raise exception 'public.enquiries is missing; migration stopped';
  end if;

  if not exists (
    select 1 from pg_class
    where oid = table_oid and relrowsecurity
  ) then
    raise exception 'RLS is not enabled on public.enquiries; migration stopped';
  end if;

  select count(*) into column_total
  from information_schema.columns
  where table_schema = 'public' and table_name = 'enquiries'
    and (
      (column_name = 'id' and data_type = 'uuid' and is_nullable = 'NO') or
      (column_name in ('created_at', 'submitted_at') and data_type = 'timestamp with time zone' and is_nullable = 'NO') or
      (column_name in ('full_name', 'email', 'phone_number', 'service', 'project_description', 'contact_method', 'source') and data_type = 'text' and is_nullable = 'NO') or
      (column_name in ('company', 'budget', 'timeline') and data_type = 'text' and is_nullable = 'YES')
    );
  if column_total <> 13 then
    raise exception 'public.enquiries no longer has the reviewed 13-column schema; migration stopped';
  end if;

  select count(*) into policy_total
  from pg_policies
  where schemaname = 'public' and tablename = 'enquiries';
  if policy_total <> 0 then
    raise exception 'RLS policies changed since inspection; migration stopped';
  end if;

  if to_regrole('vraelix_enquiry_writer') is not null then
    raise exception 'vraelix_enquiry_writer already exists; inspect it before proceeding';
  end if;
end;
$$;

-- The connection password is set separately and never stored in this file.
-- No role memberships are granted to or from this dedicated LOGIN role.
create role vraelix_enquiry_writer
  with login noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls
  connection limit 5 password null;

-- Remove direct and inherited table access from public API roles. PUBLIC table
-- revocations apply to all roles; preserve the database-wide CONNECT grant and
-- all unrelated schemas/objects. The service_role grants are left unchanged.
revoke all privileges on table public.enquiries from public, anon, authenticated;
revoke select (id, created_at, full_name, email, phone_number, company, service,
  project_description, budget, timeline, contact_method, source, submitted_at),
  insert (id, created_at, full_name, email, phone_number, company, service,
  project_description, budget, timeline, contact_method, source, submitted_at),
  update (id, created_at, full_name, email, phone_number, company, service,
  project_description, budget, timeline, contact_method, source, submitted_at),
  references (id, created_at, full_name, email, phone_number, company, service,
  project_description, budget, timeline, contact_method, source, submitted_at)
  on table public.enquiries from public, anon, authenticated;

grant usage on schema public to vraelix_enquiry_writer;
grant insert (
  full_name,
  email,
  phone_number,
  company,
  service,
  project_description,
  budget,
  timeline,
  contact_method,
  source,
  submitted_at
) on table public.enquiries to vraelix_enquiry_writer;

create policy vraelix_enquiry_writer_insert
  on public.enquiries
  as permissive
  for insert
  to vraelix_enquiry_writer
  with check (true);

commit;
