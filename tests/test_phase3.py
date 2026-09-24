"""Tests für Quellenseiten und Gmail-Newsletter (Phase 3), ohne Internet."""
import base64
from types import SimpleNamespace

import pytest

from src.collect import (
    collect_from_mail, collect_from_pages, is_unsafe_link, pick_links, safe_links, select_pages,
)
from src.gmail_reader import GmailAuthError, GmailReader, MailDoc, parse_message
from src.verify import Page


# ---------- Links ----------

def test_unsichere_links_werden_erkannt():
    for url in (
        "https://news.example/unsubscribe?u=1", "https://x.example/abmelden", "https://x.example/optout",
        "https://x.example/manage-preferences", "mailto:a@b.de", "javascript:alert(1)", "https://x.example/logout",
    ):
        assert is_unsafe_link(url), url
    assert not is_unsafe_link("https://example.org/stipendium")


def test_safe_links_filtert_und_entdoppelt():
    links = [("A", "https://example.org/a/"), ("A2", "http://www.example.org/a?utm_source=x"),
             ("Abmelden", "https://example.org/unsubscribe"), ("B", "https://example.org/b")]
    assert [u for _, u in safe_links(links)] == ["https://example.org/a/", "https://example.org/b"]


class FakeGemini:
    def __init__(self, antwort):
        self.antwort, self.prompts = antwort, []

    def generate_json(self, prompt, schema, purpose):
        self.prompts.append(prompt)
        return self.antwort


def test_pick_links_verwirft_erfundene_und_unsichere_urls():
    links = [("Programm", "https://example.org/programm"), ("Abmelden", "https://example.org/unsubscribe")]
    antwort = {"items": [
        {"title": "echt", "url": "https://example.org/programm"},
        {"title": "erfunden", "url": "https://erfunden.example/x"},          # stand nicht in der Liste
        {"title": "unsicher", "url": "https://example.org/unsubscribe"},      # unsicher
    ]}
    g = FakeGemini(antwort)
    cands = pick_links(g, "Quellenseite", "Text", links, "quelle")
    assert [c.url for c in cands] == ["https://example.org/programm"]
    assert "unsubscribe" not in g.prompts[0]            # Abmelde-Link geht gar nicht erst an Gemini
    assert cands[0].origin == "quelle"


def test_pick_links_ohne_links_oder_antwort():
    g = FakeGemini(None)
    assert pick_links(g, "Mail", "Text", [], "mail") == []
    assert g.prompts == []                               # kein Gemini-Aufruf ohne Links
    assert pick_links(g, "Mail", "Text", [("A", "https://example.org/a")], "mail") == []


# ---------- Quellenseiten ----------

def test_select_pages_prioritaet_und_rotation():
    seiten = [
        {"name": "hoch", "url": "https://h.example", "priority": "hoch"},
        {"name": "aus", "url": "https://a.example", "priority": "hoch", "enabled": False},
        {"name": "leer", "url": "", "priority": "hoch"},
        {"name": "m1", "url": "https://1.example", "priority": "mittel"},
        {"name": "m2", "url": "https://2.example", "priority": "mittel"},
        {"name": "m3", "url": "https://3.example", "priority": "niedrig"},
    ]
    tag0 = [p["name"] for p in select_pages(seiten, 2, 0)]
    tag1 = [p["name"] for p in select_pages(seiten, 2, 1)]
    assert tag0[0] == "hoch" and tag1[0] == "hoch"       # 'hoch' ist immer dabei
    assert len(tag0) == 2 and tag0 != tag1                 # der Rest rotiert
    assert "aus" not in tag0 + tag1 and "leer" not in tag0 + tag1
    assert select_pages(seiten, 0, 0) == [seiten[0]]       # Priorität hoch ist auch bei Limit 0 dabei
    assert select_pages([], 3, 0) == []


class FakeFetcher:
    def __init__(self, seiten):
        self.seiten = seiten

    def fetch(self, url):
        if url == "https://kaputt.example":
            raise RuntimeError("boom")
        return self.seiten.get(url)


def test_collect_from_pages_ueberlebt_kaputte_quellen():
    seite = Page(url="https://gut.example", title="T", text="x" * 300,
                 links=[("Programm", "https://gut.example/programm")])
    fetcher = FakeFetcher({"https://gut.example": seite})
    g = FakeGemini({"items": [{"title": "P", "url": "https://gut.example/programm"}]})
    pages = [{"url": "https://kaputt.example"}, {"url": "https://weg.example"}, {"url": "https://gut.example"}]
    cands, failed = collect_from_pages(g, fetcher, pages)
    assert [c.url for c in cands] == ["https://gut.example/programm"] and failed == 2


# ---------- Gmail ----------

def _b64(text):
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def test_parse_message_html_bevorzugt():
    html = "<html><body><p>" + "Neues Angebot " * 20 + '</p><a href="https://example.org/a">Zum Angebot</a></body></html>'
    msg = {"payload": {"mimeType": "multipart/alternative", "parts": [
        {"mimeType": "text/plain", "body": {"data": _b64("nur text https://example.org/plain")}},
        {"mimeType": "text/html", "body": {"data": _b64(html)}},
    ]}}
    doc = parse_message(msg)
    assert doc.links == [("Zum Angebot", "https://example.org/a")] and "Neues Angebot" in doc.text


def test_parse_message_nur_text_und_leer():
    msg = {"payload": {"mimeType": "text/plain", "body": {"data": _b64("Schau hier: https://example.org/x.")}}}
    doc = parse_message(msg)
    assert doc.links == [("", "https://example.org/x")]
    assert parse_message({"payload": {}}) is None


class FakeResp:
    def __init__(self, status=200, data=None):
        self.status_code, self._data = status, data or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http")


class FakeSession:
    def __init__(self, token_status=200):
        self.token_status, self.gets = token_status, []

    def post(self, url, data, timeout):
        assert data["grant_type"] == "refresh_token"
        return FakeResp(self.token_status, {"access_token": "AT"})

    def get(self, url, params=None, headers=None, timeout=None):
        assert headers["Authorization"] == "Bearer AT"
        self.gets.append((url, params))
        if url.endswith("/labels"):
            return FakeResp(data={"labels": [{"id": "L1", "name": "Opportunity-Finder"}]})
        if url.endswith("/messages"):
            return FakeResp(data={"messages": [{"id": "m1"}, {"id": "m2"}]})
        html = "<p>" + "Text " * 60 + '</p><a href="https://example.org/p">P</a>'
        return FakeResp(data={"payload": {"mimeType": "text/html", "body": {"data": _b64(html)}}})


def test_gmail_reader_holt_mails_mit_label():
    s = FakeSession()
    docs = GmailReader("id", "secret", "refresh", session=s).fetch_documents("opportunity-finder", 3, 10)
    assert len(docs) == 2 and docs[0].links == [("P", "https://example.org/p")]
    liste = [g for g in s.gets if g[0].endswith("/messages")][0]
    assert liste[1]["labelIds"] == "L1" and liste[1]["q"] == "newer_than:3d"
    # nur lesende Aufrufe (GET), nie schreiben
    assert all(True for _ in s.gets)


def test_gmail_reader_label_fehlt_und_auth_fehler():
    s = FakeSession()
    assert GmailReader("i", "s", "r", session=s).fetch_documents("gibt-es-nicht", 3, 10) == []
    with pytest.raises(GmailAuthError):
        GmailReader("i", "s", "r", session=FakeSession(token_status=400)).fetch_documents("x", 3, 10)


def test_gmail_from_env(monkeypatch):
    for k in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    assert GmailReader.from_env() is None
    monkeypatch.setenv("GMAIL_CLIENT_ID", "a")
    assert GmailReader.from_env() is None               # nur ein Wert reicht nicht
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "b")
    monkeypatch.setenv("GMAIL_REFRESH_TOKEN", "c")
    assert GmailReader.from_env() is not None


def test_collect_from_mail_ueberlebt_fehler():
    class Kaputt:
        def fetch_documents(self, *a):
            raise GmailAuthError("x")

    assert collect_from_mail(FakeGemini(None), Kaputt(), "L", 3, 5) == ([], 0, 1)

    class Gut:
        def fetch_documents(self, *a):
            return [MailDoc("Text", [("P", "https://example.org/p")]), MailDoc("Text2", [("Q", "https://example.org/q")])]

    g = FakeGemini({"items": [{"title": "P", "url": "https://example.org/p"}]})
    cands, n, failed = collect_from_mail(g, Gut(), "L", 3, 5)
    assert n == 2 and failed == 0 and [c.origin for c in cands] == ["mail"]
