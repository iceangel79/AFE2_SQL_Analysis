"""Schritt 4: Statistische Tests.

Hypothesen gemäss Stand vom 21.10.2026 (AFE2-Zwischenstand). Vor der finalen
Auswertung mit dem Team abgleichen und hier anpassen:

- H1: Mehr Richtungswechsel pro Sekunde gehen mit tieferer pragmatischer Qualität (UEQ-S) einher.
      Spearman-Korrelation, erwartet negativ. Sensitivität mit anderen Schwellen: sensitivity_h1().
- H2: Längere Zeit bis zum Formular geht mit höherem Schwierigkeitswert einher
      (Skala umgepolt: 5 = sehr schwierig). Spearman, erwartet positiv.
- H3a: Task Success (0-3 richtige Antworten) unterscheidet sich zwischen OP und ML. Mann-Whitney-U.
- H3b: UEQ-S-Gesamtwert unterscheidet sich zwischen OP und ML. Mann-Whitney-U (plus Welch-t-Test).
- H4 (explorativ, zweistufig) zum Porträt nach Geschlecht ("keine Angabe" ausgeschlossen):
      H4  Verweildauer aller Besuche (Mann-Whitney; viele Nullen)
      H4b Stufe 1: Porträt überhaupt berührt ja/nein (Fisher)
      H4c Stufe 2: Verweildauer nur bei Besuchen, die das Porträt berührt haben (Mann-Whitney)
      Wegen Vermischung von Geschlecht und Variante zusätzlich nur innerhalb ML und als
      logistische Regression mit Variante als Kovariate.
- H5: Maus-Kennzahlen allein erklären weniger Varianz im UEQ-S-Gesamtwert als
      Maus-Kennzahlen plus Task Success und Schwierigkeit. Vergleich R² (OLS), mit
      adjustiertem R² und Verhältnis n/k (Beobachtungen pro Prädiktor).

Konventionen:
- Tests zweiseitig, alpha = 0.05. Bei kleinen Gruppen (n < 10) nur beschreibend interpretieren.
- Gruppenvergleiche immer "a vs. b" (z. B. OP vs. ML). Die Spalte "hoeher_in" nennt die Gruppe
  mit den höheren Werten. Rang-biseriale Korrelation: positiv = a höher, negativ = b höher.
- Fisher-Tests: Effekt = Risikodifferenz (Anteil a minus Anteil b) mit 95 %-KI (Newcombe/Wilson);
  zusätzlich Odds Ratio roh und mit Haldane-Korrektur (+0.5 je Zelle, endlich auch bei Nullzellen).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

ALPHA = 0.05
Z95 = 1.959963984540054


def _row(h, test, n, stat, p, effect=np.nan, note="", hoeher_in="", **extra):
    r = {"hypothese": h, "test": test, "n": n, "statistik": stat, "p": p, "effekt": effect,
         "hoeher_in": hoeher_in, "signifikant": bool(p < ALPHA) if pd.notna(p) else None, "hinweis": note}
    r.update(extra)
    return r


def _higher(effect: float, a: str, b: str) -> str:
    if pd.isna(effect) or effect == 0:
        return "gleich" if effect == 0 else ""
    return a if effect > 0 else b


def spearman(df: pd.DataFrame, x: str, y: str, h: str, expected: str) -> dict:
    d = df[[x, y]].dropna()
    if len(d) < 3:
        return _row(h, f"Spearman {x} ~ {y}", len(d), np.nan, np.nan, note="zu wenig Daten")
    r, p = stats.spearmanr(d[x], d[y])
    ok = (r < 0) if expected == "negativ" else (r > 0)
    direction = "positiv" if r > 0 else "negativ" if r < 0 else "keine"
    return _row(h, f"Spearman {x} ~ {y}", len(d), r, p, r,
                f"Zusammenhang {direction}; erwartet {expected}, Richtung {'passt' if ok else 'passt nicht'}")


def group_compare(df: pd.DataFrame, value: str, group: str, h: str, a: str, b: str) -> dict:
    ga = df.loc[df[group] == a, value].dropna()
    gb = df.loc[df[group] == b, value].dropna()
    n = f"{a}={len(ga)}, {b}={len(gb)}"
    test = f"Mann-Whitney {value}: {a} vs. {b}"
    if len(ga) < 2 or len(gb) < 2:
        return _row(h, test, n, np.nan, np.nan, note="zu wenig Daten")
    if ga.nunique() == 1 and gb.nunique() == 1 and ga.iloc[0] == gb.iloc[0]:
        return _row(h, test, n, np.nan, np.nan, 0.0,
                    f"keine Streuung: alle Werte = {ga.iloc[0]:g} (Decken-/Bodeneffekt)", "gleich")
    u, p = stats.mannwhitneyu(ga, gb, alternative="two-sided")
    rbc = 2 * u / (len(ga) * len(gb)) - 1  # Rang-biseriale Korrelation, positiv = a höher
    note = f"Median {a}={ga.median():.2f}, {b}={gb.median():.2f}"
    if min(len(ga), len(gb)) < 10:
        note += "; kleine Gruppen, nur beschreibend"
    return _row(h, test, n, u, p, rbc, note, _higher(rbc, a, b))


def welch(df: pd.DataFrame, value: str, group: str, h: str, a: str, b: str) -> dict:
    ga = df.loc[df[group] == a, value].dropna()
    gb = df.loc[df[group] == b, value].dropna()
    n = f"{a}={len(ga)}, {b}={len(gb)}"
    test = f"Welch-t {value}: {a} vs. {b}"
    if len(ga) < 2 or len(gb) < 2:
        return _row(h, test, n, np.nan, np.nan, note="zu wenig Daten")
    t, p = stats.ttest_ind(ga, gb, equal_var=False)
    sd = np.sqrt((ga.var(ddof=1) + gb.var(ddof=1)) / 2)
    d = (ga.mean() - gb.mean()) / sd if sd > 0 else np.nan
    return _row(h, test, n, t, p, d, f"Effekt = Cohens d; Mittel {a}={ga.mean():.2f}, {b}={gb.mean():.2f}",
                _higher(d, a, b))


def wilson(x: int, n: int) -> tuple[float, float]:
    """95 %-Konfidenzintervall eines Anteils nach Wilson."""
    if n == 0:
        return np.nan, np.nan
    p = x / n
    den = 1 + Z95**2 / n
    center = (p + Z95**2 / (2 * n)) / den
    half = Z95 * np.sqrt(p * (1 - p) / n + Z95**2 / (4 * n**2)) / den
    return center - half, center + half


def risk_difference(xa: int, na: int, xb: int, nb: int) -> tuple[float, float, float]:
    """Risikodifferenz pa - pb mit 95 %-KI nach Newcombe (Hybrid-Score, Methode 10)."""
    pa, pb = xa / na, xb / nb
    la, ua = wilson(xa, na)
    lb, ub = wilson(xb, nb)
    d = pa - pb
    lo = d - np.sqrt((pa - la) ** 2 + (ub - pb) ** 2)
    hi = d + np.sqrt((ua - pa) ** 2 + (pb - lb) ** 2)
    return d, lo, hi


def fisher(df: pd.DataFrame, flag: str, group: str, h: str, a: str, b: str) -> dict:
    d = df[df[group].isin([a, b])].dropna(subset=[flag])
    test = f"Fisher {flag}: {a} vs. {b}"
    na_, nb_ = int((d[group] == a).sum()), int((d[group] == b).sum())
    n = f"{a}={na_}, {b}={nb_}"
    if na_ == 0 or nb_ == 0:
        return _row(h, test, len(d), np.nan, np.nan, note="zu wenig Daten")
    xa = int(d.loc[d[group] == a, flag].astype(bool).sum())
    xb = int(d.loc[d[group] == b, flag].astype(bool).sum())
    rd, lo, hi = risk_difference(xa, na_, xb, nb_)
    or_h = ((xa + 0.5) * (nb_ - xb + 0.5)) / ((na_ - xa + 0.5) * (xb + 0.5))
    extra = {"risikodifferenz": rd, "rd_ki_unten": lo, "rd_ki_oben": hi, "odds_ratio_haldane": or_h}
    share = f"Anteil ja: {a}={xa / na_:.0%} ({xa}/{na_}), {b}={xb / nb_:.0%} ({xb}/{nb_})"
    if d[flag].nunique() < 2:
        return _row(h, test, n, np.nan, np.nan, 0.0, f"keine Streuung ({share})", "gleich",
                    odds_ratio=np.nan, **extra)
    odds, p = stats.fisher_exact([[xa, na_ - xa], [xb, nb_ - xb]])
    note = f"{share}; RD = {rd:+.0%} [95 %-KI {lo:+.0%}; {hi:+.0%}]"
    if xa == 0 or xb == 0 or xa == na_ or xb == nb_:
        note += f"; Nullzelle: OR roh {odds:g}, Haldane {or_h:.2f}"
    return _row(h, test, n, odds, p, rd, note, _higher(rd, a, b), odds_ratio=odds, **extra)


def logistic_with_covariate(df: pd.DataFrame, flag: str, factor: str, level: str,
                            covariate: str, cov_level: str, h: str) -> dict:
    """Logistische Regression flag ~ factor(level) + covariate(cov_level). Effekt = OR des Faktors."""
    import statsmodels.api as sm

    d = df[[flag, factor, covariate]].dropna()
    d = d[d[factor].isin(df[factor].dropna().unique())]
    test = f"Logit {flag} ~ {factor}={level} + {covariate}={cov_level}"
    if len(d) < 10 or d[flag].astype(bool).nunique() < 2:
        return _row(h, test, len(d), np.nan, np.nan, note="zu wenig Daten oder keine Streuung")
    y = d[flag].astype(bool).astype(int)
    X = sm.add_constant(pd.DataFrame({
        f"{factor}_{level}": (d[factor] == level).astype(int),
        f"{covariate}_{cov_level}": (d[covariate] == cov_level).astype(int),
    }))
    # Perfekte Trennung (z. B. niemand klickt in einer Variante) macht das Modell unschätzbar
    for col in X.columns[1:]:
        if pd.crosstab(X[col], y).eq(0).any().any():
            return _row(h, test, len(d), np.nan, np.nan,
                        note=f"nicht schätzbar: perfekte Trennung bei {col} (Nullzelle); siehe Test nur innerhalb ML")
    try:
        m = sm.Logit(y, X).fit(disp=False)
    except Exception as e:  # noqa: BLE001
        return _row(h, test, len(d), np.nan, np.nan, note=f"nicht schätzbar: {type(e).__name__}")
    name = f"{factor}_{level}"
    or_, lo, hi = np.exp(m.params[name]), *np.exp(m.conf_int().loc[name])
    return _row(h, test, len(d), m.params[name], m.pvalues[name], or_,
                f"OR {level} = {or_:.2f} [95 %-KI {lo:.2f}; {hi:.2f}], adjustiert für {covariate}",
                level if or_ > 1 else "andere" if or_ < 1 else "gleich")


def r2_compare(df: pd.DataFrame, y: str, base: list[str], extra: list[str], h: str) -> dict:
    import statsmodels.api as sm

    cols = [y] + base + extra
    d = df[cols].dropna()
    k = len(base + extra)
    info = {"praediktoren_maus": ", ".join(base), "praediktoren_kontext": ", ".join(extra),
            "k_praediktoren": k, "n_pro_praediktor": round(len(d) / k, 1) if k else np.nan}
    if len(d) < len(cols) + 3:
        return _row(h, "OLS R²-Vergleich", len(d), np.nan, np.nan, note="zu wenig Daten", **info)
    m1 = sm.OLS(d[y], sm.add_constant(d[base])).fit()
    m2 = sm.OLS(d[y], sm.add_constant(d[base + extra])).fit()
    f, p, _ = m2.compare_f_test(m1)
    info.update({"r2_maus": m1.rsquared, "r2_adj_maus": m1.rsquared_adj,
                 "r2_kontext": m2.rsquared, "r2_adj_kontext": m2.rsquared_adj})
    note = (f"Maus ({', '.join(base)}): R² {m1.rsquared:.3f}, adj. {m1.rsquared_adj:.3f}; "
            f"+ {', '.join(extra)}: R² {m2.rsquared:.3f}, adj. {m2.rsquared_adj:.3f}; "
            f"n/k = {len(d)}/{k} = {len(d) / k:.1f}")
    if len(d) / k < 10:
        note += " (< 10 Beobachtungen pro Prädiktor: Modell instabil, nur beschreibend)"
    return _row(h, "OLS R²-Vergleich (F-Test verschachtelt)", len(d), f, p, m2.rsquared - m1.rsquared,
                note, **info)


H5_MOUSE = ["dir_change_rate", "switch_rate", "pause_share"]
H5_CONTEXT = ["task_success", "seq_mean"]


def run_hypotheses(mouse: pd.DataFrame, quest: pd.DataFrame) -> pd.DataFrame:
    """mouse: eingeschlossene Besuche mit zugeordnetem Fragebogen (H1, H2, H4, H5).
    quest: alle eingeschlossenen Fragebogen, auch ohne Aufzeichnung (H3a, H3b)."""
    hovered = mouse[mouse["aoi_portrait_hovered"].fillna(False).astype(bool)] if "aoi_portrait_hovered" in mouse else mouse.iloc[0:0]
    ml = mouse[mouse["variant"] == "ML"]
    rows = [
        spearman(mouse, "dir_change_rate", "ueqs_pragmatic", "H1", "negativ"),
        spearman(mouse, "time_to_form_s", "seq_mean", "H2", "positiv"),
        group_compare(quest, "task_success", "variante", "H3a", "OP", "ML"),
        group_compare(quest, "ueqs_total", "variante", "H3b", "OP", "ML"),
        welch(quest, "ueqs_total", "variante", "H3b", "OP", "ML"),
        group_compare(mouse, "aoi_portrait_dwell_ms", "geschlecht", "H4 (explorativ)", "weiblich", "männlich"),
        fisher(mouse, "aoi_portrait_hovered", "geschlecht", "H4b Stufe 1 (explorativ)", "weiblich", "männlich"),
        group_compare(hovered, "aoi_portrait_dwell_ms", "geschlecht", "H4c Stufe 2: nur wer berührt (explorativ)",
                      "weiblich", "männlich"),
        fisher(ml, "aoi_portrait_hovered", "geschlecht", "H4b nur ML (explorativ)", "weiblich", "männlich"),
        logistic_with_covariate(mouse, "aoi_portrait_hovered", "geschlecht", "weiblich", "variant", "OP",
                                "H4b adjustiert für Variante (explorativ)"),
        r2_compare(mouse, "ueqs_total", H5_MOUSE, H5_CONTEXT, "H5"),
    ]
    return pd.DataFrame(rows)


def sensitivity_h1(mouse: pd.DataFrame, visits: pd.DataFrame, thresholds: list[int]) -> pd.DataFrame:
    """Richtungswechsel pro s mit verschiedenen Mindestbewegungen: Variantenvergleich und H1."""
    rows = []
    for t in thresholds:
        col = f"dir_change_rate_t{t}"
        if col not in visits:
            continue
        v = group_compare(visits, col, "variant", f"Schwelle {t}", "OP", "ML")
        h = spearman(mouse, col, "ueqs_pragmatic", f"Schwelle {t}", "negativ")
        rows.append({
            "schwelle_einheiten": t,
            "ML_median": visits.loc[visits["variant"] == "ML", col].median(),
            "OP_median": visits.loc[visits["variant"] == "OP", col].median(),
            "variante_p": v["p"], "variante_effekt": v["effekt"], "hoeher_in": v["hoeher_in"],
            "H1_rho": h["effekt"], "H1_p": h["p"], "H1_n": h["n"],
        })
    return pd.DataFrame(rows)


def compare_variants(visits: pd.DataFrame, metrics: dict[str, str]) -> pd.DataFrame:
    """Beschreibender Variantenvergleich aller Maus-Kennzahlen (explorativ).

    Effekt = rang-biseriale Korrelation OP vs. ML (positiv = OP höher); Spalte hoeher_in.
    Für Kennzahlen mit vielen Nullen zusätzlich Anteil > 0 und Mittelwert."""
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
            r[f"{v}_mittel"] = s.mean() if len(s) else np.nan
            r[f"{v}_anteil_gt0"] = (s > 0).mean() if len(s) else np.nan
        rows.append(r)
    return pd.DataFrame(rows).rename(columns={"hypothese": "kennzahl"})


def crosstab_variant_gender(df: pd.DataFrame, variant_col: str, label: str) -> pd.DataFrame:
    """Kreuztabelle Variante x Geschlecht (zur Beurteilung der Vermischung)."""
    if df is None or df.empty or "geschlecht" not in df:
        return pd.DataFrame()
    t = pd.crosstab(df[variant_col], df["geschlecht"], margins=True, margins_name="total")
    t.index.name = "variante"
    t = t.reset_index()
    t.insert(0, "stichprobe", label)
    return t


def holm(p: pd.Series) -> pd.Series:
    """Holm-Bonferroni-Korrektur (NaN bleibt NaN)."""
    valid = p.dropna().sort_values()
    m = len(valid)
    adj, running = {}, 0.0
    for i, (idx, val) in enumerate(valid.items()):
        running = max(running, min(1.0, (m - i) * val))
        adj[idx] = running
    return p.index.to_series().map(adj).astype(float)


def image_tests(avail: pd.DataFrame) -> pd.DataFrame:
    """Explorative Tests je Bild (alle Inhaltsbilder, nicht nur das Porträt).

    avail: Besuch x Bild (features.image_availability), optional mit Spalte geschlecht.
    Je Familie Holm-Korrektur über die 8 Bilder. Die Familien «mind. ein Bild angeklickt …»
    bestehen aus je einem einzigen Test; dort ist p_holm = p (keine Korrektur nötig).
    Geschlechtsvergleiche zusätzlich nur innerhalb ML, weil Geschlecht und Variante vermischt sind.
    """
    families = [
        ("überfahren nach Variante", None, lambda d, img: fisher(d, "hovered", "variant", img, "OP", "ML")),
        ("angeklickt nach Variante", None, lambda d, img: fisher(d, "clicked", "variant", img, "OP", "ML")),
    ]
    if "geschlecht" in avail:
        families += [
            ("überfahren nach Geschlecht", None, lambda d, img: fisher(d, "hovered", "geschlecht", img, "weiblich", "männlich")),
            ("angeklickt nach Geschlecht", None, lambda d, img: fisher(d, "clicked", "geschlecht", img, "weiblich", "männlich")),
            ("angeklickt nach Geschlecht, nur ML", "ML", lambda d, img: fisher(d, "clicked", "geschlecht", img, "weiblich", "männlich")),
            ("Verweildauer nach Geschlecht", None, lambda d, img: group_compare(d, "hover_ms", "geschlecht", img, "weiblich", "männlich")),
        ]
    rows = []
    for fam, only, fn in families:
        base = avail if only is None else avail[avail["variant"] == only]
        part = pd.DataFrame([fn(d, img.replace("-Mira-Caduff", "")) | {"familie": fam}
                             for img, d in base.groupby("image")])
        if part.empty:
            continue
        part["p_holm"] = holm(part["p"])
        part["signifikant"] = part["p_holm"] < ALPHA
        rows.append(part)

    # Zusammengefasst pro Besuch: mindestens ein Bild angeklickt (Einzeltests je eigene Familie)
    per_visit = avail.groupby("idvisit").agg(variant=("variant", "first"), clicked=("clicked", "any"))
    singles = [fisher(per_visit, "clicked", "variant", "alle Bilder", "OP", "ML")
               | {"familie": "mind. ein Bild angeklickt nach Variante"}]
    if "geschlecht" in avail:
        per_visit["geschlecht"] = avail.groupby("idvisit")["geschlecht"].first()
        singles += [
            fisher(per_visit, "clicked", "geschlecht", "alle Bilder", "weiblich", "männlich")
            | {"familie": "mind. ein Bild angeklickt nach Geschlecht"},
            fisher(per_visit[per_visit["variant"] == "ML"], "clicked", "geschlecht", "alle Bilder", "weiblich", "männlich")
            | {"familie": "mind. ein Bild angeklickt nach Geschlecht, nur ML"},
            logistic_with_covariate(per_visit, "clicked", "geschlecht", "weiblich", "variant", "OP", "alle Bilder")
            | {"familie": "mind. ein Bild angeklickt nach Geschlecht, adjustiert für Variante"},
        ]
    singles = pd.DataFrame(singles)
    singles["p_holm"] = singles["p"]
    singles["signifikant"] = singles["p"] < ALPHA
    rows.insert(0, singles)
    out = pd.concat(rows, ignore_index=True).rename(columns={"hypothese": "bild"})
    cols = ["familie", "bild", "test", "n", "statistik", "p", "p_holm", "effekt", "hoeher_in",
            "risikodifferenz", "rd_ki_unten", "rd_ki_oben", "odds_ratio", "odds_ratio_haldane",
            "signifikant", "hinweis"]
    return out.reindex(columns=cols)
