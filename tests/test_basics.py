"""Tests für Hilfsfunktionen, Profil und Datenmodell."""
from datetime import date

from src.models import COLUMNS, Opportunity, from_row, to_row
from src.profile import age_on
from src.util import make_id, normalize_url, parse_date, safe_error


def test_normalize_url_entfernt_tracking_und_anker():
    a = normalize_url("http://www.Example.org/Programm/?utm_source=x&b=2&a=1#kontakt")
    b = normalize_url("https://example.org/Programm?a=1&b=2")
    assert a == b


def test_id_gleich_fuer_gleiche_seite():
    assert make_id("https://example.org/x/") == make_id("http://www.example.org/x?utm_campaign=1")
    assert make_id("https://example.org/x") != make_id("https://example.org/y")


def test_parse_date():
    assert parse_date("2026-12-31") == date(2026, 12, 31)
    assert parse_date("unklar") is None
    assert parse_date("31.12.2026") is None
    assert parse_date("2026-02-31") is None


def test_alter_am_stichtag():
    profil = {"geburtsdatum": date(2010, 9, 20)}
    assert age_on(profil, date(2026, 9, 19)) == 15
    assert age_on(profil, date(2026, 9, 20)) == 16
    assert age_on({}, date(2026, 9, 20)) is None


def test_zeile_rundreise():
    o = Opportunity(
        id="abc", title="Sommerakademie", url="https://example.org",
        deadline=date(2026, 11, 1), fee_eur=99.5, fully_funded=True,
        benefits=["geld", "netzwerk"], warnings=["Reisekosten unklar", "a, b"],
        score=77, status="interessant", regional=False,
    )
    row = dict(zip(COLUMNS, to_row(o)))
    o2 = from_row(row)
    assert o2 == o


def test_zeile_mit_unklar_und_kaputtem_status():
    row = dict(zip(COLUMNS, to_row(Opportunity(id="x", title="T"))))
    row["status"] = "quatsch"
    row["deadline"] = "irgendwann"
    o = from_row(row)
    assert o.status == "neu" and o.deadline is None and o.fee_eur is None


def test_safe_error_zeigt_keine_meldung():
    text = safe_error("sheets", ValueError("geheimes passwort"))
    assert "geheim" not in text and "ValueError" in text


def test_beispielprofil_ist_gueltiges_yaml():
    """Das Beispielprofil muss lesbar sein und die wichtigen Schlüssel haben."""
    import yaml
    from src.config import CONFIG_DIR
    profil = yaml.safe_load((CONFIG_DIR / "profile.example.yaml").read_text(encoding="utf-8"))
    for key in ("geburtsdatum", "interessen_punkte", "kriterien", "netzwerke", "projekte", "projekte_bedarf"):
        assert key in profil
    assert abs(sum(profil["interessen_punkte"].values()) - 100) < 1e-9
