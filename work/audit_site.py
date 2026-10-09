from __future__ import annotations

from collections import defaultdict, deque
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, unquote
import base64
import http.client
import argparse
import json
import re
import xml.etree.ElementTree as ET

ROOT = Path("outputs/vraelix-premium-site")
DATA = json.loads(Path("work/site_data.json").read_text(encoding="utf-8"))
EXPECTED = [row[0] for row in DATA["pages"]] + [f'/services/{row["slug"]}/' for row in DATA["services"]]
PUBLIC_INDEXABLE = [route for route in EXPECTED if route != "/thank-you/"]
ORIGIN = ""
errors: list[str] = []
notes: list[str] = []


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.title_parts = []
        self.title_depth = 0
        self.headings = []
        self.heading_stack = []
        self.anchors = []
        self.anchor_stack = []
        self.scripts = []
        self.script_type = ""
        self.script_parts = []
        self.body_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if tag == "title":
            self.title_depth += 1
        if re.fullmatch(r"h[1-6]", tag):
            self.heading_stack.append([tag, []])
        if tag == "a":
            self.anchor_stack.append([attrs, []])
        if tag == "script":
            self.script_type = attrs.get("type", "")
            self.script_parts = []

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "title" and self.title_depth:
            self.title_depth -= 1
        if re.fullmatch(r"h[1-6]", tag) and self.heading_stack:
            heading_tag, parts = self.heading_stack.pop()
            self.headings.append((int(heading_tag[1]), " ".join(" ".join(parts).split())))
        if tag == "a" and self.anchor_stack:
            attrs, parts = self.anchor_stack.pop()
            self.anchors.append((attrs, " ".join(" ".join(parts).split())))
        if tag == "script":
            if self.script_type == "application/ld+json":
                self.scripts.append("".join(self.script_parts))
            self.script_type = ""
            self.script_parts = []

    def handle_data(self, data):
        if self.title_depth:
            self.title_parts.append(data)
        for _, parts in self.heading_stack:
            parts.append(data)
        for _, parts in self.anchor_stack:
            parts.append(data)
        if self.script_type == "application/ld+json":
            self.script_parts.append(data)
        self.body_parts.append(data)

    @property
    def title(self):
        return " ".join(" ".join(self.title_parts).split())

    @property
    def text(self):
        return " ".join(" ".join(self.body_parts).split())


def page_file(route: str) -> Path:
    return ROOT / "index.html" if route == "/" else ROOT.joinpath(*route.strip("/").split("/")) / "index.html"


def meta_content(page: Page, name: str) -> str:
    return next((attrs.get("content", "") for tag, attrs in page.tags
                 if tag == "meta" and attrs.get("name", "").lower() == name.lower()), "")


def meta_property(page: Page, name: str) -> str:
    return next((attrs.get("content", "") for tag, attrs in page.tags
                 if tag == "meta" and attrs.get("property", "").lower() == name.lower()), "")


def config_value(config: str, name: str):
    match = re.search(r"^\s*" + re.escape(name) + r"\s*:\s*(\"(?:\\.|[^\"\\])*\")", config, re.MULTILINE)
    if not match:
        return ""
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return ""


def parse_headers_file() -> tuple[str, dict[str, str]]:
    path = ROOT / "_headers"
    if not path.is_file():
        errors.append("Missing static-host _headers security configuration")
        return "", {}
    section = ""
    headers = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if not line.startswith((" ", "\t")):
            section = line.strip()
        elif section:
            key, sep, value = line.strip().partition(":")
            if sep:
                headers[key.lower()] = value.strip()
    csp = headers.get("content-security-policy", "")
    required = {
        "strict-transport-security": "max-age=31536000",
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "strict-origin-when-cross-origin",
        "permissions-policy": "camera=()",
    }
    for name, value in required.items():
        if value not in headers.get(name, ""):
            errors.append(f"Security headers: {name} is missing or incorrect")
    for directive in ("default-src 'self'", "base-uri 'self'", "object-src 'none'", "frame-ancestors 'none'", "form-action 'self'", "script-src 'self'", "style-src 'self'", "frame-src 'self'"):
        if directive not in csp:
            errors.append(f"CSP is missing {directive}")
    config = (ROOT / "assets/site-config.js").read_text(encoding="utf-8") if (ROOT / "assets/site-config.js").is_file() else ""
    expected_connect = ["'self'"]
    if config_value(config, "zapierWebhookUrl"):
        expected_connect.append("https://hooks.zapier.com")
    backend = config_value(config, "enquiryBackend") or "zapier"
    site_key = config_value(config, "turnstileSiteKey")
    supabase_url = config_value(config, "supabaseUrl")
    measurement_id = config_value(config, "ga4MeasurementId")
    if backend == "supabase" and supabase_url:
        parsed_supabase = urlsplit(supabase_url)
        expected_connect.append(f"{parsed_supabase.scheme}://{parsed_supabase.netloc}")
    if backend == "supabase" and site_key:
        expected_connect.append("https://challenges.cloudflare.com")
    if measurement_id:
        expected_connect.extend(("https://www.googletagmanager.com", "https://*.google-analytics.com", "https://*.google.com"))
    connect_directive = re.search(r"(?:^|;\s*)connect-src\s+([^;]+)", csp)
    if not connect_directive or connect_directive.group(1).split() != expected_connect:
        errors.append("CSP connect-src does not match the selected enquiry backend")
    expected_script = "script-src 'self'" + (" https://challenges.cloudflare.com" if backend == "supabase" and site_key else "")
    if measurement_id:
        expected_script += " https://www.googletagmanager.com"
    expected_frame = "frame-src 'self'" + (" https://challenges.cloudflare.com" if backend == "supabase" and site_key else "")
    if expected_script not in csp or expected_frame not in csp:
        errors.append("CSP script-src/frame-src does not match the configured Turnstile widget")
    if measurement_id:
        image_directive = re.search(r"(?:^|;\s*)img-src\s+([^;]+)", csp)
        if not image_directive or not {"https://www.googletagmanager.com", "https://*.google-analytics.com"}.issubset(set(image_directive.group(1).split())):
            errors.append("CSP img-src does not allow the configured GA4 tag endpoints")
    if "unsafe-inline" in csp or "unsafe-eval" in csp:
        errors.append("CSP contains an unsafe inline/eval exception")
    if not csp:
        errors.append("Content-Security-Policy is empty")
    return csp, headers


def check_site_origin() -> None:
    global ORIGIN
    home = Page()
    home.feed((ROOT / "index.html").read_text(encoding="utf-8"))
    canonical = next((attrs.get("href", "") for tag, attrs in home.tags if tag == "link" and attrs.get("rel") == "canonical"), "")
    if canonical:
        parsed = urlsplit(canonical)
        if parsed.scheme == "https" and parsed.netloc and parsed.path == "/" and not parsed.query and not parsed.fragment:
            ORIGIN = f"{parsed.scheme}://{parsed.netloc}"
        else:
            errors.append("Homepage canonical must be the verified HTTPS root URL")
    if ORIGIN:
        parsed = urlsplit(ORIGIN)
        if parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
            errors.append("Configured site origin must be an HTTPS origin with no path, query or fragment")
    else:
        notes.append("PENDING PRODUCTION VERIFICATION: verified public domain is not configured; absolute canonicals, social image URLs, JSON-LD and sitemap are withheld until VRAELIX_SITE_ORIGIN is set at build time.")


def check_pages() -> tuple[dict[str, Page], dict[str, list[str]]]:
    pages = {}
    outbound = defaultdict(list)
    seen_titles = defaultdict(list)
    seen_descriptions = defaultdict(list)
    for route in EXPECTED:
        path = page_file(route)
        if not path.is_file():
            errors.append(f"Missing route file: {route}")
            continue
        html = path.read_text(encoding="utf-8")
        page = Page()
        page.feed(html)
        pages[route] = page
        attrs = [a for _, a in page.tags]
        title = page.title
        description = meta_content(page, "description")
        h1s = [text for level, text in page.headings if level == 1]
        if not html.lstrip().lower().startswith("<!doctype html>"):
            errors.append(f"{route}: missing HTML5 doctype")
        if not any(tag == "html" and a.get("lang") for tag, a in page.tags):
            errors.append(f"{route}: missing document language")
        if not title:
            errors.append(f"{route}: missing title")
        elif len(title) > 70:
            notes.append(f"{route}: title is {len(title)} characters; review display length")
        if not description:
            errors.append(f"{route}: missing meta description")
        elif len(description) < 50 or len(description) > 170:
            notes.append(f"{route}: meta description is {len(description)} characters; review search-result fit")
        if len(h1s) != 1:
            errors.append(f"{route}: expected one H1, found {len(h1s)}")
        elif not h1s[0].strip():
            errors.append(f"{route}: empty H1")
        last_level = 0
        for level, heading in page.headings:
            if not heading:
                errors.append(f"{route}: empty H{level}")
            if level > last_level + 1:
                errors.append(f"{route}: heading hierarchy skips from H{last_level} to H{level}")
            last_level = level
        if not any(tag == "meta" and a.get("name") == "viewport" for tag, a in page.tags):
            errors.append(f"{route}: missing mobile viewport declaration")
        if title:
            seen_titles[title].append(route)
        if description:
            seen_descriptions[description].append(route)

        canonical = next((a.get("href", "") for tag, a in page.tags if tag == "link" and a.get("rel") == "canonical"), "")
        if ORIGIN:
            expected_canonical = ORIGIN + route
            if canonical != expected_canonical:
                errors.append(f"{route}: canonical should be {expected_canonical}, got {canonical or '(missing)'}")
        elif canonical:
            errors.append(f"{route}: do not emit an unverified canonical before the public domain is configured")
        robots = meta_content(page, "robots").lower()
        if route == "/thank-you/" and "noindex" not in robots:
            errors.append("Thank-you route must be noindex")
        if route != "/thank-you/" and "noindex" in robots:
            errors.append(f"{route}: public content route unexpectedly marked noindex")
        if ORIGIN and (meta_property(page, "og:url") != ORIGIN + route or meta_property(page, "og:image") != ORIGIN + "/assets/hero-poster.png"):
            errors.append(f"{route}: Open Graph URLs should use the verified absolute origin")
        if not any(tag == "meta" and a.get("name") == "twitter:card" for tag, a in page.tags):
            errors.append(f"{route}: missing social card type")
        if ORIGIN and not meta_content(page, "twitter:image"):
            errors.append(f"{route}: missing absolute Twitter image URL")

        ids = {a.get("id") for _, a in page.tags if a.get("id")}
        if len(ids) != len([a.get("id") for _, a in page.tags if a.get("id")]):
            errors.append(f"{route}: duplicate HTML id")
        for tag, attrs in page.tags:
            if any(name.lower().startswith("on") for name in attrs):
                errors.append(f"{route}: inline event handler found on <{tag}>")
            if tag == "style" or "style" in attrs:
                errors.append(f"{route}: inline style found; keep the CSP free of unsafe-inline")
            if tag == "a":
                href = attrs.get("href", "").strip()
                if href.lower().startswith("javascript:"):
                    errors.append(f"{route}: javascript: URL found")
                if href == "#":
                    errors.append(f"{route}: dead # link")
                if href.startswith("#") and href[1:] not in ids:
                    errors.append(f"{route}: broken fragment {href}")
                if href.startswith("/") and not href.startswith("//"):
                    target = href.split("#", 1)[0].split("?", 1)[0] or "/"
                    if target.startswith("/assets/"):
                        target_path = ROOT / target.lstrip("/")
                        if not target_path.is_file():
                            errors.append(f"{route}: broken internal asset link {href}")
                    else:
                        target_route = target if target.endswith("/") else target + "/"
                        if target_route not in EXPECTED:
                            errors.append(f"{route}: internal link targets unknown route {href}")
                if href.startswith("https://") and attrs.get("target") == "_blank":
                    rel = set(attrs.get("rel", "").lower().split())
                    if not {"noopener", "noreferrer"}.issubset(rel):
                        errors.append(f"{route}: external new-tab link lacks noopener noreferrer")
                if href.startswith("/") and not href.startswith("//"):
                    outbound[route].append(href.split("#", 1)[0].split("?", 1)[0] or "/")
            if tag in ("img", "script", "link"):
                attr = "src" if attrs.get("src") else "href"
                value = attrs.get(attr, "")
                if value.startswith("/") and not value.startswith("//"):
                    asset = value.split("?", 1)[0]
                    if asset.startswith("/assets/") and not (ROOT / asset.lstrip("/")).is_file():
                        errors.append(f"{route}: missing asset {asset}")
            if tag == "img":
                if "alt" not in attrs:
                    errors.append(f"{route}: image missing alt attribute")
                if attrs.get("alt", "").strip() == "" and attrs.get("role") != "presentation" and attrs.get("aria-hidden") != "true":
                    errors.append(f"{route}: image needs descriptive alt text or explicit decorative semantics")
        for attrs, anchor_text in page.anchors:
            href = attrs.get("href", "")
            accessible_name = attrs.get("aria-label", "").strip() or anchor_text.strip()
            if href and not accessible_name:
                errors.append(f"{route}: link has no accessible name ({href})")
            if accessible_name.lower() in {"click here", "read more", "here"}:
                notes.append(f"{route}: vague link text {accessible_name!r}")

        faq_visible = any("faq-item" in a.get("class", "").split() for tag, a in page.tags)
        schema_nodes = []
        for raw in page.scripts:
            try:
                schema = json.loads(raw)
                schema_nodes.extend(schema.get("@graph", []))
            except (json.JSONDecodeError, AttributeError) as exc:
                errors.append(f"{route}: invalid structured data ({exc})")
        if ORIGIN:
            if route == "/thank-you/":
                if page.scripts:
                    errors.append("No structured data should be emitted for the noindex thank-you route")
            elif len(page.scripts) != 1:
                errors.append(f"{route}: expected one structured data graph, found {len(page.scripts)}")
            types = {node.get("@type") for node in schema_nodes}
            if route != "/thank-you/" and not {"Organization", "WebPage"}.issubset(types):
                errors.append(f"{route}: structured data lacks Organization or WebPage")
            if route == "/" and "WebSite" not in types:
                errors.append("Homepage structured data lacks WebSite")
            if route.startswith("/services/") and route != "/services/" and "Service" not in types:
                errors.append(f"{route}: service page lacks Service structured data")
            if (route == "/services/" or route.startswith("/services/") and route != "/services/" or route == "/insights/") and faq_visible != ("FAQPage" in types):
                errors.append(f"{route}: FAQPage structured data must exactly match visible FAQs")
            if route != "/" and route != "/thank-you/" and "BreadcrumbList" not in types:
                errors.append(f"{route}: breadcrumb structured data missing")
            serialized = json.dumps(schema_nodes)
            if "__ORIGIN__" in serialized or "__VRAELIX_DOMAIN__" in serialized:
                errors.append(f"{route}: structured data contains an unresolved placeholder")
            for node in schema_nodes:
                for key in ("url", "@id"):
                    value = node.get(key)
                    if isinstance(value, str) and value.startswith("http") and not value.startswith(ORIGIN):
                        errors.append(f"{route}: structured data {key} is outside the configured origin")
        elif page.scripts:
            errors.append(f"{route}: omit domain-dependent structured data until the production domain is configured")
        if "FAQPage" in {node.get("@type") for node in schema_nodes} and not faq_visible:
            errors.append(f"{route}: FAQPage has no visible FAQ content")
        if faq_visible:
            summaries = [a for tag, a in page.tags if tag == "summary"]
            if not summaries:
                errors.append(f"{route}: FAQ entries should be semantic disclosure controls")

    for value, routes in seen_titles.items():
        if len(routes) > 1:
            errors.append(f"Duplicate title {value!r}: {', '.join(routes)}")
    for value, routes in seen_descriptions.items():
        if len(routes) > 1:
            errors.append(f"Duplicate meta description: {', '.join(routes)}")

    reachable = {"/"}
    queue = deque(["/"])
    while queue:
        route = queue.popleft()
        for href in outbound.get(route, []):
            candidate = href if href.endswith("/") else href + "/"
            if candidate in EXPECTED and candidate not in reachable:
                reachable.add(candidate)
                queue.append(candidate)
    unreachable = [route for route in PUBLIC_INDEXABLE if route not in reachable]
    if unreachable:
        errors.append("Public pages not reachable through internal links: " + ", ".join(unreachable))
    return pages, outbound


def check_form_security(pages: dict[str, Page]) -> None:
    quote = pages.get("/request-a-quote/")
    if not quote:
        return
    forms = [attrs for tag, attrs in quote.tags if tag == "form"]
    if len(forms) != 1:
        errors.append("Enquiry page must contain exactly one form")
        return
    form = forms[0]
    if form.get("action") or form.get("method", "").lower() != "post" or "novalidate" not in form:
        errors.append("Enquiry form should intercept a POST in browser code and avoid native GET submission")
    fields = {attrs.get("name"): attrs for tag, attrs in quote.tags if tag in ("input", "textarea", "select")}
    for name, max_length in (("full_name", "100"), ("email", "254"), ("phone_number", "32"), ("company", "160"), ("project_description", "2400"), ("budget", "120"), ("timeline", "120")):
        if name not in fields or fields[name].get("maxlength") != max_length:
            errors.append(f"Enquiry form field {name!r} needs client-side length bounds")
    for name in ("full_name", "email", "phone_number", "service", "project_description", "contact_method"):
        if name not in fields or "required" not in fields[name]:
            errors.append(f"Enquiry form field {name!r} must remain required")
    if fields.get("phone_number", {}).get("type") != "tel":
        errors.append("Phone number must be a separate telephone field")
    if fields.get("source", {}).get("type") != "hidden" or fields.get("source", {}).get("value") != "VRAELIX Website":
        errors.append("Enquiry form must include the hidden website source value")
    if fields.get("submitted_at", {}).get("type") != "hidden":
        errors.append("Enquiry form must include a hidden submission timestamp field")
    raw_html = page_file("/request-a-quote/").read_text(encoding="utf-8")
    for option in ("<option>Other</option>", 'value="WhatsApp"', 'value="Instagram / Social"'):
        if option not in raw_html:
            errors.append(f"Enquiry form is missing the expected option {option!r}")
    js = (ROOT / "assets/site.js").read_text(encoding="utf-8")
    zapier_adapter = (ROOT / "assets/zapier-adapter.js").read_text(encoding="utf-8")
    supabase_adapter = (ROOT / "assets/supabase-adapter.js").read_text(encoding="utf-8")
    dispatcher = (ROOT / "assets/enquiry-adapter.js").read_text(encoding="utf-8")
    for expected in ("window.VRAELIX_ENQUIRY.submitEnquiry(payload", "source: \"VRAELIX Website\"", "new Date().toISOString()", "vraelix-project-brief-confirmed", "window.location.assign(sitePath(\"/thank-you/\"))"):
        if expected not in js:
            errors.append(f"Enquiry form integration is missing {expected!r}")
    for expected in ("fetch(hookUrl", "body: JSON.stringify(payload)", "mode: \"cors\"", "credentials: \"omit\""):
        if expected not in zapier_adapter:
            errors.append(f"Zapier adapter is missing {expected!r}")
    if re.search(r"content-type", zapier_adapter, re.I):
        errors.append("Zapier browser request must not add a custom Content-Type header")
    for expected in ("/functions/v1/submit-enquiry", "turnstile_token", "result.success !== true"):
        if expected not in supabase_adapter:
            errors.append(f"Supabase browser adapter is missing {expected!r}")
    if "function submitEnquiry" not in dispatcher:
        errors.append("A modular submitEnquiry(payload) dispatcher is missing")
    for adapter in ("zapier-adapter.js", "supabase-adapter.js", "enquiry-adapter.js"):
        if f'/assets/{adapter}' not in raw_html:
            errors.append(f"Generated quote route does not load {adapter}")
    payload_start = js.find("const payload = {")
    payload_end = js.find("\n      };", payload_start)
    payload_code = js[payload_start:payload_end] if payload_start >= 0 and payload_end > payload_start else ""
    for key in ("full_name", "email", "phone_number", "company", "service", "project_description", "budget", "timeline", "contact_method", "source", "submitted_at"):
        if f"{key}:" not in payload_code:
            errors.append(f"Zapier payload is missing the separate {key!r} field")
    if "VRAELIX_ZAPIER_WEBHOOK_URL" not in Path("work/build_site.py").read_text(encoding="utf-8"):
        errors.append("Zapier URL should come from the isolated build-time environment configuration")
    config = (ROOT / "assets/site-config.js").read_text(encoding="utf-8")
    measurement_id = config_value(config, "ga4MeasurementId")
    if "zapierWebhookUrl: \"\"" not in config and "zapierWebhookUrl: \"https://hooks.zapier.com/" not in config:
        errors.append("Generated configuration should contain either an empty Zapier placeholder or a Catch Hook URL")
    submit = next((attrs for tag, attrs in quote.tags if tag == "button" and attrs.get("type") == "submit"), {})
    if "disabled" not in submit:
        errors.append("Enquiry submit button must stay disabled until browser code configures the Catch Hook")
    if "dd.textContent = brief" not in js or "brief.full_name" not in js:
        errors.append("Stored enquiry content must be inserted as text, not executable markup")
    response_index = js.find("receipt.success !== true")
    storage_index = js.find('sessionStorage.setItem("vraelix-project-brief"')
    if response_index < 0 or storage_index < response_index:
        errors.append("Enquiry details must only enter the confirmation flow after a confirmed adapter success")
    if 'form.dataset.submitting = "true"' not in js or 'form.dataset.submitting === "true"' not in js:
        errors.append("Enquiry form lacks a duplicate-submit guard")
    if "response.ok" not in zapier_adapter or "response.ok" not in supabase_adapter or "form.dataset.submitting = \"false\"" not in js:
        errors.append("Enquiry adapters must distinguish failed responses and the form must allow retry")
    if "Something went wrong while sending your enquiry" not in js:
        errors.append("Enquiry form must show a generic failure message without technical details")
    if measurement_id:
        for expected in ("data-vraelix-ga4", "__vraelixGa4Initialized", "data-consent-analytics", "analytics_storage: \"denied\"", "applyAnalytics(choice.analytics)"):
            if expected not in js:
                errors.append(f"GA4 consent gate is missing {expected!r}")
        if js.count("window.gtag(\"config\", measurementId") != 1:
            errors.append("GA4 must initialize at most once from the consent-controlled site script")
    elif 'analyticsScript.src = "https://www.googletagmanager.com/gtag/js?id="' not in js:
        errors.append("GA4 loader should remain dynamic and consent-controlled")


def check_secrets_and_surface() -> None:
    secret_patterns = [
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        re.compile(r"\bsk-[A-Za-z0-9]{24,}\b"),
        re.compile(r"\bsb_secret_[A-Za-z0-9_-]{10,}"),
        re.compile(r"(?i)(?:api[_-]?key|client[_-]?secret|database[_-]?url|password)\s*[:=]\s*[\"'][^\"']{8,}[\"']"),
    ]
    readable_exts = {".html", ".js", ".css", ".json", ".txt", ".xml", ".map", ".yml", ".yaml", ".toml", ".conf"}
    exposed = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix == ".map":
            errors.append(f"Production build includes source map: {path.relative_to(ROOT)}")
        if path.suffix.lower() in readable_exts and path.stat().st_size <= 5_000_000:
            content = path.read_text(encoding="utf-8", errors="replace")
            if any(pattern.search(content) for pattern in secret_patterns):
                exposed.append(str(path.relative_to(ROOT)))
    if exposed:
        errors.append("Possible secret material in public output: " + ", ".join(exposed))
    config = (ROOT / "assets/site-config.js").read_text(encoding="utf-8")
    public_key = config_value(config, "supabasePublishableKey")
    if public_key.startswith("sb_secret_"):
        errors.append("Generated public configuration contains a Supabase secret key")
    jwt_parts = public_key.split(".")
    if len(jwt_parts) == 3:
        try:
            claims = json.loads(base64.urlsafe_b64decode(jwt_parts[1] + "=" * (-len(jwt_parts[1]) % 4)))
            if claims.get("role") == "service_role":
                errors.append("Generated public configuration contains a service-role JWT")
        except (ValueError, UnicodeError, json.JSONDecodeError):
            pass
    if any(path.name == ".env" or path.name.startswith(".env.") for path in ROOT.rglob("*")):
        errors.append("Public output contains an environment file")
    routes = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()}
    if any(re.search(r"(^|/)(admin|debug|internal|private)(/|\.|$)", name, re.I) for name in routes):
        errors.append("Public output contains a likely admin/debug/private route")
    browser_sources = [
        (ROOT / "assets/site.js").read_text(encoding="utf-8"),
        (ROOT / "assets/zapier-adapter.js").read_text(encoding="utf-8"),
        (ROOT / "assets/supabase-adapter.js").read_text(encoding="utf-8"),
        (ROOT / "assets/enquiry-adapter.js").read_text(encoding="utf-8"),
    ]
    unexpected_clients = any(any(term in js for term in ("XMLHttpRequest", "WebSocket(", "EventSource(")) for js in browser_sources)
    if (unexpected_clients or browser_sources[0].count("fetch(") != 0 or
            browser_sources[1].count("fetch(") != 1 or browser_sources[2].count("fetch(") != 1 or
            "fetch(hookUrl" not in browser_sources[1] or "/functions/v1/submit-enquiry" not in browser_sources[2]):
        errors.append("Public JavaScript network access does not match the selected enquiry adapters")
    dev = Path("work/dev_server.py").read_text(encoding="utf-8")
    if '("127.0.0.1", port)' not in dev or '"/save"' in dev or "DESTINATION.write_bytes" in dev:
        errors.append("Development server must be loopback-only and must not expose the former /save write endpoint")
    if 'directory=str(ROOT)' not in dev or '"outputs" / "vraelix-premium-site"' not in dev:
        errors.append("Development server must expose only the generated website, not the repository/work folder")
    manifests = list(ROOT.rglob("package.json")) + list(ROOT.rglob("package-lock.json")) + list(ROOT.rglob("requirements.txt"))
    if manifests:
        notes.append("Dependency manifests exist; run the platform vulnerability checker before release: " + ", ".join(str(p) for p in manifests))
    else:
        notes.append("No runtime package/dependency manifest exists in the deployable site; dependency audit is not applicable to this static output.")


def check_indexing() -> None:
    redirect_file = ROOT / "_redirects"
    if not redirect_file.is_file():
        errors.append("Missing route-normalization redirect configuration")
    else:
        rules = [line.split() for line in redirect_file.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
        expected_rules = {(route[:-1], route, "301") for route in EXPECTED if route != "/"}
        parsed_rules = {tuple(rule) for rule in rules if len(rule) == 3}
        if parsed_rules != expected_rules or len(rules) != len(expected_rules):
            errors.append("Redirect rules must normalize each known no-slash route to its trailing-slash URL")

    robots_path = ROOT / "robots.txt"
    if not robots_path.is_file():
        errors.append("Missing robots.txt")
    else:
        robots = robots_path.read_text(encoding="utf-8")
        if "User-agent: *" not in robots or "Allow: /" not in robots:
            errors.append("robots.txt must permit crawl of the public site")
        if "__VRAELIX_DOMAIN__" in robots:
            errors.append("robots.txt contains a placeholder domain")
        sitemap_line = next((line.split(":", 1)[1].strip() for line in robots.splitlines() if line.lower().startswith("sitemap:")), "")
        if ORIGIN:
            if sitemap_line != ORIGIN + "/sitemap.xml":
                errors.append("robots.txt sitemap URL does not match the verified public origin")
        elif sitemap_line:
            errors.append("robots.txt must not point to a guessed sitemap URL before the public domain is configured")

    sitemap = ROOT / "sitemap.xml"
    if ORIGIN:
        if not sitemap.is_file():
            errors.append("Configured public origin requires an absolute sitemap.xml")
        else:
            try:
                tree = ET.parse(sitemap)
                urls = [element.text or "" for element in tree.getroot().iter() if element.tag.endswith("}loc")]
                expected = [ORIGIN + route for route in PUBLIC_INDEXABLE]
                if set(urls) != set(expected):
                    errors.append("Sitemap URLs must exactly match public indexable routes and exclude the thank-you page")
                if any(not url.startswith(ORIGIN + "/") for url in urls):
                    errors.append("Sitemap contains a URL outside the verified origin")
                if len(urls) != len(set(urls)):
                    errors.append("Sitemap contains duplicate URLs")
            except ET.ParseError as exc:
                errors.append(f"Invalid sitemap XML: {exc}")
    elif sitemap.exists():
        errors.append("Do not ship an absolute sitemap with an unverified or placeholder domain")


def check_content_and_entity(pages: dict[str, Page]) -> None:
    home = pages.get("/")
    about = pages.get("/about/")
    services = pages.get("/services/")
    if home and not all(term in home.text.lower() for term in ("digital", "business", "technology")):
        errors.append("Homepage should plainly communicate the digital/business/technology focus")
    if about and not all(term in about.text.lower() for term in ("vraelix", "business", "website development")):
        errors.append("About page is missing company identity, audience context or current core service")
    if services and "website development" not in services.text.lower():
        errors.append("Services overview should identify website development as a current core service")
    for service in DATA["services"]:
        route = f'/services/{service["slug"]}/'
        page = pages.get(route)
        if page and not all(term in page.text.lower() for term in ("who it helps", "problem it can solve", "what the work may include")):
            errors.append(f"{route}: explain audience, problem and scope in natural language")
        related = service.get("related", [])
        service_slugs = {item["slug"] for item in DATA["services"]}
        if len(related) < 2 or len(related) > 4 or service["slug"] in related or any(slug not in service_slugs for slug in related):
            errors.append(f"{route}: related services must be a short, valid, non-self-referential list")
        if page:
            raw = page_file(route).read_text(encoding="utf-8")
            block = re.search(r'<div class="related-links">(.*?)</div>', raw, re.S)
            found = set(re.findall(r'href="/services/([^/]+)/"', block.group(1))) if block else set()
            if found != set(related):
                errors.append(f"{route}: related-services links do not match the service relationships in site data")
    for route, page in pages.items():
        if re.search(r"\b\d+(?:\.\d+)?\s*%|\b\d+\+\s*(?:clients|years|projects|awards)\b", page.text, re.I):
            notes.append(f"{route}: verify numerical authority/achievement claims against evidence")
    about = pages.get("/about/")
    if about and not all(term in about.text.lower() for term in ("ansh kumar", "founder & ceo", "vraelix")):
        errors.append("About page must identify Ansh Kumar as Founder & CEO of VRAELIX")
    notes.append("Entity claim review: company name, named founder and role, services, contact email and provided social URLs are consistent in the built pages; no address, clients, awards or performance statistics are asserted.")
    notes.append("AEO/content review: visible FAQs are genuine service/planning questions with direct answers; schema is emitted only when the verified origin is configured. No FAQPage markup is generated for pages without visible FAQ content.")


def check_performance() -> None:
    css = (ROOT / "assets/site.css").read_text(encoding="utf-8")
    js = (ROOT / "assets/site.js").read_text(encoding="utf-8")
    if "@media" not in css or "prefers-reduced-motion" not in css:
        errors.append("Responsive or reduced-motion rules are missing")
    if "@import" in css.lower():
        errors.append("CSS uses @import and may delay rendering")
    video = (ROOT / "index.html").read_text(encoding="utf-8")
    page = Page()
    page.feed(video)
    video_tag = next((attrs for tag, attrs in page.tags if tag == "video"), {})
    for attr in ("autoplay", "muted", "loop", "playsinline", "poster"):
        if attr not in video_tag:
            errors.append(f"Hero video missing {attr}")
    if video_tag.get("preload") not in ("none", "metadata"):
        errors.append("Hero video should not block initial loading with eager preload")
    if not (ROOT / "assets/hero-poster.webp").is_file():
        errors.append("Hero poster fallback is missing")
    for name in ("vraelix-cinematic.mp4", "vraelix-cinematic-mobile.webm"):
        asset = ROOT / "assets" / name
        if not asset.is_file():
            errors.append(f"Missing responsive Hero video source {name}")
    if "data-responsive-video-fallback" not in video or "video/mp4" not in js or "video/webm" not in js:
        errors.append("Hero video should choose a responsive source with a correctly typed compatible fallback")
    if "prefers-reduced-motion: reduce" not in js or "video.pause()" not in js:
        errors.append("Hero video should pause when reduced motion is requested")
    for path in (ROOT / "assets").glob("founder-*"):
        if path.suffix.lower() in {".webp", ".jpg", ".jpeg", ".png"} and path.stat().st_size > 750_000:
            notes.append(f"Founder image exceeds 750 KB: {path.name}")
    largest = sorted(((path.stat().st_size, path.name) for pattern in ("*.webm", "*.mp4") for path in (ROOT / "assets").glob(pattern)), reverse=True)
    if largest:
        notes.append("Self-hosted Hero video sizes: " + ", ".join(f"{name} {size / 1_000_000:.2f} MB" for size, name in largest))
    all_html = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.rglob("*.html"))
    non_executable_jsonld_removed = re.sub(r"<script\b(?=[^>]*type=[\"']application/ld\+json[\"'])[^>]*>.*?</script>", "", all_html, flags=re.I | re.S)
    if re.search(r"<script\b[^>]*>\s*[^<\s]", non_executable_jsonld_removed, re.I):
        errors.append("Inline executable script found; CSP should remain strict")


def check_local_http(base_url: str) -> None:
    base = base_url.rstrip("/")
    headers_seen = set()
    origin = urlsplit(base)
    connection_type = http.client.HTTPSConnection if origin.scheme == "https" else http.client.HTTPConnection

    def request(path: str, method: str = "GET"):
        target = urlsplit(urljoin(base + "/", path.lstrip("/")))
        connection = connection_type(target.hostname, target.port, timeout=5)
        try:
            connection.request(method, target.path or "/", headers={"Connection": "close"})
            response = connection.getresponse()
            return response.status, response.headers, response.read(2_000_000)
        except OSError as exc:
            errors.append(f"HTTP crawl failed for {path}: {exc}")
            return 0, {}, b""
        finally:
            connection.close()

    for route in EXPECTED:
        status, headers, body = request(route)
        if status != 200:
            errors.append(f"HTTP route {route} returned {status}, expected 200")
        for name in ("Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Permissions-Policy"):
            if name.lower() not in {key.lower() for key in headers.keys()}:
                errors.append(f"HTTP route {route} did not emit {name}")
        headers_seen.update(key.lower() for key in headers.keys())
        if b"<title>" not in body.lower():
            errors.append(f"HTTP route {route} did not return an HTML document")
    for asset in ("/assets/site.css", "/assets/site.js", "/assets/hero-poster.webp"):
        status, _, _ = request(asset)
        if status != 200:
            errors.append(f"HTTP asset {asset} returned {status}")
    if ORIGIN:
        status, _, _ = request("/sitemap.xml")
        if status != 200:
            errors.append("HTTP sitemap.xml is not served")
    else:
        status, _, _ = request("/sitemap.xml")
        if status != 404:
            errors.append("Unconfigured build should not serve a guessed sitemap URL")
    for path in ("/not-a-real-route/", "/work/site_data.json", "/assets/site.js.map", "/%2e%2e/work/site_data.json"):
        status, _, _ = request(path)
        if status != 404:
            errors.append(f"HTTP path {path} should not expose a route or repository file (got {status})")
    status, headers, _ = request("/", "POST")
    if status != 405 or headers.get("Allow") != "GET, HEAD":
        errors.append("HTTP POST should be rejected without a write/form API")
    notes.append("Local HTTP crawl checked all routes, headers, static assets, an unknown route, repository-path probes and rejection of POST. HSTS is intentionally not asserted over local HTTP.")


def main():
    parser = argparse.ArgumentParser(description="Audit the generated VRAELIX static site.")
    parser.add_argument("--base-url", help="Optional running preview URL for HTTP status and header verification")
    args = parser.parse_args()
    check_site_origin()
    parse_headers_file()
    pages, _ = check_pages()
    check_form_security(pages)
    check_secrets_and_surface()
    check_indexing()
    check_content_and_entity(pages)
    check_performance()
    if args.base_url:
        check_local_http(args.base_url)
    else:
        notes.append("PENDING PRODUCTION VERIFICATION: production status codes, HTTPS redirect behavior, emitted security headers, crawl directives and external link availability cannot be checked until the public host/domain is available.")
        notes.append("Trailing-slash redirect rules are present for static hosts that support _redirects; production redirect responses and apex/www/HTTP-to-HTTPS behavior still need host verification.")
    print(f"Audited {len(pages)} of {len(EXPECTED)} routes.")
    print(f"Errors: {len(errors)}")
    for item in errors:
        print("ERROR", item)
    print(f"Notes / pending: {len(notes)}")
    for item in notes:
        print("NOTE", item)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
