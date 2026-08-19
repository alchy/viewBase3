"""Kontrakt vůči instanci: co apka slíbila v apka-kontrakt.md."""
import pytest

from graph_app import ContentRefused, GraphApp

HANA = {"subject_id": "user:hana", "capabilities": ["read", "write"]}


@pytest.fixture
def app():
    return GraphApp()


def test_bez_rukojeti_zaklada_a_pojmenovava(app):
    prvni = app.open_content(None, {}, HANA)
    druhy = app.open_content(None, {}, HANA)
    assert prvni["name"] == "Graph #1" and druhy["name"] == "Graph #2"
    assert prvni["handle"] != druhy["handle"]


def test_cislovani_jmen_je_na_vlastnika(app):
    """„Graph #1" má každý svoje – jinak by jméno prozradilo, kolik grafů
    má někdo jiný."""
    a = app.open_content(None, {}, HANA)["name"]
    b = app.open_content(None, {}, {"subject_id": "user:karel", "capabilities": ["read", "write"]})["name"]
    assert a == b == "Graph #1"


def test_neznama_rukojet_se_odmitne_a_NEZALOZI(app):
    with pytest.raises(ContentRefused):
        app.open_content("vb1_neexistuje", {}, HANA)
    assert app.list_content(HANA) == []          # nic tiše nevzniklo


def test_snapshot_nese_stav_i_kurzor(app):
    h = app.new_content("user:hana")
    app.content(h, HANA).add_node("a")
    snap = app.snapshot(h, HANA)
    assert set(snap) >= {"state", "cursor", "name"}
    assert snap["cursor"] == 1 and len(snap["state"]["nodes"]) == 1


def test_zmeny_od_kurzoru_navazuji_na_snapshot(app):
    h = app.new_content("user:hana")
    g = app.content(h, HANA)
    g.add_node("a")
    snap = app.snapshot(h, HANA)
    g.add_node("b")
    g.add_edge("a", "b")
    zmeny = g.changes_since(snap["cursor"])
    assert [c.kind for c in zmeny] == ["add_node", "add_edge"]


def test_prilis_pozdni_kurzor_da_None_misto_tiche_mezery(app):
    """Vracet 'co ještě mám' by změny tiše přeskočilo. Přiznaná mezera je
    lepší než nepřiznaná."""
    from graph_app.model import HISTORY

    h = app.new_content("user:hana")
    g = app.content(h, HANA)
    for i in range(HISTORY + 10):
        g.add_node(f"n{i}")
    assert g.changes_since(0) is None
    assert g.changes_since(g.cursor) == []


def test_zavreni_obsahu_ho_odstrani(app):
    h = app.new_content("user:hana")
    app.close_content(h)
    with pytest.raises(ContentRefused):
        app.snapshot(h, HANA)
