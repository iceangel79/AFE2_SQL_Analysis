import sqlite3
from pathlib import Path

import pytest

from afe.config import StudyConfig, AoiRule
from afe.load import import_dump

FIXTURE = Path(__file__).parent / "fixtures" / "mini_dump.sql"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "test.sqlite"
    import_dump(FIXTURE, path, verbose=False)
    con = sqlite3.connect(path)
    yield con
    con.close()


@pytest.fixture
def cfg(tmp_path):
    return StudyConfig(
        field_start="2026-11-01",
        exclude_visits_file=str(tmp_path / "none.csv"),
        device_types=[1],
        op_url_contains="one-pager",
        form_url_contains="kontakt",
        direction_min_delta=20,
        pause_ms=1000,
        dwell_cap_ms=3000,
        aoi=[AoiRule(name="bild", url_regex=r"example\.ch/$", selector_regex=r"img$")],
    )
