"""Einrichtungs-Check: Was ist schon eingerichtet, was fehlt noch?

Aufruf:
  python -m src.check          zeigt nur, welche Werte gesetzt sind (Namen, nie die Werte)
  python -m src.check --live   testet zusätzlich die echten Verbindungen (Gemini, Sheet, SMTP-Login, Gmail-Token)

Es wird nichts verschickt und nichts verändert. Ausgegeben werden nur "ok"/"FEHLT"/"FEHLER" und
der Fehlertyp, nie Schlüssel, Passwörter oder Inhalte.
"""
from __future__ import annotations

import os
import smtplib
import sys
from typing import Callable

from .config import ROOT, load_settings
from .main import load_dotenv

# Gruppe -> Namen der Werte (aus SPEC Abschnitt 11)
GROUPS: dict[str, list[str]] = {
    "Gemini (Phase 1)": ["GEMINI_API_KEY"],
    "Google Sheet (Phase 1)": ["GOOGLE_SERVICE_ACCOUNT_JSON", "SHEET_ID"],
    "E-Mail (Phase 1)": ["SMTP_USER", "SMTP_APP_PASSWORD", "MAIL_TO"],
    "Kalender-Gist (Phase 2)": ["GIST_TOKEN", "GIST_ID"],
    "Gmail lesen (Phase 3)": ["GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"],
}


def is_set(name: str) -> bool:
    """Gesetzt? Für den Service-Account zählt auch die lokale Datei service_account.json."""
    if os.environ.get(name, "").strip():
        return True
    if name == "GOOGLE_SERVICE_ACCOUNT_JSON":
        return (ROOT / "service_account.json").exists()
    if name == "MAIL_TO":  # ohne MAIL_TO geht die Mail an SMTP_USER
        return bool(os.environ.get("SMTP_USER", "").strip())
    return False


def status_report() -> tuple[list[str], int]:
    """Gibt (Zeilen, Anzahl fehlender Pflichtwerte der Phase 1) zurück."""
    lines: list[str] = []
    missing_core = 0
    for group, names in GROUPS.items():
        fehlend = [n for n in names if not is_set(n)]
        lines.append(f"{'ok    ' if not fehlend else 'FEHLT '} {group}" + (f": {', '.join(fehlend)}" if fehlend else ""))
        if "Phase 1" in group:
            missing_core += len(fehlend)
    profil = "PROFILE_YAML" if os.environ.get("PROFILE_YAML", "").strip() else (
        "profile.yaml" if (ROOT / "profile.yaml").exists() else None)
    lines.append(f"{'ok    ' if profil else 'FEHLT '} Profil" + (f" (aus {profil})" if profil else ": profile.yaml oder PROFILE_YAML"))
    return lines, missing_core


# ---------- Live-Tests (jeweils: ok oder Fehlertyp) ----------

def _live_gemini() -> None:
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    client.models.generate_content(model=load_settings()["gemini"]["model"], contents="Antworte nur mit: ok")


def _live_sheet() -> None:
    from .sheets import SheetStore, open_store

    store, echt = open_store()
    if not echt:
        raise RuntimeError("kein Sheet-Zugang")
    assert isinstance(store, SheetStore)
    store.load()  # legt die Tabs an, falls sie fehlen


def _live_smtp() -> None:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_APP_PASSWORD"])


def _live_gmail() -> None:
    from .gmail_reader import GmailReader

    reader = GmailReader.from_env()
    if reader is None:
        raise RuntimeError("Gmail-Werte fehlen")
    reader._token()


LIVE_TESTS: list[tuple[str, list[str], Callable[[], None]]] = [
    ("Gemini-Key und Modellname", ["GEMINI_API_KEY"], _live_gemini),
    ("Google Sheet erreichbar", ["GOOGLE_SERVICE_ACCOUNT_JSON", "SHEET_ID"], _live_sheet),
    ("Gmail-SMTP-Login", ["SMTP_USER", "SMTP_APP_PASSWORD"], _live_smtp),
    ("Gmail-Lesezugriff (Token)", ["GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"], _live_gmail),
]


def run_live() -> list[str]:
    lines = []
    for name, needs, test in LIVE_TESTS:
        if not all(is_set(n) for n in needs):
            lines.append(f"---    {name}: übersprungen (Werte fehlen)")
            continue
        try:
            test()
            lines.append(f"ok     {name}")
        except Exception as exc:  # noqa: BLE001 - nur der Fehlertyp wird gezeigt
            lines.append(f"FEHLER {name}: {type(exc).__name__}")
    return lines


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    lines, missing_core = status_report()
    print("Was ist eingerichtet?")
    print("\n".join(lines))
    failed = 0
    if "--live" in args:
        print("\nVerbindungstests:")
        live = run_live()
        print("\n".join(live))
        failed = sum(1 for line in live if line.startswith("FEHLER"))
    elif missing_core == 0:
        print("\nTipp: Mit --live werden die Verbindungen wirklich getestet.")
    return 1 if (missing_core or failed) else 0


if __name__ == "__main__":
    sys.exit(main())
