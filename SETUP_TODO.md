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

## 8. Weitere Quellenseiten (Phase 3)

Die kuratierten Quellenseiten stehen in `config/sources.yaml` unter `pages:`. Sie laufen ohne Zusatz-Zugang
(Gemini liest die Seite und sucht Links zu konkreten Angeboten heraus).

- [ ] **Young Founders Network** und **young leaders**: Ich kenne die genauen Web-Adressen nicht und habe keine geraten.
      Trage bei beiden die Adresse der Seite ein, auf der die aktuellen Angebote/Events aufgelistet sind
      (`url:`), und setze `enabled: true`.
- [ ] Die anderen Adressen (Devpost, MLH, Jugend forscht …) stammen aus meinem Wissen. Öffne sie einmal im Browser;
      ist eine Adresse tot oder falsch, ändere sie oder setze `enabled: false`. Eine kaputte Quelle bricht den Lauf nicht ab,
      sie erhöht nur den Zähler `fehler` im Log.
- Pro Lauf werden höchstens `sources.max_pages_per_run` Seiten gelesen (Priorität `hoch` immer, der Rest rotiert).

## 9. Gmail-Newsletter lesen (Phase 3)

Das Programm liest nur Mails mit **einem bestimmten Label** und hat **nur Lesezugriff** (`gmail.readonly`).
Es sendet, löscht oder ändert nichts. Abmelde-Links werden nie geöffnet.

**a) Label und Filter in Gmail**
1. Gmail öffnen → links **„Neues Label erstellen"** → Name: `Opportunity-Finder`
   (muss zu `gmail.label` in `config/settings.yaml` passen).
2. Für jeden Newsletter-Absender: eine Mail öffnen → drei Punkte → **„Ähnliche Nachrichten filtern"** → **„Filter erstellen"** →
   **„Label anwenden: Opportunity-Finder"** (optional auch „Posteingang überspringen") → speichern.

**b) Gmail API und OAuth-Zugang in Google Cloud (gleiches Projekt wie bei Google Sheets)**
1. https://console.cloud.google.com/ → dein Projekt wählen → **„APIs & Dienste" → „Bibliothek"** → **„Gmail API"** → **Aktivieren**.
2. **„APIs & Dienste" → „OAuth-Zustimmungsbildschirm"** (heißt je nach Oberfläche „Google Auth Platform"):
   - App-Name z. B. `opportunity-finder`, Support-E-Mail = deine Adresse.
   - Zielgruppe/Nutzertyp: **Extern**.
   - Unter **Datenzugriff / Bereiche (Scopes)**: `https://www.googleapis.com/auth/gmail.readonly` hinzufügen.
   - **Wichtig:** Den Veröffentlichungsstatus auf **„In Produktion"** stellen („App veröffentlichen").
     Im Status „Testing" laufen Refresh-Tokens nach 7 Tagen ab, und der Newsletter-Abruf würde nach einer Woche stillschweigend aufhören.
     Für private Nutzung ist keine Google-Prüfung nötig; beim Login erscheint nur der Warnhinweis „Nicht verifiziert".
3. **„Anmeldedaten" → „Anmeldedaten erstellen" → „OAuth-Client-ID"** → Typ **„Webanwendung"** →
   bei **„Autorisierte Weiterleitungs-URIs"** eintragen: `https://developers.google.com/oauthplayground` → Erstellen.
   Kopiere **Client-ID** und **Clientschlüssel**.

**c) Refresh-Token holen (einmalig, mit dem OAuth Playground)**
1. Öffne https://developers.google.com/oauthplayground/
2. Zahnrad oben rechts → Haken bei **„Use your own OAuth credentials"** → Client-ID und Clientschlüssel einfügen → Schließen.
3. Links bei **„Step 1"** ins Feld unten `https://www.googleapis.com/auth/gmail.readonly` eintippen → **„Authorize APIs"**.
4. Mit dem Google-Konto anmelden, in das die Newsletter kommen. Kommt „Google hat diese App nicht überprüft":
   **„Erweitert" → „Zu … (unsicher) wechseln"** → Zugriff erlauben.
5. **„Step 2" → „Exchange authorization code for tokens"** → den Wert **Refresh token** kopieren.

**d) Eintragen**
- `.env` (lokal) und GitHub Secrets: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`.
- Sind alle drei gesetzt, liest der Lauf Newsletter. Im Log erscheint dann `mails=<Anzahl>`.
  Bleibt `mails=0` und `fehler` steigt, stimmt meist das Token nicht (abgelaufen/widerrufen → Schritt c wiederholen).

**e) Hinweis zum Datenschutz:** Der Text der gelabelten Mails wird an die Gemini-API geschickt, damit Angebots-Links herausgesucht werden.
Labele deshalb nur echte Newsletter, keine privaten Mails. Im GitHub-Log erscheinen nie Mail-Inhalte, nur Zähler.
