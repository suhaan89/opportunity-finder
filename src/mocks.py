"""Attrappen (Mocks) für Läufe OHNE Zugangsdaten und für Tests.

Alles hier ist FIKTIV: erfundene Seiten unter example.org, keine echten Daten.
Der Mock-Modus prüft, ob die ganze Pipeline zusammenpasst (Suchen -> Prüfen -> Extrahieren ->
Filtern -> Bewerten -> Speichern -> Mail), ohne Gemini, Google Sheets oder Gmail zu brauchen.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .gemini import SearchHit, SearchResult
from .verify import Page


def _de(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def build_fixtures(today: date) -> dict[str, dict[str, Any]]:
    """Fiktive Seiten. Schlüssel = URL. Die Daten sind relativ zu 'heute', damit sie nie veralten."""
    future = today + timedelta(days=120)
    event = today + timedelta(days=240)
    past = today - timedelta(days=30)

    def page(key: str, title: str, deadline: date, extra: str = "") -> str:
        return (
            f"{title}. Bewerbungsschluss: {_de(deadline)}. "
            f"Die Veranstaltung findet ab dem {_de(event)} statt. {extra} [[fx:{key}]]"
        )

    def data(**kw: Any) -> dict[str, Any]:
        base = {
            "is_opportunity": True, "organizer": "Beispiel-Stiftung", "category": "akademie",
            "target": "person", "format": "praesenz", "language": "de", "travel_covered": "unklar",
            "benefits": [], "effort": "mittel", "fee_eur": 0, "location_city": "Zürich",
            "location_country": "Schweiz", "requires_legal_entity": False, "fully_funded": False,
        }
        base.update(kw)
        return base

    def dates(deadline: date) -> dict[str, Any]:
        return {
            "deadline": deadline.isoformat(), "deadline_quote": f"Bewerbungsschluss: {_de(deadline)}",
            "event_start": event.isoformat(), "event_quote": f"ab dem {_de(event)} statt",
        }

    fx: dict[str, dict[str, Any]] = {}

    def add(key: str, title: str, deadline: date, extra: str = "", **kw: Any) -> None:
        fx[f"https://example.org/{key}"] = {
            "page": Page(url=f"https://example.org/{key}", title=title, text=page(key, title, deadline, extra)),
            "extract": data(title=title, **dates(deadline), **kw),
        }

    add("ki-akademie", "Sommerakademie Künstliche Intelligenz", future,
        travel_covered="ja", fully_funded=True, benefits=["mentoring", "netzwerk", "zertifikat"],
        eligibility="Schüler ab 16 Jahren", age_min=16, age_max=19)
    add("ki-akademie-kopie", "Sommerakademie Künstliche Intelligenz", future,   # Duplikat mit anderer URL
        travel_covered="ja", fully_funded=True)
    add("online-hackathon", "Online Hackathon für Anfänger", future,
        format="online", category="hackathon", benefits=["zertifikat"], eligibility="offen für alle")
    add("geschichte", "Bundeswettbewerb Geschichte", future,
        category="wettbewerb", subject="Geschichte", location_country="Deutschland")
    add("abgelaufen", "Stipendium Zukunft (abgelaufen)", past, category="stipendium")
    add("cloud-credits", "Cloud-Credits für Schülerprojekte", future,
        target="projekt", category="projektfoerderung", benefits=["credits"], format="online",
        eligibility="Schulprojekte mit KI-Bezug", location_country="Deutschland", location_city="")
    add("teuer", "Premium-Camp Silicon Valley", future, fee_eur=4200, location_country="USA")
    return fx


class MockFetcher:
    """Liefert die fiktiven Seiten; alles andere ist 'nicht erreichbar'."""

    def __init__(self, fixtures: dict[str, dict[str, Any]]) -> None:
        self.fixtures = fixtures

    def fetch(self, url: str) -> Page | None:
        entry = self.fixtures.get(url)
        return entry["page"] if entry else None


class MockGemini:
    """Ersatz für den Gemini-Client. Zählt Aufrufe wie das echte Budget."""

    def __init__(self, fixtures: dict[str, dict[str, Any]], budget: Any) -> None:
        self.fixtures = fixtures
        self.budget = budget

    def search(self, query: str, today: str) -> SearchResult:
        if not self.budget.take():
            return SearchResult()
        hits = [SearchHit(v["page"].title, url) for url, v in self.fixtures.items()]
        hits.append(SearchHit("Toter Link", "https://example.org/gibt-es-nicht"))
        return SearchResult(hits=hits)

    def generate_json(self, prompt: str, schema: dict[str, Any], purpose: str = "") -> Any | None:
        if not self.budget.take():
            return None
        if purpose == "extract":
            for entry in self.fixtures.values():
                key = entry["page"].text.rsplit("[[fx:", 1)[-1].split("]]")[0]
                if f"[[fx:{key}]]" in prompt:
                    return dict(entry["extract"])
            return None
        if purpose == "score":
            prestige = 60
            if "Künstliche Intelligenz" in prompt:
                prestige = 88
            if "Cloud-Credits" in prompt:
                prestige = 75
            keys = list(schema["properties"]["interest_relevance"]["properties"].keys())
            relevance = {k: (95 if k == "ki_forschung" else 40) for k in keys}
            return {
                "interest_relevance": relevance, "prestige": prestige, "career": 80,
                "regional": False, "reason": "Passt gut zu deinen KI-Interessen (Mock-Bewertung).",
            }
        if purpose == "list_page":
            return {"items": []}
        return None
