from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import re
import sys
from urllib.parse import urlsplit

WORKSPACE = Path(__file__).resolve().parent.parent
BUILD_OUTPUT = os.environ.get("VRAELIX_BUILD_OUTPUT", "outputs/vraelix-premium-site")
if BUILD_OUTPUT not in ("outputs/vraelix-premium-site", "outputs/vraelix-staging-preview", "outputs/vraelix-live"):
    raise ValueError("VRAELIX_BUILD_OUTPUT must select a generated VRAELIX website directory")
ROOT = WORKSPACE / "outputs" / "vraelix-premium-site"
if BUILD_OUTPUT == "outputs/vraelix-staging-preview":
    ROOT = WORKSPACE / "outputs" / "vraelix-staging-preview"
elif BUILD_OUTPUT == "outputs/vraelix-live":
    ROOT = WORKSPACE / "outputs" / "vraelix-live"
try:
    config_text = (ROOT / "assets/site-config.js").read_text(encoding="utf-8")
except OSError:
    config_text = ""
def config_value(name):
    match = re.search(
        r"^\s*" + re.escape(name) + r'\s*:\s*("(?:\\.|[^"\\])*")',
        config_text,
        re.MULTILINE,
    )
    try:
        return json.loads(match.group(1)) if match else ""
    except (ValueError, json.JSONDecodeError):
        return ""


backend = config_value("enquiryBackend")
SITE_BASE_PATH = config_value("siteBasePath").rstrip("/")
backend_verified = bool(
    re.search(r"^\s*enquiryBackendVerified:\s*true\s*,?$", config_text, re.MULTILINE)
    or re.search(r"^\s*enquiryStagingTestMode:\s*true\s*,?$", config_text, re.MULTILINE)
)
connect_sources = ["'self'"]
script_sources = ["'self'"]
frame_sources = ["'self'"]
if backend_verified and backend == "zapier" and config_value("zapierWebhookUrl"):
    connect_sources.append("https://hooks.zapier.com")
if backend_verified and backend == "supabase":
    supabase_url = config_value("supabaseUrl")
    if supabase_url:
        parsed_supabase_url = urlsplit(supabase_url)
        if parsed_supabase_url.scheme == "https" and parsed_supabase_url.netloc:
            connect_sources.append(f"{parsed_supabase_url.scheme}://{parsed_supabase_url.netloc}")
    if config_value("turnstileSiteKey"):
        connect_sources.append("https://challenges.cloudflare.com")
        script_sources.append("https://challenges.cloudflare.com")
        frame_sources.append("https://challenges.cloudflare.com")
CSP = (
    "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
    f"form-action 'self'; script-src {' '.join(script_sources)}; style-src 'self'; img-src 'self' data:; "
    f"font-src 'self'; media-src 'self'; connect-src {' '.join(connect_sources)}; frame-src {' '.join(frame_sources)}; manifest-src 'self'; worker-src 'self'"
)


class Handler(SimpleHTTPRequestHandler):
    server_version = "VRAELIX-Preview"
    sys_version = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def translate_path(self, path):
        request_path = urlsplit(path).path
        if SITE_BASE_PATH and (request_path == SITE_BASE_PATH or request_path.startswith(SITE_BASE_PATH + "/")):
            request_path = request_path[len(SITE_BASE_PATH):] or "/"
            path = request_path
        return super().translate_path(path)

    def end_headers(self):
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        super().end_headers()

    def do_POST(self):
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD")
        self.end_headers()

    def log_message(self, format, *args):
        return


port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
