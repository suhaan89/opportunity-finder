"""Kleine Hilfsfunktionen: URLs, IDs, Datum, sicheres Logging."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

# Alle Datumslogik läuft in dieser Zeitzone (SPEC Abschnitt 12).
BERLIN = ZoneInfo("Europe/Berlin")

# Tracking-Parameter, die wir aus URLs entfernen, damit gleiche Seiten gleich aussehen.
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source"}


def today_berlin() -> date:
    """Heutiges Datum in Berlin (nicht in UTC, sonst stimmen Deadlines nachts nicht)."""
    return datetime.now(BERLIN).date()


def normalize_url(url: str) -> str:
    """Macht aus einer URL eine vergleichbare Form.

    Kleinschreibung bei Host, ohne www., ohne Anker (#...), ohne Tracking-Parameter,
    ohne abschließenden Schrägstrich. https und http gelten als gleich.
    """
    url = (url or "").strip()
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_KEYS and not k.lower().startswith(_TRACKING_PREFIXES)
    ]
    query.sort()
    path = parts.path.rstrip("/")
    return urlunsplit(("https", host, path, urlencode(query), ""))


def make_id(url: str) -> str:
    """ID = Hash der normalisierten URL (kurz, aber eindeutig genug)."""
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:16]


def parse_date(value: object) -> date | None:
    """Wandelt 'YYYY-MM-DD' in ein Datum um. Alles andere (auch 'unklar') wird None."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def normalize_text(text: str) -> str:
    """Kleinschreibung, Leerraum zusammenfassen (für Textvergleiche)."""
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


# Hosts, auf denen ein Pfadsegment die geheime Gist-ID ist (über die ID ist der Gist lesbar).
_GIST_API_HOST = "api.github.com"
_GIST_HTML_HOST = "gist.github.com"
_GIST_RAW_HOST = "gist.githubusercontent.com"
# Seiten auf gist.github.com, die keine Gist-ID sind.
_GIST_SITE_PAGES = {"discover", "starred"}
# Nach einer Kurzform-ID (/<id>/...) kommen diese Segmente, nicht ein Username.
_GIST_SHORT_SUFFIXES = {"raw", "forks", "edit", "revisions", "download", "archive", "stars", "fork"}
_GIST_URL_IN_TEXT = re.compile(
    r"https?://(?:www\.)?(?:api\.github\.com/gists/|gist\.github\.com/|gist\.githubusercontent\.com/)[^\s\"'<>]+",
    re.IGNORECASE,
)


def _host_key(host: str) -> str:
    host = (host or "").lower()
    if host.startswith("www."):
        return host[4:]
    return host


def _gist_path_parts(path: str) -> list[str]:
    """Pfadsegmente ohne trailing/leere Mittelteile; führendes '' für absolute Pfade bleibt."""
    trimmed = (path or "").rstrip("/")
    parts = trimmed.split("/")
    if parts and parts[0] == "":
        return [""] + [p for p in parts[1:] if p]
    return [p for p in parts if p]


def _redact_gist_path(host: str, path: str) -> str:
    """Ersetzt die Gist-ID im Pfad durch <redacted>. Andere URLs bleiben unverändert."""
    key = _host_key(host)
    parts = _gist_path_parts(path)
    if key == _GIST_API_HOST:
        # /gists/<id> und /gists/<id>/comments usw. (Pfadvergleich case-insensitive)
        if len(parts) >= 3 and parts[1].lower() == "gists" and parts[2]:
            parts[2] = "<redacted>"
    elif key == _GIST_HTML_HOST:
        # /<id>, /<id>/raw..., oder /<user>/<id>/...
        if len(parts) >= 3 and parts[1] and parts[2]:
            if parts[2].lower() in _GIST_SHORT_SUFFIXES:
                if parts[1].lower() not in _GIST_SITE_PAGES:
                    parts[1] = "<redacted>"
            else:
                parts[2] = "<redacted>"
        elif len(parts) == 2 and parts[1] and parts[1].lower() not in _GIST_SITE_PAGES:
            parts[1] = "<redacted>"
    elif key == _GIST_RAW_HOST:
        # /<user>/<id>/raw/<rev>/<datei>
        if len(parts) >= 3 and parts[2]:
            parts[2] = "<redacted>"
    return "/".join(parts)


def _safe_url(url: str) -> str:
    """URL fürs Log: Schema/Host/Pfad, ohne Query und Fragment (können Tokens tragen).

    Gist-IDs im Pfad werden zu <redacted> (API-, HTML- und Raw-Host).
    Ein geheimer Gist ist für jeden mit der ID lesbar und darf nicht in öffentliche Logs.
    """
    try:
        parts = urlsplit(url or "")
        path = _redact_gist_path(parts.hostname or "", parts.path)
        return urlunsplit((parts.scheme, parts.netloc, path, "", ""))
    except Exception:  # noqa: BLE001
        return "(url)"


def _redact_gist_urls(text: str) -> str:
    """Gist-URLs in Freitext (z. B. API-Antwort) auf dieselbe sichere Form bringen."""
    return _GIST_URL_IN_TEXT.sub(lambda match: _safe_url(match.group(0)), text)


def _response_host(resp: object) -> str:
    """Hostname der HTTP-Antwort (leer wenn unbekannt)."""
    raw = getattr(resp, "url", None) or ""
    if not raw:
        req = getattr(resp, "request", None)
        raw = getattr(req, "url", "") if req is not None else ""
    try:
        return (urlsplit(raw).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def _http_body_excerpt(exc: BaseException, limit: int = 200) -> str:
    """Kurzer Antworttext ohne Zugangsdaten. Nur ASCII-druckbare Zeichen.

    Nur für api.github.com aufrufen — andere APIs können Suchanfragen/Profil spiegeln.
    """
    resp = getattr(exc, "response", None)
    if resp is None:
        return ""
    try:
        raw = (getattr(resp, "text", None) or "")[:limit]
    except Exception:  # noqa: BLE001
        return ""
    cleaned = re.sub(r"(?i)(authorization|token|bearer|ghp_|github_pat_)[^\s\"']*", "[redacted]", raw)
    cleaned = _redact_gist_urls(cleaned)
    cleaned = re.sub(r"[^\x20-\x7E]+", " ", cleaned).strip()
    return cleaned[:limit]


def http_error_details(exc: BaseException) -> str:
    """Status und URL (ohne Query, ohne Gist-ID). Body-Ausschnitt nur bei api.github.com — nie der Token."""
    resp = getattr(exc, "response", None)
    if resp is None:
        return type(exc).__name__
    status = getattr(resp, "status_code", "?")
    url = _safe_url(getattr(resp, "url", None) or getattr(getattr(exc, "request", None), "url", "") or "")
    parts = [f"HTTP {status}", f"url={url or '(unbekannt)'}"]
    # Öffentliche Actions-Logs: Body nur vom Gist-API-Host (kein Echo von Gemini/Suche/Profil)
    if _response_host(resp) == "api.github.com":
        excerpt = _http_body_excerpt(exc)
        if excerpt:
            parts.append(f"body={excerpt}")
    return "; ".join(parts)


def safe_error(step: str, exc: BaseException) -> str:
    """Log-Text für Fehler. Standard: nur Schritt und Fehlertyp.

    Bei HTTP-Fehlern (requests) zusätzlich Status und URL ohne Query und ohne Gist-ID.
    Body-Ausschnitt nur für api.github.com (Kalender-Gist); sonst nie Antworttexte —
    Actions-Logs sind öffentlich und fremde APIs können Profil/Suche zurückspiegeln.
    """
    name = type(exc).__name__
    # requests.HTTPError und Unterklassen: response.status_code ist gesetzt
    if getattr(exc, "response", None) is not None and name == "HTTPError":
        return f"Fehler in Schritt '{step}': {name} ({http_error_details(exc)})"
    return f"Fehler in Schritt '{step}': {name}"
