"""Collect: Kandidaten (Titel + URL) einsammeln.

Phase 1: nur Gemini-Suche mit Google Search.
Die gefundenen Links sind noch UNGEPRÜFT; verify.py prüft sie danach.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from .util import normalize_url


@dataclass
class Candidate:
    """Ein möglicher Treffer, bevor wir ihn geprüft haben."""
    title: str
    url: str
    origin: str = "suche"   # suche / quelle / mail


def select_queries(queries: list[str], n: int, day_index: int) -> list[str]:
    """Wählt n Suchanfragen aus; jeden Tag rutscht das Fenster weiter (rotierend)."""
    if not queries or n <= 0:
        return []
    n = min(n, len(queries))
    start = (day_index * n) % len(queries)
    return [queries[(start + i) % len(queries)] for i in range(n)]


def unique_candidates(cands: list[Candidate]) -> list[Candidate]:
    """Entfernt doppelte URLs (nach Normalisierung), behält die Reihenfolge."""
    seen: set[str] = set()
    out: list[Candidate] = []
    for c in cands:
        key = normalize_url(c.url)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def collect_from_search(gemini: Any, queries: list[str], today: date) -> tuple[list[Candidate], int]:
    """Stellt die Suchanfragen. Eine kaputte Anfrage bricht den Lauf nicht ab.

    Gibt (Kandidaten, Anzahl fehlgeschlagener Anfragen) zurück.
    """
    cands: list[Candidate] = []
    failed = 0
    for q in queries:
        try:
            result = gemini.search(q, today.isoformat())
        except Exception:  # noqa: BLE001 - eine Anfrage darf den Lauf nicht beenden
            failed += 1
            continue
        if not result.hits:
            failed += 1
        cands.extend(Candidate(h.title, h.url, "suche") for h in result.hits)
    return unique_candidates(cands), failed
