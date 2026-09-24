# SETUP_TODO – Das musst du von Hand erledigen

Alles hier braucht dein Konto oder geheime Zugangsdaten. Claude kann das nicht für dich tun.
Bis du es erledigt hast, läuft der Code mit **Mocks** (fiktive Daten): `python -m src.main --mock`.

> **Goldene Regel:** Schlüssel und Passwörter kommen **nur** in die lokale Datei `.env` (steht in `.gitignore`)
> und in **GitHub Secrets**. Niemals in Code, Commits, Issues oder Chats. Das Repo und die Actions-Logs sind öffentlich.

Windows-Hinweis: Die Befehle unten sind für die Eingabeaufforderung/PowerShell im Projektordner
`C:\Users\User\opportunity-finder`. Python-Programme starten mit `.venv\Scripts\python`.

---

## 0. Grundlagen (einmalig)

- [ ] **`.env` anlegen:** Datei `.env.example` kopieren und die Kopie `.env` nennen.
      Jede Zeile hat die Form `NAME=wert` (ohne Leerzeichen, ohne Anführungszeichen, nur eine Zeile pro Wert).
- [ ] **Profil:** Dein echtes Profil liegt schon in `profile.yaml` (lokal, wird nie hochgeladen).
      Achtung: In der Original-`SPEC.md` war `projekte:` ungültiges YAML (`bedarf:` stand falsch eingerückt).
      In deiner `profile.yaml` heißt der Wert jetzt `projekte_bedarf`. Bitte **diese** Datei als Secret nehmen (Schritt 5).

## 1. Gemini-API-Schlüssel (Phase 1)

1. Öffne https://aistudio.google.com/apikey und melde dich mit deinem Google-Konto an.
2. Klicke **„Create API key"** (ggf. „in neuem Projekt") und kopiere den Schlüssel.
3. Trage ihn in `.env` ein: `GEMINI_API_KEY=dein_schluessel`
4. Prüfe in `config/settings.yaml` den Modellnamen (`gemini.model`). Steht dort ein Modell, das es bei dir
   nicht (mehr) gibt, wähle in Google AI Studio ein aktuelles „Flash"-Modell und trage den Namen dort ein.
5. Free-Tier-Hinweis: Die Suche mit Google-Grounding hat im Gratis-Tarif ein Tageslimit. Kommt es zu Fehlern
   (Zähler `fehler` im Log), verringere `gemini.searches_per_run` in `config/settings.yaml`.

## 2. Google Sheet + Service-Account (Phase 1)

**a) Google Cloud Projekt und Service-Account**
1. Öffne https://console.cloud.google.com/ und lege oben ein **neues Projekt** an (Name egal, z. B. „opportunity-finder").
2. Menü **„APIs & Dienste" → „Bibliothek"** → suche **„Google Sheets API"** → **Aktivieren**.
3. Menü **„IAM & Verwaltung" → „Dienstkonten"** → **„Dienstkonto erstellen"**. Name z. B. `opportunity-bot`, Rolle kannst du leer lassen → Fertig.
4. Klicke das neue Dienstkonto an → Tab **„Schlüssel"** → **„Schlüssel hinzufügen" → „Neuen Schlüssel erstellen" → JSON**.
   Eine Datei wird heruntergeladen.
5. Benenne sie in `service_account.json` um und lege sie in den Projektordner `C:\Users\User\opportunity-finder`
   (sie steht in `.gitignore` und wird nie hochgeladen). Öffne sie und kopiere den Wert von `client_email`
   (sieht aus wie `opportunity-bot@...iam.gserviceaccount.com`).

**b) Tabelle anlegen und freigeben**
1. Öffne https://sheets.google.com und erstelle eine **leere Tabelle** (Name z. B. „Opportunity-Finder"). Die Tabs legt das Programm selbst an.
2. Klicke **„Teilen"**, füge die `client_email` aus 2a als **Bearbeiter** hinzu (Benachrichtigung abwählen).
3. Die **Tabellen-ID** steht in der Adresse: `https://docs.google.com/spreadsheets/d/DIESE_ID/edit`.
   Trage sie in `.env` ein: `SHEET_ID=diese_id`
4. Lass die Tabelle **privat** (nicht „für alle mit Link").

## 3. E-Mail per Gmail (Phase 1)

1. Google-Konto → https://myaccount.google.com/security → **Bestätigung in zwei Schritten** einschalten (falls noch nicht).
2. Öffne https://myaccount.google.com/apppasswords, vergib einen Namen (z. B. `opportunity-finder`) und **erstelle** das App-Passwort.
   Du bekommst 16 Zeichen (Leerzeichen kannst du weglassen). Es wird nur einmal angezeigt.
3. In `.env`:
   ```
   SMTP_USER=deine.adresse@gmail.com
   SMTP_APP_PASSWORD=das_app_passwort
   MAIL_TO=empfaengeradresse@example.org
   ```
   (`MAIL_TO` darf dieselbe Adresse sein.)

## 4. Lokal testen (Phase 1)

- [ ] Mit fiktiven Daten (braucht nichts): `.venv\Scripts\python -m src.main --mock` → öffne danach `out\mail.html` im Browser.
- [ ] Echt (nach Schritt 1 bis 3): `.venv\Scripts\python -m src.main`
      Es erscheinen nur Zähler. Prüfe dein Google Sheet und dein Postfach.

## 5. GitHub Secrets und Actions (Phase 1)

1. Öffne https://github.com/suhaan89/opportunity-finder → **Settings → Secrets and variables → Actions → „New repository secret"**.
2. Lege diese Secrets an (Name genau so schreiben, Wert einfügen):

   | Name | Wert |
   |---|---|
   | `GEMINI_API_KEY` | Schlüssel aus Schritt 1 |
   | `PROFILE_YAML` | **kompletter Inhalt** deiner lokalen `profile.yaml` (mehrzeilig ist ok) |
   | `GOOGLE_SERVICE_ACCOUNT_JSON` | **kompletter Inhalt** von `service_account.json` |
   | `SHEET_ID` | Tabellen-ID aus Schritt 2 |
   | `SMTP_USER` | deine Gmail-Adresse |
   | `SMTP_APP_PASSWORD` | App-Passwort aus Schritt 3 |
   | `MAIL_TO` | Empfängeradresse |

3. **Fork-Schutz:** Settings → Actions → General → „Fork pull request workflows from outside collaborators"
   → **„Require approval for all outside collaborators"**. (Der tägliche Workflow läuft ohnehin nie bei Pull Requests.)
4. **Ersten Lauf starten:** Reiter **Actions → „Daily" → „Run workflow"**. Im Log sollten nur Zähler stehen.
   Steht dort „Zugangsdaten fehlen: …", fehlt das genannte Secret.

---

## 6. GitHub Pages einschalten (Phase 2)

1. Repo → **Settings → Pages** → bei **„Source"** **„GitHub Actions"** wählen. (Mehr ist nicht nötig.)
2. Danach startet nach jedem erfolgreichen „Daily"-Lauf automatisch der Workflow **„Pages"** und veröffentlicht die Seite.
   Die Adresse steht im Pages-Workflow-Lauf und unter Settings → Pages (meist `https://suhaan89.github.io/opportunity-finder/`).
3. Die Seite zeigt nur öffentliche Angebotsdaten (kein Score, Status, Notizen, Profil) und hat `noindex` (Google soll sie nicht listen).
   Alles, was du im Sheet auf Status `ignoriert` setzt, verschwindet von der Seite.

## 7. Kalender-Feed per geheimem Gist (Phase 2)

**a) Gist anlegen**
1. Öffne https://gist.github.com/ (eingeloggt).
2. Dateiname: `opportunities.ics`, Inhalt (nur diese zwei Zeilen):
   ```
   BEGIN:VCALENDAR
   END:VCALENDAR
   ```
3. Unten **„Create secret gist"** wählen (nicht „public"!).
4. Die **Gist-ID** ist der letzte Teil der Adresse: `https://gist.github.com/suhaan89/DIESE_ID`.

**b) Token anlegen (nur Recht „gist")**
1. https://github.com/settings/tokens → **„Generate new token" → „Generate new token (classic)"**.
2. Name z. B. `opportunity-finder-gist`, Ablauf nach Wunsch (bei Ablauf musst du einen neuen Token eintragen).
3. Hake **nur `gist`** an. Erzeugen und den Token sofort kopieren (wird nur einmal angezeigt).

**c) Eintragen**
- In `.env` (nur lokal) und als GitHub Secrets: `GIST_TOKEN` = Token, `GIST_ID` = Gist-ID.

**d) In Google Kalender abonnieren (einmalig)**
1. Nach dem ersten echten Lauf ist der Feed gefüllt. Die Abo-Adresse lautet:
   `https://gist.githubusercontent.com/suhaan89/DEINE_GIST_ID/raw/opportunities.ics`
   (ohne Commit-Hash, so zeigt sie immer die neueste Version.)
2. https://calendar.google.com → links bei **„Weitere Kalender"** auf **+** → **„Per URL"** → Adresse einfügen → **„Kalender hinzufügen"**.
3. Google aktualisiert abonnierte Kalender nur alle paar Stunden bis ~1 Tag, das ist normal.
4. Im Feed erscheinen nur Einträge mit Status `interessant`, `in_vorbereitung`, `beworben` oder `zusage`.
   Deadline-Reminder-Mails kommen für `interessant` und `in_vorbereitung` (7 und 2 Tage vorher).
   Setze also im Google Sheet in der Spalte `status` die Werte per Dropdown.

## Phase 3
(wird ergänzt, sobald die Funktionen gebaut sind)
