# VRAELIX website

VRAELIX is a static multi-page website built from HTML templates, CSS, browser JavaScript, JSON content and a Python build script. It is not a React, Next.js, WordPress or server-rendered application.

## Project files

- `work/build_site.py` generates the existing static routes and host metadata.
- `work/site_data.json` contains the page, service and legal copy.
- `work/assets/` contains the website's browser-side JavaScript adapters.
- `work/audit_site.py` checks the ordinary static build.
- `work/build_github_pages.py` creates and audits a clean `github-pages/` publishing copy without changing the regular Zapier build.
- `work/audit_github_pages.py` checks routes, links, local assets, base-path handling, and public-output exclusions.
- `outputs/vraelix-premium-site/` is the regular generated local/static-host output.
- `supabase/functions/submit-enquiry/index.ts` is review-stage Edge Function source; it has not been deployed.

## Build and audit

Run from the project root with Python 3:

```powershell
python work/build_site.py
python work/audit_site.py
python work/build_github_pages.py
```

The GitHub Pages build writes only to the ignored `github-pages/` directory. It builds with `VRAELIX_ENQUIRY_BACKEND=zapier`, but deliberately blanks all browser backend endpoints and credentials. The local Zapier config remains in the ordinary ignored output and rollback copy. The public artifact's quote form is disabled until a server-side endpoint is deployed and approved; a browser-visible Zapier Catch Hook is not safe to conceal with a GitHub secret.

The GitHub Actions workflow at `.github/workflows/github-pages.yml` is `workflow_dispatch` only. It derives the live origin and repository base path from GitHub's actual owner/repository context at run time, then builds and publishes the static artifact. No repository, owner, or production origin is assumed by the local build.

GitHub Pages does not apply the generated `_headers` or `_redirects` files. The Pages prep step rewrites root-absolute internal links for project-site subpaths, adds `.nojekyll`, omits `_redirects`, removes a nested `robots.txt` where GitHub Pages would not recognize it, and copies the existing CSP into a meta policy as defense in depth. A meta policy cannot replace response headers such as `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` or HSTS. If those headers remain mandatory, place a header-capable CDN/proxy in front of Pages or choose a host that can emit them before launch.

## Public and private configuration

The project-root `.env.local` is local-only and ignored by Git. The static builder reads only allowlisted names. Do not copy `.env.local` into a publishing folder.

- `VRAELIX_SUPABASE_URL` and `VRAELIX_SUPABASE_PUBLISHABLE_KEY` are public browser configuration. The GitHub Pages artifact clears them while Zapier remains selected.
- `VRAELIX_GA4_MEASUREMENT_ID` is optional and public. Add the real `G-...` value to `.env.local` for a local build, or as the GitHub Actions repository **Variable** named `VRAELIX_GA4_MEASUREMENT_ID` after the Analytics property and final website URL exist. Never use a placeholder ID.
- `VRAELIX_SITE_ORIGIN` is the verified HTTPS origin only, without a path. The GitHub Actions workflow computes the real `github.io` origin after the repository exists.
- `VRAELIX_GH_PAGES_BASE_PATH` is empty for a user/organization site and `/<repository>` for a project site. The workflow computes this from GitHub context.
- Never put a Supabase secret/service-role key, database password/URL, Turnstile secret, Upstash token, GitHub token, or other private credential in frontend configuration or the published artifact.

## GA4 privacy behavior

GA4 is inactive while the Measurement ID is blank. When a real ID is configured, the existing compact privacy panel exposes an unchecked optional analytics choice. The Google tag is not requested before explicit analytics consent; `Accept all` opts in, while saving preferences with the checkbox clear keeps analytics off. The footer settings control reopens preferences. The runtime prevents duplicate tag initialization. GA4 uses first-party analytics cookies and sends site usage/device information to Google; the Privacy and Cookie Policy copy is generated conditionally when an ID is present. Review Google property retention and data-sharing settings and applicable legal obligations before enabling it.

## Supabase Option A — review only

The existing `public.enquiries` table is reused and is not dropped or recreated. The proposed migration creates `vraelix_enquiry_writer` as a non-superuser, non-inheriting login role with RLS still enabled, a single INSERT policy, and column-level INSERT grants for only the approved enquiry fields. It omits `id` and `created_at` so existing defaults continue to apply. The migration proposes revoking table/column access from `PUBLIC`, `anon` and `authenticated`; it leaves `service_role` unchanged. It does not grant role membership to `anon`, `authenticated`, `authenticator`, or other Supabase roles. The read-only `supabase/review/enquiry_writer_acl_checks.sql` checks table/column ACLs, `PUBLIC` rights, default function grants, role memberships and effective privileges. No migration has been applied.

The Edge Function source uses a dedicated Postgres connection URL (`VRAELIX_ENQUIRY_DATABASE_URL`) through the Supabase transaction pooler, not a Supabase service-role or secret API key. The database password belongs only in the Edge Function's secure secrets. Before approving the migration, inspect inherited `PUBLIC` privileges on the database, schemas, functions and extensions; PostgreSQL has no per-role deny that cancels a `PUBLIC` grant. The migration only revokes table privileges on `public.enquiries`; any wider revocation needs its own impact review.

The public function is configured with JWT verification disabled because visitors are not signed-in Supabase users. The publishable `apikey` is public and is not authentication. The function must fail closed until exact origins, Turnstile, Upstash and the trusted client-IP header are configured. `VRAELIX_CLIENT_IP_HEADER` intentionally has no default because the actual trusted header from the Supabase request path has not been verified. CORS is not authentication or rate limiting.

Required server-side settings are `VRAELIX_ALLOWED_ORIGINS`, `VRAELIX_CLIENT_IP_HEADER`, `VRAELIX_ENQUIRY_DATABASE_URL`, `VRAELIX_TURNSTILE_SECRET_KEY`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, and `VRAELIX_RATE_LIMIT_HASH_SECRET`. Store them through Supabase's secrets mechanism only. The public Turnstile site key is `VRAELIX_TURNSTILE_SITE_KEY`; it belongs in public build configuration after the real GitHub hostname is known.

Do not change `VRAELIX_ENQUIRY_BACKEND=zapier`, apply the migration, deploy the function, or send a synthetic row until the review and explicit approvals are complete. The complete schema/permission proposal is in `supabase/migrations/202610090001_enquiry_writer_role.sql` and `supabase/functions/submit-enquiry/index.ts`.

## Verification limits

Static audits can check generated routes, links, assets, metadata, form source and public-output scans. They cannot verify visual browser breakpoints, console errors, video dropped frames, production response headers, a real Pages URL, or a Supabase insert. Those remain unverified until the site is actually published and the browser/database tests are separately approved and run.
