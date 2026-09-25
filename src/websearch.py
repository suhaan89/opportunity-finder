"""Websuche über die Brave-Search-API (kostenloses Kontingent), als Ersatz für Gemini-Grounding.

Warum: Die Google-Suche von Gemini ist im Gratis-Tarif gesperrt (Fehler 429). Brave liefert nur Titel + Link;
die Links werden danach wie immer in verify.py geprüft. Gemini liest dann nur noch die echten Seiten.

WICHTIG (öffentliche Logs): Hier wird nichts geloggt. Fehler werden als Exception nach oben gereicht,
`collect_from_search` zählt sie nur.
"""
from __future__ import annotations

import time
from typing import Any

import requests

from .gemini import SearchHit

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSearch:
    """Ruft die Brave-Suche auf. Im Gratis-Tarif ist höchstens 1 Anfrage pro Sekunde erlaubt."""

    def __init__(self, api_key: str, count: int = 10, pause: float = 1.2, session: Any = None) -> None:
        self.api_key = api_key
        self.count = count
        self.pause = pause
        self._session = session or requests
        self._last_call = 0.0

    def __call__(self, query: str, today: str = "") -> list[SearchHit]:  # noqa: ARG002 - today nur für gleiche Signatur
        wait = self.pause - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()
        resp = self._session.get(
            BRAVE_URL,
            headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
            params={"q": query, "count": self.count, "freshness": "py"},  # py = letztes Jahr
            timeout=20,
        )
        resp.raise_for_status()
        results = (resp.json().get("web") or {}).get("results") or []
        hits: list[SearchHit] = []
        for r in results:
            url = r.get("url")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                hits.append(SearchHit(str(r.get("title", ""))[:200], url))
        return hits


TAVILY_URL = "https://api.tavily.com/search"


class TavilySearch:
    """Tavily-Suche: 1000 Gratis-Credits pro Monat, keine Karte nötig. Eine einfache Suche kostet 1 Credit."""

    def __init__(self, api_key: str, count: int = 10, session: Any = None) -> None:
        self.api_key = api_key
        self.count = count
        self._session = session or requests

    def __call__(self, query: str, today: str = "") -> list[SearchHit]:  # noqa: ARG002
        resp = self._session.post(
            TAVILY_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"query": query, "max_results": self.count, "search_depth": "basic"},
            timeout=30,
        )
        resp.raise_for_status()
        hits: list[SearchHit] = []
        for r in resp.json().get("results") or []:
            url = r.get("url")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                hits.append(SearchHit(str(r.get("title", ""))[:200], url))
        return hits
