from pathlib import Path

import pandas as pd
import pytest

from afe import raffle

FIXTURE = Path(__file__).parent / "fixtures" / "mini_dump.sql"


def _cfg(cfg):
    cfg.form_ids = {79: "ML", 118: "OP"}
    return cfg


def test_emails_and_eligibility(cfg):
    df = raffle.read_emails(FIXTURE, _cfg(cfg))
    assert len(df) == 3 and set(df["email"]) == {"test@example.org"}
    people = raffle.eligible(df, cfg)
    # Eintrag vom 20.10. liegt vor Feldstart; zwei Einträge mit gleicher Adresse = eine Person
    assert len(people) == 1 and people.loc[0, "anzahl_eintraege"] == 2


def test_draw_reproducible_and_without_replacement():
    people = pd.DataFrame({"email": [f"p{i}@x.ch" for i in range(10)],
                           "erster_eintrag": pd.Timestamp("2026-11-01"), "variante": "ML"})
    a = raffle.draw(people, 3, seed=42)
    b = raffle.draw(people, 3, seed=42)
    assert list(a["email"]) == list(b["email"]) and a["email"].nunique() == 3
    with pytest.raises(ValueError):
        raffle.draw(people.head(2), 3, seed=1)


def test_no_overwrite(tmp_path, cfg):
    out = tmp_path / "v.xlsx"
    out.write_text("x")
    with pytest.raises(FileExistsError):
        raffle.run(FIXTURE, _cfg(cfg), n=1, out=out)
