from pathlib import Path
from html import escape
import base64
import hashlib
import json
import os
import re
import shutil
from urllib.parse import urlsplit

DEFAULT_ROOT = Path("outputs/vraelix-premium-site")
STAGING_PREVIEW_ROOT = Path("outputs/vraelix-staging-preview")
ROOT = Path(os.environ.get("VRAELIX_BUILD_OUTPUT", str(DEFAULT_ROOT)))
WORKSPACE = Path.cwd().resolve()
if ROOT.is_absolute():
    ROOT = ROOT.resolve()
else:
    ROOT = (WORKSPACE / ROOT).resolve()
if ROOT == WORKSPACE or WORKSPACE not in ROOT.parents:
    raise ValueError("VRAELIX_BUILD_OUTPUT must stay inside the project workspace")
IS_DEFAULT_OUTPUT = ROOT == (WORKSPACE / DEFAULT_ROOT).resolve()
IS_STAGING_PREVIEW = ROOT == (WORKSPACE / STAGING_PREVIEW_ROOT).resolve()
DATA = json.loads(Path("work/site_data.json").read_text(encoding="utf-8"))
SERVICES = DATA["services"]
EMAIL = "vraelix29@gmail.com"
INSTAGRAM = "https://www.instagram.com/mrofficial_ansh"
LINKEDIN = "https://www.linkedin.com/company/vraelix"

LOCAL_BUILD_ENV = Path(".env.staging.local" if IS_STAGING_PREVIEW else ".env.local")
BUILD_ENV_KEYS = {
    "VRAELIX_SITE_ORIGIN",
    "VRAELIX_GH_PAGES_BASE_PATH",
    "VRAELIX_GA4_MEASUREMENT_ID",
    "VRAELIX_ZAPIER_WEBHOOK_URL",
    "VRAELIX_SUPABASE_URL",
    "VRAELIX_SUPABASE_PUBLISHABLE_KEY",
    "VRAELIX_ENQUIRY_BACKEND",
    "VRAELIX_TURNSTILE_SITE_KEY",
    "VRAELIX_STAGING_FORM_TEST_MODE",
    "VRAELIX_INDEXING_APPROVED",
}


def load_local_build_env():
    """Load only documented build settings without printing their values."""
    if not LOCAL_BUILD_ENV.is_file():
        return
    for raw_line in LOCAL_BUILD_ENV.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name not in BUILD_ENV_KEYS:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if value:
            os.environ.setdefault(name, value)


load_local_build_env()

INDEXING_APPROVAL_VALUE = os.environ.get("VRAELIX_INDEXING_APPROVED", "").strip().lower()
if INDEXING_APPROVAL_VALUE not in ("", "true", "false"):
    raise ValueError("VRAELIX_INDEXING_APPROVED must be true or false")
INDEXING_APPROVED = INDEXING_APPROVAL_VALUE == "true" and not IS_STAGING_PREVIEW

STAGING_FORM_TEST_MODE_VALUE = os.environ.get("VRAELIX_STAGING_FORM_TEST_MODE", "").strip().lower()
if STAGING_FORM_TEST_MODE_VALUE not in ("", "true", "false"):
    raise ValueError("VRAELIX_STAGING_FORM_TEST_MODE must be true or false")
STAGING_FORM_TEST_MODE_REQUESTED = STAGING_FORM_TEST_MODE_VALUE == "true"
if STAGING_FORM_TEST_MODE_REQUESTED and not IS_STAGING_PREVIEW:
    raise ValueError("Staging form test mode is limited to outputs/vraelix-staging-preview")


def previous_generated_config_value(name):
    """Read a value from the current generated config as a local build fallback."""
    path = DEFAULT_ROOT / "assets/site-config.js"
    if not path.is_file():
        return ""
    try:
        source = path.read_text(encoding="utf-8")
        match = re.search(r"^\s*" + re.escape(name) + r"\s*:\s*(\"(?:\\.|[^\"\\])*\")", source, re.MULTILINE)
        return json.loads(match.group(1)) if match else ""
    except (OSError, ValueError, json.JSONDecodeError):
        return ""


def configured_supabase_public_settings():
    project_url = os.environ.get("VRAELIX_SUPABASE_URL", "").strip().rstrip("/")
    publishable_key = os.environ.get("VRAELIX_SUPABASE_PUBLISHABLE_KEY", "").strip()
    if bool(project_url) != bool(publishable_key):
        raise ValueError("Set both VRAELIX_SUPABASE_URL and VRAELIX_SUPABASE_PUBLISHABLE_KEY, or leave both empty")
    if not project_url:
        return "", ""

    parsed = urlsplit(project_url)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment
            or parsed.username or parsed.password):
        raise ValueError("VRAELIX_SUPABASE_URL must be an HTTPS project origin without a path or credentials")

    is_privileged = publishable_key.startswith("sb_secret_")
    parts = publishable_key.split(".")
    if len(parts) == 3:
        try:
            payload = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
            is_privileged = is_privileged or claims.get("role") == "service_role"
        except (ValueError, UnicodeError, json.JSONDecodeError):
            pass
    if is_privileged:
        raise ValueError("VRAELIX_SUPABASE_PUBLISHABLE_KEY must not contain a secret or service-role key")
    return project_url, publishable_key

def configured_site_origin():
    value = os.environ.get("VRAELIX_SITE_ORIGIN", "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment
            or parsed.username or parsed.password):
        raise ValueError("VRAELIX_SITE_ORIGIN must be a verified HTTPS origin with no path, query or credentials")
    return value


def configured_site_base_path():
    value = os.environ.get("VRAELIX_GH_PAGES_BASE_PATH", "").strip()
    if value in ("", "/"):
        return ""
    if (not value.startswith("/") or value.endswith("/") or "//" in value
            or any(part in ("", ".", "..") for part in value[1:].split("/"))
            or not re.fullmatch(r"/[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*", value)):
        raise ValueError("VRAELIX_GH_PAGES_BASE_PATH must be empty or a slash-prefixed URL path without a trailing slash")
    return value


def configured_ga4_measurement_id():
    value = os.environ.get("VRAELIX_GA4_MEASUREMENT_ID", "").strip().upper()
    if value and not re.fullmatch(r"G-[A-Z0-9]{5,20}", value):
        raise ValueError("VRAELIX_GA4_MEASUREMENT_ID must be a GA4 Measurement ID such as G-XXXXXXXXXX")
    return value


def configured_enquiry_backend():
    backend = os.environ.get("VRAELIX_ENQUIRY_BACKEND", "supabase").strip().lower() or "supabase"
    if backend not in {"zapier", "supabase"}:
        raise ValueError("VRAELIX_ENQUIRY_BACKEND must be either zapier or supabase")
    site_key = os.environ.get("VRAELIX_TURNSTILE_SITE_KEY", "").strip()
    if site_key and not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", site_key):
        raise ValueError("VRAELIX_TURNSTILE_SITE_KEY has an invalid format")
    if backend == "supabase" and (not SUPABASE_PROJECT_URL or not SUPABASE_PUBLISHABLE_KEY):
        raise ValueError("Supabase mode requires VRAELIX_SUPABASE_URL and VRAELIX_SUPABASE_PUBLISHABLE_KEY")
    if backend == "supabase" and (ENQUIRY_BACKEND_VERIFIED or STAGING_FORM_TEST_MODE_REQUESTED) and not site_key:
        raise ValueError("A verified Supabase form requires VRAELIX_TURNSTILE_SITE_KEY")
    return backend, site_key

SITE_ORIGIN = configured_site_origin()
SITE_BASE_PATH = configured_site_base_path()
GA4_MEASUREMENT_ID = configured_ga4_measurement_id()
# Keep the visitor form closed until a backend has passed an approved
# end-to-end verification. Re-enable only through a reviewed source change.
ENQUIRY_BACKEND_VERIFIED = False


def site_url(path):
    if not SITE_ORIGIN:
        return ""
    normalized_path = path if path.startswith("/") else "/" + path
    return SITE_ORIGIN + SITE_BASE_PATH + normalized_path


def site_path(path):
    normalized_path = path if path.startswith("/") else "/" + path
    return SITE_BASE_PATH + normalized_path


def configured_zapier_webhook():
    if "VRAELIX_ZAPIER_WEBHOOK_URL" in os.environ:
        value = os.environ.get("VRAELIX_ZAPIER_WEBHOOK_URL", "").strip()
    else:
        value = previous_generated_config_value("zapierWebhookUrl").strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        parts = parsed.path.strip("/").split("/")
        valid_path = (
            len(parts) == 4
            and parts[:2] == ["hooks", "catch"]
            and all(part and all(char.isalnum() or char in "-_" for char in part) for part in parts[2:])
        )
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() != "hooks.zapier.com"
            or parsed.query
            or parsed.fragment
            or not valid_path
        ):
            raise ValueError
    except ValueError as exc:
        raise ValueError(
            "VRAELIX_ZAPIER_WEBHOOK_URL must be an HTTPS Zapier Catch Hook URL "
            "on hooks.zapier.com, without query parameters or fragments"
        ) from exc
    return value


SUPABASE_PROJECT_URL, SUPABASE_PUBLISHABLE_KEY = configured_supabase_public_settings()
ENQUIRY_BACKEND, TURNSTILE_SITE_KEY = configured_enquiry_backend()
STAGING_PROJECT_REF = "fqgrdfxboskdyqaipabr"


def configured_staging_form_test_mode():
    if not STAGING_FORM_TEST_MODE_REQUESTED:
        return False
    parsed = urlsplit(SUPABASE_PROJECT_URL)
    if (
        not IS_STAGING_PREVIEW
        or ENQUIRY_BACKEND != "supabase"
        or parsed.scheme != "https"
        or parsed.hostname != f"{STAGING_PROJECT_REF}.supabase.co"
        or not SUPABASE_PUBLISHABLE_KEY
        or not TURNSTILE_SITE_KEY
        or SITE_ORIGIN
    ):
        raise ValueError(
            "Staging form test mode requires the separate staging output, the approved staging Supabase project, "
            "public staging keys, and no production site origin"
        )
    return True


STAGING_FORM_TEST_MODE = configured_staging_form_test_mode()
ZAPIER_WEBHOOK_URL = configured_zapier_webhook() if ENQUIRY_BACKEND_VERIFIED and ENQUIRY_BACKEND == "zapier" else ""

def esc(value):
    return escape(str(value), quote=True)

def service_path(service):
    return f"/services/{service['slug']}/"

def service_links(limit=None, services=None):
    selected = services if services is not None else (SERVICES if limit is None else SERVICES[:limit])
    return "".join(f'<a href="{service_path(s)}">{esc(s["name"])}<span aria-hidden="true">↗</span></a>' for s in selected)

def service_cards():
    return "".join(
        f'<a class="service-card service-card-large" href="{service_path(s)}">'
        f'<span class="card-index">0{i+1}</span><span class="card-arrow" aria-hidden="true">↗</span>'
        f'<h2>{esc(s["name"])}</h2><p>{esc(s["summary"])}</p>'
        '<span class="card-link">Explore service <span aria-hidden="true">→</span></span></a>'
        for i, s in enumerate(SERVICES)
    )

def faq_html(items, title="Common questions"):
    if not items:
        return ""
    rows = "".join(
        f'<details class="faq-item"><summary>{esc(q)}<span class="faq-plus" aria-hidden="true">+</span></summary><p>{esc(a)}</p></details>'
        for q, a in items
    )
    return f'<section class="section faq-section" aria-labelledby="faq-title"><div class="wrap faq-layout"><div class="section-intro"><p class="eyebrow">Clear answers</p><h2 id="faq-title">{esc(title)}</h2><p>Useful context to help you decide what makes sense for your business.</p></div><div class="faq-list">{rows}</div></div></section>'

def header(active):
    nav = [("/", "Home"), ("/about/", "About"), ("/services/", "Services"), ("/process/", "Process"), ("/insights/", "Insights"), ("/contact/", "Contact")]
    links = "".join(f'<a href="{url}"'+(' aria-current="page"' if active == url else '')+f'>{name}</a>' for url, name in nav)
    return f'''<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header" data-site-header><div class="header-inner wrap">
<a class="brand" href="/" aria-label="VRAELIX home"><picture class="brand-picture brand-light"><source type="image/webp" srcset="/assets/brand/vraelix-logo-white.webp"><img src="/assets/brand/vraelix-logo-white.png" alt="VRAELIX" width="1490" height="613" fetchpriority="high" decoding="async"></picture><picture class="brand-picture brand-dark"><source type="image/webp" srcset="/assets/brand/vraelix-logo.webp"><img src="/assets/brand/vraelix-logo.png" alt="VRAELIX" width="1490" height="613" fetchpriority="high" decoding="async"></picture></a>
<button class="menu-toggle" type="button" aria-expanded="false" aria-controls="primary-nav" aria-label="Open navigation" data-menu-toggle><span></span><span></span></button>
<nav class="primary-nav" id="primary-nav" aria-label="Main navigation" data-primary-nav>{links}<a class="nav-cta" href="/request-a-quote/">Start a project <span aria-hidden="true">↗</span></a></nav>
</div></header>'''

def footer():
    return '''<footer class="site-footer"><div class="wrap footer-top">
<div class="footer-brand-col"><a class="brand footer-brand" href="/" aria-label="VRAELIX home"><picture class="brand-picture"><source type="image/webp" srcset="/assets/brand/vraelix-logo-white.webp"><img src="/assets/brand/vraelix-logo-white.png" alt="VRAELIX" width="1490" height="613" loading="lazy" decoding="async"></picture></a><p>Thoughtful digital experiences, business systems and technology solutions around real business needs.</p><div class="footer-social" data-social-links aria-label="Social links"></div></div>
<div class="footer-column"><h2>Company</h2><a href="/about/">About</a><a href="/process/">Process</a><a href="/insights/">Insights</a><a href="/contact/">Contact</a></div>
<div class="footer-column"><h2>Services</h2><a href="/services/website-development/">Website development</a><a href="/services/business-websites/">Business websites</a><a href="/services/ecommerce/">E-commerce</a><a href="/services/seo-performance/">SEO &amp; performance</a><a href="/services/automation/">Business automation</a><a href="/services/">All services</a></div>
<div class="footer-column"><h2>Resources</h2><a href="/request-a-quote/">Request a quote</a><a href="/insights/">Guides &amp; notes</a><h2 class="footer-legal-title">Legal</h2><a href="/privacy/">Privacy</a><a href="/terms/">Terms</a><a href="/cookie-policy/">Cookie policy</a><a href="/disclaimer/">Disclaimer</a></div>
</div><div class="wrap footer-bottom"><span>© <span data-year>2026</span> VRAELIX. All rights reserved.</span><div class="footer-bottom-actions"><button class="footer-settings" type="button" data-consent-open>Privacy &amp; cookie settings</button><a href="/request-a-quote/">Start a project <span aria-hidden="true">↗</span></a></div></div></footer>'''

def consent_panel():
    analytics_enabled = bool(GA4_MEASUREMENT_ID)
    if ZAPIER_WEBHOOK_URL:
        summary = "Essential browser storage remembers your choice and temporarily keeps a submitted enquiry for the confirmation page. Submitting the form sends your details to Zapier for routing to VRAELIX."
        details = "When you submit the form, your details are sent to Zapier, which VRAELIX uses to route enquiries to Google Sheets."
        storage_detail = "Always active. It remembers this preference and temporarily stores submitted enquiry details for the confirmation page."
    else:
        summary = "Essential browser storage remembers your choice. This build's enquiry form is not connected and does not send entries."
        details = "Only essential browser storage is active, and this unconfigured build does not send enquiry form entries."
        storage_detail = "Always active. It remembers this preference. No enquiry entries are stored in this unconfigured preview."
    if analytics_enabled:
        summary += " Optional Google Analytics helps VRAELIX understand site usage and is loaded only if you choose analytics."
        analytics_option = '<label class="consent-analytics-option"><input type="checkbox" data-consent-analytics><span><strong>Optional analytics</strong><span>Allow Google Analytics 4 usage measurement. You can change this choice later in the footer.</span></span></label>'
        accept_label = "Accept all"
    else:
        summary += " No analytics or marketing cookies are active."
        analytics_option = ""
        accept_label = "Accept essential"
    return '''<aside class="consent-panel" data-consent-panel aria-labelledby="consent-title" hidden>
<div class="consent-heading-row"><h2 id="consent-title">Privacy &amp; cookies</h2><span>VRAELIX</span></div>
<p>''' + esc(summary) + ''' Read our <a href="/privacy/">Privacy Policy</a> and <a href="/cookie-policy/">Cookie Policy</a>.</p>
<div class="consent-actions" data-consent-primary-actions><button class="consent-accept" type="button" data-consent-accept>''' + accept_label + '''</button><button class="consent-manage" type="button" data-consent-manage aria-expanded="false" aria-controls="consent-management">Manage preferences</button></div>
<div class="consent-management" id="consent-management" data-consent-management hidden><p><strong>Essential storage</strong><span>''' + esc(storage_detail) + '''</span></p><p>''' + esc(details) + '''</p>''' + analytics_option + '''<div class="consent-actions"><button class="consent-accept" type="button" data-consent-save>Save preferences</button><button class="consent-manage" type="button" data-consent-back>Back</button></div></div>
</aside>'''

def page_intro(section, label, heading, copy):
    return f'''<section class="page-hero" aria-labelledby="page-title"><div class="wrap page-hero-grid"><div><p class="eyebrow">{esc(section)} <span class="eyebrow-divider" aria-hidden="true">/</span> {esc(label)}</p><h1 id="page-title">{heading}</h1></div><div class="page-hero-side"><p>{copy}</p></div></div><div class="page-hero-rule" aria-hidden="true"></div></section>'''

def cta_band(kicker, heading, copy):
    return f'''<section class="cta-band"><div class="wrap cta-band-inner"><div><p class="eyebrow">{esc(kicker)}</p><h2>{heading}</h2><p>{copy}</p></div><a class="button button-light" href="/request-a-quote/">Start a project <span aria-hidden="true">↗</span></a></div></section>'''

def render_home():
    cards = "".join(
        f'<a class="service-card" href="{service_path(s)}"><span class="card-index">0{i+1}</span><span class="card-arrow" aria-hidden="true">↗</span><h3>{esc(s["name"])}</h3><p>{esc(s["summary"])}</p><span class="card-link">Explore service <span aria-hidden="true">→</span></span></a>'
        for i, s in enumerate(SERVICES)
    )
    insight_cards = "".join(
        f'<article class="insight-card"><span>0{i+1} / {esc(item[0])}</span><h3>{esc(item[1])}</h3><p>{esc(item[2].split(".")[0])}.</p><a href="/insights/">Read the notes <span aria-hidden="true">↗</span></a></article>'
        for i, item in enumerate(DATA["insights"])
    )
    return f'''<section class="hero" aria-labelledby="hero-title">
<div class="hero__media"><video class="hero__video" autoplay muted loop playsinline preload="metadata" poster="/assets/hero-poster.webp" aria-hidden="true" tabindex="-1"><source data-responsive-video data-desktop="/assets/vraelix-cinematic.mp4" data-mobile="/assets/vraelix-cinematic-mobile.webm"><source data-responsive-video-fallback data-desktop="/assets/vraelix-cinematic-mobile.webm" data-mobile="/assets/vraelix-cinematic.mp4"></video><div class="hero__shade"></div></div>
<div class="wrap hero__content"><p class="eyebrow eyebrow-light"><span class="status-dot"></span> DIGITAL · BUSINESS · TECHNOLOGY</p><h1 id="hero-title">Build what<br>moves you <em>forward.</em></h1><p class="hero-copy">VRAELIX shapes thoughtful digital experiences and business systems around the way you work.</p><div class="hero-actions"><a class="button button-light" href="/request-a-quote/">Start a project <span aria-hidden="true">↗</span></a><a class="text-link text-link-light" href="/about/">Discover VRAELIX <span aria-hidden="true">↓</span></a></div></div>
<div class="wrap hero-bottom"><span>A modern digital technology &amp; solutions brand</span><span class="hero-scroll">Scroll to explore <span aria-hidden="true">↓</span></span></div></section>
<section class="intro-strip section"><div class="wrap intro-grid"><p class="eyebrow">The VRAELIX point of view</p><div><h2>Good technology starts with <em>understanding.</em></h2><p>We bring design, technology and business purpose together—so each digital decision has a reason to be there.</p><a class="text-link" href="/about/">More about VRAELIX <span aria-hidden="true">↗</span></a></div></div></section>
<section class="section services-home" aria-labelledby="services-heading"><div class="wrap"><div class="section-heading"><div><p class="eyebrow">What we do</p><h2 id="services-heading">Digital work,<br><em>with direction.</em></h2></div><p>Start with the business need. Find the right digital response. Build with room to grow.</p></div><div class="service-grid">{cards}</div><div class="section-foot"><a class="text-link" href="/services/">Explore all services <span aria-hidden="true">↗</span></a></div></div></section>
<section class="section founder-home" aria-labelledby="founder-heading"><div class="wrap founder-grid"><div class="founder-photo-stack"><div class="founder-photo-pair"><img class="founder-main" src="/assets/founder-work.webp" alt="VRAELIX founder working at a laptop in a light-filled office" loading="lazy" width="1086" height="1448"><img class="founder-detail" src="/assets/founder-coffee.webp" alt="VRAELIX founder taking a quiet moment between work" loading="lazy" width="1086" height="1448"></div><span class="photo-caption">A considered start. A bigger direction.</span></div><div class="founder-copy"><p class="eyebrow">Ansh Kumar · Founder &amp; CEO</p><h2 id="founder-heading">Built with a clear point of <em>view.</em></h2><p>VRAELIX began with a simple belief: digital work should make sense for the business behind it. That means listening first, making thoughtful choices and building something useful for the people who rely on it.</p><p>Today, websites are an important part of that work. They are also a foundation for a wider set of digital, creative and technology solutions as real needs emerge.</p><a class="text-link" href="/about/">Our story <span aria-hidden="true">↗</span></a></div></div></section>
<section class="section process-preview" aria-labelledby="process-heading"><div class="wrap"><div class="section-heading"><div><p class="eyebrow">How we work</p><h2 id="process-heading">A thoughtful route<br>from need to <em>next step.</em></h2></div><a class="text-link" href="/process/">Explore the process <span aria-hidden="true">↗</span></a></div><div class="steps-grid"><article class="step"><span>01</span><h3>Understand</h3><p>Start with the people, context and business need behind the request.</p></article><article class="step"><span>02</span><h3>Shape</h3><p>Agree the right scope, priorities and practical path forward.</p></article><article class="step"><span>03</span><h3>Build</h3><p>Make, review and refine the experience with care and clarity.</p></article><article class="step"><span>04</span><h3>Move forward</h3><p>Launch with a clear handover and space for what comes next.</p></article></div></div></section>
<section class="section insight-preview" aria-labelledby="insight-heading"><div class="wrap"><div class="section-heading"><div><p class="eyebrow">Notes for better decisions</p><h2 id="insight-heading">A clearer view of<br><em>digital work.</em></h2></div><a class="text-link" href="/insights/">Visit insights <span aria-hidden="true">↗</span></a></div><div class="insight-grid">{insight_cards}</div></div></section>
{cta_band("The next step","Let’s make the brief clearer.","Tell us what you are trying to improve or build. We’ll start with the need and shape the right conversation.")}'''

def render_about():
    return page_intro("VRAELIX", "About", "Technology with a<br><em>human point of view.</em>", "VRAELIX is a modern digital technology and solutions brand. We build thoughtful digital experiences and business systems around real business needs.") + '''<section class="section about-intro"><div class="wrap split-copy"><p class="eyebrow">Why VRAELIX exists</p><div><h2>Make the digital part<br>of business feel <em>clearer.</em></h2><p>Digital projects can become complicated before they become useful. VRAELIX starts with the people and the problem, then finds a considered way to make progress.</p><p>Website development is a core part of our work today. The wider direction is to support businesses with the creative, technical and operational solutions their needs call for—built carefully, one useful step at a time.</p></div></div></section>
<section class="section founder-story"><div class="wrap founder-story-grid"><div class="founder-story-copy"><p class="eyebrow">A note from the founder</p><h2>A practical idea,<br>a wider <em>horizon.</em></h2><p>Ansh Kumar is the Founder &amp; CEO of VRAELIX.</p><p>VRAELIX is being built around a simple principle: good digital work is grounded in business purpose. A website, an automation or a custom tool should have a clear role in the way people discover, understand or operate a business.</p><p>That principle is the starting point for every conversation. It keeps the work focused on what matters now while leaving room for what may be useful next.</p><a class="text-link" href="/request-a-quote/">Start a project <span aria-hidden="true">↗</span></a></div><div class="founder-story-photos"><figure><img src="/assets/founder-profile.webp" alt="VRAELIX founder, shown in a natural portrait at the office" loading="lazy" width="1086" height="1448"><figcaption>VRAELIX · Founder</figcaption></figure><figure><img src="/assets/founder-coffee.webp" alt="VRAELIX founder at work with a cup of coffee" loading="lazy" width="1086" height="1448"><figcaption>Thoughtful work, built around real needs</figcaption></figure></div></div></section>
<section class="section principles"><div class="wrap"><div class="section-heading"><div><p class="eyebrow">What guides the work</p><h2>Four things we<br>keep <em>in view.</em></h2></div></div><div class="principle-grid"><article><span>01</span><h3>Purpose before tools</h3><p>Begin with the outcome people need, then choose the technology that fits.</p></article><article><span>02</span><h3>Clarity in the details</h3><p>Make the message, structure and next action easier to understand.</p></article><article><span>03</span><h3>Care in the craft</h3><p>Consider the experience across screens, content and everyday use.</p></article><article><span>04</span><h3>Room to evolve</h3><p>Build a foundation that can accommodate new needs over time.</p></article></div></div></section>''' + cta_band("A good place to begin", "Start with the business need.", "Share the idea, challenge or opportunity you have in mind.")

def render_services():
    return page_intro("Capabilities", "Services", "Digital solutions<br>for work that <em>matters.</em>", "Website development is a core offering. Around it, VRAELIX brings together digital services that help businesses communicate clearly, operate thoughtfully and keep evolving.") + f'''<section class="section"><div class="wrap"><div class="section-heading"><div><p class="eyebrow">Our services</p><h2>Choose the need.<br><em>Shape the response.</em></h2></div><p>Each engagement begins with context. We clarify the outcome and agree the right scope before work begins.</p></div><div class="service-grid">{service_cards()}</div></div></section>''' + faq_html(DATA["faqs"]) + cta_band("Start a conversation", "Not sure which service fits?", "Tell us about the need. We can help you work out the right place to start.")

def render_service(service):
    intro = page_intro("Services", service["name"], f'{esc(service["name"])}<br><em>with purpose.</em>', esc(service["summary"]))
    detail = f'''<section class="section service-detail"><div class="wrap service-detail-grid"><aside class="service-meta"><p class="eyebrow">A considered engagement</p><a class="text-link" href="/services/">All services <span aria-hidden="true">↗</span></a></aside><div class="service-main"><h2>What this service is</h2><p>{esc(service["summary"])} We shape the work around what the business needs the experience or system to do.</p><h2>Who it helps</h2><p>{esc(service["who"])}</p><h2>The problem it can solve</h2><p>{esc(service["helps"])}</p><h2>What the work may include</h2><p>{esc(service["deliver"])}</p><div class="service-next"><p class="eyebrow">Your next step</p><p>Share the context, what is already in place and what a useful outcome would look like.</p><a class="button button-dark" href="/request-a-quote/">Start a project <span aria-hidden="true">↗</span></a></div></div></div></section>'''
    related_services = [next(item for item in SERVICES if item["slug"] == slug) for slug in service.get("related", []) if any(item["slug"] == slug for item in SERVICES)]
    related = f'''<section class="related-services section"><div class="wrap"><div class="section-heading"><div><p class="eyebrow">Related capabilities</p><h2>See the wider<br><em>picture.</em></h2></div><a class="text-link" href="/services/">All services <span aria-hidden="true">↗</span></a></div><div class="related-links">{service_links(services=related_services)}</div></div></section>'''
    return intro + detail + faq_html(service["faqs"], "Questions about this service") + related + cta_band("A useful first step", "Let’s talk through the need.", "We’ll help clarify the problem, the scope and the right way forward.")

def render_process():
    rows = [
      ("01", "Listen & understand", "Start with the context.", "We learn who the work is for, what is happening today and what needs to change. You can bring an early idea or a well-defined brief."),
      ("02", "Define & direct", "Agree what matters.", "We shape priorities, audience, scope and constraints into a practical direction. That includes deciding what does not need to be built yet."),
      ("03", "Design & build", "Make the right thing.", "The agreed solution takes shape through considered design, implementation and useful review points. Decisions stay connected to the original need."),
      ("04", "Launch & learn", "Make the next step clear.", "We prepare a handover around the agreed scope, then identify what would be useful to monitor or improve over time.")
    ]
    items = "".join(f'<article class="process-row"><span class="process-number">{n}</span><div><p class="eyebrow">{label}</p><h2>{heading}</h2><p>{text}</p></div></article>' for n,label,heading,text in rows)
    return page_intro("Our approach", "Process", "Clear thinking.<br>Careful <em>making.</em>", "A useful digital project needs shared understanding before it needs more features. Our process keeps the business need visible at every step.") + f'''<section class="section process-detail"><div class="wrap process-list">{items}</div></section><section class="section process-note"><div class="wrap split-copy"><p class="eyebrow">Made to fit the work</p><div><h2>The process is a guide,<br>not a <em>template.</em></h2><p>A small landing page and a custom system need different levels of planning. We keep the approach proportionate and agree how decisions, reviews and handovers will work for each project.</p><a class="text-link" href="/services/">See the services <span aria-hidden="true">↗</span></a></div></div></section>''' + cta_band("The beginning", "Bring us the question you are working through.", "A useful first conversation can help turn an early idea into a clearer next step.")

def render_insights():
    cards = "".join(f'<article class="insight-card insight-card-full"><span>0{i+1} / {esc(row[0])}</span><h2>{esc(row[1])}</h2><p>{esc(row[2])}</p><a href="{esc(row[4])}">Related service: {esc(row[3])} <span aria-hidden="true">↗</span></a></article>' for i,row in enumerate(DATA["insights"]))
    return page_intro("Resources", "Insights", "Useful notes for<br>better digital <em>decisions.</em>", "Direct, practical guidance on planning websites, considering technology and shaping digital work around a real business need.") + f'<section class="section"><div class="wrap insight-grid insight-grid-stack">{cards}</div></section>' + faq_html(DATA["insightFaqs"], "About these notes") + cta_band("Have a question of your own?", "Let’s make the next step clearer.", "If you are deciding what to build or improve, we can start with the context.")

def render_contact():
    return page_intro("Contact", "Start a conversation", "A clear first step<br>starts with a <em>brief.</em>", "Tell us what you are looking to build or improve. The unified project brief helps us understand the need and the right way to follow up.") + '''<section class="section contact-methods"><div class="wrap contact-grid"><div><p class="eyebrow">The simplest way to begin</p><h2>One conversation,<br>shaped around <em>you.</em></h2><p>Use the project brief for website, commerce, performance, automation or custom solution enquiries. Include only what is useful at this stage.</p><a class="button button-dark" href="/request-a-quote/">Start a project <span aria-hidden="true">↗</span></a></div><div class="contact-direct"><p class="eyebrow">Direct contact</p><div data-contact-links class="contact-link-list"></div><p class="contact-note">Direct channels complement the project brief. Your project details stay together in one place.</p></div></div></section>''' + cta_band("A considered beginning", "Tell us what you have in mind.", "A project brief is a good place to start, even if the scope is still taking shape.")

def quote_form():
    options = "".join(f'<option>{esc(s["name"])}</option>' for s in SERVICES)
    configured = (
        (ENQUIRY_BACKEND_VERIFIED or STAGING_FORM_TEST_MODE) and (
            bool(SUPABASE_PROJECT_URL and SUPABASE_PUBLISHABLE_KEY and TURNSTILE_SITE_KEY)
            if ENQUIRY_BACKEND == "supabase" else bool(ZAPIER_WEBHOOK_URL)
        )
    )
    disabled = "" if configured else " disabled"
    if configured:
        feedback = "This form needs JavaScript to send your enquiry. Please email VRAELIX if this message persists."
        privacy_copy = (
            "This local staging preview targets the separate VRAELIX staging database. Use synthetic details only. "
            if STAGING_FORM_TEST_MODE else
            "Submitting sends your information to VRAELIX so we can respond to your project enquiry. "
            if ENQUIRY_BACKEND == "supabase" else
            "Submitting sends your information to Zapier, which routes it to VRAELIX so we can respond. "
        )
        staging_notice = (
            '<p class="form-feedback" role="note">STAGING TEST ONLY — use synthetic details. This preview sends to the separate staging project, not production.</p>'
            if STAGING_FORM_TEST_MODE else ""
        )
    else:
        feedback = f'Online enquiries cannot currently be submitted. Your details will not be sent. Please <a href="mailto:{esc(EMAIL)}">email VRAELIX</a> instead.'
        privacy_copy = ""
        staging_notice = ""
    return f'''<form class="project-form" method="post" novalidate data-project-form>
<input type="hidden" name="source" value="VRAELIX Website"><input type="hidden" name="submitted_at" value="">
<div class="form-heading"><p class="eyebrow">Project brief</p><p>Fields marked <span aria-hidden="true">*</span> are required. Share enough context to make the first conversation useful.</p></div>
<div class="form-grid">
<div class="form-field"><label for="full-name">Full name <span>*</span></label><input id="full-name" name="full_name" type="text" autocomplete="name" minlength="2" maxlength="100" aria-describedby="error-full-name" required><p class="form-field-error" id="error-full-name" data-field-error="full_name" hidden></p></div>
<div class="form-field"><label for="email">Email <span>*</span></label><input id="email" name="email" type="email" autocomplete="email" maxlength="254" aria-describedby="error-email" required><p class="form-field-error" id="error-email" data-field-error="email" hidden></p></div>
<div class="form-field"><label for="company">Company / business <span class="optional">Optional</span></label><input id="company" name="company" type="text" autocomplete="organization" maxlength="160"></div>
<div class="form-field"><label for="service">Service required <span>*</span></label><select id="service" name="service" aria-describedby="error-service" required><option value="">Choose a service</option>{options}<option>Other</option><option>Not sure yet</option></select><p class="form-field-error" id="error-service" data-field-error="service" hidden></p></div>
<div class="form-field"><label for="phone-number">Phone number <span>*</span></label><input id="phone-number" name="phone_number" type="tel" inputmode="tel" autocomplete="tel" maxlength="32" aria-describedby="error-phone-number" required><p class="form-field-error" id="error-phone-number" data-field-error="phone_number" hidden></p></div>
<div class="form-field"><label for="contact-method">Preferred contact method <span>*</span></label><select id="contact-method" name="contact_method" aria-describedby="error-contact-method" required><option value="">Choose a contact method</option><option value="Email">Email</option><option value="WhatsApp">WhatsApp</option><option value="Instagram / Social">Instagram / Social</option><option value="Other">Other</option></select><p class="form-field-error" id="error-contact-method" data-field-error="contact_method" hidden></p></div>
<div class="form-field form-field-wide"><label for="description">Project description <span>*</span></label><textarea id="description" name="project_description" rows="5" minlength="10" maxlength="2400" placeholder="What are you looking to build, improve or make easier?" aria-describedby="error-project-description" required></textarea><p class="form-field-error" id="error-project-description" data-field-error="project_description" hidden></p></div>
<div class="form-field"><label for="budget">Budget range / budget <span class="optional">Optional</span></label><input id="budget" name="budget" type="text" maxlength="120" placeholder="Optional range or estimate"></div>
<div class="form-field"><label for="timeline">Timeline <span class="optional">Optional</span></label><input id="timeline" name="timeline" type="text" maxlength="120" placeholder="e.g. planning, soon, flexible"></div>
</div>
<div data-turnstile-slot hidden><div data-turnstile-widget></div></div>
{staging_notice}<p class="form-privacy">{privacy_copy}Read our <a href="/privacy/">Privacy Policy</a> and <a href="/cookie-policy/">Cookie Policy</a>.</p><p class="form-feedback" id="form-feedback" data-form-feedback aria-live="polite" role="status">{feedback}</p><button class="button button-dark" type="submit" aria-describedby="form-feedback"{disabled}>Send project enquiry <span aria-hidden="true">↗</span></button></form>'''

def render_quote():
    return page_intro("Start a project", "Request a quote", "Good work begins<br>with a clear <em>brief.</em>", "Share what you have in mind. We’ll use your answers to understand the need and prepare a useful next conversation.") + f'''<section class="section quote-section"><div class="wrap quote-grid"><div class="quote-aside"><p class="eyebrow">A little context helps</p><h2>What are you<br>trying to <em>change?</em></h2><p>Tell us what is in place today, what feels difficult and what a better experience or process could make possible.</p><div class="quote-aside-note"><span>01</span><p>One brief for all VRAELIX services</p></div><div class="quote-aside-note"><span>02</span><p>Budget and timing are optional</p></div><div class="quote-aside-note"><span>03</span><p>Choose how you would like us to follow up</p></div></div><div class="quote-form-wrap">{quote_form()}</div></div></section>'''

def render_thankyou():
    return page_intro("Project brief", "Thank you", "A clearer next step<br>starts <em>here.</em>", "Complete the project enquiry form to share the details VRAELIX needs to respond.") + '''<section class="section thankyou-section"><div class="wrap thankyou-grid"><div class="thankyou-content"><p class="eyebrow">Project enquiry</p><h2 data-thanks-title>No enquiry has been sent yet.</h2><div class="brief-summary" data-brief-summary><p data-thanks-empty>Submit the project enquiry form to see its confirmation and a copy of the details here.</p></div><div class="thankyou-actions"><div data-thanks-actions class="thanks-send-actions"></div></div><p class="thankyou-note" data-thanks-note>Return to the project form to submit an enquiry.</p><a class="text-link" href="/request-a-quote/">Return to the project form <span aria-hidden="true">↗</span></a></div></div></section>'''

def render_legal(slug):
    title, sections = DATA["legal"][slug]
    if IS_STAGING_PREVIEW and slug == "privacy":
        staging_sections = {
            "How information is handled": (
                "In this Staging preview, the Request a Quote form sends the details you enter to the Staging "
                "Supabase Edge Function. The function validates the request, verifies a Cloudflare Turnstile "
                "token, applies rate limiting with Upstash and attempts to insert accepted enquiries into the "
                "Staging public.enquiries table. Use synthetic details only. This describes Staging; Production "
                "processing has not been verified."
            ),
            "Information you may enter": (
                "The form asks for your name, email address, phone number, requested service, project description, "
                "budget, timeline and preferred contact method. Company or business name is optional. The function "
                "also records a source label and server-generated submission time. Please include only information "
                "needed to respond to your enquiry."
            ),
            "Third-party processing": (
                "The Staging function uses Supabase for the function and database, Cloudflare Turnstile to verify "
                "the challenge token, and Upstash for rate limiting. The function is coded to send a keyed hash "
                "derived from the configured client-IP header to Upstash; it does not send enquiry fields through "
                "Zapier or Google Sheets in this Staging build. Provider-side retention and hosting settings have "
                "not been verified. Production processing is unverified."
            ),
            "Retention and requests": (
                "The reviewed website code does not define an enquiry-retention period. Staging database and "
                "backup retention or deletion settings have not been verified, and Production retention is "
                "unverified. Use synthetic details only in this preview. To ask about an enquiry or request its "
                "deletion, contact vraelix29@gmail.com."
            ),
        }
        sections = [(head, staging_sections.get(head, text)) for head, text in sections]
    elif IS_STAGING_PREVIEW and slug == "cookie-policy":
        staging_sections = {
            "Cookies and browser storage": (
                "This Staging build uses localStorage to remember the privacy preference. After a successful "
                "submission, sessionStorage keeps a copy of the entered brief in the current tab for the Thank You "
                "page. Google Analytics 4 is not configured in this Staging build. The quote form loads Cloudflare "
                "Turnstile when it requests a token; the reviewed website code does not configure Turnstile "
                "pre-clearance. Provider cookie behavior and Production behavior have not been verified."
            ),
            "Enquiry submission": (
                "In this Staging preview, the browser sends the form fields and Turnstile token to the Staging "
                "Supabase Edge Function. If its checks pass, the function attempts to insert the enquiry into the "
                "Staging public.enquiries table. This build does not send enquiry fields through Zapier or Google "
                "Sheets. Production submission behavior is unverified."
            ),
            "Third-party services": (
                "The form uses Cloudflare Turnstile for its challenge and the Staging Supabase Edge Function for "
                "submission. The function is coded to use Upstash for rate limiting, sending a keyed hash derived "
                "from the configured client-IP header. Zapier and Google Sheets are not configured for this "
                "Staging build. Provider cookie behavior, retention and Production configuration have not been "
                "verified."
            ),
            "Retention": (
                "The reviewed website code does not define a retention period. Staging database and backup "
                "retention or deletion settings, and Production retention, have not been verified. Use synthetic "
                "details only in this preview. Contact vraelix29@gmail.com with a data request."
            ),
        }
        sections = [(head, staging_sections.get(head, text)) for head, text in sections]
    elif not ZAPIER_WEBHOOK_URL and slug == "privacy":
        analytics_summary = (
            " Optional Google Analytics 4 measurement is available only after you opt in through the privacy preferences."
            if GA4_MEASUREMENT_ID else
            " The site uses essential browser storage for the privacy preference; no analytics or advertising pixels are active."
        )
        disabled_form_text = "The Request a Quote form is not connected in this build and does not transmit enquiry entries." + analytics_summary
        sections = [(head, disabled_form_text if head == "How information is handled" else text) for head,text in sections]
        sections = [(head, "The form is not connected in this build, so it does not send entries to Zapier or Google Sheets." if head == "Third-party processing" else text) for head,text in sections]
        sections = [(head, "This build does not transmit enquiry entries or create records in Zapier or Google Sheets." if head == "Retention and requests" else text) for head,text in sections]
    elif not ZAPIER_WEBHOOK_URL and slug == "cookie-policy":
        analytics_summary = (
            " Optional Google Analytics 4 is loaded only if you grant analytics consent."
            if GA4_MEASUREMENT_ID else
            " This site does not set analytics, advertising or personalisation cookies."
        )
        sections = [(head, "The Request a Quote form is not connected in this build and does not send enquiry entries." + analytics_summary if head == "Cookies and browser storage" else text) for head,text in sections]
        sections = [(head, "The form is not connected in this build, so it does not send entries to Zapier or Google Sheets." if head == "Enquiry submission" else text) for head,text in sections]
        sections = [(head, "No enquiry form entries are sent to Zapier or Google Sheets in this build." if head == "Third-party services" else text) for head,text in sections]
        sections = [(head, "This build does not transmit enquiry entries or create records in Zapier or Google Sheets." if head == "Retention" else text) for head,text in sections]
    if not IS_STAGING_PREVIEW and GA4_MEASUREMENT_ID and slug == "privacy":
        form_text = (
            "When you submit the Request a Quote form, your browser sends the enquiry details to Zapier, which VRAELIX uses to route records to Google Sheets."
            if ZAPIER_WEBHOOK_URL else
            "The Request a Quote form is not connected in this build and does not transmit enquiry entries."
        )
        analytics_text = form_text + " Optional Google Analytics 4 measures general site usage only if you opt in through privacy preferences. The Google tag is not loaded before consent; Google processes opted-in analytics under its own terms and privacy practices. You can withdraw consent later in the footer settings."
        sections = [(head, analytics_text if head == "How information is handled" else text) for head,text in sections]
        processing_text = (
            "Zapier processes submitted enquiry details for routing to Google Sheets. Optional Google Analytics 4 is loaded only after analytics consent and measures site usage. Google handles analytics data under its own privacy practices."
            if ZAPIER_WEBHOOK_URL else
            "Optional Google Analytics 4 is loaded only after analytics consent and measures site usage. Google handles analytics data under its own privacy practices."
        )
        sections = [(head, processing_text if head == "Third-party processing" else text) for head,text in sections]
    if not IS_STAGING_PREVIEW and GA4_MEASUREMENT_ID and slug == "cookie-policy":
        sections = [(head, "Essential browser storage remembers your privacy choice and sessionStorage temporarily holds a submitted brief for the confirmation page. If you choose optional analytics, Google Analytics 4 may set first-party cookies such as _ga to distinguish visits. Analytics does not load before consent, and you can change your choice in the footer settings." if head == "Cookies and browser storage" else text) for head,text in sections]
        third_party_cookie_text = (
            "Zapier and Google process submitted enquiry information under their own terms and privacy practices. Google Analytics 4 is activated only after optional analytics consent and may set first-party analytics cookies."
            if ZAPIER_WEBHOOK_URL else
            "Google Analytics 4 is activated only after optional analytics consent and may set first-party analytics cookies."
        )
        sections = [(head, third_party_cookie_text if head == "Third-party services" else text) for head,text in sections]
    blocks = []
    for head,text in sections:
        paragraph = esc(text)
        if slug in ("privacy", "cookie-policy") and head in ("Third-party processing", "Third-party services"):
            provider_links = []
            if ZAPIER_WEBHOOK_URL:
                provider_links.append('<a href="https://zapier.com/privacy" target="_blank" rel="noopener noreferrer">Zapier Privacy Policy</a>')
            if GA4_MEASUREMENT_ID:
                provider_links.append('<a href="https://policies.google.com/privacy" target="_blank" rel="noopener noreferrer">Google Privacy Policy</a>')
            if provider_links:
                paragraph += " Review " + " and ".join(provider_links) + "."
        blocks.append(f'<h2>{esc(head)}</h2><p>{paragraph}</p>')
    content = "".join(blocks)
    return page_intro("VRAELIX", "Legal", f'{esc(title)}<br><em>at VRAELIX.</em>', "This page explains the basic terms for this static website. Please read it alongside the information relevant to your use.") + f'''<section class="section legal-content"><div class="wrap legal-wrap"><p class="eyebrow">Website information</p>{content}<p class="legal-updated">Last reviewed: 8 October 2026</p><a class="text-link" href="/contact/">Contact VRAELIX <span aria-hidden="true">↗</span></a></div></section>'''

def jsonld(path,title,description,service=None,faqs=None):
    if not INDEXING_APPROVED or not SITE_ORIGIN or path == "/thank-you/":
        return ""
    homepage = site_url("/")
    page_url = site_url(path)
    graph = [
      {"@type":"Organization","@id":homepage+"#organization","name":"VRAELIX","description":"A digital technology and solutions brand building thoughtful digital experiences, business systems and technology solutions around real business needs.","url":homepage,"email":EMAIL,"sameAs":[LINKEDIN,INSTAGRAM],"logo":{"@type":"ImageObject","url":homepage+"assets/brand/vraelix-logo.png"}},
      {"@type":"WebPage","@id":page_url+"#webpage","url":page_url,"name":title,"description":description,"isPartOf":{"@id":homepage+"#website"},"about":{"@id":homepage+"#organization"}}
    ]
    if path == "/":
        graph.insert(1,{"@type":"WebSite","@id":homepage+"#website","name":"VRAELIX","url":homepage,"publisher":{"@id":homepage+"#organization"}})
    else:
        graph.append({"@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"name":"Home","item":homepage},{"@type":"ListItem","position":2,"name":title.split("|")[0].strip(),"item":page_url}]})
    if service:
        graph.append({"@type":"Service","@id":page_url+"#service","name":service["name"],"serviceType":service["name"],"description":service["summary"],"provider":{"@id":homepage+"#organization"},"url":page_url})
    if faqs:
        graph.append({"@type":"FAQPage","@id":page_url+"#faq","mainEntity":[{"@type":"Question","name":q,"acceptedAnswer":{"@type":"Answer","text":a}} for q,a in faqs]})
    return json.dumps({"@context":"https://schema.org","@graph":graph},ensure_ascii=False,separators=(",",":")).replace("</","<\\/")

def shell(path,title,description,content,active="",service=None,faqs=None):
    preload = '<link rel="preload" as="image" href="/assets/hero-poster.webp" fetchpriority="high">' if path == "/" else ""
    icon_base = "/assets/brand/favicon-V"
    icon_links = []
    for color_scheme in ("light", "dark"):
        for icon_size in (16, 32, 48):
            icon_href = site_path(f"{icon_base}/favicon-{color_scheme}-{icon_size}.png")
            icon_links.append(
                f'<link rel="icon" type="image/png" sizes="{icon_size}x{icon_size}" '
                f'href="{icon_href}" media="(prefers-color-scheme: {color_scheme})">'
            )
    favicon_markup = "".join(icon_links) + f'<link rel="manifest" href="{site_path("/site.webmanifest")}">'
    ld = jsonld(path,title,description,service,faqs or [])
    canonical = f'<link rel="canonical" href="{esc(site_url(path))}">' if INDEXING_APPROVED and SITE_ORIGIN else ""
    social_urls = (
        f'<meta property="og:url" content="{esc(site_url(path))}">'
        f'<meta property="og:image" content="{esc(site_url("/assets/hero-poster.png"))}">'
        f'<meta name="twitter:image" content="{esc(site_url("/assets/hero-poster.png"))}">'
        if INDEXING_APPROVED and SITE_ORIGIN else ""
    )
    robots = "index,follow,max-image-preview:large" if INDEXING_APPROVED and path != "/thank-you/" else "noindex,follow"
    schema_script = f'<script type="application/ld+json">{ld}</script>' if ld else ""
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(description)}"><meta name="robots" content="{robots}">{canonical}{preload}<meta name="theme-color" content="#17191D">{favicon_markup}
<meta property="og:type" content="website"><meta property="og:site_name" content="VRAELIX"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}">{social_urls}<meta property="og:image:alt" content="Cinematic monochrome visual identity for VRAELIX"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{esc(title)}"><meta name="twitter:description" content="{esc(description)}">
<link rel="stylesheet" href="/assets/site.css?v={CSS_VERSION}"><script src="/assets/site-config.js"></script>{schema_script}</head>
<body data-route="{path}">{header(active)}<main id="main">{content}</main>{footer()}{consent_panel()}<script src="/assets/zapier-adapter.js" defer></script><script src="/assets/supabase-adapter.js" defer></script><script src="/assets/enquiry-adapter.js" defer></script><script src="/assets/site.js" defer></script></body></html>'''

renderers = {
  "home": render_home, "about": render_about, "services": render_services,
  "process": render_process, "insights": render_insights, "contact": render_contact,
  "quote": render_quote, "thank": render_thankyou
}
rendered_pages = list(DATA["pages"])
SERVICE_META_DESCRIPTIONS = {
    "website-development": "Plan and build a responsive website around your business, audience and goals—from page structure and design to development and launch support.",
    "business-websites": "Bring your story, services and enquiries into a clear business website, with a page structure shaped around your audience.",
    "ecommerce": "Plan an online store around your products, customer journey and operations, including storefront structure and agreed platform setup.",
    "landing-pages": "Give a campaign, offer or product a focused landing page with a clear message, responsive layout and next action.",
    "seo-performance": "Review technical and on-page SEO, internal links, accessibility, image handling and performance to make a site easier to find, understand and use.",
    "maintenance": "Website maintenance may include agreed content updates, routine checks, platform updates, backups and small improvements based on your site and support needs.",
    "automation": "Map repeatable business workflows and explore practical automation across existing tools, based on the process and its constraints.",
    "custom-solutions": "Scope a tailored web experience, business tool or system connection around its intended users, operational problem and technical constraints.",
}
for service in SERVICES:
    rendered_pages.append([service_path(service), f'{service["name"]} | VRAELIX Digital Solutions', SERVICE_META_DESCRIPTIONS[service["slug"]], "service", service["slug"]])

# Clean generated pages and hosting metadata before rebuilding, while retaining
# the checked-in static asset directory used by this project.
if ROOT.exists():
    for generated in ROOT.rglob("*.html"):
        generated.unlink()
    for filename in ("sitemap.xml", "robots.txt", "_headers", "_redirects", "README.md"):
        generated = ROOT / filename
        if generated.exists():
            generated.unlink()
(ROOT/"assets").mkdir(parents=True,exist_ok=True)
if not IS_DEFAULT_OUTPUT and not (ROOT/"assets/site.css").is_file():
    source_assets = DEFAULT_ROOT / "assets"
    if not source_assets.is_dir():
        raise ValueError("The existing generated asset directory is required to build the GitHub Pages copy")
    shutil.copytree(source_assets, ROOT / "assets", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("site-config.js"))
for asset_name in ("site.css", "site.js", "zapier-adapter.js", "supabase-adapter.js", "enquiry-adapter.js", "vraelix-logo-lockup-white.webp"):
    shutil.copyfile(Path("work/assets") / asset_name, ROOT / "assets" / asset_name)
brand_source = Path("work/assets/brand")
brand_target = ROOT / "assets" / "brand"
brand_target.mkdir(parents=True, exist_ok=True)
for asset_name in ("vraelix-logo.png", "vraelix-logo-white.png", "vraelix-logo.webp", "vraelix-logo-white.webp"):
    source_asset = brand_source / asset_name
    if not source_asset.is_file():
        raise FileNotFoundError(f"Required VRAELIX brand asset is missing: {source_asset}")
    shutil.copyfile(source_asset, brand_target / asset_name)
favicon_source = brand_source / "favicon-V"
favicon_target = brand_target / "favicon-V"
favicon_target.mkdir(parents=True, exist_ok=True)
favicon_files = [f"favicon-{scheme}-{size}.png" for scheme in ("light", "dark") for size in (16, 32, 48, 512)]
for asset_name in favicon_files:
    source_asset = favicon_source / asset_name
    if not source_asset.is_file():
        raise FileNotFoundError(f"Required favicon-V asset is missing: {source_asset}")
    shutil.copyfile(source_asset, favicon_target / asset_name)
web_manifest = {
    "name": "VRAELIX",
    "short_name": "VRAELIX",
    "start_url": site_path("/"),
    "scope": site_path("/"),
    "display": "standalone",
    "icons": [
        {
            "src": site_path(f"/assets/brand/favicon-V/favicon-{scheme}-512.png"),
            "sizes": "512x512",
            "type": "image/png",
        }
        for scheme in ("light", "dark")
    ],
}
(ROOT / "site.webmanifest").write_text(json.dumps(web_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
CSS_VERSION = hashlib.sha256((ROOT / "assets/site.css").read_bytes()).hexdigest()[:12]
desktop_video_source = Path("work/source.mp4")
desktop_video_target = ROOT/"assets/vraelix-cinematic.mp4"
if desktop_video_source.is_file():
    shutil.copyfile(desktop_video_source, desktop_video_target)
elif not desktop_video_target.is_file():
    raise ValueError("The existing desktop Hero video source is missing")
legacy_desktop_webm = ROOT/"assets/vraelix-cinematic.webm"
if legacy_desktop_webm.exists():
    legacy_desktop_webm.unlink()

for entry in rendered_pages:
    path,title,description,kind,*extra = entry
    service = None
    active = ""
    faqs = []
    if kind == "service":
        service = next(s for s in SERVICES if s["slug"] == extra[0])
        content = render_service(service)
        active = "/services/"
        faqs = service["faqs"]
    elif kind == "legal":
        content = render_legal(path.strip("/"))
    else:
        content = renderers[kind]()
        active = path if path in ("/about/","/services/","/process/","/insights/","/contact/") else ""
        if kind == "services": faqs = DATA["faqs"]
        if kind == "insights": faqs = DATA["insightFaqs"]
    directory = ROOT if path == "/" else ROOT.joinpath(*path.strip("/").split("/"))
    directory.mkdir(parents=True,exist_ok=True)
    (directory/"index.html").write_text(shell(path,title,description,content,active,service,faqs),encoding="utf-8")

(ROOT/"assets/site-config.js").write_text(
    "window.VRAELIX_CONFIG = {\n"
    f'  email: "{EMAIL}",\n'
    '  whatsapp: "", // Country code and number, digits only.\n'
    f'  instagram: "{INSTAGRAM}",\n'
    f'  linkedin: "{LINKEDIN}",\n'
    f'  zapierWebhookUrl: {json.dumps(ZAPIER_WEBHOOK_URL)}, // Set VRAELIX_ZAPIER_WEBHOOK_URL at build time; this URL is public in browser code.\n'
    f'  supabaseUrl: {json.dumps(SUPABASE_PROJECT_URL if ENQUIRY_BACKEND == "supabase" else "")},\n'
    f'  supabasePublishableKey: {json.dumps(SUPABASE_PUBLISHABLE_KEY if ENQUIRY_BACKEND == "supabase" else "")},\n'
    f'  enquiryBackend: {json.dumps(ENQUIRY_BACKEND)},\n'
    f'  enquiryBackendVerified: {str(ENQUIRY_BACKEND_VERIFIED).lower()},\n'
    f'  enquiryStagingTestMode: {str(STAGING_FORM_TEST_MODE).lower()},\n'
    f'  turnstileSiteKey: {json.dumps(TURNSTILE_SITE_KEY if ENQUIRY_BACKEND == "supabase" else "")},\n'
    f'  ga4MeasurementId: {json.dumps(GA4_MEASUREMENT_ID)},\n'
    f'  siteBasePath: {json.dumps(SITE_BASE_PATH)},\n'
    f'  services: {json.dumps([s["name"] for s in SERVICES] + ["Other", "Not sure yet"], ensure_ascii=False)}\n'
    "};\n",encoding="utf-8")

if INDEXING_APPROVED and SITE_ORIGIN:
    public_pages = [entry for entry in rendered_pages if entry[0] != "/thank-you/"]
    locations = "".join(f"  <url><loc>{site_url(entry[0])}</loc></url>\n" for entry in public_pages)
    (ROOT/"sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+locations+'</urlset>\n',encoding="utf-8")
    robots = f"User-agent: *\nAllow: /\n\nSitemap: {site_url('/sitemap.xml')}\n"
else:
    sitemap = ROOT/"sitemap.xml"
    if sitemap.exists():
        sitemap.unlink()
    robots = "User-agent: *\nAllow: /\n"
(ROOT/"robots.txt").write_text(robots,encoding="utf-8")

slash_redirects = "".join(f"{entry[0][:-1]} {entry[0]} 301\n" for entry in rendered_pages if entry[0] != "/")
(ROOT/"_redirects").write_text(slash_redirects,encoding="utf-8")

connect_sources = ["'self'"]
script_sources = ["'self'"]
frame_sources = ["'self'"]
if ZAPIER_WEBHOOK_URL:
    connect_sources.append("https://hooks.zapier.com")
if ENQUIRY_BACKEND == "supabase" and SUPABASE_PROJECT_URL:
    supabase_origin = urlsplit(SUPABASE_PROJECT_URL)
    connect_sources.append(f"{supabase_origin.scheme}://{supabase_origin.netloc}")
if ENQUIRY_BACKEND == "supabase" and TURNSTILE_SITE_KEY:
    connect_sources.append("https://challenges.cloudflare.com")
    script_sources.append("https://challenges.cloudflare.com")
    frame_sources.append("https://challenges.cloudflare.com")
img_sources = ["'self'", "data:"]
if GA4_MEASUREMENT_ID:
    connect_sources.extend(("https://www.googletagmanager.com", "https://*.google-analytics.com", "https://*.google.com"))
    script_sources.append("https://www.googletagmanager.com")
    img_sources.extend(("https://www.googletagmanager.com", "https://*.google-analytics.com"))
connect_src = " ".join(connect_sources)
script_src = " ".join(script_sources)
frame_src = " ".join(frame_sources)
img_src = " ".join(img_sources)
(ROOT/"_headers").write_text(f"""/*
  Content-Security-Policy: default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src {script_src}; style-src 'self'; img-src {img_src}; font-src 'self'; media-src 'self'; connect-src {connect_src}; frame-src {frame_src}; manifest-src 'self'; worker-src 'self'
  Strict-Transport-Security: max-age=31536000
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()
""",encoding="utf-8")
print(f"Generated {len(rendered_pages)} static pages in {ROOT}")
