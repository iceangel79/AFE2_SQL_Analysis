"""Parser für phpMyAdmin-SQL-Dumps (MySQL/MariaDB).

Liest die INSERT-Anweisungen eines Dumps direkt in Python ein, ohne dass ein
MySQL-Server installiert werden muss. Unterstützt werden die Werteformate, die
phpMyAdmin erzeugt: Zahlen, 'Strings' mit Backslash-Escapes, 0x-Hex-Blobs und NULL.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

# Kopf einer INSERT-Anweisung: INSERT INTO `tabelle` (`a`, `b`) VALUES
_INSERT_RE = re.compile(
    r"INSERT INTO `(?P<table>[^`]+)`\s*\((?P<cols>[^)]*)\)\s*VALUES\s*", re.S
)
_CREATE_RE = re.compile(r"CREATE TABLE `(?P<table>[^`]+)`\s*\((?P<body>.*?)\n\)", re.S)
_COLDEF_RE = re.compile(r"^\s*`(?P<name>[^`]+)`\s+(?P<type>[a-zA-Z]+)", re.M)

# Ein einzelner Wert innerhalb eines Tupels
_VALUE_RE = re.compile(
    r"""\s*(?:
        '(?P<str>(?:[^'\\]|\\.)*)'          # String mit Escapes
      | 0x(?P<hex>[0-9A-Fa-f]*)                 # Hex-Blob
      | (?P<null>NULL)
      | (?P<num>-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)
    )\s*""",
    re.X | re.S,
)

_ESCAPES = {
    "0": "\0", "b": "\b", "n": "\n", "r": "\r", "t": "\t", "Z": "\x1a",
    "\\": "\\", "'": "'", '"': '"', "%": "\\%", "_": "\\_",
}
_ESC_RE = re.compile(r"\\(.)", re.S)


def _unescape(s: str) -> str:
    if "\\" not in s:
        return s
    return _ESC_RE.sub(lambda m: _ESCAPES.get(m.group(1), m.group(1)), s)


def _convert(m: re.Match) -> object:
    if m.group("str") is not None:
        return _unescape(m.group("str"))
    if m.group("hex") is not None:
        return bytes.fromhex(m.group("hex"))
    if m.group("null") is not None:
        return None
    num = m.group("num")
    if "." in num or "e" in num or "E" in num:
        return float(num)
    return int(num)


def read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def table_schemas(text: str) -> dict[str, list[tuple[str, str]]]:
    """Spaltennamen und MySQL-Typen aus den CREATE-TABLE-Anweisungen."""
    out: dict[str, list[tuple[str, str]]] = {}
    for m in _CREATE_RE.finditer(text):
        out[m.group("table")] = [(c.group("name"), c.group("type").lower()) for c in _COLDEF_RE.finditer(m.group("body"))]
    return out


def iter_inserts(text: str, tables: set[str] | None = None) -> Iterator[tuple[str, list[str], list[tuple]]]:
    """Liefert pro INSERT-Anweisung (Tabelle, Spalten, Zeilen).

    tables: nur diese Tabellen auslesen (andere werden übersprungen, ohne ihre
    Werte zu parsen). None = alle.
    """
    pos = 0
    while True:
        m = _INSERT_RE.search(text, pos)
        if not m:
            return
        table = m.group("table")
        cols = [c.strip().strip("`") for c in m.group("cols").split(",")]
        pos = m.end()
        if tables is not None and table not in tables:
            pos = _skip_statement(text, pos)
            continue
        rows, pos = _parse_values(text, pos, len(cols))
        yield table, cols, rows


def _skip_statement(text: str, pos: int) -> int:
    """Springt ans Ende der Anweisung (';' ausserhalb von Strings)."""
    in_str = False
    i = pos
    n = len(text)
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == "'":
                in_str = False
        elif c == "'":
            in_str = True
        elif c == ";":
            return i + 1
        i += 1
    return n


def _parse_values(text: str, pos: int, ncols: int) -> tuple[list[tuple], int]:
    rows: list[tuple] = []
    n = len(text)
    while pos < n:
        # Tupelanfang
        while pos < n and text[pos] in " \t\r\n":
            pos += 1
        if text[pos] != "(":
            raise ValueError(f"Erwartet '(' an Position {pos}: {text[pos:pos + 40]!r}")
        pos += 1
        row = []
        while True:
            m = _VALUE_RE.match(text, pos)
            if not m:
                raise ValueError(f"Unbekannter Wert an Position {pos}: {text[pos:pos + 40]!r}")
            row.append(_convert(m))
            pos = m.end()
            c = text[pos]
            pos += 1
            if c == ",":
                continue
            if c == ")":
                break
            raise ValueError(f"Unerwartetes Zeichen {c!r} an Position {pos - 1}")
        if len(row) != ncols:
            raise ValueError(f"Zeile mit {len(row)} statt {ncols} Werten bei Position {pos}")
        rows.append(tuple(row))
        while pos < n and text[pos] in " \t\r\n":
            pos += 1
        c = text[pos]
        pos += 1
        if c == ",":
            continue
        if c == ";":
            return rows, pos
        raise ValueError(f"Unerwartetes Zeichen {c!r} nach Tupel an Position {pos - 1}")
    return rows, pos
