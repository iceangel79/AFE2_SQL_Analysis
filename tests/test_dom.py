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
