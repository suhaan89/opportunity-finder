"""Tests für Gemini-Wrapper, Verify, Extract und Collect (alles ohne Internet)."""
from datetime import date
from types import SimpleNamespace

from src.collect import Candidate, collect_from_search, select_queries, unique_candidates
from src.extract import build_opportunity, extract_opportunity
from src.gemini import Budget, GeminiClient, SearchHit, SearchResult, hits_from_response, parse_json_text
from src.verify import Fetcher, Page, is_public_http_url, parse_html

HEUTE = date(2026, 9, 24)


# ---------- Gemini ----------

def test_parse_json_text_variants():
    assert parse_json_text('{"a": 1}') == {"a": 1}
    assert parse_json_text('```json\n[{"a": 1}]\n```') == [{"a": 1}]
    assert parse_json_text('Hier ist das Ergebnis: {"a": 2} Viel Erfolg') == {"a": 2}
    assert parse_json_text("kein json") is None


def test_budget():
    b = Budget(2)
    assert b.take() and b.take() and not b.take()
    assert b.remaining == 0


def test_hits_aus_text_und_grounding():
    chunk = SimpleNamespace(web=SimpleNamespace(uri="https://vertex.example/redirect/1", title="Quelle"))
    resp = SimpleNamespace(
        text='Treffer: [{"title": "A", "url": "https://a.example/x"}, {"title": "B", "url": "kein-link"}]',
        candidates=[SimpleNamespace(grounding_metadata=SimpleNamespace(grounding_chunks=[chunk]))],
    )
    hits = hits_from_response(resp)
    assert [h.url for h in hits] == ["https://a.example/x", "https://vertex.example/redirect/1"]
    assert hits_from_response(SimpleNamespace(text="", candidates=None)) == []


class FakeSDK:
    """Attrappe für den google-genai-Client: liefert nacheinander vorbereitete Antworten."""

    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls += 1
        item = self.texts.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(text=item, candidates=None)


SCHEMA = {"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}}


def test_generate_json_wiederholt_einmal_dann_ok():
    sdk = FakeSDK(["kaputt", '{"x": 1}'])
    g = GeminiClient("k", "modell", Budget(5), seconds_between_calls=0, client=sdk)
    assert g.generate_json("p", SCHEMA) == {"x": 1}
    assert sdk.calls == 2


def test_generate_json_gibt_nach_zwei_fehlern_none():
    sdk = FakeSDK(["kaputt", '{"x": "text"}'])
    g = GeminiClient("k", "modell", Budget(5), seconds_between_calls=0, client=sdk)
    assert g.generate_json("p", SCHEMA) is None
    assert sdk.calls == 2


def test_budget_stoppt_aufrufe():
    sdk = FakeSDK(['{"x": 1}', '{"x": 2}'])
    g = GeminiClient("k", "modell", Budget(1), seconds_between_calls=0, client=sdk)
    assert g.generate_json("p", SCHEMA) == {"x": 1}
    assert g.generate_json("p", SCHEMA) is None
    assert sdk.calls == 1


def test_api_fehler_mit_retry():
    fehler = Exception("boom")
    fehler.code = 429
    sdk = FakeSDK([fehler, '{"x": 3}'])
    g = GeminiClient("k", "modell", Budget(5), seconds_between_calls=0, client=sdk)
    assert g.generate_json("p", SCHEMA) == {"x": 3}


def test_api_fehler_ohne_retry_gibt_none():
    sdk = FakeSDK([Exception("boom")])
    g = GeminiClient("k", "modell", Budget(5), seconds_between_calls=0, client=sdk)
    assert g.generate_json("p", SCHEMA) is None


# ---------- Verify ----------

def test_url_pruefung():
    assert is_public_http_url("https://example.org/x")
    assert not is_public_http_url("ftp://example.org")
    assert not is_public_http_url("http://localhost:8000")
    assert not is_public_http_url("http://127.0.0.1/")
    assert not is_public_http_url("http://192.168.1.5/")
    assert not is_public_http_url("javascript:alert(1)")


def test_html_parsen():
    html = """<html><head><title>Titel</title><script>böse()</script></head>
    <body><h1>Hallo</h1><a href="/apply">Bewerben</a><style>x{}</style></body></html>"""
    titel, text, links = parse_html(html, "https://example.org/a/", 1000)
    assert titel == "Titel" and "Hallo" in text and "böse" not in text
    assert links == [("Bewerben", "https://example.org/apply")]


class FakeResponse:
    def __init__(self, status, ctype, body, url):
        self.status_code, self.headers, self.url = status, {"Content-Type": ctype}, url
        self.encoding = "utf-8"
        self.raw = SimpleNamespace(read=lambda n, decode_content=True: body.encode())

    def close(self):
        pass


class FakeSession:
    def __init__(self, resp):
        self.resp, self.headers = resp, {}

    def get(self, url, **kw):
        return self.resp


def _fetcher(resp):
    f = Fetcher()
    f.session = FakeSession(resp)
    return f


def test_fetcher_ok_und_fehlerfaelle():
    langer_text = "<html><body><p>" + "Wort " * 100 + "</p></body></html>"
    ok = _fetcher(FakeResponse(200, "text/html; charset=utf-8", langer_text, "https://example.org/final"))
    page = ok.fetch("https://example.org/start")
    assert page and page.url == "https://example.org/final"
    assert _fetcher(FakeResponse(404, "text/html", langer_text, "https://example.org")).fetch("https://example.org") is None
    assert _fetcher(FakeResponse(200, "application/pdf", "x", "https://example.org")).fetch("https://example.org") is None
    assert _fetcher(FakeResponse(200, "text/html", "<p>kurz</p>", "https://example.org")).fetch("https://example.org") is None
    # Weiterleitung auf eine lokale Adresse wird abgelehnt
    assert _fetcher(FakeResponse(200, "text/html", langer_text, "http://127.0.0.1/x")).fetch("https://example.org") is None


# ---------- Extract ----------

SEITE = Page(
    url="https://example.org/akademie",
    title="Akademie",
    text="Sommerakademie Informatik. Bewerbungsschluss: 15. Januar 2027. Die Akademie findet vom 1. bis 14. August 2027 statt.",
)

ANTWORT = {
    "is_opportunity": True, "title": "Sommerakademie Informatik", "organizer": "Beispiel e.V.",
    "category": "akademie", "target": "person", "format": "praesenz", "language": "de",
    "travel_covered": "unklar", "benefits": ["mentoring", "mentoring"], "effort": "mittel",
    "deadline": "2027-01-15", "deadline_quote": "Bewerbungsschluss: 15. Januar 2027",
    "event_start": "2027-08-01", "event_end": "2027-08-14",
    "event_quote": "vom 1. bis 14. August 2027", "fee_eur": 0,
}


def test_extract_mit_belegen():
    o = build_opportunity(dict(ANTWORT), SEITE, HEUTE)
    assert o.deadline == date(2027, 1, 15) and o.event_start == date(2027, 8, 1)
    assert o.benefits == ["mentoring"] and o.warnings == []
    assert o.id and o.first_seen == HEUTE and o.status == "neu"


def test_extract_verwirft_unbelegte_daten():
    antwort = dict(ANTWORT, deadline_quote="Bewerbung bis 1. Dezember 2027", event_quote=None)
    o = build_opportunity(antwort, SEITE, HEUTE)
    assert o.deadline is None and o.event_start is None and o.event_end is None
    assert "Deadline nicht belegt" in o.warnings and "Eventdatum nicht belegt" in o.warnings


def test_extract_kein_angebot():
    assert build_opportunity(dict(ANTWORT, is_opportunity=False), SEITE, HEUTE) is None


class FakeGemini:
    def __init__(self, antwort):
        self.antwort = antwort

    def generate_json(self, prompt, schema, purpose):
        assert "IGNORIERE" in prompt and SEITE.text in prompt
        return self.antwort

    def search(self, q, today):
        if q == "kaputt":
            raise RuntimeError("x")
        return SearchResult(hits=[SearchHit("T", "https://a.example/" + q)])


def test_extract_opportunity_validiert_schema():
    assert extract_opportunity(SEITE, FakeGemini(dict(ANTWORT)), HEUTE) is not None
    assert extract_opportunity(SEITE, FakeGemini(dict(ANTWORT, category="quatsch")), HEUTE) is None
    assert extract_opportunity(SEITE, FakeGemini(None), HEUTE) is None
    assert extract_opportunity(SEITE, FakeGemini(dict(ANTWORT, deadline="15.01.2027")), HEUTE) is None


# ---------- Collect ----------

def test_rotation_der_suchanfragen():
    q = ["a", "b", "c", "d", "e"]
    assert select_queries(q, 2, 0) == ["a", "b"]
    assert select_queries(q, 2, 1) == ["c", "d"]
    assert select_queries(q, 2, 2) == ["e", "a"]  # springt um
    assert select_queries(q, 10, 0) == q
    assert select_queries([], 3, 0) == []


def test_unique_candidates():
    c = [Candidate("A", "https://x.org/a/"), Candidate("A2", "http://www.x.org/a?utm_source=1")]
    assert len(unique_candidates(c)) == 1


def test_collect_ueberlebt_kaputte_anfrage():
    cands, failed = collect_from_search(FakeGemini(None), ["eins", "kaputt", "zwei"], HEUTE)
    assert [c.url for c in cands] == ["https://a.example/eins", "https://a.example/zwei"]
    assert failed == 1


# ---------- Brave-Websuche (Ersatz für die gesperrte Google-Suche) ----------

class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeSession:
    def __init__(self, data):
        self.data, self.calls = data, []

    def get(self, url, headers, params, timeout):
        self.calls.append((url, headers, params))
        return _FakeResp(self.data)


def test_brave_liefert_nur_web_links():
    from src.websearch import BraveSearch

    sitzung = _FakeSession({"web": {"results": [
        {"title": "Stipendium A", "url": "https://a.example/x"},
        {"title": "kaputt", "url": "javascript:alert(1)"},
        {"title": "ohne url"},
    ]}})
    hits = BraveSearch("KEY", pause=0, session=sitzung)("Stipendium Schüler")
    assert [(h.title, h.url) for h in hits] == [("Stipendium A", "https://a.example/x")]
    url, headers, params = sitzung.calls[0]
    assert headers["X-Subscription-Token"] == "KEY" and params["q"] == "Stipendium Schüler"


def test_brave_ohne_ergebnisse_ist_leer():
    from src.websearch import BraveSearch

    assert BraveSearch("KEY", pause=0, session=_FakeSession({}))("x") == []


def test_gemini_suche_nutzt_brave_und_ruft_gemini_nicht_auf():
    class KeinSdk:
        class models:
            @staticmethod
            def generate_content(**kw):
                raise AssertionError("Gemini darf für die Suche nicht aufgerufen werden")

    g = GeminiClient("k", "modell", Budget(5), seconds_between_calls=0, client=KeinSdk(),
                     web_search=lambda q, heute: [SearchHit("T", "https://t.example")])
    result = g.search("frage", "2026-09-25")
    assert [(h.title, h.url) for h in result.hits] == [("T", "https://t.example")]
    assert g.budget.used == 0


class _FakePostSession:
    def __init__(self, data):
        self.data, self.calls = data, []

    def post(self, url, headers, json, timeout):
        self.calls.append((url, headers, json))
        return _FakeResp(self.data)


def test_tavily_liefert_nur_web_links():
    from src.websearch import TavilySearch

    sitzung = _FakePostSession({"results": [
        {"title": "Hackathon B", "url": "https://b.example/h", "content": "..."},
        {"title": "kaputt", "url": "ftp://x"},
    ]})
    hits = TavilySearch("KEY", session=sitzung)("Hackathon Schüler")
    assert [(h.title, h.url) for h in hits] == [("Hackathon B", "https://b.example/h")]
    url, headers, body = sitzung.calls[0]
    assert headers["Authorization"] == "Bearer KEY" and body["query"] == "Hackathon Schüler"


def test_anbieter_wahl_tavily_vor_brave(monkeypatch):
    from src.main import _websearch_from_env
    from src.websearch import BraveSearch, TavilySearch

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    assert _websearch_from_env() is None
    monkeypatch.setenv("BRAVE_API_KEY", "b")
    assert isinstance(_websearch_from_env(), BraveSearch)
    monkeypatch.setenv("TAVILY_API_KEY", "t")
    assert isinstance(_websearch_from_env(), TavilySearch)


def test_ueberlastung_wird_mehrfach_wiederholt_und_kostet_ein_budget():
    def ueberlast():
        e = Exception("503")
        e.code = 503
        return e

    sdk = FakeSDK([ueberlast(), ueberlast(), ueberlast(), '{"x": 7}'])
    g = GeminiClient("k", "modell", Budget(5), seconds_between_calls=0, client=sdk)
    assert g.generate_json("p", SCHEMA) == {"x": 7}
    assert sdk.calls == 4 and g.budget.used == 1


def test_nach_fuenf_totalausfaellen_keine_weiteren_aufrufe():
    def ueberlast():
        e = Exception("503")
        e.code = 503
        return e

    sdk = FakeSDK([ueberlast() for _ in range(40)])
    g = GeminiClient("k", "modell", Budget(50), seconds_between_calls=0, client=sdk)
    for _ in range(10):
        assert g._call("p", None) is None
    assert sdk.calls == GeminiClient.FAIL_STOP * GeminiClient.MAX_TRIES
