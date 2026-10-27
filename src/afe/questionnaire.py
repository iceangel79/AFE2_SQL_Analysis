"""Fragebogendaten (manuell erfasst) einlesen und auswerten.

Die Antworten kommen per E-Mail aus WPForms und werden manuell in
data/manual/fragebogen.csv übertragen (Vorlage: config/templates/fragebogen_vorlage.csv).
Die Zuordnung zu einem Besuch (idvisit) erfolgt beim Sichten der Session Recordings.

Skalen:
- UEQ-S: 8 Items, 1..7, negativer Pol links (1), positiver Pol rechts (7).
  Umrechnung auf -3..+3 (Wert - 4). Items 1-4 = pragmatische Qualität,
  Items 5-8 = hedonische Qualität, Gesamtwert = Mittel aller 8 Items.
- Schwierigkeit (SEQ-ähnlich): 1 = sehr einfach, 7 = sehr schwierig (bewusst
  umgepolt gegenüber dem Standard-SEQ). Hohe Werte = schwierig.
- Aufgaben: a1_korrekt..a3_korrekt mit 1 = richtig, 0 = falsch.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import DATA_MANUAL

UEQ_ITEMS = [f"ueq{i}" for i in range(1, 9)]
SEQ_ITEMS = ["seq1", "seq2", "seq3"]
TASK_ITEMS = ["a1_korrekt", "a2_korrekt", "a3_korrekt"]
QUESTIONNAIRE_FILE = DATA_MANUAL / "fragebogen.csv"


def load_questionnaire(path: Path = QUESTIONNAIRE_FILE) -> pd.DataFrame | None:
    if not path.exists():
        return None
    q = pd.read_csv(path, comment="#")
    if q.empty:
        return None
    q["idvisit"] = pd.to_numeric(q["idvisit"], errors="coerce").astype("Int64")
    for c in UEQ_ITEMS + SEQ_ITEMS + TASK_ITEMS:
        if c in q:
            q[c] = pd.to_numeric(q[c], errors="coerce")
    _validate(q)
    return score(q)


def _validate(q: pd.DataFrame) -> None:
    problems = []
    for c in UEQ_ITEMS + SEQ_ITEMS:
        if c in q and ((q[c] < 1) | (q[c] > 7)).any():
            problems.append(f"{c}: Werte ausserhalb 1..7")
    for c in TASK_ITEMS:
        if c in q and ~q[c].dropna().isin([0, 1]).all():
            problems.append(f"{c}: nur 0 oder 1 erlaubt")
    dup = q["idvisit"].dropna().duplicated()
    if dup.any():
        problems.append(f"idvisit doppelt: {sorted(q.loc[dup[dup].index, 'idvisit'].tolist())}")
    if problems:
        raise ValueError("Fehler in fragebogen.csv:\n  " + "\n  ".join(problems))


def score(q: pd.DataFrame) -> pd.DataFrame:
    q = q.copy()
    ueq = q[UEQ_ITEMS] - 4
    q["ueqs_pragmatic"] = ueq[UEQ_ITEMS[:4]].mean(axis=1)
    q["ueqs_hedonic"] = ueq[UEQ_ITEMS[4:]].mean(axis=1)
    q["ueqs_total"] = ueq.mean(axis=1)
    q["seq_mean"] = q[SEQ_ITEMS].mean(axis=1)
    q["task_success"] = q[TASK_ITEMS].sum(axis=1, min_count=1)
    q["task_success_all"] = q["task_success"].eq(3)
    return q
