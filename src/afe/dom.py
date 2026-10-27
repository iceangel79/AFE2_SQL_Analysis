"""Hilfsfunktionen für die DOM-Snapshots, die Matomo pro Seitenaufruf speichert.

Damit lässt sich prüfen, welches Bild an welcher Stelle im DOM steht, z. B. um
die CSS-Selektoren der AOI (Porträt) in config/study.toml zu verifizieren.
"""

from __future__ import annotations

import json
import sqlite3

import pandas as pd


def initial_dom(con: sqlite3.Connection, url: str, device_type: int = 1) -> dict | None:
    row = con.execute(
        """
        SELECT b.value_text FROM log_hsr_event e
        JOIN log_hsr h USING (idloghsr)
        JOIN log_action a ON a.idaction = h.idaction_url
        JOIN log_hsr_blob b ON b.idhsrblob = e.idhsrblob
        WHERE e.event_type = 5 AND a.name = ? AND h.device_type = ?
        ORDER BY h.server_time DESC LIMIT 1
        """,
        (url, device_type),
    ).fetchone()
    return json.loads(row[0]) if row and row[0] else None


def images(dom: dict) -> list[dict]:
    """Alle <img> mit Dateiname und DOM-Pfad (Position als nth-child, wie in Matomo-Selektoren)."""
    found: list[dict] = []

    def walk(node: dict, path: list[str]) -> None:
        kids = [c for c in node.get("childNodes", []) if c.get("nodeType") == 1]
        for i, c in enumerate(kids, 1):
            attrs = c.get("attributes", {})
            step = c["tagName"].lower()
            if "id" in attrs:
                step += f"#{attrs['id']}"
            step += f":nth-child({i})"
            p = path + [step]
            if c["tagName"] == "IMG" and not attrs.get("src", "").startswith("data:"):
                found.append({"file": attrs.get("src", "").rsplit("/", 1)[-1], "dom_path": " > ".join(p)})
            walk(c, p)

    for top in dom.get("children", []):
        if top.get("nodeType") == 1:
            walk({"childNodes": [top]}, [])
    return found


def image_table(con: sqlite3.Connection) -> pd.DataFrame:
    urls = [r[0] for r in con.execute(
        "SELECT DISTINCT a.name FROM log_hsr h JOIN log_action a ON a.idaction = h.idaction_url"
    )]
    rows = []
    for u in sorted(urls):
        dom = initial_dom(con, u)
        if not dom:
            continue
        for img in images(dom):
            p = img["dom_path"]
            k = p.find("article")
            rows.append({"url": u, "file": img["file"], "dom_path": p[k:] if k >= 0 else p})
    return pd.DataFrame(rows)
