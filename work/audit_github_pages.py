from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
import json
import os
import re
import sys


ROOT = Path(os.environ.get("VRAELIX_BUILD_OUTPUT", "github-pages")).resolve()
WORKSPACE = Path.cwd().resolve()
errors: list[str] = []
DATA = json.loads(Path("work/site_data.json").read_text(encoding="utf-8"))
ROUTES = [row[0] for row in DATA["pages"]] + [f"/services/{row['slug']}/" for row in DATA["services"]]


class Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def config_string(config: str, name: str) -> str:
    match = re.search(r"^\s*" + re.escape(name) + r"\s*:\s*(\"(?:\\.|[^\"\\])*\")", config, re.MULTILINE)
    if not match:
        return ""
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return ""


def page_path(route: str) -> Path:
    return ROOT / "index.html" if route == "/" else ROOT.joinpath(*route.strip("/").split("/")) / "index.html"


def local_target(value: str, base_path: str, route: str) -> tuple[str, Path | None]:
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return "external", None
    path = parsed.path
    if base_path:
        if not (path == base_path or path.startswith(base_path + "/")):
            return "unprefixed", None
        path = path[len(base_path):] or "/"
    if path.startswith("/assets/"):
        return "asset", ROOT / path.lstrip("/")
    normalized = path if path.endswith("/") else path + "/"
    if normalized == "//":
        normalized = "/"
    if normalized == "/":
        return "route", ROOT / "index.html"
    return "route", ROOT.joinpath(*normalized.strip("/").split("/")) / "index.html"


if ROOT == WORKSPACE or WORKSPACE not in ROOT.parents:
    errors.append("Output path is outside the workspace")
config_path = ROOT / "assets" / "site-config.js"
config = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
base_path = config_string(config, "siteBasePath")
if base_path and (not base_path.startswith("/") or base_path.endswith("/") or ".." in base_path.split("/")):
    errors.append("Invalid siteBasePath in generated configuration")
if config_string(config, "enquiryBackend") != "zapier":
    errors.append("GitHub Pages output changed the default backend selector")
if config_string(config, "zapierWebhookUrl"):
    errors.append("Browser-visible Zapier endpoint remains in the public output")
for name in ("supabaseUrl", "supabasePublishableKey", "turnstileSiteKey"):
    if config_string(config, name):
        errors.append(f"Unused public backend setting {name} should be blank while Zapier remains selected")

missing = []
for route in ROUTES:
    path = page_path(route)
    if not path.is_file():
        errors.append(f"Missing route file: {route}")
        continue
    doc = Document()
    doc.feed(path.read_text(encoding="utf-8"))
    ids = {attrs.get("id") for _, attrs in doc.tags if attrs.get("id")}
    for tag, attrs in doc.tags:
        for attr in ("href", "src", "poster", "action", "data-desktop", "data-mobile"):
            value = attrs.get(attr, "").strip()
            if value.startswith("#"):
                if value[1:] and value[1:] not in ids:
                    errors.append(f"{route}: broken fragment link {value}")
                continue
            kind, target = local_target(value, base_path, route)
            if kind == "unprefixed":
                errors.append(f"{route}: local URL is missing the GitHub Pages base path ({attr})")
            elif kind in ("route", "asset") and target and not target.is_file():
                errors.append(f"{route}: local {attr} target is missing ({target.relative_to(ROOT).as_posix()})")
            if tag == "img" and attr == "src" and "alt" not in attrs:
                errors.append(f"{route}: image is missing alt text")

    html = path.read_text(encoding="utf-8")
    if not html.lstrip().lower().startswith("<!doctype html>"):
        errors.append(f"{route}: missing HTML5 doctype")
    if '<meta http-equiv="Content-Security-Policy"' not in html:
        errors.append(f"{route}: GitHub Pages defense-in-depth CSP meta tag is missing")
    for attr in re.finditer(r'\b(?:href|src|poster|action|data-desktop|data-mobile)=["\'](/[^/][^"\']*)["\']', html, re.I):
        path_value = attr.group(1)
        if base_path and not (path_value == base_path or path_value.startswith(base_path + "/")):
            errors.append(f"{route}: root-absolute URL is not prefixed for project-site hosting")
            break

for filename in ("_headers", "_redirects"):
    if (ROOT / filename).exists():
        errors.append(f"GitHub Pages output still contains unsupported host rules: {filename}")
if not (ROOT / ".nojekyll").is_file():
    errors.append(".nojekyll marker is missing")
if base_path and (ROOT / "robots.txt").exists():
    errors.append("Project-site output contains a nested robots.txt that crawlers will not use")

home = (ROOT / "index.html").read_text(encoding="utf-8") if (ROOT / "index.html").is_file() else ""
if "/assets/hero-poster.webp" not in home or "/assets/vraelix-cinematic.mp4" not in home or "/assets/vraelix-cinematic-mobile.webm" not in home:
    errors.append("Responsive Hero video, poster, or fallback source is missing")
for asset in ("hero-poster.webp", "vraelix-cinematic.mp4", "vraelix-cinematic-mobile.webm", "founder-profile.webp", "founder-work.webp", "founder-coffee.webp"):
    if not (ROOT / "assets" / asset).is_file():
        missing.append(asset)
if missing:
    errors.append("Required media missing from publication output: " + ", ".join(missing))

for path in ROOT.rglob("*"):
    if not path.is_file():
        continue
    if path.name == ".env" or path.name.startswith(".env."):
        errors.append("Environment file found in the public output")
    if path.suffix.lower() in {".html", ".js", ".css", ".json", ".txt", ".xml", ".yml", ".yaml", ".toml"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in ("sb_secret_", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEYS", "VRAELIX_ENQUIRY_DATABASE_URL", "VRAELIX_TURNSTILE_SECRET_KEY", "UPSTASH_REDIS_REST_TOKEN", "postgresql://", "https://hooks.zapier.com/hooks/catch/"):
            if marker in text:
                errors.append("Private credential material or a live Catch Hook was found in public output")
                break

print(f"Audited GitHub Pages artifact: {len(ROUTES)} expected routes, base path {'configured' if base_path else 'empty'}.")
print(f"Errors: {len(errors)}")
for error in errors:
    print("ERROR", error)
print("Checks are static; browser viewport, console, production headers, and live traffic remain unverified.")
if errors:
    raise SystemExit(1)
