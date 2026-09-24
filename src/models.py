"""Datenmodell: eine Zeile im Sheet = ein Opportunity (SPEC Abschnitt 4).

None bedeutet überall "unklar" (nicht belegbar). Wir raten nie.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date
from typing import Any

from .util import parse_date

UNKLAR = "unklar"
LIST_SEP = " | "

CATEGORIES = [
    "stipendium", "wettbewerb", "hackathon", "akademie", "networking",
    "jugendforum", "uni_programm", "projektfoerderung", "sonstiges",
]
TARGETS = ["person", "projekt"]
FORMATS = ["praesenz", "online", "hybrid"]
LANGUAGES = ["de", "en", "andere"]
TRAVEL = ["ja", "nein", "teilweise", "unklar"]
BENEFITS = ["geld", "mentoring", "netzwerk", "zertifikat", "credits", "hardware", "inkubator", "preis"]
EFFORTS = ["niedrig", "mittel", "hoch"]
STATUSES = [
    "neu", "interessant", "in_vorbereitung", "beworben", "zusage", "absage",
    "teilgenommen", "ignoriert",
]
# Status, bei denen der Nutzer die Sache "verfolgt" (Reminder, Kalender)
ACTIVE_STATUSES = ["interessant", "in_vorbereitung"]
CALENDAR_STATUSES = ["interessant", "in_vorbereitung", "beworben", "zusage"]


@dataclass
class Opportunity:
    id: str
    title: str
    organizer: str = ""
    url: str = ""
    category: str = "sonstiges"
    target: str = "person"
    format: str = "praesenz"
    location_city: str = ""
    location_country: str = ""
    event_start: date | None = None
    event_end: date | None = None
    deadline: date | None = None
    recurring_yearly: bool | None = None
    age_min: int | None = None
    age_max: int | None = None
    eligibility: str = ""
    required_docs: str = ""
    language: str = "de"
    fee_eur: float | None = None
    travel_covered: str = "unklar"
    fully_funded: bool | None = None
    requires_legal_entity: bool | None = None
    benefits: list[str] = field(default_factory=list)
    prestige: int | None = None
    effort: str = "mittel"
    score: int | None = None
    score_reason: str = ""
    warnings: list[str] = field(default_factory=list)
    status: str = "neu"
    notes: str = ""
    first_seen: date | None = None
    last_checked: date | None = None
    # Zusatzfelder (nicht in SPEC Abschnitt 4, aber für die Filter nötig)
    subject: str = ""      # Fach bei Fachwettbewerben (Filter 9)
    regional: bool | None = None  # liegt im Umkreis des Heimatorts (Filter 11)


# Reihenfolge der Spalten im Sheet
COLUMNS = [f.name for f in fields(Opportunity)]


# ---------- Umwandlung Opportunity <-> Sheet-Zeile (alles als Text) ----------

def _s_date(d: date | None) -> str:
    return d.isoformat() if d else UNKLAR


def _s_bool(b: bool | None) -> str:
    return UNKLAR if b is None else ("ja" if b else "nein")


def _s_num(n: float | int | None) -> str:
    if n is None:
        return UNKLAR
    return str(int(n)) if float(n).is_integer() else str(n)


def to_row(o: Opportunity) -> list[str]:
    """Eine Opportunity als Liste von Texten in Spaltenreihenfolge."""
    out: list[str] = []
    for name in COLUMNS:
        v = getattr(o, name)
        if isinstance(v, list):
            out.append(LIST_SEP.join(v))
        elif isinstance(v, date):
            out.append(_s_date(v))
        elif v is None:
            out.append("" if name in ("score", "prestige") else UNKLAR)
        elif isinstance(v, bool):
            out.append(_s_bool(v))
        elif isinstance(v, float):
            out.append(_s_num(v))
        else:
            out.append(str(v))
    return out


def _p_bool(s: str) -> bool | None:
    s = (s or "").strip().lower()
    if s in ("ja", "true", "wahr", "1"):
        return True
    if s in ("nein", "false", "falsch", "0"):
        return False
    return None


def _p_int(s: str) -> int | None:
    try:
        return int(float(str(s).strip().replace(",", ".")))
    except ValueError:
        return None


def _p_float(s: str) -> float | None:
    try:
        return float(str(s).strip().replace(",", "."))
    except ValueError:
        return None


def _p_list(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split("|") if x.strip()]


def _choice(s: str, allowed: list[str], default: str) -> str:
    s = (s or "").strip().lower()
    return s if s in allowed else default


def from_row(row: dict[str, Any]) -> Opportunity:
    """Baut eine Opportunity aus einer Sheet-Zeile (Spaltenname -> Text).

    Der Nutzer darf im Sheet tippen, deshalb ist alles fehlertolerant.
    """
    def g(key: str) -> str:
        return str(row.get(key, "") or "")

    return Opportunity(
        id=g("id"),
        title=g("title"),
        organizer=g("organizer"),
        url=g("url"),
        category=_choice(g("category"), CATEGORIES, "sonstiges"),
        target=_choice(g("target"), TARGETS, "person"),
        format=_choice(g("format"), FORMATS, "praesenz"),
        location_city=g("location_city") if g("location_city") != UNKLAR else "",
        location_country=g("location_country") if g("location_country") != UNKLAR else "",
        event_start=parse_date(g("event_start")),
        event_end=parse_date(g("event_end")),
        deadline=parse_date(g("deadline")),
        recurring_yearly=_p_bool(g("recurring_yearly")),
        age_min=_p_int(g("age_min")),
        age_max=_p_int(g("age_max")),
        eligibility=g("eligibility"),
        required_docs=g("required_docs"),
        language=_choice(g("language"), LANGUAGES, "andere"),
        fee_eur=_p_float(g("fee_eur")),
        travel_covered=_choice(g("travel_covered"), TRAVEL, "unklar"),
        fully_funded=_p_bool(g("fully_funded")),
        requires_legal_entity=_p_bool(g("requires_legal_entity")),
        benefits=[b for b in _p_list(g("benefits")) if b in BENEFITS],
        prestige=_p_int(g("prestige")),
        effort=_choice(g("effort"), EFFORTS, "mittel"),
        score=_p_int(g("score")),
        score_reason=g("score_reason"),
        warnings=_p_list(g("warnings")),
        status=_choice(g("status"), STATUSES, "neu"),
        notes=g("notes"),
        first_seen=parse_date(g("first_seen")),
        last_checked=parse_date(g("last_checked")),
        subject=g("subject") if g("subject") != UNKLAR else "",
        regional=_p_bool(g("regional")),
    )
