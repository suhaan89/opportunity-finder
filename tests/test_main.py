"""Ende-zu-Ende-Test der Pipeline mit fiktiven Daten (ohne Internet, ohne Zugangsdaten)."""
from datetime import date

from src.config import load_settings, load_sources
from src.gemini import Budget
from src.main import Services, load_dotenv, run_outputs, run_pipeline
from src.mocks import MockFetcher, MockGemini, MockMailReader, build_fixtures, mock_sources_config
from src.sheets import LocalStore

HEUTE = date(2026, 9, 24)
PROFIL = {
    "geburtsdatum": date(2010, 3, 15),
    "heimatland": "Deutschland",
    "ausgeschlossene_wettbewerbsfaecher": ["geschichte"],
    "interessen_punkte": {"ki_forschung": 60, "informatik_coding": 40},
    "netzwerke": {},
    "kriterien": {"max_teilnahmegebuehr_eur": 150, "reisekosten_muessen_uebernommen_werden": True,
                  "rechtsform_erforderlich_ausschliessen": True},
}


def _umleiten(monkeypatch, tmp_path):
    """Alle Ausgabedateien in den Test-Ordner umleiten."""
    monkeypatch.setattr("src.mailer.OUT_DIR", tmp_path / "out")
    monkeypatch.setattr("src.ics.OUT_DIR", tmp_path / "out")
    monkeypatch.setattr("src.site.SITE_DIR", tmp_path / "public_site")


def services(tmp_path):
    settings = load_settings()
    budget = Budget(settings["gemini"]["max_calls_per_run"])
    fx = build_fixtures(HEUTE)
    return Services(MockGemini(fx, budget), MockFetcher(fx), LocalStore(tmp_path / "store.json"),
                    budget, settings, {**load_sources(), "pages": mock_sources_config()}, PROFIL, HEUTE,
                    is_mock=True, mail_reader=MockMailReader(fx))


def test_kompletter_lauf(tmp_path, monkeypatch):
    _umleiten(monkeypatch, tmp_path)
    for k in ("SMTP_USER", "SMTP_APP_PASSWORD", "MAIL_TO"):
        monkeypatch.delenv(k, raising=False)
    svc = services(tmp_path)
    result = run_pipeline(svc)
    c = result.counts
    # 8 aus der Suche (7 Seiten + 1 toter Link) + 1 aus der Quellenseite + 1 aus dem Newsletter
    assert c["quellen"] == 1 and c["mails"] == 1
    assert c["kandidaten"] == 10 and c["erreichbar"] == 9 and c["extrahiert"] == 9
    assert c["duplikate"] == 1
    assert c["gefiltert"] == 4          # Fach, abgelaufen, zu teuer, online mit zu wenig Prestige
    assert c["bewertet"] == 5 and c["neu_gespeichert"] == 4
    assert c["gemini_aufrufe"] <= 40
    titles = {o.title for o in result.new_opps}
    assert titles == {
        "Sommerakademie Künstliche Intelligenz", "Cloud-Credits für Schülerprojekte",
        "Stipendium für junge Programmierer", "Nachwuchs-Forum Digitalisierung",
    }
    assert [o.title for o in result.tables.projekte] == ["Cloud-Credits für Schülerprojekte"]
    assert len(result.tables.archiv) == 5 and all(o.status == "ignoriert" for o in result.tables.archiv)

    out = run_outputs(svc, result)
    assert out["mail"].startswith("lokal gespeichert")
    assert (tmp_path / "out" / "mail.html").exists()
    assert out["seite"].startswith("erstellt") and (tmp_path / "public_site" / "index.html").exists()
    assert out["kalender"].startswith("lokal") and (tmp_path / "out" / "opportunities.ics").exists()
    # Auf der öffentlichen Seite steht nichts Privates
    seite = (tmp_path / "public_site" / "index.html").read_text(encoding="utf-8")
    assert "Mock-Bewertung" not in seite


def test_zweiter_lauf_findet_nichts_neues(tmp_path, monkeypatch):
    _umleiten(monkeypatch, tmp_path)
    run_pipeline(services(tmp_path))
    zweiter = run_pipeline(services(tmp_path))
    assert zweiter.counts["neu_gespeichert"] == 0 and zweiter.counts["extrahiert"] == 0
    assert run_outputs(services(tmp_path), zweiter)["mail"] == "nichts zu senden"


def test_budget_wird_eingehalten(tmp_path):
    svc = services(tmp_path)
    svc.budget.limit = 10
    svc.settings["gemini"]["searches_per_run"] = 1
    result = run_pipeline(svc)
    assert result.counts["gemini_aufrufe"] <= 10


def test_logs_enthalten_nur_zaehler(tmp_path, capsys):
    from src.main import main  # noqa: F401 - nur Import-Test
    result = run_pipeline(services(tmp_path))
    text = str(result.counts)
    assert "Sommerakademie" not in text


def test_dotenv(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# Kommentar\nFOO_TEST=abc\nLEER=\nQUOTED=\"x y\"\n", encoding="utf-8")
    for k in ("FOO_TEST", "LEER", "QUOTED"):
        monkeypatch.delenv(k, raising=False)
    load_dotenv(env)
    import os
    assert os.environ["FOO_TEST"] == "abc" and os.environ["QUOTED"] == "x y" and "LEER" not in os.environ
    monkeypatch.delenv("FOO_TEST"); monkeypatch.delenv("QUOTED")


def test_reminder_loest_mail_aus(tmp_path, monkeypatch):
    _umleiten(monkeypatch, tmp_path)
    for k in ("SMTP_USER", "SMTP_APP_PASSWORD", "MAIL_TO"):
        monkeypatch.delenv(k, raising=False)
    svc = services(tmp_path)
    result = run_pipeline(svc)
    # Nutzer markiert einen Eintrag als 'interessant'; Deadline liegt in 7 Tagen
    eintrag = result.tables.aktiv[0]
    eintrag.status = "interessant"
    eintrag.deadline = date.fromordinal(HEUTE.toordinal() + 7)
    result.new_opps = []  # nichts Neues, nur der Reminder
    out = run_outputs(svc, result)
    assert out["mail"].startswith("lokal gespeichert")
    assert "In 7 Tagen" in (tmp_path / "out" / "mail.html").read_text(encoding="utf-8")
