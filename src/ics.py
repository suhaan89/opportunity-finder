"""Kalender-Feed (.ics) mit Deadlines und Eventterminen deiner verfolgten Einträge.

Nur Einträge mit Status interessant, in_vorbereitung, beworben oder zusage kommen hinein.
Der Feed wird als SECRET Gist gehostet (nicht öffentlich gelistet). Den Link fügst du einmal
in Google Kalender ein ("Kalender hinzufügen" -> "Per URL").
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import requests

from .config import ROOT
from .models import CALENDAR_STATUSES, Opportunity

OUT_DIR = ROOT / "out"
GIST_FILENAME = "opportunities.ics"


def _escape(text: str) -> str:
    """Sonderzeichen nach RFC 5545 maskieren."""
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Zeilen dürfen höchstens 75 Bytes lang sein; längere werden umgebrochen (Folgezeile beginnt mit Leerzeichen)."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts: list[str] = []
    current = b""
    limit = 75
    for ch in line:
        b = ch.encode("utf-8")
        if len(current) + len(b) > limit:
            parts.append(current.decode("utf-8"))
            current, limit = b"", 74  # Folgezeilen haben ein Leerzeichen vorn
        current += b
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def _d(d: date) -> str:
    return d.strftime("%Y%m%d")


def _event(uid: str, stamp: str, start: date, end_inclusive: date, summary: str, url: str, alarm: bool) -> list[str]:
    """Ein ganztägiger Termin (DTEND ist bei ganztägigen Terminen der Tag NACH dem Ende)."""
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}@opportunity-finder",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{_d(start)}",
        f"DTEND;VALUE=DATE:{_d(end_inclusive + timedelta(days=1))}",
        f"SUMMARY:{_escape(summary)}",
    ]
    if url.startswith(("http://", "https://")):
        lines.append(f"URL:{url}")
    if alarm:  # Erinnerung einen Tag vorher
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_escape(summary)}", "TRIGGER:-P1D", "END:VALARM"]
    lines.append("END:VEVENT")
    return lines


def build_ics(entries: Iterable[Opportunity], now: datetime | None = None) -> str:
    """Baut den kompletten Kalender-Text."""
    now = now or datetime.now(timezone.utc)
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//opportunity-finder//DE",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Opportunity-Finder",
        "X-WR-TIMEZONE:Europe/Berlin",
    ]
    for o in sorted(entries, key=lambda x: x.id):
        if o.status not in CALENDAR_STATUSES:
            continue
        if o.deadline:
            lines += _event(f"{o.id}-deadline", stamp, o.deadline, o.deadline, f"Deadline: {o.title}", o.url, True)
        if o.event_start:
            ende = o.event_end if o.event_end and o.event_end >= o.event_start else o.event_start
            lines += _event(f"{o.id}-event", stamp, o.event_start, ende, o.title, o.url, False)
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def write_local(ics: str, out_dir: Path | None = None) -> Path:
    out = out_dir or OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    path = out / GIST_FILENAME
    path.write_text(ics, encoding="utf-8", newline="")
    return path


def publish_gist(ics: str, token: str, gist_id: str, timeout: float = 30) -> None:
    """Aktualisiert die Datei im (geheimen) Gist. Wirft bei Fehlern eine Exception (Aufrufer fängt sie)."""
    resp = requests.patch(
        f"https://api.github.com/gists/{gist_id}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {GIST_FILENAME: {"content": ics}}},
        timeout=timeout,
    )
    resp.raise_for_status()
