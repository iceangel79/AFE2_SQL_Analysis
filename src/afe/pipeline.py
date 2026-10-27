"""Gesamter Ablauf: Datenbank -> bereinigte Tabellen -> Kennzahlen -> Bericht."""

from __future__ import annotations

import datetime as dt
import warnings
from dataclasses import dataclass

import pandas as pd

from . import clean, features, plots, stats
from .config import DATA_PROCESSED, OUTPUT, StudyConfig, ensure_dirs, load_config
from .load import connect
from .questionnaire import QUESTIONNAIRE_FILE, load_questionnaire


@dataclass
class Dataset:
    cfg: StudyConfig
    pageviews: pd.DataFrame  # mit Kennzahlen pro Seitenaufruf
    events: pd.DataFrame
    visits: pd.DataFrame  # mit Kennzahlen pro Besuch
    flow: pd.DataFrame

    @property
    def included(self) -> pd.DataFrame:
        return self.visits[self.visits["included"]]


def build(cfg: StudyConfig | None = None, write: bool = True) -> Dataset:
    cfg = cfg or load_config()
    ensure_dirs()
    con = connect()
    try:
        pv = clean.load_pageviews(con, cfg)
        ev = clean.load_events(con, pv)
        visits = clean.build_visits(con, pv, cfg)
    finally:
        con.close()
    pvf = features.pageview_features(pv, ev, cfg)
    vf = features.visit_features(visits, pvf)
    vf = clean.apply_completion_rules(vf, cfg)
    ev = ev.merge(vf[["idvisit", "variant", "included"]], on="idvisit", how="left")
    for name, mask in features._aoi_masks(ev, cfg).items():
        ev[f"aoi_{name}"] = mask
    flow = clean.sample_flow(vf)
    if write:
        pvf.to_csv(DATA_PROCESSED / "pageviews.csv", index=False)
        vf.to_csv(DATA_PROCESSED / "visits.csv", index=False)
        ev.to_csv(DATA_PROCESSED / "events.csv", index=False)
        flow.to_csv(DATA_PROCESSED / "stichprobe.csv", index=False)
    return Dataset(cfg, pvf, ev, vf, flow)


def report(ds: Dataset | None = None) -> None:
    ds = ds or build()
    ensure_dirs()
    fig_dir = OUTPUT / "figures"
    fig_dir.mkdir(exist_ok=True)
    inc = ds.included

    comparison = stats.compare_variants(inc, features.KEY_METRICS)
    sel = features.selector_summary(ds.events[ds.events["included"].fillna(False).astype(bool)])

    q = load_questionnaire(cfg=ds.cfg)
    hyp = None
    merged = None
    if q is not None:
        merged = inc.merge(q, on="idvisit", how="inner", suffixes=("", "_fb"))
        unmatched = set(q["idvisit"].dropna()) - set(inc["idvisit"])
        if unmatched:
            warnings.warn(f"Fragebogen-Zeilen ohne eingeschlossenen Besuch: {sorted(unmatched)}")
        hyp = stats.run_hypotheses(merged)

    figs = [plots.boxplots(inc, features.KEY_METRICS, fig_dir), plots.page_paths(ds.pageviews, ds.visits, fig_dir)]
    inc_ev = ds.events[ds.events["included"].fillna(False).astype(bool)]
    if "aoi_portrait" in inc_ev:
        f = plots.aoi_hover_map(inc_ev, "aoi_portrait", fig_dir, "Mauspositionen auf dem Porträt")
        if f:
            figs.append(f)

    with pd.ExcelWriter(OUTPUT / "tabellen.xlsx") as xw:
        ds.flow.to_excel(xw, sheet_name="Stichprobe", index=False)
        comparison.to_excel(xw, sheet_name="Variantenvergleich", index=False)
        inc.to_excel(xw, sheet_name="Besuche", index=False)
        sel.head(500).to_excel(xw, sheet_name="Elemente", index=False)
        if hyp is not None:
            hyp.to_excel(xw, sheet_name="Hypothesen", index=False)
            merged.to_excel(xw, sheet_name="Besuche+Fragebogen", index=False)

    _write_markdown(ds, comparison, hyp, figs)
    print(f"Bericht: {OUTPUT / 'bericht.md'}")
    print(f"Tabellen: {OUTPUT / 'tabellen.xlsx'}")


def _fmt(df: pd.DataFrame) -> str:
    return df.to_markdown(index=False, floatfmt=".3g") if _has_tabulate() else "```\n" + df.to_string(index=False) + "\n```"


def _has_tabulate() -> bool:
    try:
        import tabulate  # noqa: F401
        return True
    except ImportError:
        return False


def _write_markdown(ds: Dataset, comparison: pd.DataFrame, hyp: pd.DataFrame | None, figs: list) -> None:
    cfg = ds.cfg
    lines = [
        "# AFE2 Auswertung",
        "",
        f"Erstellt: {dt.datetime.now():%d.%m.%Y %H:%M}",
        "",
        "## Einstellungen",
        "",
        f"- Feldphase: {cfg.field_start or 'nicht gesetzt'} bis {cfg.field_end or 'offen'} ({cfg.timezone})",
        f"- Späterer Start je Variante: {cfg.variant_start or 'keiner'}",
        f"- Fragebogen-Skalen: {cfg.scale_min} bis {cfg.scale_max}",
        f"- Geräte: {cfg.device_types or 'alle'}",
        f"- Nur mit Formular: {'ja' if cfg.require_form else 'nein'}, Mindestdauer: {cfg.min_total_s:g} s",
        f"- Richtungswechsel ab {cfg.direction_min_delta} Element-Einheiten, Pause ab {cfg.pause_ms} ms, "
        f"AOI-Deckel {cfg.dwell_cap_ms} ms",
        "",
        "## Stichprobe",
        "",
        _fmt(ds.flow),
        "",
        "## Variantenvergleich Maus-Kennzahlen (explorativ)",
        "",
        _fmt(comparison[["kennzahl", "ML_n", "ML_median", "OP_n", "OP_median", "p", "effekt", "hinweis"]]),
        "",
    ]
    if hyp is not None:
        lines += ["## Hypothesen", "", _fmt(hyp), ""]
    else:
        lines += ["## Hypothesen", "", f"Noch keine Fragebogendaten ({QUESTIONNAIRE_FILE.name} fehlt).", ""]
    lines += ["## Grafiken", ""] + [f"![{f.stem}](figures/{f.name})" for f in figs]
    (OUTPUT / "bericht.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
