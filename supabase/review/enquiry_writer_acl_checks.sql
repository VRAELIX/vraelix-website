-- Read-only preflight/postflight queries. Run in the Supabase SQL Editor.
-- These queries return schema/privilege metadata and an aggregate row count;
-- they do not read enquiry contents or personal information.

-- 0. Column definitions and defaults. This result must match the reviewed
-- 13-column schema before applying the writer-role migration.
select ordinal_position, column_name, data_type, is_nullable, column_default,
       is_identity, is_generated
from information_schema.columns
where table_schema = 'public' and table_name = 'enquiries'
order by ordinal_position;

-- 0a. Constraints. Confirm the reviewed primary key and check for any new
-- constraints that could change insert behavior; this returns definitions,
-- never enquiry row contents.
select constraint_row.conname as constraint_name,
       constraint_row.contype as constraint_type,
       constraint_row.condeferrable as is_deferrable,
       constraint_row.condeferred as initially_deferred,
       constraint_row.convalidated as is_validated,
       pg_get_constraintdef(constraint_row.oid, true) as definition
from pg_constraint as constraint_row
join pg_class as relation on relation.oid = constraint_row.conrelid
join pg_namespace as namespace on namespace.oid = relation.relnamespace
where namespace.nspname = 'public' and relation.relname = 'enquiries'
order by constraint_row.contype, constraint_row.conname;

-- 0b. Indexes. Confirm the reviewed primary-key index and detect any
-- additional or changed indexes without scanning application data.
select index_relation.relname as index_name,
       index_row.indisprimary as is_primary,
       index_row.indisunique as is_unique,
       index_row.indisvalid as is_valid,
       index_row.indisready as is_ready,
       pg_get_indexdef(index_row.indexrelid) as definition
from pg_index as index_row
join pg_class as table_relation on table_relation.oid = index_row.indrelid
join pg_namespace as namespace on namespace.oid = table_relation.relnamespace
join pg_class as index_relation on index_relation.oid = index_row.indexrelid
where namespace.nspname = 'public' and table_relation.relname = 'enquiries'
order by index_relation.relname;

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

-- 2b. Generate exact effective GRANT statements for the ACL entries that the
-- migration revokes, including the reviewed Supabase service_role defaults.
-- Save the output with the raw ACL results. Do not execute these automatically;
-- use them only for a deliberate ACL restoration.
with table_grants as (
  select case when acl.grantee = 0 then 'PUBLIC' else quote_ident(grantee.rolname) end as grantee_name,
         acl.is_grantable,
         string_agg(acl.privilege_type, ', ' order by acl.privilege_type) as privileges
  from pg_class as relation
  join pg_namespace as namespace on namespace.oid = relation.relnamespace
  cross join lateral aclexplode(coalesce(relation.relacl, acldefault('r', relation.relowner))) as acl
  left join pg_roles as grantee on grantee.oid = acl.grantee
  where namespace.nspname = 'public' and relation.relname = 'enquiries'
    and (acl.grantee = 0 or grantee.rolname in ('anon', 'authenticated', 'service_role'))
  group by grantee_name, acl.is_grantable
), column_grants as (
  select case when acl.grantee = 0 then 'PUBLIC' else quote_ident(grantee.rolname) end as grantee_name,
         acl.privilege_type, acl.is_grantable,
         string_agg(quote_ident(attribute.attname), ', ' order by attribute.attname) as column_names
  from pg_attribute as attribute
  join pg_class as relation on relation.oid = attribute.attrelid
  join pg_namespace as namespace on namespace.oid = relation.relnamespace
  cross join lateral aclexplode(attribute.attacl) as acl
  left join pg_roles as grantee on grantee.oid = acl.grantee
  where namespace.nspname = 'public' and relation.relname = 'enquiries'
    and attribute.attnum > 0 and not attribute.attisdropped and attribute.attacl is not null
    and (acl.grantee = 0 or grantee.rolname in ('anon', 'authenticated', 'service_role'))
  group by grantee_name, acl.privilege_type, acl.is_grantable
)
select 'table' as acl_kind,
       format('GRANT %s ON TABLE public.enquiries TO %s%s;', privileges,
              grantee_name, case when is_grantable then ' WITH GRANT OPTION' else '' end) as rollback_grant_statement
from table_grants
union all
select 'column' as acl_kind,
       format('GRANT %s (%s) ON TABLE public.enquiries TO %s%s;', privilege_type,
              column_names, grantee_name,
              case when is_grantable then ' WITH GRANT OPTION' else '' end) as rollback_grant_statement
from column_grants
order by acl_kind, rollback_grant_statement;

-- 2c. Effective table privileges of the public API roles, including access
-- inherited through role memberships and PUBLIC.
select role_set.role_name, privilege_set.privilege,
       has_table_privilege(role_set.role_name, 'public.enquiries', privilege_set.privilege) as effective_table_privilege
from (values ('anon'), ('authenticated'), ('service_role')) as role_set(role_name)
cross join (values ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE'),
                   ('TRUNCATE'), ('REFERENCES'), ('TRIGGER')) as privilege_set(privilege)
order by role_set.role_name, privilege_set.privilege;

select role_set.role_name, column_set.column_name, privilege_set.privilege,
       has_column_privilege(role_set.role_name, 'public.enquiries', column_set.column_name, privilege_set.privilege) as effective_column_privilege
from (values ('anon'), ('authenticated'), ('service_role')) as role_set(role_name)
cross join (values ('id'), ('created_at'), ('full_name'), ('email'), ('phone_number'),
                   ('company'), ('service'), ('project_description'), ('budget'),
                   ('timeline'), ('contact_method'), ('source'), ('submitted_at')) as column_set(column_name)
cross join (values ('SELECT'), ('INSERT'), ('UPDATE'), ('REFERENCES')) as privilege_set(privilege)
order by role_set.role_name, column_set.column_name, privilege_set.privilege;

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

-- 3b. PUBLIC-executable SECURITY DEFINER functions are inherited by the
-- proposed writer whenever it has USAGE on the containing schema. Review each
-- result; this migration intentionally does not revoke function privileges.
select namespace.nspname as schema_name,
       proc.proname as function_name,
       pg_get_function_identity_arguments(proc.oid) as identity_arguments,
       pg_get_userbyid(proc.proowner) as owner,
       proc.prosecdef as security_definer,
       proc.proconfig as function_settings
from pg_proc as proc
join pg_namespace as namespace on namespace.oid = proc.pronamespace
cross join lateral aclexplode(coalesce(proc.proacl, acldefault('f', proc.proowner))) as acl
where namespace.nspname in ('public', 'extensions', 'net', 'auth')
  and acl.grantee = 0 and acl.privilege_type = 'EXECUTE'
  and proc.prosecdef
order by namespace.nspname, proc.proname, identity_arguments;

-- 4. PUBLIC database-level grants. Do not revoke CONNECT from PUBLIC in Supabase.
select
  database.datname,
  acl.privilege_type,
  acl.is_grantable
from pg_database as database
cross join lateral aclexplode(coalesce(database.datacl, acldefault('d', database.datdba))) as acl
where database.datname = current_database() and acl.grantee = 0
order by acl.privilege_type;

-- 4a. Effective TEMP privilege for every login role. This records who would
-- lose temporary-table capability if PUBLIC's grant were revoked. ACLs show
-- permission, not actual application use; confirm dependencies with each
-- database/tool owner before changing the database-wide grant.
select
  role_info.rolname,
  role_info.rolinherit,
  has_database_privilege(role_info.rolname, current_database(), 'TEMP') as effective_temp,
  exists (
    select 1
    from pg_database as target_database
    cross join lateral aclexplode(coalesce(target_database.datacl, acldefault('d', target_database.datdba))) as role_acl
    where target_database.datname = current_database()
      and role_acl.grantee = role_info.oid
      and role_acl.privilege_type = 'TEMPORARY'
  ) as explicit_role_temp_grant
from pg_roles as role_info
where role_info.rolcanlogin
order by role_info.rolname;

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

-- 10. Aggregate only; confirms existing rows without selecting their contents.
select count(*)::bigint as existing_row_count from public.enquiries;

-- 11. Database-wide temp-file counters. These are cumulative since stats_reset,
-- include sort/hash spill files (not only temporary tables), and cannot identify
-- which role used TEMPORARY. Use this only as broad impact context.
select temp_files, temp_bytes, stats_reset
from pg_stat_database
where datname = current_database();

-- 12. Current temporary relations by owner, without exposing relation names.
-- An empty result means no temp relations exist at this instant; it does not
-- prove that no role or service used temporary tables in the past.
select owner_role.rolname as owner_role, count(*)::bigint as current_temp_relation_count
from pg_class as relation
join pg_namespace as namespace on namespace.oid = relation.relnamespace
join pg_roles as owner_role on owner_role.oid = relation.relowner
where relation.relpersistence = 't'
  and namespace.nspname like 'pg_temp_%'
group by owner_role.rolname
order by owner_role.rolname;

-- 13. Active sessions grouped by role and backend type. No SQL text, client IP,
-- application_name, or enquiry contents are returned. This is a point-in-time
-- connection inventory, not historical proof of TEMPORARY use.
select usename as role_name, backend_type, state, count(*)::bigint as connections
from pg_stat_activity
where datname = current_database() and usename is not null
group by usename, backend_type, state
order by usename, backend_type, state;
