from __future__ import annotations

from html import escape
from pathlib import Path
import json
import os
import re


ROOT = Path(os.environ.get("VRAELIX_BUILD_OUTPUT", "github-pages")).resolve()
WORKSPACE = Path.cwd().resolve()
LIVE_OUTPUT = (WORKSPACE / "outputs" / "vraelix-live").resolve()
GITHUB_PAGES_OUTPUT = (WORKSPACE / "github-pages").resolve()
IS_LIVE_OUTPUT = ROOT == LIVE_OUTPUT
IS_GITHUB_PAGES_OUTPUT = ROOT == GITHUB_PAGES_OUTPUT
VERIFIED_OUTPUT_ALLOWED = IS_LIVE_OUTPUT or IS_GITHUB_PAGES_OUTPUT
MARKER = ".vraelix-github-pages-generated"
CONFIG_PATH = ROOT / "assets" / "site-config.js"

if ROOT == WORKSPACE or WORKSPACE not in ROOT.parents:
    raise SystemExit("GitHub Pages output must stay inside the project workspace.")
if not (ROOT / MARKER).is_file():
    raise SystemExit("Refusing to publish-process an unmarked directory; use work/build_github_pages.py.")
if not (ROOT / "index.html").is_file() or not CONFIG_PATH.is_file():
    raise SystemExit("Build the site before preparing the GitHub Pages directory.")


def config_value(source: str, name: str) -> str:
    match = re.search(r"^\s*" + re.escape(name) + r"\s*:\s*(\"(?:\\.|[^\"\\])*\")", source, re.MULTILINE)
    if not match:
        return ""
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return ""


def config_boolean(source: str, name: str) -> bool:
    match = re.search(r'^\s*' + re.escape(name) + r'\s*:\s*(true|false)\s*,?$', source, re.MULTILINE)
    return bool(match and match.group(1) == "true")


def set_config_value(source: str, name: str, value: str) -> str:
    pattern = re.compile(r"^(\s*" + re.escape(name) + r"\s*:\s*)(\"(?:\\.|[^\"\\])*\")", re.MULTILINE)
    updated, count = pattern.subn(lambda match: match.group(1) + json.dumps(value), source)
    if count != 1:
        raise SystemExit(f"Expected exactly one {name} entry in site-config.js.")
    return updated


def normalize_base_path(value: str) -> str:
    value = value.strip()
    if value in ("", "/"):
        return ""
    if (not value.startswith("/") or value.endswith("/") or "//" in value
            or any(part in ("", ".", "..") for part in value[1:].split("/"))
            or not re.fullmatch(r"/[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*", value)):
        raise SystemExit("VRAELIX_GH_PAGES_BASE_PATH is invalid; use an empty path or a safe repository path.")
    return value


config = CONFIG_PATH.read_text(encoding="utf-8")
backend = config_value(config, "enquiryBackend")
base_path = normalize_base_path(config_value(config, "siteBasePath"))
if backend != "supabase":
    raise SystemExit("GitHub Pages must be built with VRAELIX_ENQUIRY_BACKEND=supabase; refusing to fall back to Zapier.")
verified = config_boolean(config, "enquiryBackendVerified")
staging_test_mode = config_boolean(config, "enquiryStagingTestMode")
if verified and not VERIFIED_OUTPUT_ALLOWED:
    raise SystemExit("Verified enquiry submission is permitted only for the approved live or GitHub Pages output.")
if staging_test_mode and (IS_LIVE_OUTPUT or IS_GITHUB_PAGES_OUTPUT):
    raise SystemExit("Staging test mode is not permitted in a live or GitHub Pages output.")
if verified and (
    base_path != "/vraelix-website"
    or config_value(config, "supabaseUrl") != "https://fqgrdfxboskdyqaipabr.supabase.co"
    or not config_value(config, "supabasePublishableKey")
    or not config_value(config, "turnstileSiteKey")
):
    raise SystemExit("Verified output requires the approved project URL, public key, Turnstile site key, and project-site base path.")

# A browser-side Catch Hook is readable by every visitor. Keep it out of the
# public artifact. Supabase URL and publishable key are public client settings.
for name in ("zapierWebhookUrl",):
    config = set_config_value(config, name, "")
CONFIG_PATH.write_text(config, encoding="utf-8")

header_path = ROOT / "_headers"
csp = ""
if header_path.is_file():
    for line in header_path.read_text(encoding="utf-8").splitlines():
        candidate = line.strip()
        if candidate.lower().startswith("content-security-policy:"):
            csp = candidate.split(":", 1)[1].strip()
            break

if base_path:
    url_attr = re.compile(r"(?P<prefix>\b(?:href|src|poster|action|data-desktop|data-mobile)\s*=\s*)(?P<quote>[\"'])(?P<url>/(?!/)[^\"']*)(?P=quote)", re.IGNORECASE)

    def prefix_internal_url(match: re.Match[str]) -> str:
        url = match.group("url")
        if url == base_path or url.startswith(base_path + "/"):
            return match.group(0)
        return match.group("prefix") + match.group("quote") + base_path + url + match.group("quote")

    srcset_attr = re.compile(r"(?P<prefix>\bsrcset\s*=\s*)(?P<quote>[\"'])(?P<value>[^\"']*)(?P=quote)", re.IGNORECASE)

    def prefix_srcset_urls(match: re.Match[str]) -> str:
        value = match.group("value")

        def prefix_candidate(candidate: re.Match[str]) -> str:
            url = candidate.group(0)
            if url == base_path or url.startswith(base_path + "/"):
                return url
            return base_path + url

        value = re.sub(r"(?<![/\w:])/(?!/)[^\s,]+", prefix_candidate, value)
        return match.group("prefix") + match.group("quote") + value + match.group("quote")

else:
    url_attr = None

for page in ROOT.rglob("*.html"):
    source = page.read_text(encoding="utf-8")
    if url_attr:
        source = url_attr.sub(prefix_internal_url, source)
        source = srcset_attr.sub(prefix_srcset_urls, source)
    if csp and "http-equiv=\"Content-Security-Policy\"" not in source:
        csp_meta = '<meta http-equiv="Content-Security-Policy" content="' + escape(csp, quote=True) + '">'
        source = source.replace("</head>", csp_meta + "</head>", 1)
    page.write_text(source, encoding="utf-8")

# GitHub Pages serves project sites beneath /<repository>/; robots.txt is only
# recognized at the host root, so omit the ineffective nested copy in that case.
robots = ROOT / "robots.txt"
if base_path and robots.exists():
    robots.unlink()

# GitHub Pages does not apply the Netlify/Cloudflare _headers or _redirects formats.
for name in ("_headers", "_redirects"):
    path = ROOT / name
    if path.exists():
        path.unlink()

(ROOT / ".nojekyll").write_text("", encoding="utf-8")
(ROOT / MARKER).unlink(missing_ok=True)

for path in ROOT.rglob("*"):
    if path.is_file() and (path.name == ".env" or path.name.startswith(".env.")):
        raise SystemExit("Environment file found in the GitHub Pages output; publishing stopped.")

public_config = CONFIG_PATH.read_text(encoding="utf-8")
if config_value(public_config, "zapierWebhookUrl"):
    raise SystemExit("A browser-visible Zapier endpoint remains in the GitHub Pages output.")
if config_boolean(public_config, "enquiryBackendVerified") and (
    not config_value(public_config, "supabaseUrl")
    or not config_value(public_config, "supabasePublishableKey")
    or not config_value(public_config, "turnstileSiteKey")
):
    raise SystemExit("Verified GitHub Pages enquiries require all public Supabase and Turnstile settings.")

forbidden_markers = (
    "sb_secret_",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_SECRET_KEYS",
    "VRAELIX_ENQUIRY_DATABASE_URL",
    "VRAELIX_TURNSTILE_SECRET_KEY",
    "UPSTASH_REDIS_REST_TOKEN",
    "postgresql://",
    "https://hooks.zapier.com/hooks/catch/",
)
for path in ROOT.rglob("*"):
    if path.is_file() and path.suffix.lower() in {".html", ".js", ".css", ".json", ".txt", ".xml", ".yml", ".yaml", ".toml"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(marker in text for marker in forbidden_markers):
            raise SystemExit("A private backend credential marker was found in the GitHub Pages output.")

print(f"Prepared a clean GitHub Pages static directory with {sum(1 for _ in ROOT.rglob('*.html'))} HTML routes.")
if config_boolean(CONFIG_PATH.read_text(encoding="utf-8"), "enquiryBackendVerified"):
    print("Supabase is selected with public configuration; enquiry submission is enabled for the explicitly approved Pages build.")
else:
    print("Enquiry submission remains disabled because the build-time readiness checks were not met.")
