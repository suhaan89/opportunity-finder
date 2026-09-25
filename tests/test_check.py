"""Tests für den Einrichtungs-Check."""
from src import check

ALLE = [n for names in check.GROUPS.values() for n in names]


def _leer(monkeypatch, tmp_path):
    for n in ALLE + ["PROFILE_YAML"]:
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setattr(check, "ROOT", tmp_path)   # keine echten lokalen Dateien berücksichtigen


def test_alles_fehlt(monkeypatch, tmp_path):
    _leer(monkeypatch, tmp_path)
    lines, missing = check.status_report()
    assert missing == 7                              # Gemini 1 + Brave 1 + Sheet 2 + Mail 3 (MAIL_TO zählt ohne SMTP_USER als fehlend)
    assert all(line.startswith("FEHLT") for line in lines)


def test_teilweise_eingerichtet_und_keine_werte_im_text(monkeypatch, tmp_path):
    _leer(monkeypatch, tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "GEHEIMER-WERT")
    monkeypatch.setenv("SMTP_USER", "a@example.org")
    lines, missing = check.status_report()
    text = "\n".join(lines)
    assert "GEHEIMER-WERT" not in text and "a@example.org" not in text
    assert lines[0].startswith("ok")
    assert missing == 4                              # Brave 1 + Sheet 2 + SMTP_APP_PASSWORD 1 (MAIL_TO fällt auf SMTP_USER zurück)


def test_service_account_datei_zaehlt(monkeypatch, tmp_path):
    _leer(monkeypatch, tmp_path)
    (tmp_path / "service_account.json").write_text("{}", encoding="utf-8")
    assert check.is_set("GOOGLE_SERVICE_ACCOUNT_JSON")


def test_live_ueberspringt_fehlendes_und_zeigt_nur_fehlertyp(monkeypatch, tmp_path):
    _leer(monkeypatch, tmp_path)
    monkeypatch.setenv("SMTP_USER", "a@example.org")
    monkeypatch.setenv("SMTP_APP_PASSWORD", "GEHEIM")

    def kaputt():
        raise ConnectionError("Passwort GEHEIM falsch")

    monkeypatch.setattr(check, "LIVE_TESTS", [
        ("Gmail-SMTP-Login", ["SMTP_USER", "SMTP_APP_PASSWORD"], kaputt),
        ("Gemini", ["GEMINI_API_KEY"], lambda: None),
    ])
    lines = check.run_live()
    assert lines[0] == "FEHLER Gmail-SMTP-Login: ConnectionError"
    assert "GEHEIM" not in "\n".join(lines)
    assert "übersprungen" in lines[1]
