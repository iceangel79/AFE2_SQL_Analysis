"""Schritt 2: Rohdaten aufbereiten und Stichprobe bereinigen.

Erzeugt drei Tabellen:
- pageviews: ein Seitenaufruf pro Zeile (Matomo log_hsr)
- visits:    ein Besuch pro Zeile, mit Variante und Ein-/Ausschlussgrund
- events:    Maus-, Scroll- und Formularereignisse mit URL und CSS-Selektor

Alle Ausschlussregeln kommen aus config/study.toml bzw. config/exclude_visits.csv.
Ausgeschlossene Besuche werden nicht gelöscht, sondern markiert (included = False),
damit der Weg von der Rohstichprobe zur Analysestichprobe dokumentiert ist.
"""

from __future__ import annotations

import sqlite3
import warnings

import pandas as pd

from .config import DEVICE_TYPES, EVENT_TYPES, StudyConfig

# Ereignisse, die für die Auswertung gebraucht werden (DOM/CSS/Mutationen nicht)
ANALYSIS_EVENTS = (1, 2, 3, 4, 9, 10, 12)


def load_pageviews(con: sqlite3.Connection, cfg: StudyConfig) -> pd.DataFrame:
    pv = pd.read_sql(
        """
        SELECT h.idloghsr, h.idvisit, h.server_time, h.device_type, h.time_on_page AS time_on_page_ms,
               h.viewport_w_px, h.viewport_h_px, h.scroll_y_max_relative, h.fold_y_relative,
               a.name AS url
        FROM log_hsr h
        LEFT JOIN log_action a ON a.idaction = h.idaction_url
        """,
        con,
    )
    pv["server_time"] = pd.to_datetime(pv["server_time"])
    pv["url"] = pv["url"].fillna("")
    pv["page"] = pv["url"].map(_page_name)
    pv["device"] = pv["device_type"].map(DEVICE_TYPES).fillna("andere")
    pv["is_op_page"] = pv["url"].str.contains(cfg.op_url_contains, regex=False)
    pv["is_form_page"] = pv["url"].str.contains(cfg.form_url_contains, regex=False)
    # Matomo speichert die Scrolltiefe in Promille der Seitenhöhe
    pv["scroll_max_pct"] = pv["scroll_y_max_relative"] / 10
    pv = pv.sort_values(["idvisit", "server_time", "idloghsr"]).reset_index(drop=True)
    pv["pv_index"] = pv.groupby("idvisit").cumcount() + 1
    return pv


def _page_name(url: str) -> str:
    path = url.split("?", 1)[0]
    path = path.split("/", 1)[1] if "/" in path else ""
    path = path.strip("/")
    return path or "startseite"


def load_events(con: sqlite3.Connection, pv: pd.DataFrame) -> pd.DataFrame:
    types = ",".join(str(t) for t in ANALYSIS_EVENTS)
    ev = pd.read_sql(
        f"""
        SELECT e.idhsrevent, e.idloghsr, e.time_since_load AS t_ms, e.event_type,
               s.name AS selector, e.x, e.y
        FROM log_hsr_event e
        LEFT JOIN log_action s ON s.idaction = e.idselector
        WHERE e.event_type IN ({types})
        """,
        con,
    )
    ev["event"] = ev["event_type"].map(EVENT_TYPES)
    ev = ev.merge(pv[["idloghsr", "idvisit", "url", "page"]], on="idloghsr", how="left")
    # Bild unter dem Element (über den DOM-Snapshot der Seite aufgelöst)
    from .dom import selector_image_map

    ev = ev.merge(selector_image_map(con), on=["url", "selector"], how="left")
    return ev.sort_values(["idloghsr", "t_ms", "idhsrevent"]).reset_index(drop=True)


def classify_variant(pages: pd.DataFrame) -> str:
    """ML = nur Menüseiten (+ Formular), OP = nur Onepager (+ Formular),
    gemischt = beides gesehen, unbekannt = nur Formularseite."""
    op = pages["is_op_page"].any()
    ml = (~pages["is_op_page"] & ~pages["is_form_page"]).any()
    if op and ml:
        return "gemischt"
    if op:
        return "OP"
    if ml:
        return "ML"
    return "unbekannt"


def build_visits(con: sqlite3.Connection, pv: pd.DataFrame, cfg: StudyConfig) -> pd.DataFrame:
    g = pv.groupby("idvisit")
    visits = pd.DataFrame({
        "start": g["server_time"].min(),
        "n_pageviews": g.size(),
        "device_type": g["device_type"].max(),
        "entry_page": g["page"].first(),
    })
    visits["variant"] = pd.Series({v: classify_variant(p) for v, p in g})
    visits["device"] = visits["device_type"].map(DEVICE_TYPES).fillna("andere")
    # Matomo speichert server_time in UTC; Datumsgrenzen gelten in Lokalzeit
    visits["start_local"] = (
        visits["start"].dt.tz_localize("UTC").dt.tz_convert(cfg.timezone).dt.tz_localize(None)
    )
    visits = visits.reset_index()

    # Zusatzinfos aus log_visit (falls im Dump enthalten)
    wanted = {
        "config_browser_name": "browser", "config_os": "os", "config_resolution": "resolution",
        "visitor_returning": "visitor_returning", "visit_total_time": "visit_total_time_s",
    }
    have = {r[1] for r in con.execute("PRAGMA table_info(log_visit)")}
    cols = [c for c in wanted if c in have]
    if cols:
        sel = ", ".join(f'"{c}" AS "{wanted[c]}"' for c in cols)
        lv = pd.read_sql(f"SELECT idvisit, {sel} FROM log_visit", con)
        visits = visits.merge(lv, on="idvisit", how="left")
    else:
        warnings.warn("log_visit fehlt im Dump: Browser/OS nicht verfügbar.")

    # Besuche mit WordPress-Adminleiste = eingeloggte Admins (Tests)
    admin = {r[0] for r in con.execute(
        """SELECT DISTINCT h.idvisit FROM log_hsr_event e JOIN log_hsr h USING (idloghsr)
           JOIN log_action s ON s.idaction = e.idselector WHERE s.name LIKE '%wp-admin-bar%'""")}
    visits["admin_bar"] = visits["idvisit"].isin(admin)

    visits["exclusion"] = _exclusion_reasons(visits, cfg)
    visits["included"] = visits["exclusion"].eq("")
    return visits


def _exclusion_reasons(visits: pd.DataFrame, cfg: StudyConfig) -> pd.Series:
    """Erster zutreffender Ausschlussgrund pro Besuch (leer = eingeschlossen)."""
    reasons = pd.Series("", index=visits.index, dtype="object")

    def mark(mask: pd.Series, text: str) -> None:
        reasons.loc[mask & reasons.eq("")] = text

    manual = _read_exclusions(cfg)
    if manual:
        mark(visits["idvisit"].isin(manual), "manuell ausgeschlossen (exclude_visits.csv)")
    local = visits["start_local"]
    if cfg.field_start:
        mark(local < pd.Timestamp(cfg.field_start), "vor Feldstart")
    else:
        warnings.warn("field_start ist nicht gesetzt: Testdaten vor Feldstart werden nicht ausgeschlossen.")
    for variant, day in cfg.variant_start.items():
        mark(visits["variant"].eq(variant) & (local < pd.Timestamp(day)), f"vor gültigem Start {variant}")
    if cfg.field_end:
        mark(local >= pd.Timestamp(cfg.field_end) + pd.Timedelta(days=1), "nach Feldende")
    if cfg.exclude_admin_bar:
        mark(visits["admin_bar"], "WordPress-Admin eingeloggt (Test)")
    if cfg.device_types:
        mark(~visits["device_type"].isin(cfg.device_types), "Gerät ausgeschlossen")
    mark(visits["variant"].eq("gemischt"), "beide Varianten besucht")
    mark(visits["variant"].eq("unbekannt"), "Variante nicht bestimmbar")
    return reasons


def apply_completion_rules(visits: pd.DataFrame, cfg: StudyConfig) -> pd.DataFrame:
    """Ausschlüsse, die erst nach Berechnung der Kennzahlen möglich sind."""
    v = visits.copy()
    free = v["exclusion"].eq("")
    if cfg.min_total_s > 0:
        m = free & (v["time_total_s"].fillna(0) < cfg.min_total_s)
        v.loc[m, "exclusion"] = f"kürzer als {cfg.min_total_s:g} s"
        free &= ~m
    if cfg.require_form:
        m = free & ~v["reached_form"].fillna(False).astype(bool)
        v.loc[m, "exclusion"] = "Formular nicht erreicht"
    v["included"] = v["exclusion"].eq("")
    return v


def _read_exclusions(cfg: StudyConfig) -> set[int]:
    path = cfg.exclude_path
    if not path.exists():
        return set()
    df = pd.read_csv(path, comment="#")
    if df.empty:
        return set()
    return set(pd.to_numeric(df["idvisit"], errors="coerce").dropna().astype(int))


def sample_flow(visits: pd.DataFrame) -> pd.DataFrame:
    """Stichprobenfluss (wie viele Besuche aus welchem Grund ausgeschlossen)."""
    rows = [("Alle aufgezeichneten Besuche", len(visits))]
    for reason, n in visits.loc[~visits["included"], "exclusion"].value_counts().items():
        rows.append((f"- {reason}", -int(n)))
    rows.append(("Analysestichprobe", int(visits["included"].sum())))
    for var, n in visits.loc[visits["included"], "variant"].value_counts().sort_index().items():
        rows.append((f"  davon {var}", int(n)))
    return pd.DataFrame(rows, columns=["schritt", "besuche"])
