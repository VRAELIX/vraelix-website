-- Staging writer migration for the existing public.enquiries table.
-- This migration does not create, alter, truncate, or delete table data.
-- Run supabase/review/enquiry_writer_acl_checks.sql first and save its
-- output. This migration stops if PUBLIC, anon, or authenticated already has
-- table/column ACL entries. It permits only the exact staging-default
-- service_role table ACLs observed before review (MAINTAIN, REFERENCES,
-- TRIGGER, TRUNCATE), then revokes those API-role privileges too.

begin;

do $$
declare
  table_oid oid;
  column_total integer;
  schema_mismatch_total integer;
  policy_total integer;
  service_role_oid oid;
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
  where table_schema = 'public' and table_name = 'enquiries';
  if column_total <> 13 then
    raise exception 'public.enquiries must have exactly the reviewed 13 columns; migration stopped';
  end if;

  -- Compare the complete column set in both directions. This detects missing,
  -- unexpected, renamed, incompatible, nullable/default-changed, identity, or
  -- generated columns instead of merely counting recognized columns.
  with expected(column_name, data_type, is_nullable, column_default, is_identity, is_generated) as (
    values
      ('id', 'uuid', 'NO', 'gen_random_uuid()', 'NO', 'NEVER'),
      ('created_at', 'timestamp with time zone', 'NO', 'now()', 'NO', 'NEVER'),
      ('full_name', 'text', 'NO', null::text, 'NO', 'NEVER'),
      ('email', 'text', 'NO', null::text, 'NO', 'NEVER'),
      ('phone_number', 'text', 'NO', null::text, 'NO', 'NEVER'),
      ('company', 'text', 'YES', null::text, 'NO', 'NEVER'),
      ('service', 'text', 'NO', null::text, 'NO', 'NEVER'),
      ('project_description', 'text', 'NO', null::text, 'NO', 'NEVER'),
      ('budget', 'text', 'YES', null::text, 'NO', 'NEVER'),
      ('timeline', 'text', 'YES', null::text, 'NO', 'NEVER'),
      ('contact_method', 'text', 'NO', null::text, 'NO', 'NEVER'),
      ('source', 'text', 'NO', '''VRAELIX Website''::text', 'NO', 'NEVER'),
      ('submitted_at', 'timestamp with time zone', 'NO', 'now()', 'NO', 'NEVER')
  ), actual as (
    select column_name, data_type, is_nullable, column_default,
      is_identity, is_generated
    from information_schema.columns
    where table_schema = 'public' and table_name = 'enquiries'
  )
  select count(*) into schema_mismatch_total
  from (
    select e.column_name
    from expected e
    left join actual a using (column_name)
    where a.column_name is null
      or e.data_type is distinct from a.data_type
      or e.is_nullable is distinct from a.is_nullable
      or e.column_default is distinct from a.column_default
      or e.is_identity is distinct from a.is_identity
      or e.is_generated is distinct from a.is_generated
    union all
    select a.column_name
    from actual a
    left join expected e using (column_name)
    where e.column_name is null
  ) differences;
  if schema_mismatch_total <> 0 then
    raise exception 'public.enquiries column definitions differ from the reviewed schema; migration stopped';
  end if;

  if (select count(*) from pg_constraint where conrelid = table_oid) <> 1
    or not exists (
      select 1 from pg_constraint
      where conrelid = table_oid and conname = 'enquiries_pkey'
        and contype = 'p' and pg_get_constraintdef(oid, true) = 'PRIMARY KEY (id)'
    ) then
    raise exception 'public.enquiries constraints differ from the reviewed primary key; migration stopped';
  end if;

  if (select count(*) from pg_index where indrelid = table_oid) <> 1
    or not exists (
      select 1 from pg_index i
      join pg_class index_relation on index_relation.oid = i.indexrelid
      where i.indrelid = table_oid and i.indisprimary and i.indisunique
        and index_relation.relname = 'enquiries_pkey'
    ) then
    raise exception 'public.enquiries indexes differ from the reviewed primary key; migration stopped';
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

  -- PUBLIC grants are inherited by every role; direct anon/authenticated ACLs
  -- also must be reviewed. Stop rather than silently revoking an ACL that was
  -- not present in the read-only inspection results.
  if exists (
    select 1
    from pg_class c
    cross join lateral aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) acl
    where c.oid = table_oid
      and (acl.grantee = 0 or acl.grantee in (
        select oid from pg_roles where rolname in ('anon', 'authenticated')
      ))
  ) or exists (
    select 1
    from pg_attribute a
    -- aclexplode is STRICT, so NULL means no column ACLs. Avoid coalescing to
    -- a zero-dimensional empty array, which PostgreSQL rejects for ACL arrays.
    cross join lateral aclexplode(a.attacl) acl
    where a.attrelid = table_oid and a.attnum > 0 and not a.attisdropped
      and (acl.grantee = 0 or acl.grantee in (
        select oid from pg_roles where rolname in ('anon', 'authenticated')
      ))
  ) then
    raise exception 'PUBLIC/anon/authenticated has table or column ACL entries on public.enquiries; review saved preflight ACL output first';
  end if;

  -- The table was created by postgres with Supabase default ACLs that gave
  -- service_role exactly MAINTAIN, REFERENCES, TRIGGER, and TRUNCATE. The
  -- requested end state excludes all API roles from direct table access, so
  -- revoke those known grants below. Stop if staging has any additional or
  -- column-level service_role ACL; that would be an unreviewed permission.
  service_role_oid := to_regrole('service_role');
  if service_role_oid is null then
    raise exception 'service_role is missing; inspect the staging project before proceeding';
  end if;

  if exists (
    select 1
    from pg_class c
    cross join lateral aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) acl
    where c.oid = table_oid and acl.grantee = service_role_oid
      and (acl.privilege_type not in ('MAINTAIN', 'REFERENCES', 'TRIGGER', 'TRUNCATE')
        or acl.is_grantable)
  ) or exists (
    select 1
    from pg_attribute a
    cross join lateral aclexplode(a.attacl) acl
    where a.attrelid = table_oid and a.attnum > 0 and not a.attisdropped
      and acl.grantee = service_role_oid
  ) then
    raise exception 'service_role has unreviewed table/column ACLs on public.enquiries; migration stopped';
  end if;

  -- A new login role inherits database/schema privileges granted to PUBLIC.
  -- Database CREATE and public-schema CREATE remain blockers. The reviewed
  -- staging baseline grants TEMPORARY to PUBLIC; leave that grant unchanged
  -- and document that the writer inherits TEMPORARY as a residual capability.
  -- CONNECT and schema USAGE are intentionally allowed.
  if exists (
    select 1
    from pg_database d
    cross join lateral aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) acl
    where d.datname = current_database() and acl.grantee = 0
      and acl.privilege_type = 'CREATE'
  ) or exists (
    select 1
    from pg_namespace n
    cross join lateral aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) acl
    where n.nspname = 'public' and acl.grantee = 0
      and acl.privilege_type = 'CREATE'
  ) then
    raise exception 'PUBLIC can create database/schema objects; review inherited privileges before creating the writer role';
  end if;

  -- The writer receives USAGE on public. If PUBLIC can execute a callable
  -- SECURITY DEFINER routine in a schema the writer can use, the credential
  -- would have capabilities beyond the reviewed insert path. Event-trigger
  -- functions are excluded: PostgreSQL invokes them only through registered
  -- DDL event triggers, and their event_trigger pseudo-type is not a normal
  -- SQL-callable return type. Do not revoke function grants globally as an
  -- implicit side effect.
  if exists (
    select 1
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) acl
    where p.prosecdef and acl.grantee = 0 and acl.privilege_type = 'EXECUTE'
      and p.prorettype <> 'pg_catalog.event_trigger'::regtype
      and (
        n.nspname = 'public'
        or exists (
          select 1
          from aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) schema_acl
          where schema_acl.grantee = 0 and schema_acl.privilege_type = 'USAGE'
        )
      )
  ) then
    raise exception 'PUBLIC-executable SECURITY DEFINER function is reachable by the writer; review function ACL results first';
  end if;
end;
$$;

-- The connection password is set separately and never stored in this file.
-- This migration creates no memberships. In this staging project, Supabase's
-- role-creation path was observed to attach postgres as a member of a new
-- role. That admin edge is allowed; the writer itself must not be a member of
-- another role, and no role other than postgres may be a member of the writer.
create role vraelix_enquiry_writer
  with login noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls
  connection limit 5 password null;

-- Remove direct and inherited table access from public API roles. PUBLIC table
-- revocations apply to all roles; preserve the database-wide CONNECT grant and
-- all unrelated schemas/objects. Remove the exact service_role ACL entries
-- observed in staging too. No database-wide TEMP privilege is changed.
revoke all privileges on table public.enquiries
  from public, anon, authenticated, service_role;
revoke select (id, created_at, full_name, email, phone_number, company, service,
  project_description, budget, timeline, contact_method, source, submitted_at),
  insert (id, created_at, full_name, email, phone_number, company, service,
  project_description, budget, timeline, contact_method, source, submitted_at),
  update (id, created_at, full_name, email, phone_number, company, service,
  project_description, budget, timeline, contact_method, source, submitted_at),
  references (id, created_at, full_name, email, phone_number, company, service,
  project_description, budget, timeline, contact_method, source, submitted_at)
  on table public.enquiries from public, anon, authenticated, service_role;

-- Fail closed if any public API role still receives table access through a
-- membership in another role, including column-level grants. Direct grants
-- from PUBLIC and these API roles are revoked above; these checks verify the
-- effective privileges before creating the writer policy.
do $$
declare
  role_name text;
  privilege_name text;
begin
  foreach role_name in array array['anon', 'authenticated', 'service_role'] loop
    foreach privilege_name in array array[
      'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'
    ] loop
      if has_table_privilege(role_name, 'public.enquiries', privilege_name) then
        raise exception '% still has effective % access to public.enquiries; migration stopped',
          role_name, privilege_name;
      end if;
      if privilege_name in ('SELECT', 'INSERT', 'UPDATE', 'REFERENCES') then
        if has_any_column_privilege(role_name, 'public.enquiries', privilege_name) then
          raise exception '% still has effective column-level % access to public.enquiries; migration stopped',
            role_name, privilege_name;
        end if;
      end if;
    end loop;
  end loop;
end;
$$;

-- The new writer must not inherit privileges from other roles, and no API or
-- non-admin role may be able to SET ROLE to it. The Supabase postgres admin
-- membership edge was observed during read-only staging review and is the only
-- allowed incoming membership. NOINHERIT prevents inherited parent privileges.
do $$
declare
  writer_oid oid := to_regrole('vraelix_enquiry_writer');
begin
  if exists (
    select 1 from pg_auth_members membership
    join pg_roles member_role on member_role.oid = membership.member
    where membership.member = writer_oid
       or (membership.roleid = writer_oid and member_role.rolname <> 'postgres')
  ) then
    raise exception 'vraelix_enquiry_writer has role memberships; migration stopped';
  end if;
end;
$$;

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

-- Assert the final writer rights before committing. The login may insert the
-- approved fields only; defaults provide id and created_at. It cannot read,
-- update, delete, truncate, or directly insert those defaulted columns.
do $$
declare
  column_name text;
begin
  if not has_database_privilege('vraelix_enquiry_writer', current_database(), 'CONNECT')
    or not has_schema_privilege('vraelix_enquiry_writer', 'public', 'USAGE') then
    raise exception 'writer connection or public schema usage is missing';
  end if;
  if has_database_privilege('vraelix_enquiry_writer', current_database(), 'CREATE')
    or not has_database_privilege('vraelix_enquiry_writer', current_database(), 'TEMP') then
    raise exception 'writer inherited database privilege state differs from the reviewed TEMP-only residual';
  end if;
  if has_table_privilege('vraelix_enquiry_writer', 'public.enquiries', 'SELECT')
    or has_table_privilege('vraelix_enquiry_writer', 'public.enquiries', 'INSERT')
    or has_table_privilege('vraelix_enquiry_writer', 'public.enquiries', 'UPDATE')
    or has_table_privilege('vraelix_enquiry_writer', 'public.enquiries', 'DELETE')
    or has_table_privilege('vraelix_enquiry_writer', 'public.enquiries', 'TRUNCATE')
    or has_table_privilege('vraelix_enquiry_writer', 'public.enquiries', 'REFERENCES')
    or has_table_privilege('vraelix_enquiry_writer', 'public.enquiries', 'TRIGGER') then
    raise exception 'writer has unexpected table-level privileges';
  end if;
  if has_any_column_privilege('vraelix_enquiry_writer', 'public.enquiries', 'SELECT')
    or has_any_column_privilege('vraelix_enquiry_writer', 'public.enquiries', 'UPDATE')
    or has_any_column_privilege('vraelix_enquiry_writer', 'public.enquiries', 'REFERENCES') then
    raise exception 'writer has an unexpected column-level privilege';
  end if;

  foreach column_name in array array[
    'full_name', 'email', 'phone_number', 'company', 'service',
    'project_description', 'budget', 'timeline', 'contact_method',
    'source', 'submitted_at'
  ] loop
    if not has_column_privilege(
      'vraelix_enquiry_writer', 'public.enquiries', column_name, 'INSERT'
    ) then
      raise exception 'writer is missing approved INSERT privilege on %', column_name;
    end if;
  end loop;
  if has_column_privilege('vraelix_enquiry_writer', 'public.enquiries', 'id', 'INSERT')
    or has_column_privilege('vraelix_enquiry_writer', 'public.enquiries', 'created_at', 'INSERT') then
    raise exception 'writer can override id or created_at defaults';
  end if;
end;
$$;

create policy vraelix_enquiry_writer_insert
  on public.enquiries
  as permissive
  for insert
  to vraelix_enquiry_writer
  with check (true);

commit;
