"""Schritt 1: SQL-Dump aus phpMyAdmin in eine lokale SQLite-Datenbank laden.

Datenschutz: Es werden nur die Matomo-Tabellen übernommen, die für die
Auswertung nötig sind. Aus log_visit werden nur unkritische Spalten übernommen
(keine IP, keine Besucher-ID, kein Standort). Der Rohdump bleibt in data/raw/.
"""

from __future__ import annotations

import re
import sqlite3
import zlib
from pathlib import Path

from . import sqldump
from .config import DB_PATH, ensure_dirs

# Tabellen (ohne Präfix wie "wp_matomo_") und optional erlaubte Spalten (None = alle)
TABLES: dict[str, list[str] | None] = {
    "log_hsr": None,
    "log_hsr_event": None,
    "log_hsr_blob": None,
    "log_hsr_site": None,
    "site_hsr": [
        "idsitehsr", "idsite", "name", "description", "sample_rate", "sample_limit",
        "match_page_rules", "excluded_elements", "record_type", "breakpoint_mobile",
        "breakpoint_tablet", "min_session_time", "requires_activity", "capture_keystrokes",
        "created_date", "updated_date", "status",
    ],
    "log_action": None,
    "log_visit": [
        "idvisit", "idsite", "visit_first_action_time", "visit_last_action_time",
        "visit_total_time", "visit_total_actions", "visit_total_interactions",
        "visitor_returning", "visitor_count_visits", "visit_entry_idaction_url",
        "visit_exit_idaction_url", "referer_type", "referer_name",
        "location_browser_lang", "config_browser_engine", "config_browser_name",
        "config_browser_version", "config_client_type", "config_device_type",
        "config_device_brand", "config_device_model", "config_os", "config_os_version",
        "config_resolution", "visitor_localtime", "location_country",
    ],
}

_PREFIX_RE = re.compile(r"^(?P<prefix>\w*?matomo_)(?P<name>.+)$")

_SQLITE_TYPES = {
    "int": "INTEGER", "bigint": "INTEGER", "smallint": "INTEGER", "tinyint": "INTEGER",
    "mediumint": "INTEGER", "decimal": "REAL", "float": "REAL", "double": "REAL",
    "blob": "BLOB", "mediumblob": "BLOB", "longblob": "BLOB", "binary": "BLOB", "varbinary": "BLOB",
}


def _strip_prefix(table: str) -> str | None:
    m = _PREFIX_RE.match(table)
    return m.group("name") if m else None


def import_dump(sql_path: str | Path, db_path: Path = DB_PATH, verbose: bool = True) -> dict[str, int]:
    """Liest den Dump und schreibt eine neue SQLite-Datenbank. Gibt Zeilen pro Tabelle zurück."""
    ensure_dirs()
    text = sqldump.read_text(sql_path)
    schemas = sqldump.table_schemas(text)

    # Dump-Tabellennamen (mit Präfix) -> Zielname
    wanted = {t: _strip_prefix(t) for t in schemas if _strip_prefix(t) in TABLES}
    if not wanted:
        raise ValueError("Keine Matomo-Tabellen im Dump gefunden (erwartet z. B. wp_matomo_log_hsr_event).")

    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    counts: dict[str, int] = {}
    try:
        for src, dst in wanted.items():
            allowed = TABLES[dst]
            cols = [(c, t) for c, t in schemas[src] if allowed is None or c in allowed]
            coldefs = ", ".join(f'"{c}" {_SQLITE_TYPES.get(t, "TEXT")}' for c, t in cols)
            con.execute(f'CREATE TABLE "{dst}" ({coldefs})')
            counts[dst] = 0

        for src, cols, rows in sqldump.iter_inserts(text, set(wanted)):
            dst = wanted[src]
            allowed = TABLES[dst]
            idx = [i for i, c in enumerate(cols) if allowed is None or c in allowed]
            names = ", ".join(f'"{cols[i]}"' for i in idx)
            ph = ", ".join("?" for _ in idx)
            con.executemany(f'INSERT INTO "{dst}" ({names}) VALUES ({ph})', ([r[i] for i in idx] for r in rows))
            counts[dst] += len(rows)

        _add_decoded_blobs(con)
        _create_indexes(con)
        con.execute("CREATE TABLE _meta (key TEXT PRIMARY KEY, value TEXT)")
        con.execute("INSERT INTO _meta VALUES ('source_file', ?)", (Path(sql_path).name,))
        con.commit()
    finally:
        con.close()

    missing = [t for t in TABLES if t not in counts]
    if verbose:
        for t, n in counts.items():
            print(f"  {t:<15} {n:>8} Zeilen")
        if missing:
            print(f"  Hinweis: fehlende Tabellen im Dump: {', '.join(missing)}")
    return counts


def _add_decoded_blobs(con: sqlite3.Connection) -> None:
    """Entpackt die zlib-komprimierten Blobs (DOM, CSS, Formularwerte) als Text."""
    if not con.execute("SELECT name FROM sqlite_master WHERE name='log_hsr_blob'").fetchone():
        return
    con.execute("ALTER TABLE log_hsr_blob ADD COLUMN value_text TEXT")
    rows = con.execute("SELECT idhsrblob, compressed, value FROM log_hsr_blob").fetchall()
    out = []
    for idb, comp, val in rows:
        if val is None:
            out.append((None, idb))
            continue
        try:
            raw = zlib.decompress(val) if comp else val
            out.append((raw.decode("utf-8", errors="replace"), idb))
        except zlib.error:
            out.append((None, idb))
    con.executemany("UPDATE log_hsr_blob SET value_text = ? WHERE idhsrblob = ?", out)


def _create_indexes(con: sqlite3.Connection) -> None:
    stmts = [
        "CREATE INDEX IF NOT EXISTS ix_event_hsr ON log_hsr_event(idloghsr, time_since_load)",
        "CREATE INDEX IF NOT EXISTS ix_hsr_visit ON log_hsr(idvisit)",
    ]
    for s in stmts:
        try:
            con.execute(s)
        except sqlite3.OperationalError:
            pass


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    if not Path(db_path).exists():
        raise FileNotFoundError(f"{db_path} fehlt. Zuerst 'afe.bat import <dump.sql>' ausführen.")
    return sqlite3.connect(db_path)
