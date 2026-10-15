# VRAELIX website

VRAELIX is a static multi-page website built from HTML templates, CSS, browser JavaScript, JSON content and a Python build script. It is not a React, Next.js, WordPress or server-rendered application.

## Project files

- `work/build_site.py` generates the existing static routes and host metadata.
- `work/site_data.json` contains the page, service and legal copy.
- `work/assets/site.css` is the authoritative stylesheet; `work/assets/` also contains the browser-side JavaScript adapters.
- `work/audit_site.py` checks the ordinary static build.
- `work/build_github_pages.py` creates and audits a clean `github-pages/` publishing copy with Supabase selected and enquiry submission disabled until verified.
- `work/audit_github_pages.py` checks routes, links, local assets, base-path handling, and public-output exclusions.
- `outputs/vraelix-premium-site/` is the regular generated local/static-host output.
- `supabase/functions/submit-enquiry/index.ts` is the Edge Function source. Deployment status is external to this repository and must be checked in the intended Supabase project.

## Build and audit

Run from the project root with Python 3:

```powershell
python work/build_site.py
python work/audit_site.py
python work/build_github_pages.py
```

The GitHub Pages build writes only to the ignored `github-pages/` directory and explicitly selects Supabase. It includes only the public Project URL and publishable key from the build environment. It never copies `.env.local` or server credentials. The quote form remains disabled because `ENQUIRY_BACKEND_VERIFIED` is held false in the source until the Edge Function, database permissions, Turnstile, rate limiting, origin checks and approved end-to-end test are verified. The Zapier adapter remains available in source for a reviewed rollback; its browser-visible Catch Hook is omitted from the public artifact.

The GitHub Actions workflow at `.github/workflows/github-pages.yml` is `workflow_dispatch` only. It derives the live origin and repository base path from GitHub's actual owner/repository context at run time, then builds and publishes the static artifact. No repository, owner, or production origin is assumed by the local build.

GitHub Pages does not apply the generated `_headers` or `_redirects` files. The Pages prep step rewrites root-absolute internal links for project-site subpaths, adds `.nojekyll`, omits `_redirects`, removes a nested `robots.txt` where GitHub Pages would not recognize it, and copies the existing CSP into a meta policy as defense in depth. A meta policy cannot replace response headers such as `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` or HSTS. If those headers remain mandatory, place a header-capable CDN/proxy in front of Pages or choose a host that can emit them before launch.

## Public and private configuration

The project-root `.env.local` is local-only and ignored by Git. The static builder reads only allowlisted names. Do not copy `.env.local` into a publishing folder.

- `VRAELIX_ENQUIRY_BACKEND` is set to `supabase` in local `.env.local` and explicitly in the Pages workflow; the build fails if the public Supabase URL or publishable key is missing.
- `VRAELIX_SUPABASE_URL` and `VRAELIX_SUPABASE_PUBLISHABLE_KEY` are public browser configuration. Local builds read them from `.env.local`; GitHub Actions reads matching repository **Variables** with those exact names. These values appear in `assets/site-config.js` only when Supabase is selected. A publishable key is not authentication or a substitute for RLS and Edge Function checks.
- `VRAELIX_TURNSTILE_SITE_KEY` is a public site key. Configure it as a local build value and a GitHub Actions repository **Variable** after the actual Pages hostname is known. The form remains disabled while backend verification is false.
- `VRAELIX_GA4_MEASUREMENT_ID` is optional and public. Add the real `G-...` value to `.env.local` for a local build, or as the GitHub Actions repository **Variable** named `VRAELIX_GA4_MEASUREMENT_ID` after the Analytics property and final website URL exist. Never use a placeholder ID.
- `VRAELIX_SITE_ORIGIN` is the verified HTTPS origin only, without a path. The GitHub Actions workflow computes the real `github.io` origin after the repository exists.
- `VRAELIX_GH_PAGES_BASE_PATH` is empty for a user/organization site and `/<repository>` for a project site. The workflow computes this from GitHub context.
- Never put a Supabase secret/service-role key, database password/URL, Turnstile secret, Upstash token, GitHub token, or other private credential in frontend configuration or the published artifact.

## GA4 privacy behavior

GA4 is inactive while the Measurement ID is blank. When a real ID is configured, the existing compact privacy panel exposes an unchecked optional analytics choice. The Google tag is not requested before explicit analytics consent; `Accept all` opts in, while saving preferences with the checkbox clear keeps analytics off. The footer settings control reopens preferences. The runtime prevents duplicate tag initialization. GA4 uses first-party analytics cookies and sends site usage/device information to Google; the Privacy and Cookie Policy copy is generated conditionally when an ID is present. Review Google property retention and data-sharing settings and applicable legal obligations before enabling it.

## Supabase staging integration — current state

The separate staging project is `fqgrdfxboskdyqaipabr`; Production is `ttustzodhlvzanovtzoj`. The migrations below describe the intended staging schema and writer permissions, but repository files do not prove the current remote state. Verify table rows, RLS, grants, deployments, and secrets directly in Staging before relying on them. Production changes require a separate explicit approval.

The staging migrations were previously applied through the Dashboard SQL Editor, while a prior read-only check found no `supabase_migrations.schema_migrations` relation. Before any CLI migration operation, inspect the current Staging state and use only Supabase's supported history-repair workflow if it remains appropriate. Do not rerun migration SQL, create migration-history tables manually, or use `supabase db push` to reconcile manually applied changes.

The Edge Function should use the dedicated `vraelix_enquiry_writer` connection through the server-side `VRAELIX_ENQUIRY_DATABASE_URL` secret. Keep its password and connection URL in the Staging Function secret store only; never place them in `.env.local`, source files, logs, frontend output, Git, or chat. The function must not use a service-role key for database writes.

The public function endpoint has JWT verification disabled because visitors are not signed-in Supabase users; it must instead enforce the exact Origin allowlist, Turnstile, fail-closed Upstash rate limiting, request validation, and the restricted writer connection. Verify the deployed function revision and trusted client-IP header from the actual Staging ingress before treating rate limiting as operational. CORS and the public publishable key are not authentication.

Required server-side Function secret names are `VRAELIX_ALLOWED_ORIGINS`, `VRAELIX_CLIENT_IP_HEADER`, `VRAELIX_ENQUIRY_DATABASE_URL`, `VRAELIX_TURNSTILE_SECRET_KEY`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, and `VRAELIX_RATE_LIMIT_HASH_SECRET`. Store values in Supabase's Function secret store only. The public `VRAELIX_TURNSTILE_SITE_KEY`, Staging Supabase URL, and publishable key belong in ignored `.env.staging.local` for local Staging builds.

For a later local staging browser test, build to the ignored `outputs/vraelix-staging-preview/` with `VRAELIX_BUILD_OUTPUT=outputs/vraelix-staging-preview` and set `VRAELIX_STAGING_FORM_TEST_MODE=true` in the build process environment. The builder only accepts that mode for this separate output directory, the approved staging project reference, staging public keys, a Turnstile site key, and no production site origin. The local server can serve that output when given the same `VRAELIX_BUILD_OUTPUT`. Use synthetic data only. The normal local and GitHub Pages builds keep `enquiryBackendVerified` false, the form disabled, and production settings unchanged.

The migrations are `supabase/migrations/202610090000_enquiries_schema.sql` and `supabase/migrations/202610090001_enquiry_writer_role.sql`. A local build or source review cannot establish whether the current deployed function, secret configuration, database connection, or test submission is working; verify those in the Staging project before claiming end-to-end readiness.

## Verification limits

Static audits can check generated routes, links, assets, metadata, form source and public-output scans. They cannot verify visual browser breakpoints, console errors, video dropped frames, production response headers, a real Pages URL, or a Supabase insert. Those remain unverified until the site is actually published and the browser/database tests are separately approved and run.
