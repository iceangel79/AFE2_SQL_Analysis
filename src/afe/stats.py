"""Schritt 4: Statistische Tests.

Hypothesen gemäss Stand vom 21.10.2026 (AFE2-Zwischenstand). Vor der finalen
Auswertung mit dem Team abgleichen und hier anpassen:

- H1: Mehr Richtungswechsel pro Sekunde gehen mit tieferer pragmatischer Qualität (UEQ-S) einher.
      Spearman-Korrelation, erwartet negativ.
- H2: Längere Zeit bis zum Formular geht mit höherem Schwierigkeitswert einher
      (Skala umgepolt: 5 = sehr schwierig). Spearman, erwartet positiv.
- H3a: Task Success (0-3 richtige Antworten) unterscheidet sich zwischen OP und ML. Mann-Whitney-U.
- H3b: UEQ-S-Gesamtwert unterscheidet sich zwischen OP und ML. Mann-Whitney-U (plus Welch-t-Test).
- H4 (explorativ): Verweildauer der Maus auf dem Porträt unterscheidet sich zwischen
      weiblich und männlich ("keine Angabe" ausgeschlossen). Mann-Whitney-U.
- H5: Maus-Kennzahlen allein erklären weniger Varianz im UEQ-S-Gesamtwert als
      Maus-Kennzahlen plus Task Success und Schwierigkeit. Vergleich R² (OLS).

Tests sind zweiseitig, alpha = 0.05. Bei kleinen Gruppen (n < 10) sind die
Ergebnisse nur beschreibend zu interpretieren.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

ALPHA = 0.05


def _row(h, test, n, stat, p, effect=np.nan, note=""):
    return {"hypothese": h, "test": test, "n": n, "statistik": stat, "p": p, "effekt": effect,
            "signifikant": bool(p < ALPHA) if pd.notna(p) else None, "hinweis": note}


def spearman(df: pd.DataFrame, x: str, y: str, h: str, expected: str) -> dict:
    d = df[[x, y]].dropna()
    if len(d) < 3:
        return _row(h, f"Spearman {x} ~ {y}", len(d), np.nan, np.nan, note="zu wenig Daten")
    r, p = stats.spearmanr(d[x], d[y])
    ok = (r < 0) if expected == "negativ" else (r > 0)
    return _row(h, f"Spearman {x} ~ {y}", len(d), r, p, r, f"erwartet {expected}, Richtung {'passt' if ok else 'passt nicht'}")


def group_compare(df: pd.DataFrame, value: str, group: str, h: str, a: str, b: str) -> dict:
    ga = df.loc[df[group] == a, value].dropna()
    gb = df.loc[df[group] == b, value].dropna()
    n = f"{a}={len(ga)}, {b}={len(gb)}"
    if len(ga) < 2 or len(gb) < 2:
        return _row(h, f"Mann-Whitney {value} nach {group}", n, np.nan, np.nan, note="zu wenig Daten")
    u, p = stats.mannwhitneyu(ga, gb, alternative="two-sided")
    # Effektstärke: Rang-biseriale Korrelation (-1..1, positiv = Gruppe a höher)
    rbc = 2 * u / (len(ga) * len(gb)) - 1
    note = f"Median {a}={ga.median():.2f}, {b}={gb.median():.2f}"
    if min(len(ga), len(gb)) < 10:
        note += "; kleine Gruppen, nur beschreibend"
    return _row(h, f"Mann-Whitney {value} nach {group}", n, u, p, rbc, note)


def welch(df: pd.DataFrame, value: str, group: str, h: str, a: str, b: str) -> dict:
    ga = df.loc[df[group] == a, value].dropna()
    gb = df.loc[df[group] == b, value].dropna()
    n = f"{a}={len(ga)}, {b}={len(gb)}"
    if len(ga) < 2 or len(gb) < 2:
        return _row(h, f"Welch-t {value} nach {group}", n, np.nan, np.nan, note="zu wenig Daten")
    t, p = stats.ttest_ind(ga, gb, equal_var=False)
    sd = np.sqrt((ga.var(ddof=1) + gb.var(ddof=1)) / 2)
    d = (ga.mean() - gb.mean()) / sd if sd > 0 else np.nan
    return _row(h, f"Welch-t {value} nach {group}", n, t, p, d, "Effekt = Cohens d")


def r2_compare(df: pd.DataFrame, y: str, base: list[str], extra: list[str], h: str) -> dict:
    import statsmodels.api as sm

    cols = [y] + base + extra
    d = df[cols].dropna()
    if len(d) < len(cols) + 3:
        return _row(h, "OLS R²-Vergleich", len(d), np.nan, np.nan, note="zu wenig Daten")
    m1 = sm.OLS(d[y], sm.add_constant(d[base])).fit()
    m2 = sm.OLS(d[y], sm.add_constant(d[base + extra])).fit()
    f, p, _ = m2.compare_f_test(m1)
    return _row(h, "OLS R²-Vergleich (F-Test verschachtelt)", len(d), f, p, m2.rsquared - m1.rsquared,
                f"R² Maus={m1.rsquared:.3f}, R² Maus+Kontext={m2.rsquared:.3f}")


def run_hypotheses(df: pd.DataFrame) -> pd.DataFrame:
    """df: eingeschlossene Besuche, verknüpft mit Fragebogen."""
    mouse = ["dir_change_rate", "switch_rate", "pause_share"]
    rows = [
        spearman(df, "dir_change_rate", "ueqs_pragmatic", "H1", "negativ"),
        spearman(df, "time_to_form_s", "seq_mean", "H2", "positiv"),
        group_compare(df, "task_success", "variant", "H3a", "OP", "ML"),
        group_compare(df, "ueqs_total", "variant", "H3b", "OP", "ML"),
        welch(df, "ueqs_total", "variant", "H3b", "OP", "ML"),
    ]
    if "geschlecht" in df:
        rows.append(group_compare(df, "aoi_portrait_dwell_ms", "geschlecht", "H4 (explorativ)", "weiblich", "männlich"))
    rows.append(r2_compare(df, "ueqs_total", mouse, ["task_success", "seq_mean"], "H5"))
    return pd.DataFrame(rows)


def compare_variants(visits: pd.DataFrame, metrics: dict[str, str]) -> pd.DataFrame:
    """Beschreibender Variantenvergleich aller Maus-Kennzahlen (explorativ)."""
    rows = []
    for col, label in metrics.items():
        if col not in visits:
            continue
        r = group_compare(visits, col, "variant", label, "OP", "ML")
        for v in ("ML", "OP"):
            s = visits.loc[visits["variant"] == v, col].dropna()
            r[f"{v}_n"] = len(s)
            r[f"{v}_median"] = s.median() if len(s) else np.nan
            r[f"{v}_q1"] = s.quantile(0.25) if len(s) else np.nan
            r[f"{v}_q3"] = s.quantile(0.75) if len(s) else np.nan
        rows.append(r)
    out = pd.DataFrame(rows).rename(columns={"hypothese": "kennzahl"})
    return out
