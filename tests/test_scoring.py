"""Tests für das Scoring."""
from src.models import Opportunity
from src.scoring import (
    adjust_prestige, compute_score, feasibility_score, funding_score, interest_fit,
    is_fully_funded_international, network_score, score_opportunity,
)

SETTINGS = {
    "scoring": {
        "weights": {"interest_fit": 0.35, "funding": 0.20, "prestige": 0.20,
                    "career": 0.15, "network": 0.05, "feasibility": 0.05},
        "fully_funded_bonus": 10,
        "top_provider_prestige_floor": 90,
        "top_providers": ["Studienstiftung"],
    }
}
PROFIL = {
    "heimatland": "Deutschland",
    "interessen_punkte": {"ki_forschung": 50, "informatik_coding": 30, "sport": 20},
    "netzwerke": {"young_founders_network": 10, "young_leaders": 6},
}


def opp(**kw) -> Opportunity:
    return Opportunity(id="x", title="Test", **kw)


def test_gewichte_summe_ist_eins():
    assert abs(sum(SETTINGS["scoring"]["weights"].values()) - 1.0) < 1e-9


def test_interessen_fit_gewichtet_mit_profilpunkten():
    # nur KI passt voll: 50 von 100 Punkten
    assert interest_fit({"ki_forschung": 100}, PROFIL) == 50
    assert interest_fit({"ki_forschung": 100, "informatik_coding": 100, "sport": 100}, PROFIL) == 100
    assert interest_fit({}, PROFIL) == 0
    assert interest_fit({"ki_forschung": 500}, PROFIL) == 50  # wird auf 100 gedeckelt


def test_foerderwert():
    assert funding_score(opp()) == 0
    assert funding_score(opp(fully_funded=True, travel_covered="ja", benefits=["geld", "mentoring"])) == 95
    assert funding_score(opp(fully_funded=True, travel_covered="ja", benefits=["geld", "hardware", "preis"])) == 100


def test_netzwerk_gestaffelt():
    assert network_score(opp(organizer="Young Founders Network"), PROFIL) == 100
    assert network_score(opp(organizer="Young Leaders e.V."), PROFIL) == 60
    assert network_score(opp(organizer="Irgendwer"), PROFIL) == 0


def test_machbarkeit_sinkt_bei_unklarem():
    sicher = opp(deadline=None, event_start=None, eligibility="ab 16", travel_covered="ja")
    assert feasibility_score(sicher) == 75
    alles_unklar = opp(effort="hoch")
    assert feasibility_score(alles_unklar) == 100 - 15 - 10 - 10 - 10 - 10


def test_top_anbieter_prestige_floor():
    o = opp(organizer="Studienstiftung des deutschen Volkes")
    assert adjust_prestige(o, 40, SETTINGS) == 90
    assert adjust_prestige(o, 95, SETTINGS) == 95
    assert adjust_prestige(opp(organizer="Unbekannt"), 40, SETTINGS) == 40


def test_bonus_voll_finanziert_international():
    o = opp(fully_funded=True, travel_covered="ja", location_country="USA")
    assert is_fully_funded_international(o, PROFIL)
    assert not is_fully_funded_international(opp(fully_funded=True, location_country="Deutschland"), PROFIL)
    assert not is_fully_funded_international(
        opp(fully_funded=True, location_country="USA", format="online"), PROFIL
    )


def test_gesamtscore_und_deckel():
    ai = {"interest_relevance": {"ki_forschung": 100, "informatik_coding": 100, "sport": 100},
          "prestige": 100, "career": 100}
    o = opp(fully_funded=True, travel_covered="ja", location_country="USA",
            benefits=["geld", "hardware", "preis"], eligibility="x", organizer="Young Founders Network")
    o.deadline = None
    score, teile = compute_score(o, ai, PROFIL, SETTINGS)
    assert score == 100  # 100 + Bonus wird bei 100 gedeckelt
    assert teile["network"] == 100


def test_gesamtscore_rechnung():
    ai = {"interest_relevance": {"ki_forschung": 100}, "prestige": 50, "career": 40}
    # interest 50, funding 0, prestige 50, career 40, network 0, feasibility 100-15-10-10-10 = 55
    o = opp(travel_covered="unklar")
    score, _ = compute_score(o, ai, PROFIL, SETTINGS)
    erwartet = 50 * 0.35 + 0 + 50 * 0.20 + 40 * 0.15 + 0 + 55 * 0.05
    assert score == round(erwartet)


class FakeGemini:
    def __init__(self, antwort):
        self.antwort = antwort

    def generate_json(self, prompt, schema, purpose):
        assert "1999" not in prompt  # kein Geburtsdatum im Prompt
        return self.antwort


def test_score_opportunity_ok_und_fehler():
    gut = {"interest_relevance": {"ki_forschung": 80, "informatik_coding": 60, "sport": 0},
           "prestige": 70, "career": 60, "regional": True, "reason": "Passt gut\nzu KI."}
    o = opp(travel_covered="ja")
    assert score_opportunity(o, PROFIL, SETTINGS, FakeGemini(gut))
    assert o.score is not None and o.prestige == 70 and o.regional is True
    assert "\n" not in o.score_reason

    kaputt = {"prestige": 70}
    o2 = opp()
    assert not score_opportunity(o2, PROFIL, SETTINGS, FakeGemini(kaputt))
    assert o2.score is None
    assert not score_opportunity(opp(), PROFIL, SETTINGS, FakeGemini(None))


def test_extra_interessen_aus_settings():
    from src.scoring import with_extra_interests
    profil = {"interessen_punkte": {"ki_forschung": 60}}
    s = {"scoring": {"extra_interests": {"reisen": 40, "ki_forschung": 5}}}
    p = with_extra_interests(profil, s)
    assert p["interessen_punkte"] == {"reisen": 40, "ki_forschung": 60}
    assert profil["interessen_punkte"] == {"ki_forschung": 60}      # Original unverändert
    assert with_extra_interests(profil, {}) is profil
