from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent / "outputs" / "vraelix-premium-site"
try:
    config_text = (ROOT / "assets/site-config.js").read_text(encoding="utf-8")
except OSError:
    config_text = ""
zapier_connect = " https://hooks.zapier.com" if 'zapierWebhookUrl: "https://hooks.zapier.com/' in config_text else ""
CSP = (
    "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
    "form-action 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    f"font-src 'self'; media-src 'self'; connect-src 'self'{zapier_connect}; manifest-src 'self'; worker-src 'self'"
)


class Handler(SimpleHTTPRequestHandler):
    server_version = "VRAELIX-Preview"
    sys_version = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

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
