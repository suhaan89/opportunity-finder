"""Tests für alle Filter (jeder Filter einzeln)."""
from datetime import date

from src.filters import (
    add_warnings, apply_post_score_filters, apply_pre_score_filters, filter_alter,
    filter_deadline_vorbei, filter_fach, filter_gebuehr, filter_land, filter_rechtsform,
    filter_reisekosten, filter_sperrzeitraum, filter_sprache,
)
from src.models import Opportunity

HEUTE = date(2026, 9, 24)

PROFIL = {
    "geburtsdatum": date(2010, 3, 15),
    "ausgeschlossene_laender": ["Indien", "Israel"],
    "ausgeschlossene_wettbewerbsfaecher": ["geschichte", "deutsch"],
    "kriterien": {
        "max_teilnahmegebuehr_eur": 150,
        "reisekosten_muessen_uebernommen_werden": True,
        "rechtsform_erforderlich_ausschliessen": True,
        "sperrzeitraeume": [{"von": date(2027, 3, 1), "bis": date(2027, 5, 5)}],
    },
}
SETTINGS = {"scoring": {"online_min_prestige": 85, "regional_min_prestige": 80}}


def opp(**kw) -> Opportunity:
    return Opportunity(id="x", title="Test", **kw)


def test_deadline_vorbei():
    assert filter_deadline_vorbei(opp(deadline=date(2026, 9, 23)), PROFIL, HEUTE) == "deadline_vorbei"
    assert filter_deadline_vorbei(opp(deadline=HEUTE), PROFIL, HEUTE) is None  # heute zählt noch
    assert filter_deadline_vorbei(opp(deadline=None), PROFIL, HEUTE) is None
    # ohne Deadline, aber Event schon vorbei
    assert filter_deadline_vorbei(opp(event_end=date(2026, 1, 1)), PROFIL, HEUTE) == "deadline_vorbei"


def test_alter_zum_eventdatum():
    # Geboren 2010-03-15: am 2027-01-01 ist die Person 16
    assert filter_alter(opp(event_start=date(2027, 1, 1), age_max=15), PROFIL, HEUTE) == "zu_alt"
    assert filter_alter(opp(event_start=date(2027, 1, 1), age_max=16), PROFIL, HEUTE) is None
    assert filter_alter(opp(event_start=date(2027, 1, 1), age_min=18), PROFIL, HEUTE) == "zu_jung"
    # am 2027-03-14 noch 16, am 2027-03-15 schon 17
    assert filter_alter(opp(event_start=date(2027, 3, 14), age_max=16), PROFIL, HEUTE) is None
    assert filter_alter(opp(event_start=date(2027, 3, 15), age_max=16), PROFIL, HEUTE) == "zu_alt"
    # kein Datum -> behalten
    assert filter_alter(opp(age_max=10), PROFIL, HEUTE) is None


def test_sprache():
    assert filter_sprache(opp(language="andere"), PROFIL, HEUTE) == "sprache"
    assert filter_sprache(opp(language="en"), PROFIL, HEUTE) is None


def test_land_auch_englische_schreibweise():
    assert filter_land(opp(location_country="India"), PROFIL, HEUTE) == "land"
    assert filter_land(opp(location_country="israel"), PROFIL, HEUTE) == "land"
    assert filter_land(opp(location_country="Deutschland"), PROFIL, HEUTE) is None
    assert filter_land(opp(location_country=""), PROFIL, HEUTE) is None


def test_gebuehr():
    assert filter_gebuehr(opp(fee_eur=151), PROFIL, HEUTE) == "gebuehr"
    assert filter_gebuehr(opp(fee_eur=150), PROFIL, HEUTE) is None
    assert filter_gebuehr(opp(fee_eur=None), PROFIL, HEUTE) is None


def test_reisekosten():
    assert filter_reisekosten(opp(travel_covered="nein"), PROFIL, HEUTE) == "reisekosten"
    assert filter_reisekosten(opp(travel_covered="unklar"), PROFIL, HEUTE) is None
    assert filter_reisekosten(opp(travel_covered="teilweise"), PROFIL, HEUTE) is None
    assert filter_reisekosten(opp(travel_covered="nein", format="online"), PROFIL, HEUTE) is None


def test_rechtsform():
    assert filter_rechtsform(opp(requires_legal_entity=True), PROFIL, HEUTE) == "rechtsform"
    assert filter_rechtsform(opp(requires_legal_entity=False), PROFIL, HEUTE) is None
    assert filter_rechtsform(opp(requires_legal_entity=None), PROFIL, HEUTE) is None


def test_sperrzeitraum():
    assert filter_sperrzeitraum(opp(event_start=date(2027, 4, 1)), PROFIL, HEUTE) == "sperrzeitraum"
    # Event beginnt davor, reicht aber hinein
    assert filter_sperrzeitraum(
        opp(event_start=date(2027, 2, 20), event_end=date(2027, 3, 2)), PROFIL, HEUTE
    ) == "sperrzeitraum"
    assert filter_sperrzeitraum(opp(event_start=date(2027, 5, 6)), PROFIL, HEUTE) is None
    assert filter_sperrzeitraum(opp(event_start=date(2027, 2, 1), event_end=date(2027, 2, 10)), PROFIL, HEUTE) is None
    assert filter_sperrzeitraum(opp(), PROFIL, HEUTE) is None


def test_fach():
    assert filter_fach(opp(category="wettbewerb", subject="Geschichte"), PROFIL, HEUTE) == "fach"
    assert filter_fach(opp(category="wettbewerb", subject="Informatik"), PROFIL, HEUTE) is None
    assert filter_fach(opp(category="stipendium", subject="Geschichte"), PROFIL, HEUTE) is None


def test_online_und_regional_ausnahme():
    assert apply_post_score_filters(opp(format="online", prestige=84), SETTINGS) == "online"
    assert apply_post_score_filters(opp(format="online", prestige=85), SETTINGS) is None
    assert apply_post_score_filters(opp(regional=True, prestige=79), SETTINGS) == "regional"
    assert apply_post_score_filters(opp(regional=True, prestige=80), SETTINGS) is None
    assert apply_post_score_filters(opp(format="praesenz", prestige=10), SETTINGS) is None
    # Projektförderung ist von Online-/Regional-Filter ausgenommen (Entscheidung, siehe PROGRESS.md)
    assert apply_post_score_filters(opp(target="projekt", format="online", prestige=10), SETTINGS) is None


def test_sammel_filter_gibt_ersten_grund():
    o = opp(deadline=date(2020, 1, 1), language="andere")
    assert apply_pre_score_filters(o, PROFIL, HEUTE) == "deadline_vorbei"
    assert apply_pre_score_filters(opp(deadline=date(2026, 12, 1)), PROFIL, HEUTE) is None


def test_warnungen_bei_unklar():
    o = opp(travel_covered="unklar")
    add_warnings(o, PROFIL)
    add_warnings(o, PROFIL)  # zweimal aufrufen darf nichts doppeln
    assert "Reisekosten unklar" in o.warnings
    assert "Deadline unklar" in o.warnings
    assert len(o.warnings) == len(set(o.warnings))
    online = opp(format="online", travel_covered="unklar")
    add_warnings(online, PROFIL)
    assert "Reisekosten unklar" not in online.warnings
