"""Gesamter Ablauf: Datenbank -> bereinigte Tabellen -> Kennzahlen -> Bericht."""

from __future__ import annotations

import datetime as dt
import warnings
from dataclasses import dataclass

import pandas as pd

from . import clean, dom, features, forms, plots, stats
from .config import DATA_PROCESSED, OUTPUT, StudyConfig, ensure_dirs, load_config
from .load import connect
from .questionnaire import QUESTIONNAIRE_FILE, load_questionnaire, score


@dataclass
class Dataset:
    cfg: StudyConfig
    pageviews: pd.DataFrame  # mit Kennzahlen pro Seitenaufruf
    events: pd.DataFrame
    visits: pd.DataFrame  # mit Kennzahlen pro Besuch
    flow: pd.DataFrame
    entries: pd.DataFrame | None = None  # Fragebogen (ein Eintrag pro Zeile, mit Zuordnung)
    entry_flow: pd.DataFrame | None = None
    image_usage: pd.DataFrame | None = None  # pro Besuch und Bild
    page_images: dict | None = None  # URL -> Inhaltsbilder

    @property
    def included(self) -> pd.DataFrame:
        return self.visits[self.visits["included"]]

    @property
    def questionnaire(self) -> pd.DataFrame | None:
        """Eingeschlossene Fragebogen (für H3a, H3b)."""
        return None if self.entries is None else self.entries[self.entries["entry_included"]]

    @property
    def mouse_questionnaire(self) -> pd.DataFrame | None:
        """Besuche mit Kennzahlen + zugeordnetem Fragebogen (für H1, H2, H4, H5)."""
        if self.entries is None:
            return None
        e = self.entries[self.entries["mouse_included"]].drop(
            columns=["visit_variant", "visit_included", "visit_exclusion"], errors="ignore")
        return self.included.merge(e, on="idvisit", how="inner")


def build(cfg: StudyConfig | None = None, write: bool = True) -> Dataset:
    cfg = cfg or load_config()
    ensure_dirs()
    con = connect()
    try:
        pv = clean.load_pageviews(con, cfg)
        ev = clean.load_events(con, pv)
        visits = clean.build_visits(con, pv, cfg)
        pvf = features.pageview_features(pv, ev, cfg)
        vf = features.visit_features(visits, pvf)
        vf = clean.apply_completion_rules(vf, cfg)
        entries = _load_entries(con, vf, pvf, cfg)
        page_imgs = dom.page_images(con, cfg.content_image_regex)
    finally:
        con.close()
    entry_flow = forms.entry_flow(entries) if entries is not None else None
    usage = features.visit_image_usage(ev, pvf, cfg)
    ev = ev.merge(vf[["idvisit", "variant", "included"]], on="idvisit", how="left")
    for name, mask in features._aoi_masks(ev, cfg).items():
        ev[f"aoi_{name}"] = mask
    flow = clean.sample_flow(vf)
    if write:
        pvf.to_csv(DATA_PROCESSED / "pageviews.csv", index=False)
        vf.to_csv(DATA_PROCESSED / "visits.csv", index=False)
        ev.to_csv(DATA_PROCESSED / "events.csv", index=False)
        flow.to_csv(DATA_PROCESSED / "stichprobe.csv", index=False)
        usage.to_csv(DATA_PROCESSED / "bilder.csv", index=False)
        if entries is not None:
            entries.to_csv(DATA_PROCESSED / "fragebogen.csv", index=False)
    return Dataset(cfg, pvf, ev, vf, flow, entries, entry_flow, usage, page_imgs)


def _load_entries(con, visits: pd.DataFrame, pvf: pd.DataFrame, cfg: StudyConfig) -> pd.DataFrame | None:
    """Fragebogen aus WPForms (bevorzugt) oder aus der manuellen CSV."""
    if forms.has_entries(con):
        e = forms.code_answers(forms.parse_entries(con, cfg), cfg)
        e = forms.match_entries(e, visits, pvf, cfg)
    else:
        q = load_questionnaire(cfg=cfg)
        if q is None:
            return None
        e = q.copy()
        e["entry_id"] = range(1, len(e) + 1)
        e["submitted_local"] = pd.NaT
        e["match_status"] = "manuell (CSV)"
        if "variante" not in e:
            e = e.merge(visits[["idvisit", "variant"]].rename(columns={"variant": "variante"}), on="idvisit", how="left")
    e = forms.entry_exclusions(e, visits, cfg)
    return score(e, cfg.scale_min, cfg.scale_max)


def report(ds: Dataset | None = None) -> None:
    ds = ds or build()
    ensure_dirs()
    fig_dir = OUTPUT / "figures"
    fig_dir.mkdir(exist_ok=True)
    inc = ds.included

    comparison = stats.compare_variants(inc, features.KEY_METRICS)
    avail = features.image_availability(ds.image_usage, inc, ds.pageviews, ds.page_images)
    if ds.entries is not None:
        gender = ds.entries.loc[ds.entries["mouse_included"], ["idvisit", "geschlecht"]].dropna().drop_duplicates("idvisit")
        avail = avail.merge(gender, on="idvisit", how="left")
    img_summary = features.image_summary(avail, "variant")
    img_gender = features.image_summary(avail.dropna(subset=["geschlecht"]), "geschlecht") if "geschlecht" in avail else None
    img_tests = stats.image_tests(avail)
    sel = features.selector_summary(ds.events[ds.events["included"].fillna(False).astype(bool)])

    hyp = None
    merged = ds.mouse_questionnaire
    if ds.questionnaire is not None:
        hyp = stats.run_hypotheses(merged, ds.questionnaire)

    figs = [plots.boxplots(inc, features.KEY_METRICS, fig_dir), plots.page_paths(ds.pageviews, ds.visits, fig_dir)]
    for f in (plots.image_usage(img_summary, fig_dir),
              plots.image_usage(img_gender, fig_dir, "geschlecht", ("weiblich", "männlich"), "bilder_geschlecht")
              if img_gender is not None else None):
        if f:
            figs.append(f)
    inc_ev = ds.events[ds.events["included"].fillna(False).astype(bool)]
    if "aoi_portrait" in inc_ev:
        f = plots.aoi_hover_map(inc_ev, "aoi_portrait", fig_dir, "Mauspositionen auf dem Porträt")
        if f:
            figs.append(f)

    prov = _provenance(ds)
    with pd.ExcelWriter(OUTPUT / "tabellen.xlsx") as xw:
        prov.to_excel(xw, sheet_name="Info", index=False)
        ds.flow.to_excel(xw, sheet_name="Stichprobe", index=False)
        comparison.to_excel(xw, sheet_name="Variantenvergleich", index=False)
        img_summary.to_excel(xw, sheet_name="Bilder nach Variante", index=False)
        if img_gender is not None:
            img_gender.to_excel(xw, sheet_name="Bilder nach Geschlecht", index=False)
        img_tests.to_excel(xw, sheet_name="Bilder Tests", index=False)
        inc.to_excel(xw, sheet_name="Besuche", index=False)
        sel.head(500).to_excel(xw, sheet_name="Elemente", index=False)
        if hyp is not None:
            ds.entry_flow.to_excel(xw, sheet_name="Stichprobe Fragebogen", index=False)
            hyp.to_excel(xw, sheet_name="Hypothesen", index=False)
            ds.entries.drop(columns=["feedback"], errors="ignore").to_excel(xw, sheet_name="Fragebogen", index=False)
            merged.to_excel(xw, sheet_name="Besuche+Fragebogen", index=False)

    _write_markdown(ds, comparison, hyp, figs, img_summary, img_gender, img_tests, prov)
    print(f"Bericht: {OUTPUT / 'bericht.md'}")
    print(f"Tabellen: {OUTPUT / 'tabellen.xlsx'}")


def _provenance(ds: Dataset) -> pd.DataFrame:
    """Herkunft der Zahlen: Code-Version, Quelldatei, Zeitpunkt."""
    import subprocess

    from .config import ROOT
    from .load import connect

    def git(*args: str) -> str:
        try:
            return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception:
            return ""

    commit = git("rev-parse", "--short", "HEAD") or "unbekannt"
    if git("status", "--porcelain", "--", "src", "config"):
        commit += " (mit lokalen Änderungen an Code/Konfiguration)"
    con = connect()
    try:
        row = con.execute("SELECT value FROM _meta WHERE key='source_file'").fetchone()
    finally:
        con.close()
    return pd.DataFrame([
        ("Erstellt", dt.datetime.now().strftime("%d.%m.%Y %H:%M")),
        ("Code-Version (Git-Commit)", commit),
        ("Quelldatei (SQL-Export)", row[0] if row else "unbekannt"),
    ], columns=["feld", "wert"])


def _fmt(df: pd.DataFrame) -> str:
    return df.to_markdown(index=False, floatfmt=".3g") if _has_tabulate() else "```\n" + df.to_string(index=False) + "\n```"


def _has_tabulate() -> bool:
    try:
        import tabulate  # noqa: F401
        return True
    except ImportError:
        return False


def _write_markdown(ds: Dataset, comparison: pd.DataFrame, hyp: pd.DataFrame | None, figs: list,
                    img_summary: pd.DataFrame, img_gender: pd.DataFrame | None, img_tests: pd.DataFrame,
                    prov: pd.DataFrame) -> None:
    cfg = ds.cfg
    lines = [
        "# AFE2 Auswertung",
        "",
        *[f"- {r.feld}: {r.wert}" for r in prov.itertuples()],
        "",
        "## Einstellungen",
        "",
        f"- Feldphase: {cfg.field_start or 'nicht gesetzt'} bis {cfg.field_end or 'offen'} ({cfg.timezone})",
        f"- Späterer Start je Variante: {cfg.variant_start or 'keiner'}",
        f"- Fragebogen-Skalen: {cfg.scale_min} bis {cfg.scale_max}",
        f"- Geräte: {cfg.device_types or 'alle'}",
        f"- Nur mit Formular: {'ja' if cfg.require_form else 'nein'}, Mindestdauer: {cfg.min_total_s:g} s, "
        f"Admin-Besuche ausgeschlossen: {'ja' if cfg.exclude_admin_bar else 'nein'}",
        f"- Richtungswechsel ab {cfg.direction_min_delta} Element-Einheiten, Pause ab {cfg.pause_ms} ms, "
        f"AOI-Deckel {cfg.dwell_cap_ms} ms",
        "",
        "## Stichprobe Maus-Tracking (Besuche)",
        "",
        _fmt(ds.flow),
        "",
        "## Variantenvergleich Maus-Kennzahlen (explorativ)",
        "",
        _fmt(comparison[["kennzahl", "ML_n", "ML_median", "OP_n", "OP_median", "p", "effekt", "hinweis"]]),
        "",
        "## Bilder: überfahren und angeklickt (Vergrösserung)",
        "",
        "Basis: eingeschlossene Besuche, die eine Seite mit dem Bild aufgerufen haben.",
        "",
        _fmt(img_summary.assign(image=img_summary["image"].str.replace("-Mira-Caduff", "", regex=False))[
            ["variant", "image", "besuche_mit_bild", "anteil_ueberfahren", "anteil_angeklickt", "median_ms_wenn_ueberfahren"]]),
        "",
    ]
    if img_gender is not None:
        lines += ["Nach Geschlecht (nur Besuche mit zugeordnetem Fragebogen):", "",
                  _fmt(img_gender.assign(image=img_gender["image"].str.replace("-Mira-Caduff", "", regex=False))[
                      ["geschlecht", "image", "besuche_mit_bild", "anteil_ueberfahren", "anteil_angeklickt",
                       "median_ms_wenn_ueberfahren"]]), ""]
    lines += ["### Tests je Bild (explorativ, Holm-korrigiert je Familie)", "",
              _fmt(img_tests[["familie", "bild", "n", "p", "p_holm", "effekt", "hinweis"]]), ""]
    if hyp is not None:
        e = ds.entries
        lines += ["## Stichprobe Fragebogen", "", _fmt(ds.entry_flow), "",
                  "Zuordnung Fragebogen zu Besuch: " + ", ".join(
                      f"{k}: {v}" for k, v in e["match_status"].value_counts().items()), ""]
        q = ds.questionnaire
        desc = q.groupby("variante")[["task_success", "seq_mean", "ueqs_pragmatic", "ueqs_hedonic", "ueqs_total"]].agg(
            ["count", "mean", "median"]).round(2)
        desc.columns = [f"{a}_{b}" for a, b in desc.columns]
        lines += ["## Fragebogen nach Variante", "", _fmt(desc.reset_index()), ""]
        lines += ["## Hypothesen", "", _fmt(hyp), ""]
    else:
        lines += ["## Hypothesen", "", f"Noch keine Fragebogendaten ({QUESTIONNAIRE_FILE.name} fehlt).", ""]
    lines += ["## Grafiken", ""] + [f"![{f.stem}](figures/{f.name})" for f in figs]
    (OUTPUT / "bericht.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
