# PROGRESS – Stand der Umsetzung

Eine neue Session muss allein mit dieser Datei + `SPEC.md` + `SETUP_TODO.md` weitermachen können.

## Regeln (vom Nutzer)
1. Kleine Schritte. Nach jedem Schritt: Tests, Commit mit klarer Nachricht, Push.
2. Manuelle Punkte (Google Cloud, Secrets, App-Passwort, OAuth) → `SETUP_TODO.md`, bis dahin Mocks.
3. Nie Schlüssel, Profildaten, Scores oder Mail-Inhalte in Code, Commits oder Logs (Actions-Logs sind öffentlich).
4. Code auf Deutsch kommentieren; am Ende jeder Phase hier einfach erklären, was gebaut wurde.
5. Umfang: Phasen 1–3 aus `SPEC.md`, am Stück.

## Ort / Umgebung
- Lokal: `C:\Users\User\opportunity-finder`, Remote: github.com/suhaan89/opportunity-finder (public)
- Python-Umgebung: `.venv` (Windows: `.venv\Scripts\python`), Tests: `.venv\Scripts\python -m pytest -q`
- Git-Autor in diesem Repo: `suhannawaz331@gmail.com` (lokal gesetzt, wegen GitHub-Mail-Schutz)
- Echtes Profil nur lokal in `profile.yaml` (ignoriert). `SPEC.md` im Repo ist bereinigt (fiktives Profil).

## Status
- [x] Schritt 0: `.gitignore`, `.env.example`, bereinigte `SPEC.md`, Beispielprofil
- Phase 1: Kern (MVP)
  - [x] 1.1 Gerüst: requirements, settings/sources.yaml, config, Profil-Loader, Datenmodell, Hilfsfunktionen
  - [x] 1.2 Harte Filter (`filters.py`, alle 11 einzeln getestet, Warnungen bei unklar)
  - [ ] 1.3 Scoring, 1.4 Dedupe, 1.5 Gemini/Collect/Verify/Extract, 1.6 Sheets, 1.7 Mail, 1.8 main + Mocks + Workflow
- Phase 2: Ausgaben (Reminder, .ics, GitHub Pages) – offen
- Phase 3: Mehr Quellen (Quellenseiten, Gmail) – offen

## Als Nächstes
1.3 Scoring (`src/scoring.py`).

## Offene Probleme
- keine
