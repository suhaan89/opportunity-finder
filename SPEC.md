# SPEC.md: Opportunity-Finder

Persönliches System, das täglich automatisch nach Events, Stipendien, Wettbewerben, Hackathons, Akademien, Uni-Programmen und Projektförderungen sucht, sie nach festen Kriterien filtert, per KI bewertet und die besten Treffer per E-Mail schickt.

Diese Datei ist die verbindliche Spezifikation für Claude Code. Bitte phasenweise umsetzen (siehe Abschnitt 10) und nach jeder Phase stoppen, testen und erklären.

---

## 1. Rahmenbedingungen

- **Nutzer:** Schüler, Coding-Anfänger. Code muss verständlich, kommentiert und einfach aufgebaut sein. Nach jedem Schritt kurz erklären, was gebaut wurde und warum.
- **Sprache:** Python 3.12
- **Ausführung:** GitHub Actions, täglich per Cron. Kein eigener Server.
- **KI:** Gemini API (Google AI Studio, Free Tier) mit Grounding über Google Search. Modellname kommt aus der Config, nie hart im Code.
- **Datenbank:** Google Sheets (privat)
- **Ausgabe:** tägliche HTML-E-Mail, öffentliche GitHub-Pages-Seite, privater Kalender-Feed (.ics)
- **Repo:** öffentlich. Daraus folgt:
  - Keine persönlichen Daten im Repo. Profil und Zugangsdaten nur als GitHub Secrets.
  - **GitHub-Actions-Logs sind öffentlich.** Niemals Profil, Scores, Status, E-Mail-Inhalte oder Secrets loggen. Nur technische Zähler (z. B. "12 gefunden, 4 gefiltert").
  - Workflows dürfen nicht durch Pull Requests aus Forks mit Secrets laufen.
- **Kosten:** 0 €. Budget-Schutz: maximale Anzahl Gemini-Aufrufe pro Lauf ist konfigurierbar (Standard 40).

---

## 2. Architektur

```
GitHub Actions (täglich 05:00 UTC)
        |
        v
[1] Collect      Suchanfragen an Gemini mit Google Search
                 + kuratierte Quellenseiten (sources.yaml)
                 + Gmail-Newsletter (ab Phase 3)
        |
        v
[2] Verify       Redirect-Links auflösen, URL erreichbar? (HTTP 200)
                 Seite laden, Fakten aus dem ECHTEN Seiteninhalt extrahieren
        |
        v
[3] Extract      Gemini extrahiert strukturierte Felder (JSON-Schema, Abschnitt 4)
        |
        v
[4] Dedupe       normalisierte URL + Titel-Ähnlichkeit gegen Sheet
        |
        v
[5] Filter       harte Ausschlusskriterien, deterministisch in Python (Abschnitt 5)
        |
        v
[6] Score        Match-Score 0 bis 100 plus 1 Satz Begründung (Abschnitt 6)
        |
        v
[7] Store        Google Sheets (neue Einträge, Updates, Archiv)
        |
        v
[8] Output       E-Mail (nur wenn Neues oder Deadline-Reminder)
                 GitHub Pages (öffentliche Liste ohne persönliche Daten)
                 .ics-Feed (privat, Secret Gist)
```

**Wichtig gegen erfundene Links:** Gemini darf nie die Quelle der Wahrheit sein. Jeder Eintrag braucht eine erreichbare URL, und Deadline, Kosten und Voraussetzungen werden aus dem geladenen Seitentext extrahiert. Kann ein Feld nicht belegt werden, wird es als `unklar` gespeichert, nicht geraten.

---

## 3. Repo-Struktur

```
opportunity-finder/
├── SPEC.md
├── README.md                    Setup-Anleitung für andere Nutzer
├── requirements.txt
├── config/
│   ├── settings.yaml            Modellname, Limits, Schwellenwerte
│   ├── sources.yaml             Quellen und Suchanfragen
│   └── profile.example.yaml     Beispielprofil (öffentlich, fiktiv)
├── src/
│   ├── main.py                  Pipeline-Einstieg
│   ├── collect.py
│   ├── verify.py
│   ├── extract.py
│   ├── dedupe.py
│   ├── filters.py
│   ├── scoring.py
│   ├── sheets.py
│   ├── mailer.py
│   ├── site.py                  GitHub-Pages-Generator
│   ├── ics.py
│   ├── gmail_reader.py          ab Phase 3
│   └── profile.py               lädt Profil aus Secret
├── templates/
│   ├── email.html.j2
│   └── site.html.j2
├── tests/
└── .github/workflows/
    ├── daily.yml
    └── pages.yml
```

---

## 4. Datenmodell (eine Zeile im Sheet)

| Feld | Typ | Beschreibung |
|---|---|---|
| id | str | Hash aus normalisierter URL |
| title | str | |
| organizer | str | |
| url | str | geprüft erreichbar |
| category | enum | stipendium, wettbewerb, hackathon, akademie, networking, jugendforum, uni_programm, projektfoerderung, sonstiges |
| target | enum | person oder projekt (eigenes Projekt) |
| format | enum | praesenz, online, hybrid |
| location_city / location_country | str | |
| event_start / event_end | date oder unklar | |
| deadline | date oder unklar | |
| recurring_yearly | bool | |
| age_min / age_max | int oder unklar | |
| eligibility | str | Kurzfassung der Voraussetzungen |
| required_docs | str | Unterlagen |
| language | enum | de, en, andere |
| fee_eur | float oder unklar | |
| travel_covered | ja / nein / teilweise / unklar | |
| fully_funded | bool | |
| requires_legal_entity | bool | e.V., GmbH o. ä. nötig |
| benefits | list | geld, mentoring, netzwerk, zertifikat, credits, hardware, inkubator, preis |
| prestige | int 0-100 | |
| effort | niedrig / mittel / hoch | |
| score | int 0-100 | privat |
| score_reason | str | privat, 1 Satz |
| warnings | list | z. B. "Reisekosten unklar", "Pay-to-play-Verdacht" |
| status | enum | neu, interessant, in_vorbereitung, beworben, zusage, absage, teilgenommen, ignoriert |
| notes | str | vom Nutzer |
| first_seen / last_checked | date | |

**Sheet-Tabs:** `Aktiv`, `Archiv`, `Projekte` (target = projekt), `Log` (nur technische Zähler).

---

## 5. Harte Filter (deterministisch, in Python)

Ein Eintrag fliegt raus, wenn:

1. Deadline in der Vergangenheit liegt.
2. Altersgrenze verletzt ist. Prüfen gegen das Alter **zum Eventdatum** (Geburtsdatum aus Profil).
3. Sprache nicht Deutsch oder Englisch ist.
4. Veranstaltungsort oder Uni in einem ausgeschlossenen Land liegt (Liste im Profil).
5. Teilnahmegebühr über dem Maximum liegt (Profil: 150 €).
6. Reisekosten nachweislich **nicht** übernommen werden. Bei `unklar`: behalten, aber Warnung setzen.
7. Eine Rechtsform (e.V., GmbH) vorausgesetzt wird.
8. Das Event in einem Sperrzeitraum liegt (Abi-Phase, im Profil konfigurierbar).
9. Es ein Fachwettbewerb in einem ausgeschlossenen Fach ist (Profil).
10. Es online ist und nicht die Online-Ausnahme erfüllt (Abschnitt 6).
11. Es regional (Umkreis im Profil) ist und nicht die Regional-Ausnahme erfüllt (Abschnitt 6).

Jeder Filter ist eine eigene, getestete Funktion.

---

## 6. Match-Score

Score = gewichtete Summe von Teilwerten (je 0 bis 100). Gewichte in `settings.yaml`.

| Teilwert | Gewicht | Quelle |
|---|---|---|
| Interessen-Fit | 35 % | Gemini bewertet gegen die Interessenpunkte im Profil |
| Förderwert | 20 % | fully_funded, travel_covered, benefits |
| Prestige | 20 % | Gemini-Einschätzung plus bekannte Top-Anbieter |
| Karrierenutzen | 15 % | Nutzen für KI-Forschung, Top-Uni-Bewerbung, Startups |
| Netzwerk-Bonus | 5 % | Anbieter aus Netzwerkliste im Profil, gestaffelt |
| Machbarkeit | 5 % | Voraussetzungen sicher erfüllt, Termin passt |

Sonderregeln:
- **Online-Ausnahme:** Online-Angebote bleiben nur, wenn Prestige ≥ 85.
- **Regional-Ausnahme:** Events im Regionalradius bleiben nur, wenn Prestige ≥ 80.
- **Voll finanziert international** (Reise, Unterkunft, Programm gezahlt): +10 Bonus, maximal 100.
- **Feedback-Lernen (Phase 4):** Kategorien und Anbieter, die der Nutzer im Sheet als `interessant`, `beworben` oder `zusage` markiert, bekommen einen kleinen Bonus. `ignoriert` gibt einen kleinen Malus. Maximal ±10 Punkte.

Gemini liefert Teilwerte als JSON (mit Schema-Validierung). Der Gesamtscore wird in Python berechnet, nicht vom Modell.

**E-Mail-Schwelle:** Score ≥ 70.

---

## 7. Quellen (`config/sources.yaml`)

Zwei Arten, beide editierbar:

**a) Suchanfragen für Gemini mit Google Search** (Deutsch und Englisch), rotierend, damit pro Lauf das Aufruf-Limit hält. Beispiele:
- fully funded summer program high school students AI
- KI Wettbewerb Schüler 2027
- Schülerstipendium Deutschland Informatik
- international youth summit fully funded 2027
- Hackathon Schüler Deutschland
- Sommerakademie Schüler MINT
- pre-college research program AI scholarship
- youth startup incubator Europe students
- Förderung Schülerfirma Projekt KI
- cloud credits nonprofit student project

**b) Kuratierte Quellenseiten**, die direkt geladen und ausgewertet werden. Startliste (vom Nutzer erweiterbar):
- Young Founders Network (Priorität hoch)
- young leaders (Priorität mittel)
- SALTO-YOUTH / European Youth Portal (Priorität niedrig)
- Deutsche SchülerAkademie, Jugend forscht, Bundesweite Informatikwettbewerbe
- Studienstiftung, e-fellows.net
- Stiftung Bildung, Start-up Teens
- Devpost, Major League Hacking

Bereits genutzte Förderungen (z. B. Programme, die der Nutzer schon hat) stehen im Profil unter `bereits_gefoerdert` und werden markiert statt erneut vorgeschlagen.

---

## 8. Ausgaben

**E-Mail (täglich, nur wenn es etwas gibt):**
- Abschnitt "Neue Top-Matches" (Score ≥ 70, sortiert), je Karte: Titel, Score mit Begründung, Deadline, Ort, Kosten/Förderung, Voraussetzungen, Aufwand, Warnungen, Link.
- Abschnitt "Deadlines bald": Einträge mit Status `interessant` oder `in_vorbereitung`, 7 und 2 Tage vor Deadline.
- Abschnitt "Projektförderung" separat.
- Modernes, mobiloptimiertes HTML (Inline-CSS, Dark-Mode-tauglich). Versand über Gmail SMTP mit App-Passwort.

**GitHub Pages (öffentlich):**
- Liste aller aktiven Angebote mit Filtern (Kategorie, Land, Deadline, Online/Präsenz).
- Ohne Score, Status, Notizen oder Profildaten.
- Statisch generiert (Jinja2), schönes, modernes Design, mobil gut nutzbar.

**Kalender-Feed (.ics):**
- Nur Deadlines und Eventtermine von Einträgen mit Status `interessant`, `in_vorbereitung`, `beworben`, `zusage`.
- Gehostet als Secret Gist (nicht öffentlich gelistet), Abo-Link einmal in Google Kalender einfügen.

---

## 9. Profil (Secret `PROFILE_YAML`, nie ins Repo)

```yaml
# Beispielprofil (fiktiv, öffentlich). Das echte Profil liegt als GitHub Secret PROFILE_YAML
# bzw. lokal in profile.yaml (beides nie im Repo).
geburtsdatum: 2010-03-15
schulabschluss: Abitur 2027 (Beispiel-Bundesland)
schnitt: 2.0
coding_level: anfaenger
heimatort: Musterstadt
sprachen_programme: [de, en]

interessen_punkte:
  ki_forschung: 40
  informatik_coding: 20
  social_startups: 20
  politik_demokratie: 10
  wirtschaft: 5
  sport: 5

ausgeschlossene_wettbewerbsfaecher: [geschichte, deutsch, englisch]
ausgeschlossene_laender: [Beispielland]

studium:
  ziel: gute Uni weltweit, Duales Studium als Alternative
  richtungen: [Informatik, KI]

kriterien:
  kategorien: alle
  reichweite: weltweit
  format_praeferenz: praesenz
  reisekosten_muessen_uebernommen_werden: true
  max_teilnahmegebuehr_eur: 150
  regionalradius_km: 60
  auch_nach_abi: true
  sperrzeitraeume:
    - von: 2027-03-01
      bis: 2027-05-05
  rechtsform_erforderlich_ausschliessen: true

netzwerke:
  young_founders_network: 10
  young_leaders: 6
  salto_youth: 2

projekte:
  - name: Projekt A
    beschreibung: Beispielprojekt
  bedarf: [geld, api_credits, cloud_credits, hardware, mentoring, inkubator, preise]

bereits_gefoerdert: [Beispielprogramm]
```

---

## 10. Umsetzungsphasen

Nach jeder Phase: Tests laufen lassen, Ergebnis zeigen, erklären, auf OK warten.

**Phase 1: Kern (MVP)**
Collect (nur Gemini-Suche), Verify, Extract, Dedupe, Filter, Score, Sheets, E-Mail. Erst lokal mit `.env` testen, dann GitHub Actions.

**Phase 2: Ausgaben**
GitHub-Pages-Seite, .ics-Feed, Deadline-Reminder.

**Phase 3: Mehr Quellen**
Kuratierte Quellenseiten aus `sources.yaml`, Gmail-Newsletter lesen (Gmail API, nur Lesezugriff, nur bestimmtes Label).

**Phase 4: Intelligenz**
Feedback-Lernen aus Sheet-Status, jährliche Wiederholungen vormerken, Pay-to-play-Erkennung, optional Bewerbungs-Checkliste pro Eintrag.

**Phase 5: Für andere nutzbar**
README mit Setup-Anleitung, `profile.example.yaml`, Fork-fähig (z. B. für die KI-AG).

---

## 11. Secrets (GitHub → Settings → Secrets)

| Secret | Wofür | Phase |
|---|---|---|
| GEMINI_API_KEY | Google AI Studio | 1 |
| PROFILE_YAML | Profil aus Abschnitt 9 | 1 |
| GOOGLE_SERVICE_ACCOUNT_JSON | Zugriff auf Google Sheets | 1 |
| SHEET_ID | ID der Tabelle | 1 |
| SMTP_USER / SMTP_APP_PASSWORD / MAIL_TO | E-Mail-Versand | 1 |
| GIST_TOKEN / GIST_ID | .ics-Feed | 2 |
| GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / GMAIL_REFRESH_TOKEN | Gmail lesen | 3 |

Hinweis Gmail API: Eine Google-OAuth-App im Status "Testing" liefert Refresh-Tokens, die nach 7 Tagen ablaufen. App auf "In production" stellen (für private Nutzung ohne Verifizierung möglich, mit Warnhinweis beim Login).

---

## 12. Qualitätsregeln für Claude Code

- Kleine, testbare Funktionen, Typ-Hinweise, Kommentare auf Deutsch.
- Pytest für Filter, Scoring, Dedupe und Datumslogik.
- Alle Gemini-Antworten gegen JSON-Schema validieren, bei Fehler einmal wiederholen, dann überspringen.
- Robuste Fehlerbehandlung: Eine kaputte Quelle darf den Lauf nicht abbrechen.
- Keine neuen Abhängigkeiten ohne kurze Begründung.
- Datumslogik in Zeitzone Europe/Berlin.
- Nichts Persönliches loggen (Abschnitt 1).
