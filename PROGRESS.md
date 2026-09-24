# PROGRESS – Stand der Umsetzung

Eine neue Session muss allein mit dieser Datei + `SPEC.md` + `SETUP_TODO.md` weitermachen können.

## Regeln (vom Nutzer)
1. Kleine Schritte. Nach jedem Schritt: Tests, Commit mit klarer Nachricht, Push.
2. Manuelle Punkte (Google Cloud, Secrets, App-Passwort, OAuth) → `SETUP_TODO.md`, bis dahin Mocks.
3. Nie Schlüssel, Profildaten, Scores oder Mail-Inhalte in Code, Commits oder Logs (Actions-Logs sind öffentlich).
4. Code auf Deutsch kommentieren; am Ende jeder Phase hier einfach erklären, was gebaut wurde.
5. Umfang: Phasen 1–3 aus `SPEC.md`, am Stück. Danach stoppen.

## Ort / Umgebung
- Lokal: `C:\Users\User\opportunity-finder`, Remote: github.com/suhaan89/opportunity-finder (public)
- Python-Umgebung: `.venv` (Windows: `.venv\Scripts\python`), Tests: `.venv\Scripts\python -m pytest -q`
- Lauf ohne Zugangsdaten: `.venv\Scripts\python -m src.main --mock` (schreibt nach `out/`, ignoriert)
- Echter Lauf: `python -m src.main` (mit `.env`); in Actions: `python -m src.main --real` (bricht ab, wenn Secrets fehlen)
- Git-Autor in diesem Repo: `suhannawaz331@gmail.com` (lokal gesetzt, wegen GitHub-Mail-Schutz)
- Echtes Profil nur lokal in `profile.yaml` (ignoriert). `SPEC.md` im Repo ist bereinigt (fiktives Profil).
  Die Original-SPEC liegt auf dem Desktop (dort steht noch das ungültige YAML bei `projekte:`).

## Status
- [x] Schritt 0: `.gitignore`, `.env.example`, bereinigte `SPEC.md`, Beispielprofil
- [x] **Phase 1: Kern (MVP)** – Code fertig und getestet (Mock-Lauf grün). Echtlauf wartet auf `SETUP_TODO.md` Schritte 1–5.
  - 1.1 Gerüst, Config, Profil-Loader, Datenmodell (`models.py`, `util.py`, `config.py`, `profile.py`)
  - 1.2 Harte Filter (`filters.py`, 11 einzeln getestet) · 1.3 Scoring (`scoring.py`) · 1.4 Dedupe (`dedupe.py`)
  - 1.5 Gemini-Wrapper mit Budget (`gemini.py`), Collect, Verify, Extract
  - 1.6 Speicher (`sheets.py`, Google Sheets + lokaler Ersatz) · 1.7 Mailer (`mailer.py`)
  - 1.8 `main.py`, `mocks.py`, Workflows `daily.yml` + `tests.yml`
- [x] **Phase 2: Ausgaben** – Code fertig und getestet. Echtbetrieb wartet auf `SETUP_TODO.md` Schritte 6–7.
  - 2.1 `reminders.py` (7/2 Tage vor Deadline, nur Status interessant/in_vorbereitung), `ics.py` (Feed + Upload in geheimen Gist),
    `site.py` + `templates/site.html.j2` (statische Seite mit Filtern)
  - 2.2 Einbindung in `main.py` (`run_outputs`: Mail inkl. Reminder, Seite nach `public_site/`, Kalender), `pages.yml`,
    `daily.yml` lädt nur `public_site` als Artefakt hoch
- [ ] Phase 3: Mehr Quellen (Quellenseiten aus `sources.yaml`, Gmail-Newsletter)

## Als Nächstes
Phase 3: `collect.py` um Quellenseiten erweitern (Gemini liest Listenseiten), `gmail_reader.py` (Gmail-API nur lesen, nur Label), in `main.gather_candidates` einhängen.

## Phase 1 in einfachen Worten (was wurde gebaut?)
Das Programm ist wie ein Fließband, das jeden Tag läuft:
1. **Sammeln:** Gemini sucht mit Google nach Angeboten (Stipendien, Hackathons, Akademien …) und liefert Titel + Link.
2. **Prüfen:** Wir öffnen jeden Link selbst. Was nicht erreichbar ist, fliegt raus. Wir lesen den *echten* Text der Seite.
3. **Auslesen:** Gemini zieht aus dem Seitentext Deadline, Kosten, Alter usw. Jede Deadline braucht ein wörtliches
   Zitat von der Seite, sonst wird sie als „unklar" gespeichert. So gibt es keine erfundenen Termine.
4. **Doppelte raus:** Gleiche Links oder fast gleiche Titel werden nur einmal behalten.
5. **Filter:** Reine Python-Regeln (Alter, Land, Gebühr, Deadline, Abi-Sperrzeit …) sortieren Unpassendes aus.
6. **Bewerten:** Gemini schätzt nur „weiche" Dinge (passt zu Interessen? renommiert?). Den Gesamtscore 0–100 rechnet Python aus.
7. **Speichern:** Gute Treffer kommen ins Google Sheet (Tab „Aktiv", Projekte in „Projekte"), Aussortiertes ins „Archiv".
8. **Mail:** Gibt es neue Treffer mit Score ≥ 70, kommt eine HTML-Mail.
Ohne Zugangsdaten läuft alles mit erfundenen Beispieldaten (`--mock`), damit man das Zusammenspiel testen kann.
Im öffentlichen Log stehen nur Zahlen (z. B. „kandidaten=8, gefiltert=4"), nie Inhalte.

## Phase 2 in einfachen Worten (was wurde gebaut?)
- **Deadline-Reminder:** Setzt du im Sheet den Status auf „interessant" oder „in_vorbereitung", steht der Eintrag genau
  7 und 2 Tage vor der Deadline in der Tages-Mail (Abschnitt „Deadlines bald"). Auch ohne neue Treffer kommt dann eine Mail.
- **Kalender-Feed (.ics):** Eine Datei mit Deadlines und Eventterminen deiner verfolgten Einträge. Sie liegt in einem geheimen Gist;
  Google Kalender abonniert die Adresse. Deadlines haben eine Erinnerung einen Tag vorher.
- **Öffentliche Seite:** Eine einzelne HTML-Seite (hell/dunkel, handytauglich) mit Suche und Filtern (Kategorie, Land, Format, Deadline).
  Eine feste Positivliste (`public_view`) bestimmt, welche Felder erscheinen; Score, Status, Notizen und Profil kommen nie darauf.
  Der Workflow „Pages" veröffentlicht sie nach jedem erfolgreichen Tageslauf.

## Entscheidungen / Abweichungen von der SPEC (bitte kurz prüfen)
- `SPEC.md` im Repo enthält statt deines Profils ein **fiktives** Beispiel (Repo ist öffentlich).
- Profil-YAML aus der SPEC war ungültig (`bedarf:` falsch eingerückt) → jetzt `projekte_bedarf:` (Profil, Beispiel, SPEC).
- Filter 10 (Online) und 11 (Regional) gelten **nicht** für `target = projekt` (Cloud-Credits etc. sind fast immer online).
- Aussortierte Einträge und Titel-Duplikate werden mit Status `ignoriert` ins **Archiv** geschrieben (Warnung „Gefiltert: <Grund>"
  bzw. „Duplikat"), damit sie nicht jeden Tag erneut Abrufe/Gemini-Aufrufe kosten.
- Zusatzfelder im Sheet: `subject` (Fach bei Wettbewerben, für Filter 9) und `regional` (Umkreis-Einschätzung von Gemini, Filter 11).
- Das Sheet wird pro Lauf komplett neu geschrieben: Änderungen, die du *während* des Laufs (Minuten um 05:00 UTC) machst, können verloren gehen.
- Die öffentliche Seite hat `noindex` (nicht in Suchmaschinen listen) und zeigt auch Einträge aus „Projekte"; `ignoriert` wird ausgeblendet.
- `pages.yml` läuft per `workflow_run` nach „Daily" und holt das Artefakt `site` (nur die öffentliche Seite; Artefakte öffentlicher Repos sind für alle sichtbar).
- Extraktion + Bewertung kosten je 1 Gemini-Aufruf pro Eintrag; Extraktion nutzt max. die Hälfte des Restbudgets.

## Offene Probleme
- Echtlauf gegen Gemini/Sheets/SMTP noch nicht getestet (fehlende Zugangsdaten → `SETUP_TODO.md`). Die Anbindung ist
  gegen Attrappen getestet; beim ersten echten Lauf können API-Details (Modellname, Grounding-Limits) Anpassungen brauchen.
- Modellname `gemini-2.5-flash` ist eine Annahme; in `config/settings.yaml` prüfen.
- Feedback-Lernen, Pay-to-play, jährliche Wiederholungen (Phase 4) und README/Fork-Fähigkeit (Phase 5) sind nicht Teil dieses Auftrags.
