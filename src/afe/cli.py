"""Kommandozeile: afe.bat <befehl>  (bzw. python -m afe <befehl>)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import DATA_RAW, DB_PATH


def _latest_dump() -> Path:
    dumps = sorted(DATA_RAW.glob("*.sql"), key=lambda p: p.stat().st_mtime)
    if not dumps:
        sys.exit(f"Kein SQL-Dump in {DATA_RAW} gefunden. Datei dort ablegen oder Pfad angeben.")
    return dumps[-1]


def cmd_import(a) -> None:
    from .load import import_dump

    path = Path(a.dump) if a.dump else _latest_dump()
    print(f"Importiere {path.name} -> {DB_PATH.relative_to(DB_PATH.parents[2])}")
    import_dump(path)


def cmd_build(a) -> None:
    from .pipeline import build

    ds = build()
    print(ds.flow.to_string(index=False))


def cmd_report(a) -> None:
    from .pipeline import report

    report()


def cmd_all(a) -> None:
    cmd_import(a)
    cmd_report(a)


def cmd_info(a) -> None:
    from .pipeline import build

    ds = build(write=False)
    print(ds.flow.to_string(index=False))
    cols = ["idvisit", "start", "variant", "device", "n_pageviews", "time_total_s", "time_to_form_s", "exclusion"]
    print()
    print(ds.visits[cols].to_string(index=False))


def cmd_forms(a) -> None:
    from .pipeline import build

    ds = build(write=False)
    if ds.entries is None:
        print("Keine Fragebogendaten (weder WPForms-Tabelle im Dump noch data/manual/fragebogen.csv).")
        return
    print(ds.entry_flow.to_string(index=False))
    print()
    cols = ["entry_id", "variante", "submitted_local", "idvisit", "match_status", "match_diff_s",
            "match_candidates", "entry_exclusion", "mouse_included", "task_success"]
    print(ds.entries[cols].to_string(index=False))


def cmd_images(a) -> None:
    from .dom import image_table
    from .load import connect

    con = connect()
    print(image_table(con).to_string(index=False))


def cmd_selectors(a) -> None:
    from .features import selector_summary
    from .pipeline import build

    ds = build(write=False)
    s = selector_summary(ds.events)
    if a.page:
        s = s[s["page"] == a.page]
    print(s.head(a.top).to_string(index=False))


def cmd_strip(a) -> None:
    """Löscht Outputs aller Notebooks (sonst landen Daten im öffentlichen Repo)."""
    import json

    from .config import ROOT

    for nb in (ROOT / "notebooks").glob("*.ipynb"):
        data = json.loads(nb.read_text(encoding="utf-8"))
        changed = False
        for cell in data.get("cells", []):
            if cell.get("cell_type") == "code" and (cell.get("outputs") or cell.get("execution_count")):
                cell["outputs"], cell["execution_count"] = [], None
                changed = True
        if changed:
            nb.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Outputs entfernt: {nb.name}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="afe", description="AFE2 Maus-Tracking-Auswertung")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("import", help="SQL-Dump in lokale Datenbank laden (Standard: neuster Dump in data/raw)")
    s.add_argument("dump", nargs="?")
    s.set_defaults(func=cmd_import)

    sub.add_parser("build", help="Daten bereinigen und Kennzahlen berechnen (CSV in data/processed)").set_defaults(func=cmd_build)
    sub.add_parser("report", help="Bericht, Tabellen und Grafiken erzeugen (output/)").set_defaults(func=cmd_report)

    s = sub.add_parser("all", help="import + build + report")
    s.add_argument("dump", nargs="?")
    s.set_defaults(func=cmd_all)

    sub.add_parser("info", help="Übersicht aller Besuche mit Variante und Ausschlussgrund").set_defaults(func=cmd_info)
    sub.add_parser("fragebogen", help="Formulareinträge mit Zuordnung zum Besuch und Ausschlussgrund").set_defaults(func=cmd_forms)
    sub.add_parser("images", help="Bilder je Seite mit DOM-Position (zur Prüfung der AOI)").set_defaults(func=cmd_images)

    s = sub.add_parser("selectors", help="Meistbenutzte Elemente (CSS-Selektoren) je Seite")
    s.add_argument("--page", help="z. B. startseite, one-pager, kontakt")
    s.add_argument("--top", type=int, default=30)
    s.set_defaults(func=cmd_selectors)

    sub.add_parser("strip", help="Outputs aus allen Notebooks löschen (vor jedem Commit)").set_defaults(func=cmd_strip)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
