"""E-Mail: Inhalt zusammenstellen, als HTML rendern und über Gmail SMTP verschicken.

Versand mit App-Passwort (SMTP_USER / SMTP_APP_PASSWORD / MAIL_TO). Sind die nicht gesetzt,
wird die Mail stattdessen nach out/mail.html geschrieben (zum Ansehen im Browser).
Es wird nur gemailt, wenn es etwas Neues oder einen Deadline-Reminder gibt.
"""
from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass, field
from datetime import date
from email.message import EmailMessage
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import ROOT
from .models import Opportunity


OUT_DIR = ROOT / "out"  # hierhin wird die Mail geschrieben, wenn kein SMTP-Zugang da ist


@dataclass
class MailContent:
    top: list[Opportunity] = field(default_factory=list)          # neue Top-Matches (Personen)
    projects: list[Opportunity] = field(default_factory=list)     # neue Projektförderungen
    reminders: list[tuple[Opportunity, int]] = field(default_factory=list)  # (Eintrag, Tage bis Deadline)

    def is_empty(self) -> bool:
        return not (self.top or self.projects or self.reminders)


def build_mail_content(
    new_opps: list[Opportunity], reminders: list[tuple[Opportunity, int]], min_score: int
) -> MailContent:
    """Wählt aus den NEUEN Einträgen die aus, die die Score-Schwelle erreichen."""
    good = sorted(
        (o for o in new_opps if (o.score or 0) >= min_score), key=lambda o: o.score or 0, reverse=True
    )
    return MailContent(
        top=[o for o in good if o.target != "projekt"],
        projects=[o for o in good if o.target == "projekt"],
        reminders=reminders,
    )


# ---------- Darstellung ----------

def _date_text(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else "unklar"


def _place_text(o: Opportunity) -> str:
    if o.format == "online":
        return "Online"
    place = ", ".join(p for p in (o.location_city, o.location_country) if p)
    return f"{place or 'Ort unklar'}" + (" (hybrid)" if o.format == "hybrid" else "")


def _money_text(o: Opportunity) -> str:
    fee = "Gebühr unklar" if o.fee_eur is None else ("kostenlos" if o.fee_eur == 0 else f"{o.fee_eur:g} € Gebühr")
    parts = [fee]
    if o.fully_funded:
        parts.append("voll finanziert")
    if o.travel_covered != "unklar":
        parts.append(f"Reise: {o.travel_covered}")
    if o.benefits:
        parts.append(", ".join(o.benefits))
    return " · ".join(parts)


def _view(o: Opportunity) -> dict[str, Any]:
    """Eintrag + fertige Anzeige-Texte für die Vorlage."""
    url = o.url if o.url.startswith(("http://", "https://")) else "#"
    return {
        "title": o.title, "organizer": o.organizer, "url": url, "score": o.score,
        "score_reason": o.score_reason, "deadline_text": _date_text(o.deadline),
        "place_text": _place_text(o), "money_text": _money_text(o),
        "eligibility": o.eligibility, "effort": o.effort, "warnings": o.warnings,
    }


def render_email(content: MailContent, today: date) -> tuple[str, str]:
    """Gibt (Betreff, HTML) zurück. Der Betreff enthält nur Zahlen, keine Inhalte."""
    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html", "j2"], default=True),
    )
    n = len(content.top) + len(content.projects)
    parts = []
    if n:
        parts.append(f"{n} neue Treffer")
    if content.reminders:
        parts.append(f"{len(content.reminders)} Deadline(s) bald")
    subject = "Opportunity-Finder: " + " · ".join(parts)
    html = env.get_template("email.html.j2").render(
        subject=subject,
        datum=today.strftime("%d.%m.%Y"),
        top=[_view(o) for o in content.top],
        projects=[_view(o) for o in content.projects],
        reminders=[(_view(o), d) for o, d in content.reminders],
    )
    return subject, html


def send_email(subject: str, html: str, out_dir: Any = None) -> bool:
    """Verschickt die Mail. True = wirklich gesendet, False = nur lokal gespeichert (kein SMTP-Zugang)."""
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_APP_PASSWORD", "").strip()
    to = os.environ.get("MAIL_TO", "").strip() or user
    if not (user and password and to):
        out = out_dir or OUT_DIR
        out.mkdir(parents=True, exist_ok=True)
        (out / "mail.html").write_text(html, encoding="utf-8")
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content("Diese Mail braucht ein Programm, das HTML anzeigen kann.")
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    return True
