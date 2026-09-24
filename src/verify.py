"""Verify: Ist der Link echt und erreichbar? Was steht WIRKLICH auf der Seite?

Das ist die Schutzschicht gegen erfundene Links (SPEC Abschnitt 2): Gemini darf nie die
Quelle der Wahrheit sein. Wir laden die Seite selbst, folgen Weiterleitungen und geben den
echten Seitentext für die Extraktion weiter.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

MAX_BYTES = 2_000_000  # so viel HTML laden wir höchstens


@dataclass
class Page:
    """Eine erfolgreich geladene Seite."""
    url: str            # endgültige URL nach allen Weiterleitungen
    title: str
    text: str           # sichtbarer Text, gekürzt
    links: list[tuple[str, str]] = field(default_factory=list)  # (Linktext, absolute URL)


def is_public_http_url(url: str) -> bool:
    """Nur http(s) und keine lokalen/privaten Adressen (Schutz vor Missbrauch)."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    host = parts.hostname.lower()
    if host == "localhost" or host.endswith(".local") or host.endswith(".internal"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True  # normaler Domainname
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)


def parse_html(html: str, base_url: str, max_chars: int, max_links: int = 200) -> tuple[str, str, list[tuple[str, str]]]:
    """Zieht Titel, sichtbaren Text und Links aus HTML."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    links: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if href.startswith("http"):
            links.append((a.get_text(" ", strip=True)[:120], href))
        if len(links) >= max_links:
            break
    text = " ".join(soup.get_text(" ", strip=True).split())
    return title[:200], text[:max_chars], links


class Fetcher:
    """Lädt Webseiten. In Tests/Mock-Modus durch eine Attrappe mit gleicher Methode ersetzbar."""

    def __init__(self, timeout: float = 15, max_chars: int = 12000, user_agent: str = "opportunity-finder") -> None:
        self.timeout = timeout
        self.max_chars = max_chars
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent

    def fetch(self, url: str) -> Page | None:
        """Lädt die Seite. None, wenn nicht erreichbar, kein HTTP 200 oder kein Text."""
        if not is_public_http_url(url):
            return None
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True, stream=True)
            try:
                if resp.status_code != 200 or not is_public_http_url(resp.url):
                    return None
                ctype = resp.headers.get("Content-Type", "").lower()
                if "html" not in ctype and "text" not in ctype:
                    return None  # z. B. PDF: überspringen
                raw = resp.raw.read(MAX_BYTES, decode_content=True)
                encoding = resp.encoding or "utf-8"
            finally:
                resp.close()
            html = raw.decode(encoding, errors="replace")
        except (requests.RequestException, LookupError, OSError):
            return None
        title, text, links = parse_html(html, resp.url, self.max_chars)
        if len(text) < 200:  # praktisch leere Seite (z. B. nur JavaScript)
            return None
        return Page(url=resp.url, title=title, text=text, links=links)
