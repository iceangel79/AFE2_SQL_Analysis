import numpy as np
import pandas as pd

from afe import clean, features
from afe.questionnaire import score


def test_direction_changes_within_element_only():
    x = np.array([100, 300, 100, 300, 500])
    sel = np.array(["a", "a", "a", "a", "b"])
    assert features._direction_changes(x, sel, 20) == 2


def test_direction_changes_ignore_jitter():
    x = np.array([100, 110, 100, 110])
    assert features._direction_changes(x, np.array(["a"] * 4), 20) == 0


def test_sign_reversals():
    assert features._sign_reversals(np.array([0, 100, 300, 200, 200, 400])) == 2


def test_classify_variant():
    df = lambda op, form: pd.DataFrame({"is_op_page": op, "is_form_page": form})
    assert clean.classify_variant(df([True, False], [False, True])) == "OP"
    assert clean.classify_variant(df([False, False], [False, True])) == "ML"
    assert clean.classify_variant(df([True, False], [False, False])) == "gemischt"
    assert clean.classify_variant(df([False], [True])) == "unbekannt"


def test_pipeline_on_fixture(db, cfg):
    pv = clean.load_pageviews(db, cfg)
    ev = clean.load_events(db, pv)
    visits = clean.build_visits(db, pv, cfg)
    vf = features.visit_features(visits, features.pageview_features(pv, ev, cfg))
    vf = clean.apply_completion_rules(vf, cfg).set_index("idvisit")

    assert vf.loc[10, "variant"] == "ML" and vf.loc[10, "included"]
    assert vf.loc[11, "variant"] == "OP"
    assert vf.loc[12, "exclusion"] == "vor Feldstart"
    assert vf.loc[13, "exclusion"] == "Gerät ausgeschlossen"

    # Besuch 10: 10 s auf Startseite + 1.5 s bis zur ersten Formulareingabe
    assert vf.loc[10, "time_to_form_s"] == 11.5
    assert vf.loc[10, "pages_before_form"] == 1
    assert vf.loc[10, "dir_changes"] == 2
    assert vf.loc[10, "n_pauses"] == 1
    # AOI: Ereignisse 5 und 6 auf img, gehalten 200 ms + Rest der Seite (gedeckelt auf 3000)
    assert vf.loc[10, "aoi_bild_dwell_ms"] == 200 + 3000
    assert vf.loc[11, "scroll_reversals"] == 1
    assert vf.loc[11, "time_to_form_s"] == 0.9


def test_ueqs_scoring():
    q = pd.DataFrame({
        "idvisit": [1], **{f"ueq{i}": [5] for i in range(1, 5)}, **{f"ueq{i}": [1] for i in range(5, 9)},
        "seq1": [1], "seq2": [2], "seq3": [3], "a1_korrekt": [1], "a2_korrekt": [1], "a3_korrekt": [0],
    })
    s = score(q, 1, 5).iloc[0]
    assert s["ueqs_pragmatic"] == 2 and s["ueqs_hedonic"] == -2 and s["ueqs_total"] == 0
    assert s["seq_mean"] == 2 and s["task_success"] == 2


def test_questionnaire_validation(tmp_path, cfg):
    import pytest
    from afe.questionnaire import load_questionnaire

    f = tmp_path / "fb.csv"
    f.write_text("idvisit,ueq1,a1_korrekt\n1,6,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ueq1"):
        load_questionnaire(f, cfg)
    f.write_text("idvisit,ueq1,a1_korrekt\n1,5,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="a1_korrekt"):
        load_questionnaire(f, cfg)


def test_variant_specific_start_and_local_time(db, cfg):
    cfg.variant_start = {"ML": "2026-11-03"}
    pv = clean.load_pageviews(db, cfg)
    v = clean.build_visits(db, pv, cfg).set_index("idvisit")
    assert v.loc[10, "exclusion"] == "vor gültigem Start ML"
    assert v.loc[11, "included"]
    # 10:00 UTC = 11:00 Lokalzeit (Winterzeit)
    assert v.loc[10, "start_local"].hour == 11
