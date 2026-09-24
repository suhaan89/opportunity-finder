"""Tests für den Mailer."""
from datetime import date

from src.mailer import MailContent, build_mail_content, render_email, send_email
from src.models import Opportunity

HEUTE = date(2026, 9, 24)


def opp(id_, score, **kw):
    return Opportunity(id=id_, title=f"Titel {id_}", url=f"https://example.org/{id_}", score=score,
                       score_reason="Passt gut", **kw)


def test_auswahl_nach_schwelle_und_sortierung():
    neu = [opp("a", 60), opp("b", 90), opp("c", 75), opp("p", 80, target="projekt")]
    c = build_mail_content(neu, [], 70)
    assert [o.id for o in c.top] == ["b", "c"]
    assert [o.id for o in c.projects] == ["p"]
    assert not c.is_empty()
    assert build_mail_content([opp("x", 10)], [], 70).is_empty()


def test_html_und_betreff():
    o = opp("a", 88, deadline=date(2027, 1, 15), fee_eur=0, fully_funded=True, warnings=["Reisekosten unklar"])
    c = MailContent(top=[o], reminders=[(opp("r", 50, deadline=date(2026, 10, 1)), 7)])
    subject, html = render_email(c, HEUTE)
    assert subject == "Opportunity-Finder: 1 neue Treffer · 1 Deadline(s) bald"
    assert "88/100" in html and "15.01.2027" in html and "kostenlos" in html
    assert "Reisekosten unklar" in html and "In 7 Tagen" in html
    assert "prefers-color-scheme: dark" in html


def test_html_wird_maskiert():
    o = opp("a", 88)
    o.title = "<script>alert(1)</script>"
    _, html = render_email(MailContent(top=[o]), HEUTE)
    assert "<script>alert" not in html and "&lt;script&gt;" in html


def test_unsichere_url_wird_ersetzt():
    o = opp("a", 88)
    o.url = "javascript:alert(1)"
    _, html = render_email(MailContent(top=[o]), HEUTE)
    assert "javascript:" not in html


def test_ohne_smtp_wird_datei_geschrieben(tmp_path, monkeypatch):
    for k in ("SMTP_USER", "SMTP_APP_PASSWORD", "MAIL_TO"):
        monkeypatch.delenv(k, raising=False)
    assert send_email("Betreff", "<p>Hallo</p>", out_dir=tmp_path) is False
    assert (tmp_path / "mail.html").read_text(encoding="utf-8") == "<p>Hallo</p>"


def test_mit_smtp_wird_gesendet(monkeypatch):
    gesendet = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            gesendet["host"] = host

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, user, pw):
            gesendet["login"] = (user, pw)

        def send_message(self, msg):
            gesendet["to"] = msg["To"]

    monkeypatch.setenv("SMTP_USER", "a@example.org")
    monkeypatch.setenv("SMTP_APP_PASSWORD", "pw")
    monkeypatch.setenv("MAIL_TO", "b@example.org")
    monkeypatch.setattr("src.mailer.smtplib.SMTP_SSL", FakeSMTP)
    assert send_email("Betreff", "<p>Hallo</p>") is True
    assert gesendet["host"] == "smtp.gmail.com" and gesendet["to"] == "b@example.org"
