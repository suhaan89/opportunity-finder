"""Tests für Reminder, Kalender-Feed und öffentliche Seite."""
from datetime import date, datetime, timezone

from src.ics import build_ics, publish_gist, write_local, _fold
from src.models import Opportunity
from src.reminders import deadline_reminders
from src.site import build_site, public_view, select_public

HEUTE = date(2026, 9, 24)


def opp(id_, **kw):
    return Opportunity(id=id_, title=f"Titel {id_}", url=f"https://example.org/{id_}", **kw)


# ---------- Reminder ----------

def test_reminder_nur_bei_status_und_genau_7_oder_2_tagen():
    eintraege = [
        opp("a", status="interessant", deadline=date(2026, 10, 1)),        # in 7 Tagen -> ja
        opp("b", status="in_vorbereitung", deadline=date(2026, 9, 26)),    # in 2 Tagen -> ja
        opp("c", status="neu", deadline=date(2026, 10, 1)),                # falscher Status
        opp("d", status="interessant", deadline=date(2026, 9, 30)),        # in 6 Tagen -> nein
        opp("e", status="interessant", deadline=None),                     # keine Deadline
        opp("f", status="beworben", deadline=date(2026, 9, 26)),           # schon beworben
    ]
    r = deadline_reminders(eintraege, HEUTE, [7, 2])
    assert [(o.id, d) for o, d in r] == [("b", 2), ("a", 7)]


# ---------- ICS ----------

def test_ics_enthaelt_nur_verfolgte_eintraege():
    eintraege = [
        opp("a", status="interessant", deadline=date(2026, 12, 1), event_start=date(2027, 2, 1), event_end=date(2027, 2, 5)),
        opp("b", status="neu", deadline=date(2026, 12, 2)),
        opp("c", status="zusage", event_start=date(2027, 3, 3)),
        opp("d", status="ignoriert", deadline=date(2026, 12, 3)),
    ]
    ics = build_ics(eintraege, datetime(2026, 9, 24, 5, 0, tzinfo=timezone.utc))
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert ics.count("BEGIN:VEVENT") == 3          # Deadline + Event von a, Event von c
    assert "UID:a-deadline@opportunity-finder" in ics
    assert "DTSTART;VALUE=DATE:20261201" in ics and "DTEND;VALUE=DATE:20261202" in ics
    assert "DTSTART;VALUE=DATE:20270201" in ics and "DTEND;VALUE=DATE:20270206" in ics  # Ende inklusive
    assert "Titel b" not in ics and "Titel d" not in ics
    assert "DTSTAMP:20260924T050000Z" in ics


def test_ics_maskiert_sonderzeichen_und_bricht_lange_zeilen():
    o = opp("a", status="interessant", deadline=date(2026, 12, 1))
    o.title = "A, B; C\\D " + "x" * 200
    ics = build_ics([o], datetime(2026, 9, 24, tzinfo=timezone.utc))
    assert "A\\, B\\; C\\\\D" in ics
    for zeile in ics.split("\r\n"):
        assert len(zeile.encode("utf-8")) <= 75
    assert _fold("kurz") == "kurz"


def test_ics_datei_und_gist(tmp_path, monkeypatch):
    pfad = write_local("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", tmp_path)
    assert pfad.read_bytes().startswith(b"BEGIN:VCALENDAR\r\n")

    gesehen = {}

    class Antwort:
        def raise_for_status(self):
            gesehen["geprueft"] = True

    def fake_patch(url, headers, json, timeout):
        gesehen.update(url=url, auth=headers["Authorization"], dateien=list(json["files"]))
        return Antwort()

    monkeypatch.setattr("src.ics.requests.patch", fake_patch)
    publish_gist("x", "TOKEN", "GISTID")
    assert gesehen["url"].endswith("/gists/GISTID") and gesehen["dateien"] == ["opportunities.ics"]
    assert gesehen["geprueft"]


# ---------- Seite ----------

def test_public_view_hat_keine_privaten_felder():
    o = opp("a", score=91, score_reason="GEHEIMER GRUND", status="interessant", notes="MEINE NOTIZ",
            warnings=["Reisekosten unklar"], prestige=95, deadline=date(2026, 12, 1), fee_eur=0)
    view = public_view(o)
    text = str(view)
    for privat in ("GEHEIMER", "interessant", "MEINE NOTIZ", "Reisekosten"):
        assert privat not in text
    assert set(view) == {
        "title", "organizer", "url", "category", "category_label", "format", "format_label", "city",
        "country", "deadline_iso", "deadline_text", "event_text", "fee", "funding", "benefits", "eligibility",
    }


def test_seite_wird_gebaut_ohne_private_daten(tmp_path):
    eintraege = [
        opp("a", score=91, score_reason="GEHEIMER GRUND", status="interessant", notes="MEINE NOTIZ",
            warnings=["Reisekosten unklar"], deadline=date(2026, 12, 1), category="stipendium",
            location_country="Schweiz", fully_funded=True),
        opp("b", status="ignoriert"),
        opp("c", deadline=None, format="online"),
    ]
    pfad = build_site(eintraege, HEUTE, tmp_path)
    html = pfad.read_text(encoding="utf-8")
    assert "Titel a" in html and "Titel c" in html and "Titel b" not in html   # ignoriert fehlt
    for privat in ("GEHEIMER GRUND", "MEINE NOTIZ", "Reisekosten unklar", "91/100"):
        assert privat not in html
    assert "Schweiz" in html and "voll finanziert" in html
    assert (tmp_path / ".nojekyll").exists()


def test_seite_maskiert_html():
    o = opp("a", deadline=date(2026, 12, 1))
    o.title = "<img src=x onerror=alert(1)>"
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        html = build_site([o], HEUTE, pathlib.Path(d)).read_text(encoding="utf-8")
    assert "<img src=x" not in html and "&lt;img" in html


def test_sortierung_nach_deadline_unklar_zuletzt():
    liste = select_public([opp("z"), opp("b", deadline=date(2026, 12, 5)), opp("a", deadline=date(2026, 11, 1))])
    assert [o.id for o in liste] == ["a", "b", "z"]
