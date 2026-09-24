"""Pipeline-Einstieg: python -m src.main [--mock]

Ablauf (SPEC Abschnitt 2):
  Collect -> Verify -> Extract -> Dedupe -> Filter -> Score -> Store -> Output

WICHTIG: Die GitHub-Actions-Logs sind öffentlich. Deshalb gibt dieses Programm NUR technische
Zähler aus (z. B. "12 Kandidaten, 4 gefiltert"), niemals Titel, Profil, Scores oder Mail-Inhalte.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .collect import Candidate, collect_from_search, select_queries, unique_candidates
from .config import ROOT, load_settings, load_sources
from .dedupe import dedupe_batch
from .extract import extract_opportunity
from .filters import add_warnings, apply_post_score_filters, apply_pre_score_filters
from .gemini import Budget, GeminiClient
from .ics import build_ics, publish_gist, write_local
from .mailer import MailContent, build_mail_content, render_email, send_email
from .mocks import MockFetcher, MockGemini, build_fixtures
from .models import Opportunity
from .profile import load_profile
from .reminders import deadline_reminders
from .scoring import score_opportunity
from .site import build_site
from .sheets import LocalStore, Store, Tables, add_new, archive_expired, open_store, touch_seen
from .util import make_id, safe_error, today_berlin
from .verify import Fetcher


def load_dotenv(path: Any = None) -> None:
    """Liest eine lokale .env-Datei (KEY=WERT, eine Zeile pro Wert). Bereits gesetzte Werte bleiben."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if value and key not in os.environ:
            os.environ[key] = value


def missing_secrets() -> list[str]:
    """Namen (nie Werte!) der Pflicht-Secrets, die fehlen. Für den echten Lauf nötig."""
    fehlend = [k for k in ("GEMINI_API_KEY", "SHEET_ID") if not os.environ.get(k, "").strip()]
    if not os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip() and not (ROOT / "service_account.json").exists():
        fehlend.append("GOOGLE_SERVICE_ACCOUNT_JSON")
    return fehlend


@dataclass
class Services:
    """Alles, was die Pipeline von außen braucht (echt oder Mock)."""
    gemini: Any
    fetcher: Any
    store: Store
    budget: Budget
    settings: dict[str, Any]
    sources: dict[str, Any]
    profile: dict[str, Any]
    today: date
    is_mock: bool = False


@dataclass
class RunResult:
    counts: dict[str, int] = field(default_factory=dict)
    new_opps: list[Opportunity] = field(default_factory=list)   # neu gespeichert (aktiv/projekte)
    tables: Tables = field(default_factory=Tables)


def build_services(mock: bool) -> Services:
    settings, sources, profile = load_settings(), load_sources(), load_profile()
    today = today_berlin()
    budget = Budget(int(settings["gemini"]["max_calls_per_run"]))
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if mock or not api_key:
        fixtures = build_fixtures(today)
        return Services(
            MockGemini(fixtures, budget), MockFetcher(fixtures), LocalStore(), budget,
            settings, sources, profile, today, is_mock=True,
        )
    g = settings["gemini"]
    fetch = settings.get("fetch", {})
    store, _echt = open_store()
    return Services(
        GeminiClient(api_key, g["model"], budget, g.get("seconds_between_calls", 5)),
        Fetcher(fetch.get("timeout_seconds", 15), fetch.get("max_chars", 12000), fetch.get("user_agent", "opportunity-finder")),
        store, budget, settings, sources, profile, today,
    )


def _count(counts: dict[str, int], key: str, n: int = 1) -> None:
    counts[key] = counts.get(key, 0) + n


def gather_candidates(svc: Services, counts: dict[str, int]) -> list[Candidate]:
    """Schritt 1: Collect. (Quellenseiten und Gmail kommen in Phase 3 dazu.)"""
    cfg = svc.settings["gemini"]
    queries = select_queries(svc.sources.get("queries", []), cfg.get("searches_per_run", 6), svc.today.toordinal())
    cands, failed = collect_from_search(svc.gemini, queries, svc.today)
    counts["suchanfragen"] = len(queries)
    _count(counts, "fehler", failed)
    return cands


def run_pipeline(svc: Services) -> RunResult:
    counts: dict[str, int] = {"datum": svc.today.isoformat()}  # type: ignore[dict-item]
    tables = svc.store.load()
    known = tables.all_known()
    known_ids = {o.id for o in known}
    seen_again: set[str] = set()

    # 1. Collect
    cands = unique_candidates(gather_candidates(svc, counts))
    counts["kandidaten"] = len(cands)

    # Schon bekannte Seiten überspringen (spart Abrufe und Gemini-Aufrufe)
    fresh: list[Candidate] = []
    for c in cands:
        cid = make_id(c.url)
        if cid in known_ids:
            seen_again.add(cid)
        else:
            fresh.append(c)

    # 2. Verify: Link erreichbar? Echten Seitentext laden.
    pages = []
    page_ids: set[str] = set()
    for c in fresh:
        try:
            page = svc.fetcher.fetch(c.url)
        except Exception as exc:  # noqa: BLE001 - kaputte Seite darf den Lauf nicht abbrechen
            print(safe_error("verify", exc))
            _count(counts, "fehler")
            continue
        if page is None:
            continue
        pid = make_id(page.url)
        if pid in known_ids:
            seen_again.add(pid)
        elif pid not in page_ids:
            page_ids.add(pid)
            pages.append(page)
    counts["erreichbar"] = len(pages)

    # 3. Extract (höchstens die Hälfte des Restbudgets, der Rest bleibt fürs Bewerten)
    opps: list[Opportunity] = []
    extract_limit = svc.budget.remaining // 2
    for page in pages[:extract_limit]:
        try:
            o = extract_opportunity(page, svc.gemini, svc.today)
        except Exception as exc:  # noqa: BLE001
            print(safe_error("extract", exc))
            _count(counts, "fehler")
            continue
        if o:
            opps.append(o)
    counts["extrahiert"] = len(opps)

    # 4. Dedupe (ähnliche Titel)
    threshold = svc.settings.get("dedupe", {}).get("title_similarity", 0.88)
    opps, dups = dedupe_batch(opps, known, threshold)
    counts["duplikate"] = len(dups)
    for d in dups:
        d.status = "ignoriert"
        d.warnings.append("Duplikat")

    # 5. Filter (Filter 1-9) und Warnungen
    survivors: list[Opportunity] = []
    filtered: list[Opportunity] = []
    for o in opps:
        reason = apply_pre_score_filters(o, svc.profile, svc.today)
        if reason:
            o.status = "ignoriert"
            o.warnings.append(f"Gefiltert: {reason}")
            filtered.append(o)
        else:
            add_warnings(o, svc.profile)
            survivors.append(o)

    # 6. Score (Gesamtscore in Python), danach Filter 10 und 11 (brauchen das Prestige)
    accepted: list[Opportunity] = []
    scored = 0
    for o in survivors:
        try:
            ok = score_opportunity(o, svc.profile, svc.settings, svc.gemini)
        except Exception as exc:  # noqa: BLE001
            print(safe_error("score", exc))
            _count(counts, "fehler")
            continue
        if not ok:
            continue  # ungültige Antwort oder Budget leer -> morgen nochmal
        scored += 1
        reason = apply_post_score_filters(o, svc.settings)
        if reason:
            o.status = "ignoriert"
            o.warnings.append(f"Gefiltert: {reason}")
            filtered.append(o)
        else:
            accepted.append(o)
    counts["bewertet"] = scored
    counts["gefiltert"] = len(filtered)

    # 7. Store: Gefilterte kommen mit Status 'ignoriert' ins Archiv, damit sie morgen nicht
    #    erneut Abrufe und Gemini-Aufrufe kosten. Gleiches gilt für Titel-Duplikate.
    add_new(tables, accepted)
    tables.archiv.extend(filtered + dups)
    touch_seen(tables, seen_again, svc.today)
    counts["archiviert"] = archive_expired(tables, svc.today)
    counts["neu_gespeichert"] = len(accepted)
    counts["gemini_aufrufe"] = svc.budget.used
    svc.store.save(tables)
    svc.store.log(counts)
    return RunResult(counts=counts, new_opps=accepted, tables=tables)


def run_outputs(svc: Services, result: RunResult) -> dict[str, str]:
    """Ausgaben: E-Mail, öffentliche Seite, Kalender-Feed.

    Jede Ausgabe ist einzeln abgesichert: ein Fehler in einer stoppt die anderen nicht.
    Im Log landet nur ein kurzer Status pro Ausgabe.
    """
    status: dict[str, str] = {}
    entries = result.tables.aktiv + result.tables.projekte
    mail_cfg = svc.settings.get("mail", {})

    # E-Mail: neue Top-Matches + Deadline-Reminder (nur senden, wenn es etwas gibt)
    try:
        reminders = deadline_reminders(entries, svc.today, mail_cfg.get("reminder_days", [7, 2]))
        content: MailContent = build_mail_content(result.new_opps, reminders, mail_cfg.get("min_score", 70))
        if content.is_empty():
            status["mail"] = "nichts zu senden"
        else:
            subject, html = render_email(content, svc.today)
            status["mail"] = "gesendet" if send_email(subject, html) else "lokal gespeichert (out/mail.html)"
    except Exception as exc:  # noqa: BLE001
        print(safe_error("mail", exc))
        status["mail"] = "FEHLER"

    # Öffentliche Seite (GitHub Pages): Ordner public_site/, wird vom Workflow veröffentlicht
    try:
        build_site(entries, svc.today)
        status["seite"] = "erstellt (public_site/)"
    except Exception as exc:  # noqa: BLE001
        print(safe_error("seite", exc))
        status["seite"] = "FEHLER"

    # Kalender-Feed: in den geheimen Gist hochladen, sonst lokal speichern
    try:
        ics = build_ics(entries)
        token, gist_id = os.environ.get("GIST_TOKEN", "").strip(), os.environ.get("GIST_ID", "").strip()
        if token and gist_id and not svc.is_mock:
            publish_gist(ics, token, gist_id)
            status["kalender"] = "aktualisiert"
        else:
            write_local(ics)
            status["kalender"] = "lokal gespeichert (out/opportunities.ics)"
    except Exception as exc:  # noqa: BLE001
        print(safe_error("kalender", exc))
        status["kalender"] = "FEHLER"
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Opportunity-Finder Pipeline")
    parser.add_argument("--mock", action="store_true", help="fiktive Daten statt Gemini/Sheets (kein Internet nötig)")
    parser.add_argument("--real", action="store_true",
                        help="Abbruch, wenn Zugangsdaten fehlen (für GitHub Actions: nie stillschweigend Mock)")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):  # Windows-Konsole: Umlaute richtig ausgeben
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    if args.real:
        fehlend = missing_secrets()
        if fehlend:
            print("Zugangsdaten fehlen: " + ", ".join(fehlend) + " (siehe SETUP_TODO.md)")
            return 1
    try:
        svc = build_services(args.mock)
    except Exception as exc:  # noqa: BLE001
        print(safe_error("start", exc))
        return 1
    if svc.is_mock:
        print("MOCK-Modus: fiktive Daten, kein Zugriff auf Gemini/Sheets.")
    try:
        result = run_pipeline(svc)
    except Exception as exc:  # noqa: BLE001
        print(safe_error("pipeline", exc))
        return 1
    # Nur Zähler ausgeben
    print("Zähler: " + ", ".join(f"{k}={v}" for k, v in result.counts.items() if k != "datum"))
    out = run_outputs(svc, result)
    print("Ausgaben: " + ", ".join(f"{k}={v}" for k, v in out.items()))
    return 1 if "FEHLER" in out.values() else 0


if __name__ == "__main__":
    sys.exit(main())
