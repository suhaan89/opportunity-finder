"""Speicher: Google Sheets (privat) als Datenbank, plus lokaler Ersatz für Tests ohne Zugangsdaten.

Tabs (SPEC Abschnitt 4): Aktiv, Archiv, Projekte (target = projekt), Log (nur technische Zähler).

Wichtig: Beim Speichern schreiben wir die Tabs komplett neu. Änderungen, die du im Sheet
GENAU WÄHREND eines laufenden Pipeline-Laufs machst, können dadurch verloren gehen
(der Lauf dauert nur wenige Minuten, nachts um 05:00 UTC).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from .config import ROOT
from .filters import filter_deadline_vorbei
from .models import COLUMNS, STATUSES, Opportunity, from_row, to_row

TAB_AKTIV, TAB_ARCHIV, TAB_PROJEKTE, TAB_LOG = "Aktiv", "Archiv", "Projekte", "Log"

# Log-Spalten: NUR Zähler, niemals Inhalte (die Actions-Logs und das Sheet-Log sollen unkritisch sein)
LOG_COLUMNS = [
    "datum", "suchanfragen", "quellen", "mails", "kandidaten", "erreichbar", "extrahiert",
    "duplikate", "gefiltert", "bewertet", "neu_gespeichert", "archiviert", "gemini_aufrufe", "fehler",
]


@dataclass
class Tables:
    """Alle Einträge im Speicher (im Arbeitsspeicher während des Laufs)."""
    aktiv: list[Opportunity] = field(default_factory=list)
    archiv: list[Opportunity] = field(default_factory=list)
    projekte: list[Opportunity] = field(default_factory=list)

    def all_known(self) -> list[Opportunity]:
        """Alles, was wir schon kennen (auch Archiv, damit Altes nicht wiederkommt)."""
        return self.aktiv + self.projekte + self.archiv


class Store(Protocol):
    def load(self) -> Tables: ...
    def save(self, tables: Tables) -> None: ...
    def log(self, counts: dict[str, int]) -> None: ...


# ---------- Logik auf den Tabellen (ohne Speicherzugriff, gut testbar) ----------

def add_new(tables: Tables, opps: list[Opportunity]) -> None:
    """Neue Einträge einsortieren: Projektförderung in 'Projekte', alles andere in 'Aktiv'."""
    for o in opps:
        (tables.projekte if o.target == "projekt" else tables.aktiv).append(o)


def touch_seen(tables: Tables, known_ids: set[str], today: date) -> None:
    """Setzt last_checked für alles, was in diesem Lauf wieder gefunden wurde."""
    for o in tables.aktiv + tables.projekte:
        if o.id in known_ids:
            o.last_checked = today


def archive_expired(tables: Tables, today: date) -> int:
    """Verschiebt abgelaufene Einträge (Deadline/Event vorbei) ins Archiv. Gibt die Anzahl zurück."""
    moved = 0
    for name in ("aktiv", "projekte"):
        rest: list[Opportunity] = []
        for o in getattr(tables, name):
            if filter_deadline_vorbei(o, {}, today):
                tables.archiv.append(o)
                moved += 1
            else:
                rest.append(o)
        setattr(tables, name, rest)
    return moved


def _log_row(counts: dict[str, int]) -> list[str]:
    return [str(int(counts.get(c, 0))) if c != "datum" else str(counts.get(c, "")) for c in LOG_COLUMNS]


# ---------- lokaler Ersatzspeicher (JSON-Datei, steht in .gitignore) ----------

class LocalStore:
    """Für Tests und lokale Läufe ohne Google-Zugang. Datei liegt in out/ (nicht im Repo)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or ROOT / "out" / "store.json"

    def _read(self) -> dict[str, Any]:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {}

    def load(self) -> Tables:
        raw = self._read()

        def conv(name: str) -> list[Opportunity]:
            return [from_row(dict(zip(COLUMNS, r))) for r in raw.get(name, [])]

        return Tables(conv(TAB_AKTIV), conv(TAB_ARCHIV), conv(TAB_PROJEKTE))

    def save(self, tables: Tables) -> None:
        raw = self._read()
        raw[TAB_AKTIV] = [to_row(o) for o in tables.aktiv]
        raw[TAB_ARCHIV] = [to_row(o) for o in tables.archiv]
        raw[TAB_PROJEKTE] = [to_row(o) for o in tables.projekte]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    def log(self, counts: dict[str, int]) -> None:
        raw = self._read()
        raw.setdefault(TAB_LOG, []).append(_log_row(counts))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")


# ---------- Google Sheets ----------

class SheetStore:
    """Echter Speicher in Google Sheets. `spreadsheet` ist ein gspread-Spreadsheet (oder eine Attrappe)."""

    def __init__(self, spreadsheet: Any) -> None:
        self.sh = spreadsheet

    def _worksheet(self, name: str, header: list[str]) -> Any:
        """Holt ein Tab oder legt es mit Kopfzeile an."""
        import gspread

        try:
            return self.sh.worksheet(name)
        except gspread.WorksheetNotFound:
            ws = self.sh.add_worksheet(title=name, rows=1000, cols=len(header))
            ws.update(values=[header], range_name="A1", value_input_option="RAW")
            if name in (TAB_AKTIV, TAB_PROJEKTE):
                self._status_dropdown(ws)
            return ws

    def _status_dropdown(self, ws: Any) -> None:
        """Dropdown für die Spalte 'status', damit du nur gültige Werte auswählen kannst (best effort)."""
        try:
            col = COLUMNS.index("status")
            self.sh.batch_update({"requests": [{"setDataValidation": {
                "range": {"sheetId": ws.id, "startRowIndex": 1, "startColumnIndex": col, "endColumnIndex": col + 1},
                "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": s} for s in STATUSES]},
                         "showCustomUi": True, "strict": False},
            }}]})
        except Exception:  # noqa: BLE001 - reine Komfortfunktion
            pass

    def _read_tab(self, name: str) -> list[Opportunity]:
        ws = self._worksheet(name, COLUMNS)
        values = ws.get_all_values()
        if len(values) < 2:
            return []
        header = values[0]
        rows = [dict(zip(header, r)) for r in values[1:]]
        return [from_row(r) for r in rows if r.get("id")]

    def _write_tab(self, name: str, opps: list[Opportunity]) -> None:
        ws = self._worksheet(name, COLUMNS)
        ws.clear()
        ws.update(values=[COLUMNS] + [to_row(o) for o in opps], range_name="A1", value_input_option="RAW")

    def load(self) -> Tables:
        return Tables(self._read_tab(TAB_AKTIV), self._read_tab(TAB_ARCHIV), self._read_tab(TAB_PROJEKTE))

    def save(self, tables: Tables) -> None:
        self._write_tab(TAB_AKTIV, tables.aktiv)
        self._write_tab(TAB_ARCHIV, tables.archiv)
        self._write_tab(TAB_PROJEKTE, tables.projekte)

    def log(self, counts: dict[str, int]) -> None:
        ws = self._worksheet(TAB_LOG, LOG_COLUMNS)
        ws.append_row(_log_row(counts), value_input_option="RAW")


def open_store() -> tuple[Store, bool]:
    """Wählt den Speicher: Google Sheets, wenn Zugangsdaten da sind, sonst lokal.

    Gibt (Speicher, ist_echt) zurück. Zugangsdaten: GOOGLE_SERVICE_ACCOUNT_JSON (Text) oder
    Datei service_account.json, dazu SHEET_ID.
    """
    sheet_id = os.environ.get("SHEET_ID", "").strip()
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    local_file = ROOT / "service_account.json"
    if not raw and local_file.exists():
        raw = local_file.read_text(encoding="utf-8")
    if not (sheet_id and raw):
        return LocalStore(), False
    import gspread

    gc = gspread.service_account_from_dict(json.loads(raw))
    return SheetStore(gc.open_by_key(sheet_id)), True
