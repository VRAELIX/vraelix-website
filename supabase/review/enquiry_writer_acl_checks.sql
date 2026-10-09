-- Read-only preflight/postflight queries. Run in the Supabase SQL Editor.
-- These queries return schema/privilege metadata only; they do not read enquiry rows.

-- 1. Current table-level grants, including grants made to PUBLIC.
select
  case when acl.grantee = 0 then 'PUBLIC' else grantee.rolname end as grantee,
  acl.privilege_type,
  acl.is_grantable
from pg_class as relation
join pg_namespace as namespace on namespace.oid = relation.relnamespace
cross join lateral aclexplode(coalesce(relation.relacl, acldefault('r', relation.relowner))) as acl
left join pg_roles as grantee on grantee.oid = acl.grantee
where namespace.nspname = 'public' and relation.relname = 'enquiries'
order by grantee, acl.privilege_type;

-- 2. Column-level table grants (including PUBLIC), which are separate from table ACLs.
select
  attribute.attname as column_name,
  case when acl.grantee = 0 then 'PUBLIC' else grantee.rolname end as grantee,
  acl.privilege_type,
  acl.is_grantable
from pg_attribute as attribute
join pg_class as relation on relation.oid = attribute.attrelid
join pg_namespace as namespace on namespace.oid = relation.relnamespace
cross join lateral aclexplode(attribute.attacl) as acl
left join pg_roles as grantee on grantee.oid = acl.grantee
where namespace.nspname = 'public' and relation.relname = 'enquiries'
  and attribute.attnum > 0 and not attribute.attisdropped
  and attribute.attacl is not null
order by attribute.attname, grantee, acl.privilege_type;

-- 3. PUBLIC grants on schemas/objects that a database login role could inherit.
-- Pay particular attention to CREATE on public and execute rights in net/extensions.
select
  namespace.nspname as schema_name,
  case when acl.grantee = 0 then 'PUBLIC' else grantee.rolname end as grantee,
  acl.privilege_type,
  acl.is_grantable
from pg_namespace as namespace
cross join lateral aclexplode(coalesce(namespace.nspacl, acldefault('n', namespace.nspowner))) as acl
left join pg_roles as grantee on grantee.oid = acl.grantee
where namespace.nspname in ('public', 'extensions', 'net', 'auth')
  and acl.grantee = 0
order by namespace.nspname, acl.privilege_type;

-- 4. PUBLIC database-level grants. Do not revoke CONNECT from PUBLIC in Supabase.
select
  database.datname,
  acl.privilege_type,
  acl.is_grantable
from pg_database as database
cross join lateral aclexplode(coalesce(database.datacl, acldefault('d', database.datdba))) as acl
where database.datname = current_database() and acl.grantee = 0
order by acl.privilege_type;

-- 5. Memberships involving the proposed writer role, if it already exists.
select
  member.rolname as member_role,
  granted.rolname as granted_role,
  membership.admin_option
from pg_auth_members as membership
join pg_roles as member on member.oid = membership.member
join pg_roles as granted on granted.oid = membership.roleid
where member.rolname = 'vraelix_enquiry_writer'
   or granted.rolname = 'vraelix_enquiry_writer'
order by member.rolname, granted.rolname;

-- 6. Effective access checks for the proposed writer role, if it exists.
select
  to_regrole('vraelix_enquiry_writer') is not null as role_exists,
  case when to_regrole('vraelix_enquiry_writer') is null then null else has_schema_privilege('vraelix_enquiry_writer', 'public', 'CREATE') end as can_create_in_public,
  case when to_regrole('vraelix_enquiry_writer') is null then null else has_database_privilege('vraelix_enquiry_writer', current_database(), 'CREATE') end as can_create_database,
  case when to_regrole('vraelix_enquiry_writer') is null then null else has_database_privilege('vraelix_enquiry_writer', current_database(), 'TEMP') end as can_create_temp_tables,
  case when to_regrole('vraelix_enquiry_writer') is null then null else has_table_privilege('vraelix_enquiry_writer', 'public.enquiries', 'SELECT') end as can_select_enquiries,
  case when to_regrole('vraelix_enquiry_writer') is null then null else has_table_privilege('vraelix_enquiry_writer', 'public.enquiries', 'INSERT') end as has_table_wide_insert,
  case when to_regrole('vraelix_enquiry_writer') is null then null else has_table_privilege('vraelix_enquiry_writer', 'public.enquiries', 'UPDATE') end as can_update_enquiries,
  case when to_regrole('vraelix_enquiry_writer') is null then null else has_table_privilege('vraelix_enquiry_writer', 'public.enquiries', 'DELETE') end as can_delete_enquiries;

select
  attribute.attname as column_name,
  case when to_regrole('vraelix_enquiry_writer') is null then null else has_column_privilege('vraelix_enquiry_writer', 'public.enquiries', attribute.attname, 'INSERT') end as can_insert,
  case when to_regrole('vraelix_enquiry_writer') is null then null else has_column_privilege('vraelix_enquiry_writer', 'public.enquiries', attribute.attname, 'SELECT') end as can_select,
  case when to_regrole('vraelix_enquiry_writer') is null then null else has_column_privilege('vraelix_enquiry_writer', 'public.enquiries', attribute.attname, 'UPDATE') end as can_update,
  case when to_regrole('vraelix_enquiry_writer') is null then null else has_column_privilege('vraelix_enquiry_writer', 'public.enquiries', attribute.attname, 'REFERENCES') end as can_reference
from pg_attribute as attribute
join pg_class as relation on relation.oid = attribute.attrelid
join pg_namespace as namespace on namespace.oid = relation.relnamespace
where to_regrole('vraelix_enquiry_writer') is not null
  and namespace.nspname = 'public' and relation.relname = 'enquiries'
  and attribute.attnum > 0 and not attribute.attisdropped
order by attribute.attnum;

-- 7. PUBLIC function execution rights and defaults on potentially relevant schemas.
select
  namespace.nspname as schema_name,
  count(*) filter (where acl.privilege_type = 'EXECUTE') as public_executable_functions
from pg_proc as proc
join pg_namespace as namespace on namespace.oid = proc.pronamespace
cross join lateral aclexplode(coalesce(proc.proacl, acldefault('f', proc.proowner))) as acl
where namespace.nspname in ('public', 'extensions', 'net', 'auth')
  and acl.grantee = 0
group by namespace.nspname
order by namespace.nspname;

select
  default_acl.defaclrole::regrole as owner_role,
  coalesce(namespace.nspname, '(all schemas)') as schema_name,
  default_acl.defaclobjtype as object_type,
  acl.privilege_type
from pg_default_acl as default_acl
left join pg_namespace as namespace on namespace.oid = default_acl.defaclnamespace
cross join lateral aclexplode(default_acl.defaclacl) as acl
where acl.grantee = 0
order by owner_role, schema_name, object_type, acl.privilege_type;

-- 8. Role attributes and memberships; the writer should have no memberships,
-- LOGIN, NOINHERIT, and BYPASSRLS=false after the reviewed migration.
select rolname, rolcanlogin, rolinherit, rolsuper, rolcreatedb, rolcreaterole,
  rolreplication, rolbypassrls, rolconnlimit
from pg_roles
where rolname = 'vraelix_enquiry_writer';

-- 9. RLS state and existing policies; this does not read table contents.
select relation.relrowsecurity as rls_enabled, relation.relforcerowsecurity as rls_forced
from pg_class as relation
join pg_namespace as namespace on namespace.oid = relation.relnamespace
where namespace.nspname = 'public' and relation.relname = 'enquiries';

select policyname, permissive, roles, cmd, qual, with_check
from pg_policies
where schemaname = 'public' and tablename = 'enquiries'
order by policyname;
