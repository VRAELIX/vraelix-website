from __future__ import annotations

from html import escape
from pathlib import Path
import json
import os
import re


ROOT = Path(os.environ.get("VRAELIX_BUILD_OUTPUT", "github-pages")).resolve()
WORKSPACE = Path.cwd().resolve()
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
if backend != "zapier":
    raise SystemExit("The GitHub Pages prep step expects Zapier to remain selected until Supabase cutover is approved.")

# A browser-side Catch Hook is readable by every visitor. Keep it out of the
# public artifact. The local Zapier configuration remains in the existing build.
for name in ("zapierWebhookUrl", "supabaseUrl", "supabasePublishableKey", "turnstileSiteKey"):
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
        return match.group("prefix") + match.group("quote") + base_path + match.group("url") + match.group("quote")

else:
    url_attr = None

for page in ROOT.rglob("*.html"):
    source = page.read_text(encoding="utf-8")
    if url_attr:
        source = url_attr.sub(prefix_internal_url, source)
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
if config_value(public_config, "zapierWebhookUrl") or config_value(public_config, "supabaseUrl") or config_value(public_config, "supabasePublishableKey"):
    raise SystemExit("Public backend configuration was not scrubbed from the GitHub Pages output.")

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
print("Zapier remains selected in source, but its browser-visible Catch Hook is omitted from this public artifact; the quote form remains disabled until a safe server endpoint is approved.")
