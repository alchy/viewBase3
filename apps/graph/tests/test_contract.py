"""Kontrakt vůči instanci: co apka slíbila v apka-kontrakt.md."""
import pytest

from graph_app import ContentRefused

from conftest import HANA, KAREL


def test_zakladani_pojmenovava(app, zaloz):
    prvni, druhy = zaloz(), zaloz()
    assert app.snapshot(prvni, HANA)["title"] == "Graph #1"
    assert app.snapshot(druhy, HANA)["title"] == "Graph #2"


def test_cislovani_jmen_je_na_vlastnika(app, zaloz):
    """„Graph #1" má každý svoje – jinak by jméno prozradilo, kolik grafů
    má někdo jiný."""
    a, b = zaloz(HANA), zaloz(KAREL)
    assert app.snapshot(a, HANA)["title"] == app.snapshot(b, KAREL)["title"] == "Graph #1"


def test_rukojet_razi_instance_apka_ji_jen_dostane(app):
    """D-29: apka si rukojeť nerazí. Nemá k tomu ani metodu — `create_content`
    ji vyžaduje jako argument."""
    import inspect
    parametry = list(inspect.signature(app.create_content).parameters)
    assert parametry[0] == "handle"
    assert not [j for j in dir(app) if j.startswith("new_")]


def test_neznama_rukojet_se_odmitne_a_NEZALOZI(app):
    with pytest.raises(ContentRefused):
        app.open_content("vb1_neexistuje", HANA)
    assert app.list_content() == []              # nic tiše nevzniklo


def test_zalozit_na_obsazenou_rukojet_se_odmitne(app, zaloz):
    """Kdyby se sem dalo připojit, byl by z 'založ' a 'otevři' jeden příkaz
    a překlep by tiše otevřel cizí graf."""
    h = zaloz()
    with pytest.raises(ContentRefused):
        app.create_content(h, {}, HANA)


def test_snapshot_nese_stav_i_kurzor(app, zaloz):
    h = zaloz()
    app.content(h, HANA).add_node("a")
    snap = app.snapshot(h, HANA)
    assert set(snap) >= {"state", "cursor", "title"}
    assert snap["cursor"] == 1 and len(snap["state"]["nodes"]) == 1


def test_zmeny_od_kurzoru_navazuji_na_snapshot(app, zaloz):
    h = zaloz()
    g = app.content(h, HANA)
    g.add_node("a")
    snap = app.snapshot(h, HANA)
    g.add_node("b")
    g.add_edge("a", "b")
    zmeny = g.changes_since(snap["cursor"])
    assert [c.kind for c in zmeny] == ["add_node", "add_edge"]


def test_prilis_pozdni_kurzor_da_None_misto_tiche_mezery(app, zaloz):
    """Vracet 'co ještě mám' by změny tiše přeskočilo. Přiznaná mezera je
    lepší než nepřiznaná."""
    from graph_app.model import HISTORY

    h = zaloz()
    g = app.content(h, HANA)
    for i in range(HISTORY + 10):
        g.add_node(f"n{i}")
    assert g.changes_since(0) is None
    assert g.changes_since(g.cursor) == []


def test_zavreni_obsahu_ho_odstrani(app, zaloz):
    h = zaloz()
    app.close_content(h)
    with pytest.raises(ContentRefused):
        app.snapshot(h, HANA)
