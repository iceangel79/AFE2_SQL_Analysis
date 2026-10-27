import pandas as pd

from afe import clean, features, forms
from afe.questionnaire import score


def _prepare(db, cfg):
    cfg.form_ids = {79: "ML", 118: "OP"}
    cfg.answers = {"a1": ["prättigau", "schiers"], "a2": ["andrin", "flury"], "a3": ["gipfelgold"]}
    pv = clean.load_pageviews(db, cfg)
    ev = clean.load_events(db, pv)
    v = clean.build_visits(db, pv, cfg)
    pvf = features.pageview_features(pv, ev, cfg)
    v = clean.apply_completion_rules(features.visit_features(v, pvf), cfg)
    return v, pvf


def test_email_ip_removed_on_import(db):
    cols = {r[1] for r in db.execute("PRAGMA table_info(wpforms_entries)")}
    assert "ip_address" not in cols and "user_agent" not in cols
    assert db.execute("SELECT COUNT(*) FROM wpforms_entries WHERE fields LIKE '%@%'").fetchone()[0] == 0


def test_parse_and_code(db, cfg):
    _prepare(db, cfg)
    e = forms.code_answers(forms.parse_entries(db, cfg), cfg).set_index("entry_id")
    assert e.loc[1, "geschlecht"] == "männlich"
    assert e.loc[1, "variante"] == "ML" and e.loc[2, "variante"] == "OP"
    assert list(e.loc[1, [f"ueq{i}" for i in range(1, 9)]]) == [5, 5, 4, 4, 3, 3, 2, 2]
    assert list(e.loc[2, ["seq1", "seq2", "seq3"]]) == [2, 2, 3]
    assert list(e.loc[1, ["a1_korrekt", "a2_korrekt", "a3_korrekt"]]) == [1, 1, 1]
    assert list(e.loc[2, ["a1_korrekt", "a2_korrekt", "a3_korrekt"]]) == [0, 1, 1]
    assert "feedback" in e and not any("@" in str(x) for x in e.astype(str).values.ravel())


def test_match_and_exclusions(db, cfg):
    v, pvf = _prepare(db, cfg)
    e = forms.code_answers(forms.parse_entries(db, cfg), cfg)
    e = forms.entry_exclusions(forms.match_entries(e, v, pvf, cfg), v, cfg)
    e = score(e, 1, 5).set_index("entry_id")
    # Eintrag 1 (ML) gehört zu Besuch 10, Eintrag 2 (OP) zu Besuch 11
    assert e.loc[1, "idvisit"] == 10 and e.loc[2, "idvisit"] == 11
    assert e.loc[1, "match_status"] == "automatisch"
    assert e.loc[1, "mouse_included"] and e.loc[2, "mouse_included"]
    # Eintrag 3 vor Feldstart, ohne Besuch
    assert e.loc[3, "entry_exclusion"] == "vor Feldstart"
    assert pd.isna(e.loc[3, "idvisit"])
    assert e.loc[1, "ueqs_pragmatic"] == 1.5
