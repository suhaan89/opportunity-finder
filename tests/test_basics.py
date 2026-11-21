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


def test_safe_error_http_zeigt_status_url_ohne_token():
    import requests

    resp = requests.Response()
    resp.status_code = 401
    resp.url = "https://api.github.com/gists/abc123?access_token=GEHEIM"
    resp._content = b'{"message":"Bad credentials","documentation_url":"https://docs.github.com"}'
    err = requests.HTTPError("401 Client Error", response=resp)
    text = safe_error("kalender", err)
    assert "HTTPError" in text and "HTTP 401" in text
    assert "url=https://api.github.com/gists/<redacted>" in text
    assert "abc123" not in text
    assert "Bad credentials" in text
    assert "GEHEIM" not in text and "access_token" not in text


def test_safe_error_gist_id_erscheint_nie_im_log():
    """Eine echte Gist-ID darf in keiner geloggten URL stehen (API, HTML, Raw, Body)."""
    import requests
    from src.util import _safe_url

    gist_id = "a1b2c3d4e5f6789012345678abcdef01"
    faelle = [
        f"https://api.github.com/gists/{gist_id}?access_token=GEHEIM",
        f"https://api.github.com/gists/{gist_id}/comments",
        f"https://api.github.com/GISTS/{gist_id}",  # case-insensitive /gists/
        f"https://gist.github.com/owner/{gist_id}",
        f"https://gist.github.com/{gist_id}#file-opportunities",
        f"https://gist.github.com/{gist_id}/",  # Kurzform + trailing slash
        f"https://gist.github.com/{gist_id}/raw",  # Kurzform + /raw (nicht user/id)
        f"https://gist.github.com/{gist_id}//",  # doppelter trailing slash
        f"https://www.gist.github.com/owner/{gist_id}/",
        f"https://gist.githubusercontent.com/owner/{gist_id}/raw/rev/opportunities.ics?token=GEHEIM",
    ]
    for url in faelle:
        resp = requests.Response()
        resp.status_code = 404
        resp.url = url
        resp._content = b'{"message":"Not Found"}'
        text = safe_error("kalender", requests.HTTPError("404", response=resp))
        assert gist_id not in text, url
        assert "<redacted>" in text
        assert "GEHEIM" not in text and "token=" not in text and "access_token" not in text

    # Kurzform-Pfad: ID steht in Segment 1, nicht fälschlich „raw“ ersetzen
    assert _safe_url(f"https://gist.github.com/{gist_id}/") == "https://gist.github.com/<redacted>"
    assert _safe_url(f"https://gist.github.com/{gist_id}/raw") == "https://gist.github.com/<redacted>/raw"
    assert gist_id not in _safe_url(f"https://gist.github.com/{gist_id}//raw")

    # Antworttext der GitHub-API kann selbst eine Gist-URL enthalten (Auszug bleibt unter 200 Zeichen).
    resp = requests.Response()
    resp.status_code = 401
    resp.url = f"https://api.github.com/gists/{gist_id}"
    resp._content = (
        f'https://gist.github.com/o/{gist_id} '
        f'https://gist.githubusercontent.com/o/{gist_id}/raw/f'
    ).encode()
    text = safe_error("kalender", requests.HTTPError("401", response=resp))
    assert gist_id not in text
    assert "url=https://api.github.com/gists/<redacted>" in text
    assert "https://gist.github.com/o/<redacted>" in text
    assert "https://gist.githubusercontent.com/o/<redacted>/raw/f" in text


def test_safe_error_http_body_nur_bei_github_api():
    """Fremde API-Bodies (Gemini o. Ä.) dürfen nicht in öffentliche Logs."""
    import requests

    resp = requests.Response()
    resp.status_code = 400
    resp.url = "https://generativelanguage.googleapis.com/v1beta/models/x:generateContent"
    resp._content = b'{"error":{"message":"Profil: heimatland Deutschland Interessen ki_forschung"}}'
    err = requests.HTTPError("400", response=resp)
    text = safe_error("score", err)
    assert "HTTP 400" in text
    assert "url=https://generativelanguage.googleapis.com/v1beta/models/x:generateContent" in text
    assert "body=" not in text
    assert "heimatland" not in text and "ki_forschung" not in text and "Profil" not in text


def test_beispielprofil_ist_gueltiges_yaml():
    """Das Beispielprofil muss lesbar sein und die wichtigen Schlüssel haben."""
    import yaml
    from src.config import CONFIG_DIR
    profil = yaml.safe_load((CONFIG_DIR / "profile.example.yaml").read_text(encoding="utf-8"))
    for key in ("geburtsdatum", "interessen_punkte", "kriterien", "netzwerke", "projekte", "projekte_bedarf"):
        assert key in profil
    assert abs(sum(profil["interessen_punkte"].values()) - 100) < 1e-9
