"""Harte Filter (SPEC Abschnitt 5). Alles deterministisch in Python, kein KI-Urteil.

Jeder Filter ist eine eigene kleine Funktion und bekommt (Eintrag, Profil, heute).
Er gibt None zurück, wenn der Eintrag BLEIBEN darf, sonst einen kurzen technischen
Ausschluss-Grund (nur für Zähler im Log, nie mit Inhalten).

Bei "unklar" (None) wird im Zweifel behalten und höchstens eine Warnung gesetzt.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

from .models import Opportunity
from .profile import age_on, blocked_periods, criteria
from .util import normalize_text

# Länder-Schreibweisen vereinheitlichen (Englisch -> Deutsch, klein geschrieben)
_COUNTRY_ALIASES = {
    "india": "indien",
    "israel": "israel",
    "germany": "deutschland",
    "austria": "österreich",
    "switzerland": "schweiz",
    "russia": "russland",
    "china": "china",
    "turkey": "türkei",
    "iran": "iran",
}


def _country(name: str) -> str:
    n = normalize_text(name)
    return _COUNTRY_ALIASES.get(n, n)


# ---------- die einzelnen Filter ----------

def filter_deadline_vorbei(o: Opportunity, profile: dict[str, Any], today: date) -> str | None:
    """1. Deadline liegt in der Vergangenheit (oder das Event ist schon vorbei)."""
    if o.deadline is not None:
        return "deadline_vorbei" if o.deadline < today else None
    # Ohne Deadline: ein bereits beendetes Event ist auch abgelaufen
    end = o.event_end or o.event_start
    if end is not None and end < today:
        return "deadline_vorbei"
    return None


def filter_alter(o: Opportunity, profile: dict[str, Any], today: date) -> str | None:
    """2. Altersgrenze, geprüft gegen das Alter zum Eventdatum (Ersatz: Deadline)."""
    stichtag = o.event_start or o.deadline
    if stichtag is None:
        return None
    alter = age_on(profile, stichtag)
    if alter is None:
        return None
    if o.age_max is not None and alter > o.age_max:
        return "zu_alt"
    if o.age_min is not None and alter < o.age_min:
        return "zu_jung"
    return None


def filter_sprache(o: Opportunity, profile: dict[str, Any], today: date) -> str | None:
    """3. Sprache muss Deutsch oder Englisch sein."""
    return "sprache" if o.language == "andere" else None


def filter_land(o: Opportunity, profile: dict[str, Any], today: date) -> str | None:
    """4. Ort in einem ausgeschlossenen Land."""
    ausgeschlossen = {_country(c) for c in profile.get("ausgeschlossene_laender", []) or []}
    if o.location_country and _country(o.location_country) in ausgeschlossen:
        return "land"
    return None


def filter_gebuehr(o: Opportunity, profile: dict[str, Any], today: date) -> str | None:
    """5. Teilnahmegebühr über dem Maximum."""
    maximum = criteria(profile).get("max_teilnahmegebuehr_eur")
    if maximum is not None and o.fee_eur is not None and o.fee_eur > maximum:
        return "gebuehr"
    return None


def filter_reisekosten(o: Opportunity, profile: dict[str, Any], today: date) -> str | None:
    """6. Reisekosten nachweislich NICHT übernommen (bei unklar: behalten + Warnung)."""
    if not criteria(profile).get("reisekosten_muessen_uebernommen_werden", False):
        return None
    if o.format == "online":  # online reist niemand
        return None
    return "reisekosten" if o.travel_covered == "nein" else None


def filter_rechtsform(o: Opportunity, profile: dict[str, Any], today: date) -> str | None:
    """7. Es wird eine Rechtsform (e.V., GmbH) vorausgesetzt."""
    if criteria(profile).get("rechtsform_erforderlich_ausschliessen", False) and o.requires_legal_entity:
        return "rechtsform"
    return None


def filter_sperrzeitraum(o: Opportunity, profile: dict[str, Any], today: date) -> str | None:
    """8. Event überschneidet sich mit einem Sperrzeitraum (z. B. Abi-Phase)."""
    if o.event_start is None:
        return None
    ende = o.event_end or o.event_start
    for von, bis in blocked_periods(profile):
        if o.event_start <= bis and ende >= von:
            return "sperrzeitraum"
    return None


def filter_fach(o: Opportunity, profile: dict[str, Any], today: date) -> str | None:
    """9. Fachwettbewerb in einem ausgeschlossenen Fach."""
    if o.category != "wettbewerb" or not o.subject:
        return None
    faecher = {normalize_text(f) for f in profile.get("ausgeschlossene_wettbewerbsfaecher", []) or []}
    return "fach" if normalize_text(o.subject) in faecher else None


# Filter 1-9 laufen VOR dem Scoring (spart Gemini-Aufrufe).
PRE_SCORE_FILTERS: list[Callable[[Opportunity, dict[str, Any], date], str | None]] = [
    filter_deadline_vorbei,
    filter_alter,
    filter_sprache,
    filter_land,
    filter_gebuehr,
    filter_reisekosten,
    filter_rechtsform,
    filter_sperrzeitraum,
    filter_fach,
]


def apply_pre_score_filters(o: Opportunity, profile: dict[str, Any], today: date) -> str | None:
    """Gibt den ersten Ausschluss-Grund zurück, oder None wenn der Eintrag bleibt."""
    for f in PRE_SCORE_FILTERS:
        reason = f(o, profile, today)
        if reason:
            return reason
    return None


# ---------- Filter 10 und 11: brauchen das Prestige (also erst NACH dem Scoring) ----------

def filter_online(o: Opportunity, settings: dict[str, Any]) -> str | None:
    """10. Online nur mit Prestige >= Schwelle (Online-Ausnahme, Standard 85)."""
    minimum = settings.get("scoring", {}).get("online_min_prestige", 85)
    if o.format == "online" and (o.prestige or 0) < minimum:
        return "online"
    return None


def filter_regional(o: Opportunity, settings: dict[str, Any]) -> str | None:
    """11. Im Regionalradius nur mit Prestige >= Schwelle (Regional-Ausnahme, Standard 80)."""
    minimum = settings.get("scoring", {}).get("regional_min_prestige", 80)
    if o.regional and (o.prestige or 0) < minimum:
        return "regional"
    return None


def apply_post_score_filters(o: Opportunity, settings: dict[str, Any]) -> str | None:
    return filter_online(o, settings) or filter_regional(o, settings)


# ---------- Warnungen für unklare Angaben ----------

def add_warnings(o: Opportunity, profile: dict[str, Any]) -> None:
    """Ergänzt Warnungen für Dinge, die wir nicht belegen konnten."""
    def warn(text: str) -> None:
        if text not in o.warnings:
            o.warnings.append(text)

    if (
        criteria(profile).get("reisekosten_muessen_uebernommen_werden", False)
        and o.format != "online"
        and o.travel_covered == "unklar"
    ):
        warn("Reisekosten unklar")
    if o.deadline is None:
        warn("Deadline unklar")
    if o.fee_eur is None:
        warn("Teilnahmegebühr unklar")
    if o.requires_legal_entity is None:
        warn("Rechtsform unklar")
