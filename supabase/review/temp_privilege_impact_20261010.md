# Production `PUBLIC TEMPORARY` impact snapshot — 2026-10-10

Read-only inspection of project `ttustzodhlvzanovtzoj` in the Supabase Dashboard. No SQL changed database state. This is the single existing project in the account organization and it is labeled Production; no non-production project was available.

## Effective privilege

All nine login roles have effective `TEMPORARY` on the current database through the grant to `PUBLIC`:

- `authenticator`
- `pgbouncer`
- `postgres`
- `supabase_admin`
- `supabase_auth_admin`
- `supabase_etl_admin`
- `supabase_read_only_user`
- `supabase_replication_admin`
- `supabase_storage_admin`

Only `postgres` has an explicit role-level TEMP grant in the ACL snapshot. The other eight inherit the PUBLIC grant. Three roles have `NOINHERIT`, yet still show effective TEMP; `NOINHERIT` does not cancel a privilege granted to PUBLIC.

## Usage evidence and limits

- At inspection time there were no current temporary relations visible in `pg_class` under temporary schemas.
- The `pg_stat_database` counters showed 21 temporary files and 174,956,544 bytes since the statistics reset at `2026-10-02 18:01:15 UTC`. These are database-wide query temporary-file counters, not a per-role history and not proof of temporary-table use. PostgreSQL counts temp files from any query operation, including sorts and hashes. See [PostgreSQL cumulative statistics](https://www.postgresql.org/docs/current/monitoring-stats.html).
- The point-in-time session snapshot showed connections for `authenticator`, `pgbouncer`, `postgres`, `supabase_admin`, and `supabase_storage_admin`, including `pg_net` and `pg_cron` background workers. This confirms platform-managed activity but does not identify which service has created temporary tables historically.
- The available standard catalog/statistics snapshot cannot attribute past temporary-table use to a role or dependent service. Current absence of temp relations is not proof of no past usage.

## Migration impact and safest decision

The existing writer migration still fails closed while PUBLIC can create temporary objects. Do not revoke TEMP from PUBLIC in Production: that would change an inherited database-wide capability for every login role, including Supabase-managed roles, and the available evidence cannot identify safe replacement grants. Do not change the `ensure_rls` event trigger.

The least disruptive review option is to test the dedicated writer design in an authorized non-production project without changing existing PUBLIC grants. The writer would then inherit TEMP, while its table access remains limited to INSERT on the 11 approved enquiry columns and its only `public.enquiries` RLS policy is INSERT. This has a documented residual risk: a compromised writer credential could create temporary objects and consume temporary resources for its sessions, but it would not gain SELECT/UPDATE/DELETE on enquiries. The migration must explicitly document and verify that trade-off before any staging application.

If the requirement is that the writer must not have TEMP at all, PostgreSQL has no role-specific deny that overrides the PUBLIC grant. That requires revoking TEMP from PUBLIC and granting it back only to confirmed consumers. No evidence here is sufficient to safely choose those consumers; production changes would need a complete dependency inventory and explicit approval.

## Staging review update — 2026-10-11

The authorized `VRAELIX Staging` project (`fqgrdfxboskdyqaipabr`) also grants
`TEMPORARY` to `PUBLIC`. Its read-only snapshot found no custom public-callable
`SECURITY DEFINER` routines and no current temporary relations; database temp
file counters remain global and do not identify a role or service. The revised
writer migration checks PUBLIC database-level `CREATE` and `public` schema
`CREATE`, but deliberately does not block on `TEMPORARY`. It leaves the grant
unchanged, so the writer inherits TEMPORARY. No Production permissions were
changed. The residual capability is accepted only for this approved staging
setup; it does not expand the writer's table access beyond INSERT on the
approved columns.

## Required before any permission change

1. Use a separate staging project, not Production.
2. Have each project/service owner confirm whether it creates explicit temporary tables; inspect app names and database logs only through approved, privacy-safe tooling.
3. Decide explicitly whether the writer may inherit TEMP in staging, or whether a broader PUBLIC privilege redesign is required.
4. Re-run and save the ACL snapshot immediately before a migration, review the migration again, and obtain separate approval before applying it.
