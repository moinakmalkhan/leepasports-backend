"""
Language & country detection.

Country comes from the edge/CDN header (Cloudflare `CF-IPCountry`, Vercel
`X-Vercel-IP-Country`, CloudFront `CloudFront-Viewer-Country`, or a generic
`X-Country-Code` set by nginx GeoIP). We deliberately do not ship a GeoIP
database: the CDN in front of chobbar.shop already knows the visitor's country.

Precedence for the language: explicit choice (`?lang=` / cookie / `X-Language`)
> Accept-Language > country default > English.
"""

from django.conf import settings
from django.utils import translation

SUPPORTED = [code for code, _ in settings.LANGUAGES]
RTL = {"ur", "ar"}

COUNTRY_LANGUAGE = {
    "PK": "ur",
    # Arabic-speaking markets
    "SA": "ar",
    "AE": "ar",
    "QA": "ar",
    "KW": "ar",
    "BH": "ar",
    "OM": "ar",
    "EG": "ar",
    "JO": "ar",
    "IQ": "ar",
    "LB": "ar",
    "LY": "ar",
    "MA": "ar",
    "DZ": "ar",
    "TN": "ar",
    "YE": "ar",
    "SY": "ar",
    "SD": "ar",
    "PS": "ar",
}

COUNTRY_HEADERS = ("HTTP_CF_IPCOUNTRY", "HTTP_X_VERCEL_IP_COUNTRY", "HTTP_CLOUDFRONT_VIEWER_COUNTRY", "HTTP_X_COUNTRY_CODE")


def detect_country(request) -> str:
    for header in COUNTRY_HEADERS:
        value = (request.META.get(header) or "").strip().upper()
        if len(value) == 2 and value not in ("XX", "T1"):
            return value
    return ""


def normalize(code: str | None) -> str | None:
    if not code:
        return None
    code = code.lower().split("-")[0].split("_")[0]
    return code if code in SUPPORTED else None


def explicit_language(request) -> str | None:
    return (
        normalize(request.GET.get("lang"))
        or normalize(request.headers.get("X-Language"))
        or normalize(request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME))
    )


def accept_language(request) -> str | None:
    header = request.headers.get("Accept-Language", "")
    for part in header.split(","):
        code = normalize(part.split(";")[0].strip())
        if code:
            return code
    return None


def detect_language(request) -> tuple[str, str]:
    """Return (language, source)."""
    lang = explicit_language(request)
    if lang:
        return lang, "explicit"
    lang = COUNTRY_LANGUAGE.get(detect_country(request))
    if lang:
        return lang, "country"
    lang = accept_language(request)
    if lang:
        return lang, "browser"
    return settings.LANGUAGE_CODE, "default"


class LanguageMiddleware:
    """Activate the detected language for the request (replaces LocaleMiddleware for the API)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lang, _ = detect_language(request)
        translation.activate(lang)
        request.LANGUAGE_CODE = lang
        response = self.get_response(request)
        response.headers.setdefault("Content-Language", lang)
        vary = response.headers.get("Vary", "")
        if "Accept-Language" not in vary:
            response.headers["Vary"] = f"{vary}, Accept-Language, X-Language".strip(", ")
        translation.deactivate()
        return response


def translate(instance, field: str, lang: str | None = None):
    """Pick `instance.translations[lang][field]`, falling back to the base field."""
    lang = lang or translation.get_language() or settings.LANGUAGE_CODE
    base = getattr(instance, field, "")
    if lang == settings.LANGUAGE_CODE:
        return base
    data = getattr(instance, "translations", None) or {}
    return (data.get(lang) or {}).get(field) or base
