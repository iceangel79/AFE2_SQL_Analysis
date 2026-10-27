"""Fragebogen aus WPForms (Tabelle wp_wpforms_entries) einlesen und den Besuchen zuordnen.

Ablauf:
1. parse_entries():  JSON der Formularfelder -> eine Zeile pro Eintrag mit den Spalten der
   Fragebogenvorlage (geschlecht, a1_antwort, seq1, ueq1 ...). Die Felder werden über ihre
   Bezeichnung erkannt, nicht über die Feld-ID (die IDs haben sich während der Tests geändert).
2. code_answers():   Freitextantworten automatisch als richtig/falsch bewerten
   (Suchbegriffe in config/study.toml, [questionnaire.answers]).
3. match_entries():  Eintrag -> Matomo-Besuch. Kandidaten sind Besuche derselben Variante mit
   Formulareingaben. Gewählt wird der Besuch, dessen letzte Formulareingabe am nächsten vor
   dem Absendezeitpunkt liegt (höchstens match_tolerance_s). Jeder Besuch wird höchstens
   einem Eintrag zugeordnet. Manuelle Korrekturen: config/match_overrides.csv.

Die Zeitstempel beider Systeme sind UTC (geprüft am Export vom 27.10.2026).
E-Mail-Adressen werden bereits beim Import entfernt (load.py).
"""

from __future__ import annotations

import html
import json
import sqlite3

import pandas as pd

from .config import StudyConfig

# Erster Pol der UEQ-S-Items in der Reihenfolge ueq1..ueq8 (Erkennung über die Feldbezeichnung)
UEQ_POLES = ["behindernd", "kompliziert", "ineffizient", "verwirrend",
             "langweilig", "uninteressant", "konventionell", "herkömmlich"]
# Suchaufgaben (Erkennung über die Feldbezeichnung)
TASK_LABELS = {"a1": "aufgewachsen", "a2": "trainer", "a3": "sporternährung"}


def has_entries(con: sqlite3.Connection) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE name='wpforms_entries'").fetchone() is not None


def parse_entries(con: sqlite3.Connection, cfg: StudyConfig) -> pd.DataFrame:
    raw = pd.read_sql("SELECT entry_id, form_id, date, fields FROM wpforms_entries", con)
    rows = [_parse_fields(json.loads(f)) for f in raw["fields"]]
    df = pd.concat([raw.drop(columns="fields"), pd.DataFrame(rows)], axis=1)
    df["submitted_utc"] = pd.to_datetime(df.pop("date"))
    df["submitted_local"] = (
        df["submitted_utc"].dt.tz_localize("UTC").dt.tz_convert(cfg.timezone).dt.tz_localize(None)
    )
    df["variante"] = df["form_id"].map(cfg.form_ids).fillna("unbekannt")
    return df.sort_values("entry_id").reset_index(drop=True)


def _parse_fields(fields: dict) -> dict:
    out: dict = {}
    last_task = None
    for f in fields.values():  # Reihenfolge im JSON = Reihenfolge im Formular
        label = html.unescape(f.get("name", "")).lower()
        value = (f.get("value") or "").strip()
        if label.startswith("geschlecht"):
            out["geschlecht"] = value
        elif label.startswith("alter"):
            out["altersgruppe"] = value
        elif label.startswith("feedback"):
            out["feedback"] = value
        elif "schwierig" in label and last_task:
            out[f"seq{last_task[1]}"] = _num(value)
        elif any(p in label for p in UEQ_POLES):
            for i, pole in enumerate(UEQ_POLES, 1):
                if f"1={pole}" in label.replace(" ", ""):
                    out[f"ueq{i}"] = _num(value)
        else:
            for key, word in TASK_LABELS.items():
                if word in label:
                    out[f"{key}_antwort"] = value
                    last_task = key
    return out


def _num(v: str) -> float | None:
    try:
        return float(v)
    except ValueError:
        return None


def code_answers(df: pd.DataFrame, cfg: StudyConfig) -> pd.DataFrame:
    df = df.copy()
    for key, words in cfg.answers.items():
        ans = df.get(f"{key}_antwort", pd.Series("", index=df.index)).fillna("").str.lower()
        df[f"{key}_korrekt"] = ans.map(lambda a: int(any(w in a for w in words)))
    return df


def visit_form_times(pvf: pd.DataFrame) -> pd.DataFrame:
    """Pro Besuch: Zeitpunkt (UTC) der ersten und letzten Formulareingabe."""
    p = pvf.dropna(subset=["first_form_ms"])
    first = p["server_time"] + pd.to_timedelta(p["first_form_ms"], unit="ms")
    last = p["server_time"] + pd.to_timedelta(p["last_form_ms"], unit="ms")
    return pd.DataFrame({"form_first_utc": first.groupby(p["idvisit"]).min(),
                         "form_last_utc": last.groupby(p["idvisit"]).max()}).reset_index()


def match_entries(entries: pd.DataFrame, visits: pd.DataFrame, pvf: pd.DataFrame, cfg: StudyConfig) -> pd.DataFrame:
    """Ergänzt idvisit, match_diff_s und match_status pro Eintrag."""
    ft = visit_form_times(pvf).merge(visits[["idvisit", "variant"]], on="idvisit")
    cands = entries[["entry_id", "variante", "submitted_utc"]].merge(ft, how="cross")
    # Gleiche Variante; Besuche mit beiden Varianten bleiben Kandidaten (werden später ausgeschlossen)
    cands = cands[(cands["variant"] == cands["variante"]) | (cands["variant"] == "gemischt")]
    cands["diff_s"] = (cands["submitted_utc"] - cands["form_last_utc"]).dt.total_seconds()
    # Absenden liegt zwischen erster Eingabe und letzter Eingabe + Toleranz. Nach dem Absenden
    # leert WPForms das Formular; das erzeugt noch Ereignisse, daher kann diff_s negativ sein.
    after_first = (cands["submitted_utc"] - cands["form_first_utc"]).dt.total_seconds() >= -30
    cands = cands[after_first & (cands["diff_s"] <= cfg.match_tolerance_s) & (cands["diff_s"] >= -120)]
    cands = cands.assign(abs_diff=cands["diff_s"].abs()).sort_values("abs_diff")

    overrides = _read_overrides(cfg)
    used_entries, used_visits, result = set(), set(), {}
    for e, v in overrides.items():
        result[e] = (v, None, "manuell" if v is not None else "manuell: kein Besuch")
        used_entries.add(e)
        if v is not None:
            used_visits.add(v)
    # Greedy nach kleinstem Zeitabstand, jeder Besuch höchstens einmal
    for r in cands.itertuples(index=False):
        # Besuche mit beiden Varianten dürfen mehrere Einträge haben (z. B. beide Formulare)
        if r.entry_id in used_entries or (r.idvisit in used_visits and r.variant != "gemischt"):
            continue
        result[r.entry_id] = (int(r.idvisit), r.diff_s, "automatisch")
        used_entries.add(r.entry_id)
        used_visits.add(r.idvisit)

    out = entries.copy()
    out["idvisit"] = out["entry_id"].map(lambda e: result.get(e, (None,))[0]).astype("Int64")
    out["match_diff_s"] = out["entry_id"].map(lambda e: result.get(e, (None, None))[1])
    out["match_status"] = out["entry_id"].map(lambda e: result.get(e, (None, None, "kein Besuch gefunden"))[2])
    n_cands = cands.groupby("entry_id").size()
    out["match_candidates"] = out["entry_id"].map(n_cands).fillna(0).astype(int)
    return out


def _read_overrides(cfg: StudyConfig) -> dict[int, int | None]:
    path = cfg.match_overrides_path
    if not path.exists():
        return {}
    df = pd.read_csv(path, comment="#")
    if df.empty:
        return {}
    out = {}
    for r in df.itertuples(index=False):
        v = pd.to_numeric(r.idvisit, errors="coerce")
        out[int(r.entry_id)] = None if pd.isna(v) else int(v)
    return out


def entry_exclusions(entries: pd.DataFrame, visits: pd.DataFrame, cfg: StudyConfig) -> pd.DataFrame:
    """Ein-/Ausschluss der Fragebogen (unabhängig davon, ob eine Maus-Aufzeichnung existiert).

    - entry_included: Fragebogen zählt für fragebogenbasierte Auswertungen (H3a, H3b)
    - mouse_included: zusätzlich ein eingeschlossener Besuch zugeordnet (H1, H2, H4, H5)
    variant_start gilt nur für die Aufzeichnung, nicht für den Fragebogen: Das Formular
    funktionierte auch am Tag mit dem Tracking-Problem.
    """
    from .questionnaire import SEQ_ITEMS, UEQ_ITEMS

    e = entries.merge(visits[["idvisit", "variant", "included", "exclusion"]].rename(
        columns={"variant": "visit_variant", "included": "visit_included", "exclusion": "visit_exclusion"}),
        on="idvisit", how="left")
    reasons = pd.Series("", index=e.index, dtype="object")

    def mark(mask, text):
        reasons.loc[mask & reasons.eq("")] = text

    manual = _read_entry_exclusions(cfg)
    mark(e["entry_id"].isin(manual), "manuell ausgeschlossen (exclude_entries.csv)")
    if cfg.field_start:
        mark(e["submitted_local"] < pd.Timestamp(cfg.field_start), "vor Feldstart")
    if cfg.field_end:
        mark(e["submitted_local"] >= pd.Timestamp(cfg.field_end) + pd.Timedelta(days=1), "nach Feldende")
    mark(e["variante"].eq("unbekannt"), "Formular unbekannt")
    mark(e["visit_variant"].eq("gemischt"), "Besuch mit beiden Varianten")
    items = [c for c in UEQ_ITEMS + SEQ_ITEMS if c in e]
    bad = ((e[items] < cfg.scale_min) | (e[items] > cfg.scale_max)).any(axis=1)
    mark(bad, "Skalenwerte ausserhalb Bereich")
    e["entry_exclusion"] = reasons
    e["entry_included"] = reasons.eq("")
    e["mouse_included"] = e["entry_included"] & e["visit_included"].fillna(False).astype(bool)
    return e


def _read_entry_exclusions(cfg: StudyConfig) -> set[int]:
    path = cfg.exclude_entries_path
    if not path.exists():
        return set()
    df = pd.read_csv(path, comment="#")
    return set(pd.to_numeric(df.get("entry_id", pd.Series(dtype=float)), errors="coerce").dropna().astype(int))


def entry_flow(e: pd.DataFrame) -> pd.DataFrame:
    rows = [("Alle Formulareinträge", len(e))]
    for reason, n in e.loc[~e["entry_included"], "entry_exclusion"].value_counts().items():
        rows.append((f"- {reason}", -int(n)))
    inc = e[e["entry_included"]]
    rows.append(("Fragebogen-Stichprobe (H3a, H3b)", len(inc)))
    for var, n in inc["variante"].value_counts().sort_index().items():
        rows.append((f"  davon {var}", int(n)))
    rows.append(("  ohne passende Aufzeichnung", int((inc["idvisit"].isna()).sum())))
    rows.append(("  Aufzeichnung ausgeschlossen", int((inc["idvisit"].notna() & ~inc["mouse_included"]).sum())))
    rows.append(("Maus+Fragebogen-Stichprobe (H1, H2, H4, H5)", int(e["mouse_included"].sum())))
    for var, n in e.loc[e["mouse_included"], "variante"].value_counts().sort_index().items():
        rows.append((f"  davon {var}", int(n)))
    return pd.DataFrame(rows, columns=["schritt", "anzahl"])
