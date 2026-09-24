"""Duplikate erkennen: gleiche URL (über die ID) oder sehr ähnlicher Titel."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import Opportunity
from .util import normalize_text


def _zahlen(text: str) -> set[str]:
    """Alle Zahlen im Titel (z. B. Jahreszahlen). 'Hackathon 2026' != 'Hackathon 2027'."""
    return set(re.findall(r"\d+", text))


def title_similarity(a: str, b: str) -> float:
    """Ähnlichkeit zweier Titel zwischen 0 und 1."""
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def is_duplicate(o: Opportunity, other: Opportunity, threshold: float = 0.88) -> bool:
    """Gleiche ID = gleiche Seite. Sonst: sehr ähnlicher Titel UND gleiche Zahlen im Titel."""
    if o.id and o.id == other.id:
        return True
    za, zb = _zahlen(o.title), _zahlen(other.title)
    if za != zb:
        return False
    return title_similarity(o.title, other.title) >= threshold


def dedupe_batch(
    neu: list[Opportunity], vorhanden: list[Opportunity], threshold: float = 0.88
) -> tuple[list[Opportunity], list[Opportunity]]:
    """Entfernt aus `neu` alles, was schon in `vorhanden` steht oder doppelt in `neu` vorkommt.

    Gibt (behaltene Einträge, entfernte Einträge) zurück.
    """
    behalten: list[Opportunity] = []
    entfernt: list[Opportunity] = []
    for o in neu:
        if any(is_duplicate(o, x, threshold) for x in vorhanden + behalten):
            entfernt.append(o)
        else:
            behalten.append(o)
    return behalten, entfernt
