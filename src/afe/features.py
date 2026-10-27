"""Schritt 3: Kennzahlen pro Seitenaufruf und pro Besuch berechnen.

Wichtig zur Datengrundlage (Matomo Heatmap & Session Recording):
- Mausereignisse (Bewegung, Klick) speichern x/y NICHT als Bildschirmpixel,
  sondern relativ zum Element unter der Maus (CSS-Selektor), skaliert auf 0..2000.
  Absolute Pfadlängen in Pixeln sind daher nicht direkt berechenbar.
- Richtungswechsel werden deshalb nur zwischen aufeinanderfolgenden Ereignissen
  im selben Element gezählt; dort ist die Richtung eindeutig.
- Bewegungen werden etwa alle 200 ms erfasst, solange sich die Maus bewegt.
  Lücken zwischen Ereignissen bedeuten also: Maus ruht (Pause/Zögern).

Alle Schwellenwerte stehen in config/study.toml ([metrics]).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import StudyConfig


def _direction_changes(x: np.ndarray, sel: np.ndarray, min_delta: int) -> int:
    """Vorzeichenwechsel der Bewegungsrichtung innerhalb desselben Elements.

    Kleine Bewegungen unter min_delta werden ignoriert (Zittern)."""
    changes = 0
    last_sign = 0
    for i in range(1, len(x)):
        if sel[i] != sel[i - 1]:
            last_sign = 0
            continue
        d = x[i] - x[i - 1]
        if abs(d) < min_delta:
            continue
        s = 1 if d > 0 else -1
        if last_sign and s != last_sign:
            changes += 1
        last_sign = s
    return changes


def _sign_reversals(values: np.ndarray) -> int:
    d = np.diff(values)
    d = d[d != 0]
    if len(d) < 2:
        return 0
    return int((np.sign(d[1:]) != np.sign(d[:-1])).sum())


def _aoi_masks(ev: pd.DataFrame, cfg: StudyConfig) -> dict[str, pd.Series]:
    masks: dict[str, pd.Series] = {}
    sel = ev["selector"].fillna("")
    url = ev["url"].fillna("")
    img = ev["image"].fillna("") if "image" in ev else pd.Series("", index=ev.index)
    for rule in cfg.aoi:
        m = pd.Series(True, index=ev.index)
        if rule.url_regex:
            m &= url.str.contains(rule.url_regex, regex=True)
        if rule.selector_regex:
            m &= sel.str.contains(rule.selector_regex, regex=True)
        if rule.image_regex:
            m &= img.str.contains(rule.image_regex, regex=True)
        masks[rule.name] = masks.get(rule.name, pd.Series(False, index=ev.index)) | m
    return masks


def pageview_features(pv: pd.DataFrame, ev: pd.DataFrame, cfg: StudyConfig) -> pd.DataFrame:
    ev = ev.copy()
    for name, mask in _aoi_masks(ev, cfg).items():
        ev[f"aoi_{name}"] = mask
    aoi_cols = [c for c in ev.columns if c.startswith("aoi_")]

    by_pv = {k: g for k, g in ev.groupby("idloghsr")}
    rows = []
    for p in pv.itertuples(index=False):
        g = by_pv.get(p.idloghsr)
        r = {"idloghsr": p.idloghsr}
        dur_s = max(p.time_on_page_ms, 1) / 1000
        if g is None:
            g = ev.iloc[0:0]
        mouse = g[g["event_type"].isin((1, 2))]
        moves = g[g["event_type"] == 1]
        clicks = g[g["event_type"] == 2]
        scrolls = g[g["event_type"] == 3]
        forms = g[g["event_type"].isin((9, 10))]

        r["n_moves"] = len(moves)
        r["n_clicks"] = len(clicks)
        r["n_scroll_events"] = len(scrolls)
        r["first_click_ms"] = clicks["t_ms"].min() if len(clicks) else np.nan
        r["first_form_ms"] = forms["t_ms"].min() if len(forms) else np.nan
        r["last_form_ms"] = forms["t_ms"].max() if len(forms) else np.nan
        r["n_form_events"] = len(forms)

        sel = mouse["selector"].fillna("").to_numpy()
        t = mouse["t_ms"].to_numpy()
        r["n_elements"] = len(set(sel))
        r["element_switches"] = int((sel[1:] != sel[:-1]).sum()) if len(sel) > 1 else 0

        msel = moves["selector"].fillna("").to_numpy()
        dx = _direction_changes(moves["x"].to_numpy(), msel, cfg.direction_min_delta)
        dy = _direction_changes(moves["y"].to_numpy(), msel, cfg.direction_min_delta)
        r["dir_changes_x"] = dx
        r["dir_changes_y"] = dy
        r["dir_changes"] = dx + dy

        gaps = np.diff(t) if len(t) > 1 else np.array([])
        long_gaps = gaps[gaps >= cfg.pause_ms]
        r["n_pauses"] = len(long_gaps)
        r["pause_time_ms"] = float(long_gaps.sum())

        r["scroll_reversals"] = _sign_reversals(scrolls["y"].to_numpy())

        # AOI-Verweildauer: Zeit bis zum nächsten Mausereignis (gedeckelt), solange Maus in AOI
        if len(t):
            next_t = np.append(t[1:], p.time_on_page_ms)
            hold = np.clip(next_t - t, 0, cfg.dwell_cap_ms)
        for c in aoi_cols:
            m = mouse[c].to_numpy() if len(mouse) else np.array([], dtype=bool)
            r[f"{c}_dwell_ms"] = float(hold[m].sum()) if len(t) else 0.0
            r[f"{c}_events"] = int(m.sum())
            r[f"{c}_first_ms"] = float(t[m].min()) if m.any() else np.nan

        # Bilder (Selektor -> Bild über den DOM-Snapshot, siehe dom.selector_image_map)
        imgs = mouse["image"] if "image" in mouse else pd.Series(dtype=object)
        has_img = imgs.notna().to_numpy() if len(mouse) else np.array([], dtype=bool)
        r["n_images_hovered"] = int(imgs.dropna().nunique())
        r["image_clicks"] = int(((mouse["event_type"] == 2).to_numpy() & has_img).sum()) if len(mouse) else 0
        lb = mouse["selector"].fillna("").str.startswith(("div#lightbox", "div#lightboxOverlay")).to_numpy() if len(mouse) else np.array([], dtype=bool)
        r["lightbox_ms"] = float(hold[lb].sum()) if len(t) else 0.0
        r["image_dwell_ms"] = float(hold[has_img].sum()) if len(t) else 0.0

        r["dir_change_rate"] = r["dir_changes"] / dur_s
        r["switch_rate"] = r["element_switches"] / dur_s
        rows.append(r)

    feats = pd.DataFrame(rows)
    return pv.merge(feats, on="idloghsr", how="left")


SUM_COLS = [
    "image_clicks", "lightbox_ms", "image_dwell_ms",
    "time_on_page_ms", "n_moves", "n_clicks", "n_scroll_events", "n_form_events", "element_switches",
    "dir_changes_x", "dir_changes_y", "dir_changes", "n_pauses", "pause_time_ms", "scroll_reversals",
]


def visit_features(visits: pd.DataFrame, pvf: pd.DataFrame) -> pd.DataFrame:
    aoi_dwell = [c for c in pvf.columns if c.startswith("aoi_") and c.endswith(("_dwell_ms", "_events"))]
    agg = pvf.groupby("idvisit")[SUM_COLS + aoi_dwell].sum()
    agg["n_pages_distinct"] = pvf.groupby("idvisit")["page"].nunique()
    for c in [c for c in pvf.columns if c.startswith("aoi_") and c.endswith("_events")]:
        agg[c.replace("_events", "_hovered")] = agg[c] > 0
    agg["scroll_max_pct_mean"] = pvf.groupby("idvisit")["scroll_max_pct"].mean()

    # Time-to-Form: Zeit bis zur ersten Formulareingabe.
    # time_to_form_s      = Summe der Verweildauer aller Seiten davor + Zeit auf der Formularseite
    #                       bis zur ersten Eingabe (gleiche Zeitbasis wie time_total_s, Hauptmass)
    # time_to_form_wall_s = Uhrzeit-Differenz ab Besuchsbeginn (enthält Zeit in anderen Tabs)
    pvf = pvf.sort_values(["idvisit", "pv_index"]).copy()
    first_form_pv = pvf.dropna(subset=["first_form_ms"]).groupby("idvisit")["pv_index"].min()
    pvf["_form_pv"] = pvf["idvisit"].map(first_form_pv)
    before = pvf[pvf["pv_index"] < pvf["_form_pv"]].groupby("idvisit")["time_on_page_ms"].sum()
    at = pvf[pvf["pv_index"] == pvf["_form_pv"]].set_index("idvisit")["first_form_ms"]
    agg["time_to_form_s"] = (before.reindex(at.index, fill_value=0) + at) / 1000
    start = pvf.groupby("idvisit")["server_time"].transform("min")
    form_wall = (pvf["server_time"] - start).dt.total_seconds() + pvf["first_form_ms"] / 1000
    agg["time_to_form_wall_s"] = form_wall.groupby(pvf["idvisit"]).min()
    agg["pages_before_form"] = first_form_pv - 1
    agg["reached_form"] = agg["time_to_form_s"].notna()

    total_s = agg["time_on_page_ms"] / 1000
    agg["time_total_s"] = total_s
    agg["dir_change_rate"] = agg["dir_changes"] / total_s.where(total_s > 0)
    agg["switch_rate"] = agg["element_switches"] / total_s.where(total_s > 0)
    agg["pause_share"] = agg["pause_time_ms"] / agg["time_on_page_ms"].where(agg["time_on_page_ms"] > 0)
    return visits.merge(agg.reset_index(), on="idvisit", how="left")


# Kennzahlen, die im Variantenvergleich und in den Grafiken verwendet werden
KEY_METRICS = {
    "time_total_s": "Gesamtzeit (s)",
    "time_to_form_s": "Zeit bis Formular (s)",
    "n_clicks": "Klicks",
    "dir_change_rate": "Richtungswechsel pro s",
    "switch_rate": "Elementwechsel pro s",
    "pause_share": "Anteil Pausenzeit",
    "scroll_reversals": "Scroll-Richtungswechsel",
    "aoi_portrait_dwell_ms": "Verweildauer Porträt (ms)",
    "n_images_hovered": "Bilder überfahren (Anzahl)",
    "image_clicks": "Klicks auf Bilder (Vergrösserung)",
    "lightbox_ms": "Zeit in Vergrösserung (ms)",
}


def selector_summary(ev: pd.DataFrame) -> pd.DataFrame:
    m = ev[ev["event_type"].isin((1, 2))]
    out = m.groupby(["page", "selector"]).agg(
        moves=("event_type", lambda s: int((s == 1).sum())),
        clicks=("event_type", lambda s: int((s == 2).sum())),
        pageviews=("idloghsr", "nunique"),
    )
    return out.reset_index().sort_values(["page", "moves"], ascending=[True, False])



def visit_image_usage(ev: pd.DataFrame, pv: pd.DataFrame, cfg: StudyConfig) -> pd.DataFrame:
    """Pro Besuch und Bild: Bild geladen (Seite besucht), überfahren, Verweildauer, angeklickt."""
    import re

    rx = re.compile(cfg.content_image_regex) if cfg.content_image_regex else None
    m = ev[ev["event_type"].isin((1, 2))].sort_values(["idloghsr", "t_ms"]).copy()
    end = m["idloghsr"].map(pv.set_index("idloghsr")["time_on_page_ms"])
    nxt = m.groupby("idloghsr")["t_ms"].shift(-1).fillna(end)
    m["hold_ms"] = (nxt - m["t_ms"]).clip(0, cfg.dwell_cap_ms)
    m = m.dropna(subset=["image"])
    if rx is not None:
        m = m[m["image"].map(lambda s: bool(rx.search(s)))]
    g = m.groupby(["idvisit", "image"])
    return pd.DataFrame({
        "hover_ms": g["hold_ms"].sum(),
        "events": g.size(),
        "clicked": g["event_type"].apply(lambda s: bool((s == 2).any())),
    }).reset_index()


def image_summary(usage: pd.DataFrame, visits: pd.DataFrame, pv: pd.DataFrame,
                  page_imgs: dict[str, set[str]]) -> pd.DataFrame:
    """Pro Variante und Bild: wie viele Besuche hatten das Bild auf einer besuchten Seite,
    wie viele haben es überfahren bzw. angeklickt (Vergrösserung)?

    visits: nur eingeschlossene Besuche."""
    avail = (pv[pv["idvisit"].isin(visits["idvisit"])]
             .assign(images=lambda d: d["url"].map(lambda u: sorted(page_imgs.get(u, set()))))
             .explode("images").dropna(subset=["images"])
             .rename(columns={"images": "image"})[["idvisit", "image"]].drop_duplicates())
    avail = avail.merge(visits[["idvisit", "variant"]], on="idvisit")
    d = avail.merge(usage, on=["idvisit", "image"], how="left")
    d["hovered"] = d["events"].fillna(0) > 0
    d["clicked"] = d["clicked"].fillna(False).astype(bool)
    g = d.groupby(["variant", "image"])
    out = pd.DataFrame({
        "besuche_mit_bild": g.size(),
        "ueberfahren": g["hovered"].sum(),
        "angeklickt": g["clicked"].sum(),
        "median_ms_wenn_ueberfahren": g.apply(lambda x: x.loc[x["hovered"], "hover_ms"].median()),
    }).reset_index()
    out["anteil_ueberfahren"] = out["ueberfahren"] / out["besuche_mit_bild"]
    out["anteil_angeklickt"] = out["angeklickt"] / out["besuche_mit_bild"]
    return out
