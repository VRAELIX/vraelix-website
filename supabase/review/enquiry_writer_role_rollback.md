# VRAELIX enquiry-writer migration review and rollback

The staging-only migrations were applied to project `fqgrdfxboskdyqaipabr` on 2026-10-11 through the Supabase Dashboard SQL Editor. The writer migration source is `supabase/migrations/202610090001_enquiry_writer_role.sql`; it includes fail-closed preflight checks for the table, ACLs, role memberships, and inherited database/schema privileges. Production was not touched.

## Permission changes

- Creates `vraelix_enquiry_writer` as a login role with `NOINHERIT`, no superuser, database/role creation, replication, or RLS-bypass privileges, and a five-connection limit. The migration sets `PASSWORD NULL`; a strong password must be set separately through a secure credential workflow before the function can connect.
- Revokes table-level privileges from `PUBLIC`, `anon`, `authenticated`, and `service_role`, and revokes explicit column-level `SELECT`, `INSERT`, `UPDATE`, and `REFERENCES` grants from those same grantees.
- Before revoking, it now stops if any table or column ACL entry exists for `PUBLIC`, `anon`, or `authenticated`. This matters because PUBLIC privileges are inherited by every database role, not just the two Supabase API roles, and direct API-role grants must also match the saved inspection.
- It stops if PUBLIC can create database objects or create objects in schema `public`. The reviewed projects grant `TEMPORARY` to PUBLIC. That grant is intentionally left unchanged, and the writer therefore inherits TEMPORARY; it is a residual capability that allows session-scoped temporary objects but does not grant access to `public.enquiries`. Removing TEMPORARY from PUBLIC is database-wide and may disrupt existing roles or tools, so this migration does not do that.
- The review query lists PUBLIC-executable `SECURITY DEFINER` routines. A normal SQL-callable routine in a schema the writer can use would be a blocker; do not work around that with a blanket function revoke. The observed `public.rls_auto_enable()` returns the `event_trigger` pseudo-type and is attached to the enabled `ensure_rls` DDL event trigger, filtered to table-creation commands. PostgreSQL invokes event-trigger functions through their registered DDL event trigger; this is not a normal SQL-callable endpoint. The migration preflight now excludes `event_trigger` return types while continuing to stop for callable SECURITY DEFINER routines. Do not alter or revoke the existing trigger/function as part of this migration.
- The reviewed staging table had the exact `service_role` table ACL entries `MAINTAIN`, `REFERENCES`, `TRIGGER`, and `TRUNCATE`, with no column ACLs. The migration permits only those observed entries, revokes them, then checks effective table and column rights for `anon`, `authenticated`, and `service_role` are all false. This means service-role-key clients cannot access this table directly; the dedicated writer role is the intended database path.
- Fails if `anon`, `authenticated`, or `service_role` still has effective table/column access through another role membership.
- Grants the dedicated role `USAGE` on schema `public`, plus `INSERT` only on `full_name`, `email`, `phone_number`, `company`, `service`, `project_description`, `budget`, `timeline`, `contact_method`, `source`, and `submitted_at`. It receives no `SELECT`, `UPDATE`, `DELETE`, `TRUNCATE`, sequence, or table-owner privilege.
- Adds one RLS `INSERT` policy for the dedicated role. It creates no public policy and does not change the existing table schema or rows.

## Staging schema bootstrap

`supabase/migrations/202610090000_enquiries_schema.sql` creates the staging table using the exact 13-column Production definition checked from catalog metadata. It enables (but does not force) RLS and revokes table privileges for `PUBLIC`, `anon`, and `authenticated`. Supabase's `postgres` default ACL initially gave `service_role` `MAINTAIN`, `REFERENCES`, `TRIGGER`, and `TRUNCATE`; the follow-up writer migration removes those exact known entries. No database-wide TEMP privileges are changed. Rolling back the writer role does not drop the table; do not drop the table as a cleanup step because that would delete any staging records created later.

### Staging application record — 2026-10-11

- `202610090000_enquiries_schema.sql` applied successfully to staging project `fqgrdfxboskdyqaipabr` only. Catalog checks confirmed all 13 columns/defaults, the primary key, RLS enabled and not forced, no policies, no `PUBLIC`/`anon`/`authenticated` ACL entries, and zero rows.
- `202610090001_enquiry_writer_role.sql` then applied successfully to staging only in one transaction through the Dashboard SQL Editor. Its guard accepted the previously observed Supabase admin membership (`postgres` is a member of the writer role) while verifying the writer is not a member of any other role and no non-admin role can assume it. No role memberships were granted by the migration.
- Postflight confirmed the schema still exactly matches the reviewed 13 columns/defaults, with only `enquiries_pkey`, RLS enabled/not forced, one INSERT-only policy for `vraelix_enquiry_writer`, and zero rows.
- Effective table-level and column-level privileges for `anon`, `authenticated`, and `service_role` are all false for read/write/maintenance rights tested. `PUBLIC`/API direct table ACLs are absent.
- The writer has LOGIN, NOINHERIT, no superuser/createdb/createrole/replication/BYPASSRLS flags, and a five-connection limit. It has database CONNECT and `public` USAGE, no database/schema CREATE, no table-wide rights, and INSERT on exactly the 11 approved columns. It cannot insert `id` or `created_at`, and has no SELECT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER rights.
- As reviewed, `PUBLIC TEMPORARY` remains unchanged and the writer effectively inherits TEMP; PUBLIC database CREATE remains absent. The writer role was created with `PASSWORD NULL`, so database permission checks passed but password-authenticated connection testing is not possible until the credential is set through a secure workflow.
- A read-only check found no `supabase_migrations.schema_migrations` relation in this staging database. The Dashboard SQL Editor therefore applied the SQL but did not register these versions in a Supabase CLI migration history. Before a future `supabase db push`, reconcile/baseline migration history safely; do not blindly push these files and attempt to recreate the existing table or writer role.
- Earlier attempts at the writer migration were rolled back after guard defects were found. The successful transaction is the only persisted writer-role application. No production project was opened for a write, no Edge Function was deployed, no secret was configured, and no enquiry record was inserted.

The role itself can insert arbitrary values into its 11 permitted columns if its password is compromised. The Edge Function therefore remains responsible for validation, setting `source`/`submitted_at`, Turnstile checks, origin checks, and rate limiting. The role cannot read or modify enquiry rows. RLS remains enabled. Direct `service_role` access to this table has been revoked in staging; do not rely on a service-role client for the visitor-facing function.

## Transaction and preflight

All writer migration statements are inside one transaction. A failed assertion rolls back the role, grants, and policy. The migration compares the complete 13-column set in both directions and verifies type, nullability, default, identity, and generated-column status. It also checks the primary-key constraint and index, requires RLS enabled/not forced, no existing policies, and no pre-existing writer role. It contains no enquiry-row `INSERT`, `UPDATE`, `DELETE`, or `TRUNCATE`, table recreation, or schema alteration.

Preflight outputs must be retained because the migration removes ACL entries for `PUBLIC`, `anon`, `authenticated`, and `service_role`. The review query includes schema/defaults, raw and expanded ACLs, effective API-role privileges, role memberships, and generated `GRANT` statements for a possible exact-permission rollback. It does not save a snapshot inside the database. The migration stops if PUBLIC/anon/authenticated grants exist or if service_role has anything beyond the exact observed staging defaults. Production ACLs were not changed.

## Rollback

The preferred application rollback is to disable the form/function first, then remove only the new writer capability while retaining the public-role revocations. After confirming the function has no active database sessions, run:

```sql
begin;
drop policy if exists vraelix_enquiry_writer_insert on public.enquiries;
revoke insert (
  full_name, email, phone_number, company, service, project_description,
  budget, timeline, contact_method, source, submitted_at
) on table public.enquiries from vraelix_enquiry_writer;
revoke usage on schema public from vraelix_enquiry_writer;
alter role vraelix_enquiry_writer nologin;
commit;
```

Check `pg_stat_activity` for sessions using `vraelix_enquiry_writer`. Once none remain, `DROP ROLE vraelix_enquiry_writer;` removes the unused login. Do not use `DROP OWNED` as a cleanup shortcut.

That rollback disables the writer but intentionally keeps the tightened `PUBLIC`/API-role table ACLs. To restore the exact pre-migration ACL, use the saved preflight ACL outputs to reconstruct only the original table and column grants, after reviewing their security effect. Never restore a blanket `PUBLIC` grant or assume that re-granting all prior access is safe.
