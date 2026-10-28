"""Hilfsfunktionen für die DOM-Snapshots, die Matomo pro Seitenaufruf speichert.

Damit lässt sich prüfen, welches Bild an welcher Stelle im DOM steht, z. B. um
die CSS-Selektoren der AOI (Porträt) in config/study.toml zu verifizieren.
"""

from __future__ import annotations

import json
import re
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
                found.append({"file": attrs.get("src", "").rsplit("/", 1)[-1],
                              "image": normalize_image(attrs.get("src", "")), "dom_path": " > ".join(p)})
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
            rows.append({"url": u, "image": img["image"], "dom_path": p[k:] if k >= 0 else p})
    return pd.DataFrame(rows)


# --- CSS-Selektoren aus Matomo im DOM-Snapshot auflösen -------------------------------
# Matomo-Selektoren bestehen nur aus Kind-Kombinatoren (" > ") und Schritten der Form
# tag#id.klasse1.klasse2:nth-child(n). Das reicht für einen kleinen eigenen Matcher.

_STEP_RE = re.compile(
    r"^(?P<tag>[a-zA-Z0-9]+)?(?P<id>#[^.:\s]+)?(?P<classes>(?:\.[^.:\s]+)*)(?::nth-child\((?P<nth>\d+)\))?$"
)
_SIZE_RE = re.compile(r"-\d+x\d+(?=\.\w+$)")


def parse_selector(selector: str) -> list[dict] | None:
    steps = []
    for part in selector.split(" > "):
        m = _STEP_RE.match(part.strip())
        if not m:
            return None
        steps.append({
            "tag": (m.group("tag") or "").upper(),
            "id": (m.group("id") or "")[1:],
            "classes": [c for c in (m.group("classes") or "").split(".") if c],
            "nth": int(m.group("nth")) if m.group("nth") else None,
        })
    return steps


class DomIndex:
    """Elementbaum eines DOM-Snapshots mit Eltern-Verweisen und Position unter Geschwistern."""

    def __init__(self, dom: dict):
        self.nodes: list[dict] = []
        for top in dom.get("children", []):
            if top.get("nodeType") == 1:
                self._add(top, None, 1)

    def _add(self, node: dict, parent: dict | None, pos: int) -> None:
        node["_parent"], node["_pos"] = parent, pos
        self.nodes.append(node)
        kids = [c for c in node.get("childNodes", []) if c.get("nodeType") == 1]
        node["_kids"] = kids
        for i, c in enumerate(kids, 1):
            self._add(c, node, i)

    @staticmethod
    def _match(node: dict, step: dict) -> bool:
        attrs = node.get("attributes", {})
        if step["tag"] and node.get("tagName") != step["tag"]:
            return False
        if step["id"] and attrs.get("id") != step["id"]:
            return False
        if step["classes"] and not set(step["classes"]) <= set(attrs.get("class", "").split()):
            return False
        if step["nth"] is not None and node["_pos"] != step["nth"]:
            return False
        return True

    def select(self, selector: str) -> list[dict]:
        steps = parse_selector(selector)
        if not steps:
            return []
        current = [n for n in self.nodes if self._match(n, steps[0])]
        for step in steps[1:]:
            current = [k for n in current for k in n["_kids"] if self._match(k, step)]
        return current


def normalize_image(src: str) -> str:
    """Dateiname ohne Pfad, Grössenangabe (-300x167) und Endung: 'Portrait-Mira-Caduff'."""
    name = src.split("?", 1)[0].rsplit("/", 1)[-1]
    name = _SIZE_RE.sub("", name)
    return name.rsplit(".", 1)[0]


def _descendant_images(node: dict) -> list[dict]:
    out = []
    stack = list(node["_kids"])
    while stack:
        n = stack.pop()
        if n.get("tagName") == "IMG":
            out.append(n)
        stack.extend(n["_kids"])
    return out


def image_for_node(node: dict) -> str | None:
    """Bild unter dem Element: das IMG selbst, ein einziges IMG darin (figure, a) oder None."""
    if node.get("tagName") == "IMG":
        imgs = [node]
    else:
        imgs = _descendant_images(node)
    raw = [i.get("attributes", {}).get("src", "") for i in imgs]
    srcs = {normalize_image(r) for r in raw if r and not r.startswith("data:")}
    return srcs.pop() if len(srcs) == 1 else None


def selector_image_map(con: sqlite3.Connection) -> pd.DataFrame:
    """Für jede Seite und jeden benutzten Selektor: welches Bild liegt darunter?"""
    used = pd.read_sql(
        """
        SELECT DISTINCT a.name AS url, s.name AS selector
        FROM log_hsr_event e
        JOIN log_hsr h USING (idloghsr)
        JOIN log_action a ON a.idaction = h.idaction_url
        JOIN log_action s ON s.idaction = e.idselector
        WHERE e.event_type IN (1, 2)
        """,
        con,
    )
    rows = []
    for url, g in used.groupby("url"):
        dom = initial_dom(con, url)
        if not dom:
            continue
        idx = DomIndex(dom)
        for sel in g["selector"]:
            nodes = idx.select(sel)
            node = nodes[0] if len(nodes) == 1 else None
            img = image_for_node(node) if node is not None else None
            rows.append({"url": url, "selector": sel, "image": img, "click_cat": click_category(sel, node)})
    out = pd.DataFrame(rows, columns=["url", "selector", "image", "click_cat"])
    return out


_IMAGE_HREF = re.compile(r"\.(?:jpe?g|png|gif|webp)(?:\?.*)?$", re.I)
CLICK_CATEGORIES = ("navigation", "bild", "lightbox", "formular", "sonstiges")


def click_category(selector: str, node: dict | None) -> str:
    """Art des angeklickten Elements.

    - lightbox:   Elemente der geöffneten Vergrösserung (Schliessen, Blättern, Overlay)
    - bild:       Bild bzw. Link auf eine Bilddatei (öffnet die Vergrösserung)
    - navigation: Menüpunkte und alle übrigen Links (Seitenwechsel, Anker)
    - formular:   Felder und Knöpfe des Fragebogens
    - sonstiges:  Klicks auf Text, Flächen usw.
    Die Lightbox wird erst beim Öffnen erzeugt und fehlt im ersten DOM-Snapshot; sie wird
    daher über den Selektor erkannt. Gleiches gilt als Rückfall, wenn der Selektor im
    Snapshot nicht eindeutig auflösbar ist.
    """
    sel = selector or ""
    if sel.startswith(("div#lightbox", "div#lightboxOverlay")):
        return "lightbox"
    if "wpforms" in sel:
        return "formular"
    if node is None:
        if "menu-item" in sel or sel.startswith(("nav", "ul#ast-hf")):
            return "navigation"
        return "bild" if sel.endswith("img") else "sonstiges"
    n = node
    while n is not None:
        tag = n.get("tagName")
        if tag in ("FORM", "INPUT", "BUTTON", "SELECT", "TEXTAREA", "LABEL"):
            return "formular"
        if tag == "A":
            href = n.get("attributes", {}).get("href", "")
            return "bild" if _IMAGE_HREF.search(href) else "navigation"
        n = n.get("_parent")
    return "bild" if node.get("tagName") == "IMG" else "sonstiges"


def page_images(con: sqlite3.Connection, content_regex: str = "") -> dict[str, set[str]]:
    """Welche Inhaltsbilder stehen auf welcher Seite (URL)?"""
    rx = re.compile(content_regex) if content_regex else None
    out: dict[str, set[str]] = {}
    for (url,) in con.execute(
        "SELECT DISTINCT a.name FROM log_hsr h JOIN log_action a ON a.idaction = h.idaction_url"
    ):
        dom = initial_dom(con, url)
        if dom:
            out[url] = {i["image"] for i in images(dom) if rx is None or rx.search(i["image"])}
    return out
