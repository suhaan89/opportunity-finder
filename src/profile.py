"""Lädt das persönliche Profil. Es steht NIE im Repo.

Reihenfolge:
1. Umgebungsvariable PROFILE_YAML (GitHub Secret oder .env)
2. Lokale Datei profile.yaml (steht in .gitignore)
3. config/profile.example.yaml (fiktives Beispiel, nur zum Ausprobieren)
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any

import yaml

from .config import CONFIG_DIR, ROOT


def load_profile() -> dict[str, Any]:
    text = os.environ.get("PROFILE_YAML", "").strip()
    if text:
        return yaml.safe_load(text) or {}
    local = ROOT / "profile.yaml"
    if local.exists():
        return yaml.safe_load(local.read_text(encoding="utf-8")) or {}
    return yaml.safe_load((CONFIG_DIR / "profile.example.yaml").read_text(encoding="utf-8")) or {}


def _to_date(value: Any) -> date | None:
    """YAML macht aus 2010-03-15 schon ein date; Strings wandeln wir um."""
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def birthdate(profile: dict[str, Any]) -> date | None:
    return _to_date(profile.get("geburtsdatum"))


def age_on(profile: dict[str, Any], day: date) -> int | None:
    """Alter in vollen Jahren an einem bestimmten Tag (None, wenn kein Geburtsdatum)."""
    born = birthdate(profile)
    if born is None:
        return None
    years = day.year - born.year
    if (day.month, day.day) < (born.month, born.day):
        years -= 1
    return years


def blocked_periods(profile: dict[str, Any]) -> list[tuple[date, date]]:
    """Sperrzeiträume (z. B. Abi-Phase) als Liste von (von, bis)."""
    result = []
    for item in profile.get("kriterien", {}).get("sperrzeitraeume", []) or []:
        start, end = _to_date(item.get("von")), _to_date(item.get("bis"))
        if start and end:
            result.append((start, end))
    return result


def criteria(profile: dict[str, Any]) -> dict[str, Any]:
    return profile.get("kriterien", {}) or {}
