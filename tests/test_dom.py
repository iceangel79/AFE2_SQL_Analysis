from afe.dom import DomIndex, image_for_node, normalize_image


def _el(tag, attrs=None, kids=None):
    return {"nodeType": 1, "tagName": tag, "attributes": attrs or {}, "childNodes": kids or []}


DOM = {"children": [_el("HTML", kids=[_el("BODY", kids=[
    _el("ARTICLE", {"id": "post-1"}, [
        _el("DIV", {"class": "row"}, [_el("FIGURE", kids=[_el("A", kids=[_el("IMG", {"src": "/u/Titel-Bild-300x167.jpg"})])])]),
        _el("DIV", {"class": "row special"}, [_el("FIGURE", kids=[_el("A", kids=[_el("IMG", {"src": "/u/Portrait-X-242x300.jpg"})])])]),
    ]),
])])]}


def test_normalize_image():
    assert normalize_image("https://x.ch/a/Portrait-Mira-Caduff-242x300.jpg?ver=2") == "Portrait-Mira-Caduff"
    assert normalize_image("Podest-Mira-Caduff.jpg") == "Podest-Mira-Caduff"


def test_select_nth_child_and_class():
    idx = DomIndex(DOM)
    n = idx.select("article#post-1 > div:nth-child(2) > figure > a > img")
    assert len(n) == 1 and image_for_node(n[0]) == "Portrait-X"
    n = idx.select("article#post-1 > div.special > figure")
    assert len(n) == 1 and image_for_node(n[0]) == "Portrait-X"
    # Element mit zwei Bildern darunter ist nicht eindeutig
    assert image_for_node(idx.select("article#post-1")[0]) is None


def test_holm():
    import pandas as pd
    from afe.stats import holm

    p = pd.Series([0.01, 0.04, None, 0.03])
    adj = holm(p)
    assert round(adj[0], 3) == 0.03 and round(adj[3], 3) == 0.06 and round(adj[1], 3) == 0.06
    assert pd.isna(adj[2])


def test_click_category():
    from afe.dom import click_category

    link_img = {"tagName": "A", "attributes": {"href": "/u/Strand-1024x687.jpg"}, "_parent": None}
    img = {"tagName": "IMG", "attributes": {}, "_parent": link_img}
    nav = {"tagName": "A", "attributes": {"href": "/training/"}, "_parent": None}
    span = {"tagName": "SPAN", "attributes": {}, "_parent": nav}
    text = {"tagName": "P", "attributes": {}, "_parent": None}
    assert click_category("x > img", img) == "bild"
    assert click_category("li#menu-item-40 > a > span", span) == "navigation"
    assert click_category("article > p", text) == "sonstiges"
    assert click_category("input#wpforms-79-field_4", None) == "formular"
    assert click_category("div#lightbox > div.lb-dataContainer", None) == "lightbox"
    assert click_category("li#menu-item-41 > a", None) == "navigation"


def test_risk_difference_and_fisher_zero_cell():
    import pandas as pd
    from afe.stats import fisher, risk_difference

    d, lo, hi = risk_difference(5, 10, 0, 10)
    assert d == 0.5 and lo < 0.5 < hi and 0 < lo
    df = pd.DataFrame({"g": ["a"] * 10 + ["b"] * 10, "f": [True] * 5 + [False] * 5 + [False] * 10})
    r = fisher(df, "f", "g", "t", "a", "b")
    assert r["hoeher_in"] == "a" and r["effekt"] == 0.5
    assert 0 < r["odds_ratio_haldane"] < float("inf")


def test_logistic_reports_separation():
    import pandas as pd
    from afe.stats import logistic_with_covariate

    df = pd.DataFrame({"f": [True, False] * 6 + [False] * 8,
                       "geschlecht": ["weiblich", "männlich"] * 10,
                       "variant": ["ML"] * 12 + ["OP"] * 8})
    r = logistic_with_covariate(df, "f", "geschlecht", "weiblich", "variant", "OP", "t")
    assert "perfekte Trennung" in r["hinweis"]
