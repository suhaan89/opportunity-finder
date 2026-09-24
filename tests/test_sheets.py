"""Tests für Speicher-Logik, lokalen Speicher und den Sheets-Speicher (mit Attrappe)."""
from datetime import date

import gspread
from pathlib import Path

from src.models import COLUMNS, Opportunity
from src.sheets import (
    LOG_COLUMNS, LocalStore, SheetStore, Tables, add_new, archive_expired, open_store, touch_seen,
)

HEUTE = date(2026, 9, 24)


def opp(id_, **kw):
    return Opportunity(id=id_, title="T" + id_, **kw)


def test_neue_eintraege_werden_einsortiert():
    t = Tables()
    add_new(t, [opp("1"), opp("2", target="projekt")])
    assert [o.id for o in t.aktiv] == ["1"] and [o.id for o in t.projekte] == ["2"]


def test_archivieren_abgelaufener():
    t = Tables(aktiv=[opp("alt", deadline=date(2026, 1, 1)), opp("neu", deadline=date(2027, 1, 1))],
               projekte=[opp("palt", deadline=date(2026, 9, 1), target="projekt")])
    assert archive_expired(t, HEUTE) == 2
    assert [o.id for o in t.aktiv] == ["neu"]
    assert sorted(o.id for o in t.archiv) == ["alt", "palt"]
    assert t.projekte == []


def test_touch_seen():
    t = Tables(aktiv=[opp("1"), opp("2")])
    touch_seen(t, {"1"}, HEUTE)
    assert t.aktiv[0].last_checked == HEUTE and t.aktiv[1].last_checked is None


def test_localstore_rundreise(tmp_path):
    s = LocalStore(tmp_path / "store.json")
    assert s.load().aktiv == []
    t = Tables(aktiv=[opp("1", deadline=date(2027, 1, 1), score=80)], archiv=[opp("2")])
    s.save(t)
    s.log({"datum": "2026-09-24", "kandidaten": 5})
    geladen = s.load()
    assert geladen.aktiv == t.aktiv and geladen.archiv == t.archiv
    assert len(geladen.all_known()) == 2


# ---------- Attrappe für gspread ----------

class FakeWorksheet:
    def __init__(self, title):
        self.title, self.id, self.values = title, 1, []

    def update(self, values, range_name="A1", value_input_option=None):
        self.values = [list(r) for r in values]

    def clear(self):
        self.values = []

    def get_all_values(self):
        return self.values

    def append_row(self, row, value_input_option=None):
        self.values.append(list(row))


class FakeSpreadsheet:
    def __init__(self):
        self.tabs = {}

    def worksheet(self, name):
        if name not in self.tabs:
            raise gspread.WorksheetNotFound(name)
        return self.tabs[name]

    def add_worksheet(self, title, rows, cols):
        self.tabs[title] = FakeWorksheet(title)
        return self.tabs[title]

    def batch_update(self, body):
        pass


def test_sheetstore_rundreise_und_log():
    sh = FakeSpreadsheet()
    s = SheetStore(sh)
    t = Tables(aktiv=[opp("1", deadline=date(2027, 1, 1), notes="meine Notiz, mit Komma")],
               projekte=[opp("2", target="projekt")])
    s.save(t)
    assert sh.tabs["Aktiv"].values[0] == COLUMNS
    geladen = s.load()
    assert geladen.aktiv == t.aktiv and geladen.projekte == t.projekte
    s.log({"datum": "2026-09-24", "kandidaten": 7})
    assert sh.tabs["Log"].values[0] == LOG_COLUMNS
    assert sh.tabs["Log"].values[1][LOG_COLUMNS.index("kandidaten")] == "7"


def test_open_store_ohne_zugangsdaten_ist_lokal(monkeypatch):
    for k in ("SHEET_ID", "GOOGLE_SERVICE_ACCOUNT_JSON"):
        monkeypatch.delenv(k, raising=False)
    # falls lokal eine service_account.json liegt, darf der Test nicht davon abhängen
    monkeypatch.setattr("src.sheets.ROOT", Path("/nonexistent"))
    store, echt = open_store()
    assert isinstance(store, LocalStore) and not echt
