-- Staging bootstrap for the existing VRAELIX enquiries schema.
-- The 13-column definition below was read-only verified against the existing
-- Production public.enquiries table on 2026-10-11. This creates the same
-- schema in the separate VRAELIX Staging project; it does not copy data.
-- PUBLIC, anon, and authenticated receive no table access. The explicit
-- revokes also clear staging's observed postgres default table ACL entries.
-- Staging's postgres default ACL also grants service_role MAINTAIN, REFERENCES,
-- TRIGGER, and TRUNCATE; the approved follow-up writer migration revokes those
-- exact table grants before the staging backend can use the table.
-- RLS is enabled but not forced, matching Production. No TEMP database grants
-- or unrelated permissions are changed.

begin;

create table public.enquiries (
  id uuid not null default gen_random_uuid(),
  created_at timestamp with time zone not null default now(),
  full_name text not null,
  email text not null,
  phone_number text not null,
  company text,
  service text not null,
  project_description text not null,
  budget text,
  timeline text,
  contact_method text not null,
  source text not null default 'VRAELIX Website'::text,
  submitted_at timestamp with time zone not null default now(),
  constraint enquiries_pkey primary key (id)
);

alter table public.enquiries enable row level security;

revoke all privileges on table public.enquiries
  from public, anon, authenticated;

commit;
