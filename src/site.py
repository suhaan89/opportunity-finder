"""GitHub-Pages-Generator: eine statische, ÖFFENTLICHE Seite mit allen aktiven Angeboten.

DATENSCHUTZ: Auf die Seite kommen nur öffentliche Angebotsdaten. Nie Score, Status, Notizen,
Warnungen oder Profildaten. Die Auswahl der Felder passiert in `public_view` (eine Positivliste).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Iterable

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import ROOT
from .models import Opportunity

SITE_DIR = ROOT / "public_site"

CATEGORY_LABELS = {
    "stipendium": "Stipendium", "wettbewerb": "Wettbewerb", "hackathon": "Hackathon",
    "akademie": "Akademie", "networking": "Networking", "jugendforum": "Jugendforum",
    "uni_programm": "Uni-Programm", "projektfoerderung": "Projektförderung", "sonstiges": "Sonstiges",
}
FORMAT_LABELS = {"praesenz": "Präsenz", "online": "Online", "hybrid": "Hybrid"}
TRAVEL_LABELS = {"ja": "Voll übernommen", "teilweise": "Teilweise", "nein": "Nicht übernommen", "unklar": "Unklar"}
BENEFIT_LABELS = {
    "geld": "Geld", "mentoring": "Mentoring", "netzwerk": "Netzwerk", "zertifikat": "Zertifikat",
    "credits": "Credits", "hardware": "Hardware", "inkubator": "Inkubator", "preis": "Preis",
}


def _date_text(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else ""


def public_view(o: Opportunity) -> dict[str, Any]:
    """Positivliste: NUR diese Felder dürfen auf die öffentliche Seite."""
    if o.fee_eur is None:
        fee = "Gebühr unklar"
    else:
        fee = "kostenlos" if o.fee_eur == 0 else f"{o.fee_eur:g} €"
    funding = ["voll finanziert"] if o.fully_funded else []
    return {
        "title": o.title,
        "organizer": o.organizer,
        "url": o.url if o.url.startswith(("http://", "https://")) else "#",
        "category": o.category,
        "category_label": CATEGORY_LABELS.get(o.category, o.category),
        "format": o.format,
        "format_label": FORMAT_LABELS.get(o.format, o.format),
        "city": o.location_city,
        "country": o.location_country,
        "deadline_iso": o.deadline.isoformat() if o.deadline else "",
        "deadline_text": _date_text(o.deadline) or "unklar",
        "event_text": " – ".join(t for t in (_date_text(o.event_start), _date_text(o.event_end)) if t),
        "fee": fee,
        "free": o.fee_eur == 0,
        "travel": o.travel_covered,
        "travel_label": TRAVEL_LABELS.get(o.travel_covered, "Unklar"),
        "funding": funding,
        "benefits": list(o.benefits),
        "benefit_labels": [BENEFIT_LABELS.get(b, b) for b in o.benefits],
        "eligibility": o.eligibility,
    }


def select_public(entries: Iterable[Opportunity]) -> list[Opportunity]:
    """Alles Aktive, außer was du im Sheet auf 'ignoriert' gesetzt hast. Nach Deadline sortiert."""
    result = [o for o in entries if o.status != "ignoriert"]
    result.sort(key=lambda o: (o.deadline is None, o.deadline or date.max, o.title.lower()))
    return result


def build_site(entries: Iterable[Opportunity], today: date, out_dir: Path | None = None) -> Path:
    """Schreibt index.html (und .nojekyll) in den Ausgabeordner und gibt den Pfad zurück."""
    out = out_dir or SITE_DIR
    out.mkdir(parents=True, exist_ok=True)
    items = [public_view(o) for o in select_public(entries)]
    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html", "j2"], default=True),
    )
    html = env.get_template("site.html.j2").render(
        items=items,
        stand=today.strftime("%d.%m.%Y"),
        today_iso=today.isoformat(),
        categories=sorted({(i["category"], i["category_label"]) for i in items}, key=lambda c: c[1]),
        countries=sorted({i["country"] for i in items if i["country"]}),
        benefit_options=sorted({(b, BENEFIT_LABELS.get(b, b)) for i in items for b in i["benefits"]}, key=lambda b: b[1]),
    )
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return out / "index.html"
