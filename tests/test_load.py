def test_only_matomo_tables_imported(db):
    names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "users" not in names and "wp_users" not in names
    assert {"log_hsr", "log_hsr_event", "log_action", "log_visit"} <= names


def test_sensitive_visit_columns_dropped(db):
    cols = {r[1] for r in db.execute("PRAGMA table_info(log_visit)")}
    assert "location_ip" not in cols
    assert "idvisitor" not in cols
    assert "location_city" not in cols
    assert "config_browser_name" in cols


def test_blob_decoded(db):
    assert db.execute("SELECT value_text FROM log_hsr_blob").fetchone()[0] == "1"
