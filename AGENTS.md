# AGENTS.md

Anleitung für KI-Assistenten (Claude, Codex, Copilot usw.) und neue Mitwirkende.
Zuerst lesen, dann arbeiten.

## Zweck

Auswertung der Maus-Tracking-Daten der AFE2-Studie (FFHS MSc Wirtschaftsinformatik,
Adrian Wegmann und Adrian Martic, Betreuung Dr. Christof Imhof). Die Auswertung muss
**nachvollziehbar und reproduzierbar** sein: Jeder Schritt von den Rohdaten bis zur
Kennzahl steht im Code oder in `config/`, damit er im Methodenteil der Arbeit belegt
werden kann.

## Studiendesign (Kurzfassung)

- A/B-Vergleich zweier Varianten derselben WordPress-Website (eagle-wings.ch, eine Installation):
  - **ML** (Menüversion): Startseite `eagle-wings.ch/` plus Unterseiten (erfolge, saison-und-wettkampfkalender,
    training, material, partner, abseits-vom-bike), Fragebogen auf `kontakt/`
  - **OP** (Onepager): `eagle-wings.ch/one-pager/`, Fragebogen direkt auf der Seite eingebettet
- Inhalt: Profil der Mountainbikerin «Mira Caduff» mit Porträt (AOI)
- Teilnehmende lösen drei Suchaufgaben (Herkunft, Trainer, Sporternährung) und füllen danach den
  Fragebogen aus. Ziel: max. ca. 50 Personen. Fragebogen (WPForms):
  - Demografie: Geschlecht (männlich, weiblich, keine Angabe), Altersgruppe
  - pro Aufgabe: Freitextantwort + Schwierigkeit 1-5 (1 = sehr einfach, 5 = sehr schwierig)
  - UEQ-S, 8 Items, **5-stufig** (Original 7-stufig, daher keine Benchmark-Vergleiche)
  - optional E-Mail (nur Verlosung, wird nie importiert) und Feedback
- Feldphase ab 26.10.2026. Am 26.10. zeichnete Matomo in der Menüversion nur die erste Seite auf;
  ML-Mausdaten zählen deshalb erst ab 27.10., OP ab 26.10. (`variant_start` in `config/study.toml`).
  Die Fragebogen vom 26.10. sind in beiden Varianten gültig (Teamentscheid 27.10.2026).
- Aufgabe 1: «Prättigau» und «Schiers» gelten beide als richtig (Teamentscheid 27.10.2026).
- Zuteilung zur Variante über zwei Hälften der Verteilerliste (keine Randomisierung).
- Tracking: Matomo On-Premise für WordPress mit Plugin Heatmap & Session Recording.
- Fragebogendaten stehen in `wp_wpforms_entries` (Formular 79 = ML, 118 = OP). Es gibt keine
  Teilnehmer-ID; die Zuordnung Fragebogen ↔ Besuch erfolgt automatisch über den Zeitpunkt
  (`forms.py`), Korrekturen in `config/match_overrides.csv`. Zeitstempel von Matomo und WPForms sind UTC.
- Zwei Stichproben: Fragebogen (H3a, H3b, auch ohne Aufzeichnung) und Maus+Fragebogen (H1, H2, H4, H5).

## Befehle

```
setup.bat                       # einmalig: .venv + Pakete
afe.bat all                     # Import + Aufbereitung + Bericht
afe.bat info                    # Besuche, Variante, Ausschlussgrund
.venv\Scripts\python -m pytest  # Tests (müssen grün sein vor jedem Commit)
afe.bat strip                   # Notebook-Outputs löschen vor jedem Commit
```

Unter Linux/macOS (z. B. in einer KI-Sandbox): `python -m venv .venv && .venv/bin/pip install -r requirements.txt -e .`,
danach `.venv/bin/python -m afe all`.

## Architektur

```
src/afe/
  sqldump.py       Parser für phpMyAdmin-Dumps (kein MySQL-Server nötig)
  load.py          Dump -> data/processed/afe.sqlite (Whitelist von Tabellen und Spalten)
  clean.py         Seitenaufrufe, Ereignisse, Besuche; Variante; Ausschlussregeln
  features.py      Kennzahlen pro Seitenaufruf und Besuch, AOI
  forms.py         WPForms-Einträge parsen, Antworten bewerten, Besuchen zuordnen, Ausschlüsse
  questionnaire.py UEQ-S/Schwierigkeit/Task Success berechnen; manuelle CSV als Fallback
  stats.py         Hypothesentests H1-H5, Variantenvergleich
  plots.py         Grafiken
  dom.py           DOM-Snapshots: CSS-Selektoren auflösen, Bild unter der Maus bestimmen
  pipeline.py      Ablauf build() -> report()
  cli.py           Befehle für afe.bat
config/study.toml  ALLE methodischen Parameter
```

Datenfluss: `data/raw/*.sql` → `afe.sqlite` → `data/processed/{pageviews,visits,events,stichprobe}.csv`
→ `output/{bericht.md,tabellen.xlsx,figures/}`.

## Matomo-Datenmodell (verifiziert am Export vom 27.10.2026)

Tabellen (Präfix `wp_matomo_` wird beim Import entfernt):

| Tabelle | Inhalt |
|---|---|
| `log_hsr` | ein Seitenaufruf mit Aufzeichnung: `idvisit`, `idaction_url`, `device_type`, `server_time` (UTC), `time_on_page` (ms), Viewport, `scroll_y_max_relative` (Promille) |
| `log_hsr_event` | Ereignisse: `time_since_load` (ms), `event_type`, `idselector`, `x`, `y`, `idhsrblob` |
| `log_hsr_blob` | zlib-komprimierte Inhalte (DOM-Snapshot, Mutationen, CSS, Formularwerte); beim Import entpackt in `value_text` |
| `log_action` | URLs (type 1), Seitentitel (type 4), CSS-Selektoren (type 96) |
| `log_visit` | Besuch: Browser, OS, Auflösung (nur unkritische Spalten importiert) |
| `site_hsr`, `log_hsr_site` | Heatmap-/Recording-Konfigurationen und Zuordnung |
| `wpforms_entries` | Formulareinträge: `entry_id`, `form_id`, `date` (UTC), `fields` (JSON; E-Mail-Felder beim Import entfernt) |

WPForms `fields`: Die Feld-IDs haben sich während der Tests geändert. Felder deshalb immer über die
Bezeichnung erkennen (siehe `forms._parse_fields`), nicht über die ID. Nach dem Absenden leert WPForms
das Formular; Matomo zeichnet dabei noch Formularereignisse bis ca. 30 s nach dem Absenden auf.

`event_type`: 1 Bewegung, 2 Klick, 3 Scroll, 4 Resize, 5 initialer DOM, 6 DOM-Mutation,
9 Formular-Text (maskiert als `****`), 10 Formular-Auswahl, 12 Scroll in Element, 13 CSS.

**Koordinaten (wichtig):**
- Bewegung/Klick: `x`, `y` sind **relativ zum Element** `idselector`, skaliert auf ca. 0..2000
  (beobachtet: -250..2100). Keine Bildschirmpixel.
- Bewegungen werden etwa alle 200 ms gespeichert, nur solange sich die Maus bewegt.
- Scroll (3): `y` ist die Scrollposition in Promille der Seite (0..1000), `x` = 0.
- Absolute Pfade in Pixeln brauchen die Elementpositionen. Diese liessen sich rekonstruieren,
  indem der DOM-Snapshot (Typ 5 + CSS Typ 13) mit Playwright in der Viewport-Grösse gerendert
  und die Bounding-Box jedes Selektors gemessen wird. **Noch nicht umgesetzt** (offene Aufgabe).

Bilder: Jeder Selektor wird im DOM-Snapshot der Seite aufgelöst (`dom.DomIndex`); liegt darunter
genau ein IMG, wird es dem Ereignis zugeordnet (Spalte `image`, Dateiname ohne Grösse/Endung).
Beide Varianten zeigen dieselben 8 Inhaltsbilder (`*-Mira-Caduff`), alle mit Link zur Vergrösserung
(Lightbox; Ereignisse mit Selektor `div#lightbox...`). Porträt-AOI = Bild `Portrait-Mira-Caduff`
(Startseite ML und Onepager). Prüfen mit `afe.bat images`.
Besuche mit Selektoren `wp-admin-bar` stammen von eingeloggten Admins und werden ausgeschlossen.

## Regeln

### Datenschutz (öffentliches Repo)
- **Nie** Daten committen: keine `.sql`, `.sqlite`, `.csv` (ausser `config/` und `tests/fixtures/`),
  `.xlsx`, Grafiken mit echten Daten, Notebook-Outputs. `.gitignore` nicht aufweichen.
- Keine Besuchs-IDs, Zeitstempel, Namen, Antworten oder E-Mail-Adressen echter Teilnehmender in Code,
  Kommentare, Commit-Messages, Issues oder Doku schreiben. Ausnahme: `config/exclude_visits.csv`,
  `config/exclude_entries.csv` und `config/match_overrides.csv` enthalten nur IDs mit generischem Grund.
- Freitext-Feedback der Teilnehmenden nie in Bericht oder Repo übernehmen.
- Tests nur mit synthetischen Daten (`tests/fixtures/mini_dump.sql`).
- `load.py` importiert bewusst keine IP, Besucher-ID oder Standortdaten. Diese Whitelist nicht erweitern,
  ohne Rücksprache.

### Methodik
- Methodische Parameter gehören in `config/study.toml`, nicht hartcodiert in den Code.
- Daten nie von Hand in `data/processed/` ändern. Korrekturen über Konfiguration oder Code.
- Ausschlüsse markieren (`included`, `exclusion`), nie stillschweigend löschen.
- Jede neue Kennzahl braucht eine Definition im Docstring, eine Zeile in der Kennzahl-Tabelle im
  README und einen Test.
- Annahmen über das Matomo-Datenformat als solche kennzeichnen und am echten Export prüfen.
- Statistische Tests: zweiseitig, alpha 0.05, nichtparametrisch als Standard (kleine Gruppen);
  Effektstärken immer mit angeben.

### Code
- Python ≥ 3.11 (Ziel 3.12), Abhängigkeiten nur über `requirements.txt` mit fixierten Versionen.
  Neue Pakete nur, wenn nötig, und dann dort eintragen.
- Bezeichner auf Englisch, Kommentare, Docstrings, Ausgaben und Doku auf Deutsch.
- Schweizer Rechtschreibung: kein «ß», immer «ss». Keine Gender-Sonderzeichen (*, :, /).
- Ausgaben in Batch-/PowerShell-Skripten ohne Umlaute (Konsolen-Encoding unter Windows).
- Kleine, nachvollziehbare Commits mit deutscher Commit-Message.

## Offene Punkte

- Einzelne Testbesuche während der Feldphase in `exclude_visits.csv` eintragen (z. B. WordPress-Customizer-Vorschau).
- `require_form = true` (Teamentscheid 27.10.2026): Maus-Kennzahlen nur von Besuchen bis zum Formular.
- Hypothesen in `stats.py` mit der finalen Fassung der Arbeit abgleichen (Stand 21.10.2026:
  H1 auf UEQ-S pragmatische Qualität, H2 mit umgepolter Schwierigkeit).
- Optional: absolute Koordinaten über Playwright-Rendering der DOM-Snapshots (für Movement Path Entropy).
- Bilder: Auswertung umfasst alle 8 Inhaltsbilder, nicht nur das Porträt. Bei Vergleichen nach Geschlecht
  die Verteilung Geschlecht x Variante beachten (Konfundierung, z. B. Klicks nur in der Menüversion).
- Deckeneffekt prüfen: In der Feldphase lösen bisher alle Teilnehmenden alle drei Aufgaben (H3a ohne Streuung).
