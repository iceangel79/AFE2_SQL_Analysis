"""Verlosung (3x CHF 50) unter allen Teilnehmenden, die eine E-Mail-Adresse angegeben haben.

Mit der Eingabe der E-Mail-Adresse im Fragebogen haben die Teilnehmenden der Teilnahme
an der Verlosung zugestimmt. Die Adressen werden NUR für die Verlosung verwendet:
- Sie werden direkt aus dem SQL-Dump (data/raw) gelesen und nie in die Analyse-Datenbank,
  den Bericht oder das Repo übernommen.
- Das Ergebnis liegt in output/verlosung.xlsx (nicht im Repo, siehe .gitignore).
  Nach der Verlosung die Datei löschen (Zusage in der Einladung).

Regeln der Ziehung:
- Teilnahmeberechtigt: Einträge ab Feldstart (und bis Feldende, falls gesetzt), nicht in
  config/exclude_entries.csv, mit gültiger E-Mail-Adresse. Testeinträge vor dem Feldstart zählen nicht.
- Pro E-Mail-Adresse eine Gewinnchance (Duplikate werden zusammengefasst, Gross-/Kleinschreibung egal).
- Ziehung ohne Zurücklegen mit Pythons Zufallsgenerator und einem zufällig erzeugten Seed.
  Der Seed steht im Protokoll; mit demselben Seed und derselben Liste ergibt sich dieselbe Ziehung.
- Eine bestehende Ziehung wird nicht überschrieben (ausser mit --neu).
"""

from __future__ import annotations

import datetime as dt
import json
import random
import re
import secrets
from pathlib import Path

import pandas as pd

from . import sqldump
from .config import OUTPUT, StudyConfig, ensure_dirs

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RESULT_FILE = OUTPUT / "verlosung.xlsx"


def read_emails(dump: Path, cfg: StudyConfig) -> pd.DataFrame:
    """Alle Formulareinträge mit E-Mail-Adresse aus dem Rohdump (nur im Speicher)."""
    text = sqldump.read_text(dump)
    rows = []
    for table, cols, data in sqldump.iter_inserts(text):
        if not table.endswith("wpforms_entries"):
            continue
        i = {c: k for k, c in enumerate(cols)}
        for r in data:
            fields = json.loads(r[i["fields"]])
            mails = [f.get("value", "").strip() for f in fields.values()
                     if isinstance(f, dict) and f.get("type") == "email" and f.get("value", "").strip()]
            for m in mails:
                rows.append({"entry_id": r[i["entry_id"]], "form_id": r[i["form_id"]],
                             "submitted_utc": r[i["date"]], "email": m})
    df = pd.DataFrame(rows, columns=["entry_id", "form_id", "submitted_utc", "email"])
    if df.empty:
        return df
    df["submitted_utc"] = pd.to_datetime(df["submitted_utc"])
    df["eingereicht"] = (df["submitted_utc"].dt.tz_localize("UTC").dt.tz_convert(cfg.timezone)
                         .dt.tz_localize(None))
    df["variante"] = df["form_id"].map(cfg.form_ids).fillna("unbekannt")
    return df


def eligible(df: pd.DataFrame, cfg: StudyConfig) -> pd.DataFrame:
    """Teilnahmeberechtigte Adressen, eine Zeile pro Person (E-Mail)."""
    d = df.copy()
    if cfg.field_start:
        d = d[d["eingereicht"] >= pd.Timestamp(cfg.field_start)]
    if cfg.field_end:
        d = d[d["eingereicht"] < pd.Timestamp(cfg.field_end) + pd.Timedelta(days=1)]
    if cfg.exclude_entries_path.exists():
        ex = pd.read_csv(cfg.exclude_entries_path, comment="#")
        if not ex.empty:
            d = d[~d["entry_id"].isin(pd.to_numeric(ex["entry_id"], errors="coerce"))]
    d["email_norm"] = d["email"].str.strip().str.lower()
    d = d[d["email_norm"].str.match(EMAIL_RE)]
    d = d.sort_values("eingereicht")
    out = d.groupby("email_norm").agg(
        email=("email", "first"),
        erster_eintrag=("eingereicht", "min"),
        variante=("variante", "first"),
        anzahl_eintraege=("entry_id", "size"),
    ).reset_index(drop=True)
    return out.sort_values("erster_eintrag").reset_index(drop=True)


def draw(people: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """Zieht n Adressen ohne Zurücklegen. Reihenfolge der Liste: nach erstem Eintrag (stabil)."""
    if len(people) < n:
        raise ValueError(f"Nur {len(people)} teilnahmeberechtigte Adressen für {n} Preise.")
    rng = random.Random(seed)
    idx = rng.sample(range(len(people)), n)
    winners = people.iloc[idx][["email", "erster_eintrag", "variante"]].reset_index(drop=True)
    winners.insert(0, "rang", range(1, n + 1))
    return winners


def run(dump: Path, cfg: StudyConfig, n: int = 3, prize: str = "CHF 50", seed: int | None = None,
        new: bool = False, out: Path = RESULT_FILE) -> pd.DataFrame:
    ensure_dirs()
    if out.exists() and not new:
        raise FileExistsError(
            f"{out.name} existiert bereits (Ziehung schon erfolgt). Für eine neue Ziehung --neu angeben."
        )
    people = eligible(read_emails(dump, cfg), cfg)
    seed = seed if seed is not None else secrets.randbelow(10**9)
    winners = draw(people, n, seed)
    winners["preis"] = prize
    protocol = pd.DataFrame([
        ("Zeitpunkt der Ziehung", dt.datetime.now().strftime("%d.%m.%Y %H:%M:%S")),
        ("Quelldatei", dump.name),
        ("Feldphase", f"{cfg.field_start or 'offen'} bis {cfg.field_end or 'offen'}"),
        ("Teilnahmeberechtigte Adressen", len(people)),
        ("Anzahl Preise", f"{n} x {prize}"),
        ("Seed", seed),
        ("Verfahren", "random.Random(seed).sample über die Liste 'Teilnehmende' (sortiert nach erstem Eintrag)"),
        ("Hinweis", "Datei nach Abschluss der Verlosung löschen; Adressen nur für die Verlosung verwenden."),
    ], columns=["feld", "wert"])
    with pd.ExcelWriter(out) as xw:
        winners.to_excel(xw, sheet_name="Gewinner", index=False)
        people.to_excel(xw, sheet_name="Teilnehmende", index=False)
        protocol.to_excel(xw, sheet_name="Protokoll", index=False)
    return winners
