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


def safe_error(step: str, exc: BaseException) -> str:
    """Log-Text für Fehler. Enthält NUR den Schritt und den Fehlertyp.

    Die Fehlermeldung selbst kann Zugangsdaten, Mail- oder Profilinhalte enthalten,
    und die Actions-Logs sind öffentlich. Deshalb wird sie nie ausgegeben.
    """
    return f"Fehler in Schritt '{step}': {type(exc).__name__}"
