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
