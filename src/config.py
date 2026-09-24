"""Lädt config/settings.yaml und config/sources.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_settings(path: Path | None = None) -> dict[str, Any]:
    """Einstellungen (Modellname, Limits, Gewichte ...)."""
    return _load_yaml(path or CONFIG_DIR / "settings.yaml")


def load_sources(path: Path | None = None) -> dict[str, Any]:
    """Suchanfragen und Quellenseiten."""
    return _load_yaml(path or CONFIG_DIR / "sources.yaml")
