from pathlib import Path

from afe import sqldump

FIXTURE = Path(__file__).parent / "fixtures" / "mini_dump.sql"


def test_values_and_escapes():
    text = sqldump.read_text(FIXTURE)
    tables = {t: rows for t, _, rows in sqldump.iter_inserts(text)}
    actions = {r[0]: r for r in tables["wp_matomo_log_action"]}
    assert actions[6][1] == 'It\'s a "test"\n'
    assert actions[4][4] is None
    blob = tables["wp_matomo_log_hsr_blob"][0]
    assert isinstance(blob[3], bytes)


def test_semicolon_inside_string_does_not_break_parsing():
    text = sqldump.read_text(FIXTURE)
    tables = {t: rows for t, _, rows in sqldump.iter_inserts(text)}
    assert tables["wp_users"][0][1] == "$P$geheim;mit;semikolon"


def test_table_filter_skips_other_tables():
    text = sqldump.read_text(FIXTURE)
    names = {t for t, _, _ in sqldump.iter_inserts(text, {"wp_matomo_log_hsr"})}
    assert names == {"wp_matomo_log_hsr"}


def test_schemas():
    schemas = sqldump.table_schemas(sqldump.read_text(FIXTURE))
    assert ("time_on_page", "bigint") in schemas["wp_matomo_log_hsr"]


def test_binary_blob_as_escaped_string(tmp_path):
    """phpMyAdmin ohne Hex-Option: Blob als String mit rohen Bytes und MySQL-Escapes."""
    import sqlite3
    import zlib

    from afe.load import import_dump

    payload = zlib.compress('{"a": "Prättigau"}'.encode())
    esc = (payload.replace(b"\\", b"\\\\").replace(b"'", b"\\'").replace(b'"', b'\\"')
           .replace(b"\0", b"\\0").replace(b"\n", b"\\n").replace(b"\r", b"\\r").replace(b"\x1a", b"\\Z"))
    sql = (b"CREATE TABLE `wp_matomo_log_hsr_blob` (\n  `idhsrblob` int NOT NULL,\n  `hash` int NOT NULL,\n"
           b"  `compressed` tinyint NOT NULL,\n  `value` mediumblob\n) ENGINE=InnoDB;\n\n"
           b"INSERT INTO `wp_matomo_log_hsr_blob` (`idhsrblob`, `hash`, `compressed`, `value`) VALUES\n"
           b"(1, 1, 1, '" + esc + b"'),\n(2, 2, 0, 'Pr\xc3\xa4ttigau');\n")
    dump = tmp_path / "bin.sql"
    dump.write_bytes(sql)
    db = tmp_path / "t.sqlite"
    import_dump(dump, db, verbose=False)
    con = sqlite3.connect(db)
    rows = dict(con.execute("SELECT idhsrblob, value_text FROM log_hsr_blob"))
    assert rows[1] == '{"a": "Prättigau"}'
    assert rows[2] == "Prättigau"
