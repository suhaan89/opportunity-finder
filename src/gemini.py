"""Dünner Wrapper um die Gemini-API.

Aufgaben:
- Budget-Schutz: höchstens `max_calls_per_run` Aufrufe pro Lauf (SPEC Abschnitt 1).
- Suche mit Google-Grounding (`search`).
- JSON-Antworten holen und gegen ein Schema prüfen (`generate_json`), bei Fehler einmal wiederholen.
- Der Modellname kommt aus der Config, nie aus dem Code.

WICHTIG (öffentliche Logs): Hier wird nichts geloggt außer technischen Zählern.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator


class Budget:
    """Zählt Gemini-Aufrufe und verweigert weitere, wenn das Limit erreicht ist."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def take(self) -> bool:
        """True, wenn noch ein Aufruf erlaubt ist (und zählt ihn mit)."""
        if self.used >= self.limit:
            return False
        self.used += 1
        return True


@dataclass
class SearchHit:
    """Ein Fundstück aus der Suche: Titel + URL (noch UNGEPRÜFT!)."""
    title: str
    url: str


@dataclass
class SearchResult:
    text: str = ""
    hits: list[SearchHit] = field(default_factory=list)


def parse_json_text(text: str) -> Any | None:
    """Holt JSON aus einer Modellantwort (auch wenn sie in ```json ... ``` steckt)."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    # Notlösung: erstes Objekt oder Array im Text suchen
    for pattern in (r"\{.*\}", r"\[.*\]"):
        m = re.search(pattern, text, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                continue
    return None


def hits_from_response(response: Any) -> list[SearchHit]:
    """Sammelt Fundstücke aus (a) dem JSON-Array im Text und (b) den Grounding-Quellen.

    Die Grounding-Links sind Weiterleitungen (redirect); sie werden später in verify.py aufgelöst.
    """
    hits: list[SearchHit] = []
    data = parse_json_text(getattr(response, "text", "") or "")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("url"), str) and item["url"].startswith("http"):
                hits.append(SearchHit(str(item.get("title", ""))[:200], item["url"]))
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks or []
    except (AttributeError, IndexError, TypeError):
        chunks = []
    for ch in chunks:
        web = getattr(ch, "web", None)
        uri = getattr(web, "uri", None)
        if isinstance(uri, str) and uri.startswith("http"):
            hits.append(SearchHit(str(getattr(web, "title", "") or "")[:200], uri))
    return hits


class GeminiClient:
    """Echter Gemini-Client. `client` kann in Tests durch eine Attrappe ersetzt werden."""

    def __init__(
        self,
        api_key: str,
        model: str,
        budget: Budget,
        seconds_between_calls: float = 5,
        client: Any = None,
    ) -> None:
        self.model = model
        self.budget = budget
        self.pause = seconds_between_calls
        self._last_call = 0.0
        if client is None:
            from google import genai  # erst hier importieren, damit Tests ohne SDK-Aufrufe laufen

            client = genai.Client(api_key=api_key)
        self._client = client

    # ----- interne Hilfe -----
    def _call(self, prompt: str, config: Any) -> Any | None:
        """Ein API-Aufruf mit Budget, Pause und EINEM Wiederholversuch bei Serverfehlern/429."""
        for attempt in range(2):
            if not self.budget.take():
                return None
            wait = self.pause - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            try:
                return self._client.models.generate_content(
                    model=self.model, contents=prompt, config=config
                )
            except Exception as exc:  # noqa: BLE001 - jede API-Störung soll den Lauf nicht beenden
                code = getattr(exc, "code", None)
                if attempt == 0 and code in (429, 500, 502, 503, 504):
                    time.sleep(min(30, self.pause * 4))
                    continue
                return None
        return None

    # ----- öffentliche Funktionen -----
    def search(self, query: str, today: str) -> SearchResult:
        """Websuche mit Google-Grounding. Liefert Fundstücke (Titel + URL), ungeprüft."""
        from google.genai import types

        prompt = (
            f"Heute ist der {today}. Suche im Web nach konkreten, AKTUELLEN Angeboten zu: {query}\n"
            "Gemeint sind Events, Stipendien, Wettbewerbe, Hackathons, Akademien, Uni-Programme "
            "oder Förderungen mit offizieller Webseite. Nenne bis zu 8 Treffer.\n"
            'Beende deine Antwort mit einem JSON-Array: [{"title": "...", "url": "https://..."}]'
        )
        config = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
        response = self._call(prompt, config)
        if response is None:
            return SearchResult()
        return SearchResult(text="", hits=hits_from_response(response))

    def generate_json(self, prompt: str, schema: dict[str, Any], purpose: str = "") -> Any | None:
        """Holt eine JSON-Antwort und prüft sie gegen `schema`.

        Bei ungültiger Antwort wird EINMAL wiederholt, danach gibt es None (Eintrag überspringen).
        """
        from google.genai import types

        config = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
        validator = Draft202012Validator(schema)
        hint = ""
        for _ in range(2):
            response = self._call(prompt + hint, config)
            if response is None:
                return None
            data = parse_json_text(getattr(response, "text", "") or "")
            if data is not None and not list(validator.iter_errors(data)):
                return data
            hint = "\n\nDEINE LETZTE ANTWORT WAR UNGÜLTIG. Antworte ausschließlich mit gültigem JSON nach dem Schema."
        return None
