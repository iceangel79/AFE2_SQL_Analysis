# AFE2 – Auswertung Maus-Tracking

Reproduzierbare Auswertung der Matomo-Daten (Heatmap & Session Recording) für die
Semesterarbeit «Optimierung der User Experience» von Adrian Wegmann und Adrian Martic
(MSc Wirtschaftsinformatik, FFHS).

Der Code liest den SQL-Export der WordPress-Datenbank lokal ein, bereinigt die
Stichprobe nach dokumentierten Regeln, berechnet Kennzahlen pro Besuch und testet
die Hypothesen. Jeder Schritt ist im Code nachvollziehbar, die Auswertung ist also
keine Blackbox.

> **Datenschutz:** Das Repo ist öffentlich. Rohdaten, Datenbank, CSV-Dateien und
> Ergebnisse werden nie committet (siehe `.gitignore`). Im Repo liegen nur Code,
> Konfiguration und Dokumentation.

## Einrichtung (Windows, einmal pro Rechner)

1. **Python 3.12** installieren: <https://www.python.org/downloads/>
   (bei der Installation «Add python.exe to PATH» anhaken).
2. Repo klonen:
   ```
   git clone https://github.com/iceangel79/AFE2_SQL_Analysis.git
   cd AFE2_SQL_Analysis
   ```
3. `setup.bat` doppelklicken. Das Skript
   - erstellt die virtuelle Umgebung `.venv`,
   - installiert alle Pakete in den fixierten Versionen aus `requirements.txt`,
   - registriert den Jupyter-Kernel «Python (AFE)»,
   - legt die lokalen Datenordner an.

Bei Problemen die Umgebung neu aufbauen: `powershell -ExecutionPolicy Bypass -File setup.ps1 -Recreate`

## Ablauf

1. **Export aus phpMyAdmin** (Hoststar): Datenbank wählen → *Exportieren* → *Angepasst* →
   nur diese Tabellen auswählen, Format SQL:
   `wp_matomo_log_action`, `wp_matomo_log_hsr`, `wp_matomo_log_hsr_blob`,
   `wp_matomo_log_hsr_event`, `wp_matomo_log_hsr_site`, `wp_matomo_log_visit`,
   `wp_matomo_site_hsr`
2. Die `.sql`-Datei nach `data\raw\` kopieren.
3. Auswertung starten:
   ```
   afe.bat all
   ```
   Ergebnis in `output\`: `bericht.md`, `tabellen.xlsx` und Grafiken in `output\figures\`.

### Befehle

| Befehl | Zweck |
|---|---|
| `afe.bat import [datei.sql]` | Dump in die lokale Datenbank `data\processed\afe.sqlite` laden (ohne Angabe: neuster Dump in `data\raw`) |
| `afe.bat build` | Bereinigen und Kennzahlen berechnen, CSV in `data\processed\` |
| `afe.bat report` | Bericht, Excel-Tabellen und Grafiken in `output\` |
| `afe.bat all` | alles zusammen |
| `afe.bat info` | alle Besuche mit Variante und Ausschlussgrund |
| `afe.bat images` | Bilder je Seite mit DOM-Position (AOI prüfen) |
| `afe.bat selectors --page startseite` | meistbenutzte Elemente einer Seite |
| `afe.bat notebook` | Jupyter Lab für explorative Analysen |
| `afe.bat strip` | Notebook-Outputs löschen (vor jedem Commit) |
| `.venv\Scripts\python -m pytest` | Tests |

## Methodische Einstellungen

Alle Entscheidungen der Auswertung stehen in **`config/study.toml`**, nicht im Code:

- Feldphase (`field_start`, `field_end`): alles davor gilt als Testdaten
- `config/exclude_visits.csv`: einzelne Besuche mit Begründung ausschliessen
- Gerätetypen (Standard: nur Desktop, da Maus-Tracking)
- Optional: nur Besuche mit Formular, Mindestdauer
- Schwellenwerte der Kennzahlen (Richtungswechsel, Pausen, AOI-Verweildauer)
- AOI-Definitionen (Porträt) als URL- und CSS-Selektor-Regeln

Ausgeschlossene Besuche werden nicht gelöscht, sondern mit Grund markiert.
`bericht.md` enthält den Stichprobenfluss für den Methodenteil.

## Fragebogendaten

Die Antworten aus WPForms (E-Mail) werden manuell erfasst:

1. `config\templates\fragebogen_vorlage.csv` nach `data\manual\fragebogen.csv` kopieren.
2. Pro Teilnehmenden eine Zeile; die `idvisit` beim Sichten der Session Recording in
   Matomo ablesen (`afe.bat info` hilft beim Zuordnen über Zeitpunkt und Variante).
3. Skalen: `ueq1`–`ueq8` und `seq1`–`seq3` als Rohwerte 1–7, `a1_korrekt`–`a3_korrekt` als 0/1.

Sobald die Datei existiert, rechnet `afe.bat report` die Hypothesentests mit.

## Kennzahlen

| Kennzahl | Definition |
|---|---|
| `time_total_s` | Summe der Verweildauer aller Seiten des Besuchs |
| `time_to_form_s` | aktive Zeit bis zur ersten Eingabe im Fragebogen |
| `dir_change_rate` | Richtungswechsel der Maus pro Sekunde (innerhalb desselben Elements, ab Mindestbewegung) |
| `switch_rate` | Wechsel des Elements unter der Maus pro Sekunde |
| `pause_share` | Anteil der Zeit mit ruhender Maus (Lücken ≥ `pause_ms`) |
| `scroll_reversals` | Wechsel der Scrollrichtung |
| `aoi_portrait_dwell_ms` | Verweildauer der Maus auf dem Porträt |

**Einschränkung:** Matomo speichert Mauspositionen relativ zum Element unter der Maus
(skaliert auf 0–2000), nicht in Bildschirmpixeln. Absolute Pfadlängen oder eine
klassische Movement Path Entropy sind deshalb ohne Rekonstruktion des Layouts nicht
möglich. Details in `AGENTS.md`.

## Struktur

```
config/          Studienkonfiguration, Ausschlussliste, Vorlagen
src/afe/         Python-Paket (sqldump → load → clean → features → stats/plots → pipeline)
notebooks/       explorative Analysen (ohne Outputs committen)
tests/           Tests mit synthetischem Mini-Dump
data/            lokal: raw (Dumps), processed (DB, CSV), manual (Fragebogen) – nicht im Repo
output/          lokal: Bericht, Tabellen, Grafiken – nicht im Repo
```
