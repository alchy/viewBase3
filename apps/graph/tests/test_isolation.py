"""Izolace obsahů — test, který si vyžádal kontrakt (D-43).

Workbench tuhle chybu NEPOZNÁ ani v principu: když apka odpoví na rukojeť A
daty od B, z jeho pohledu odpověděla na to, na co byla dotázána. Proto to
musí doložit apka sama — a POKUSEM O PROLNUTÍ, ne tvrzením, že dva obsahy
jsou různé objekty.
"""
import pytest

from graph_app import ContentRefused, GraphApp

HANA = {"subject_id": "user:hana", "groups": []}
KAREL = {"subject_id": "user:karel", "groups": []}
ADMIN = {"subject_id": "user:workbench", "groups": ["group:administrator"]}


@pytest.fixture
def app():
    return GraphApp()


def test_stejna_id_uzlu_ve_dvou_obsazich_se_neprolnou(app):
    """Nejpravděpodobnější podoba té chyby: klíč je id uzlu, ne dvojice
    (obsah, uzel)."""
    a = app.new_content("user:hana")
    b = app.new_content("user:hana")

    app.content(a, HANA).add_node("srv", name="A")
    app.content(b, HANA).add_node("srv", name="B")
    app.content(a, HANA).add_node("jen-v-a", name="X")

    stav_a = app.snapshot(a, HANA)["state"]
    stav_b = app.snapshot(b, HANA)["state"]
    assert [n["meta"]["name"] for n in stav_a["nodes"] if n["id"] == "srv"] == ["A"]
    assert [n["meta"]["name"] for n in stav_b["nodes"] if n["id"] == "srv"] == ["B"]
    assert {n["id"] for n in stav_b["nodes"]} == {"srv"}      # X se nepřelil


def test_smazani_v_jednom_obsahu_nesahne_do_druheho(app):
    a, b = app.new_content("user:hana"), app.new_content("user:hana")
    for h in (a, b):
        app.content(h, HANA).add_node("srv")
    app.content(a, HANA).remove_node("srv")
    assert app.snapshot(a, HANA)["state"]["nodes"] == []
    assert len(app.snapshot(b, HANA)["state"]["nodes"]) == 1


def test_typy_uzlu_se_neprolnou(app):
    """Typy jsou slovník na obsahu; sdílený by znamenal, že jeden graf
    přebarví druhý."""
    a, b = app.new_content("user:hana"), app.new_content("user:hana")
    app.content(a, HANA).define_type("server", color="#f00")
    with pytest.raises(ValueError):
        app.content(b, HANA).add_node("x", type="server")   # v B typ neexistuje


def test_kurzory_jsou_nezavisle(app):
    """Sdílený čítač by způsobil, že si klient jednoho obsahu vyžádá změny
    a dostane mezeru, kterou nikdo nezpůsobil."""
    a, b = app.new_content("user:hana"), app.new_content("user:hana")
    for _ in range(5):
        app.content(a, HANA).add_node(f"n{_}")
    assert app.content(a, HANA).cursor == 5
    assert app.content(b, HANA).cursor == 0


def test_cizi_obsah_se_neda_otevrit_ani_kdyz_znam_rukojet(app):
    """Rukojeť identifikuje, neopravňuje — i na prezentačním kanálu."""
    cizi = app.new_content("user:hana")
    with pytest.raises(ContentRefused):
        app.open_content(cizi, {}, KAREL)
    with pytest.raises(ContentRefused):
        app.snapshot(cizi, KAREL)
    with pytest.raises(ContentRefused):
        app.content(cizi, KAREL)


def test_spravce_projde_i_k_cizimu(app):
    cizi = app.new_content("user:hana")
    assert app.open_content(cizi, {}, ADMIN)["handle"] == cizi


def test_vypis_ukaze_jen_sve(app):
    app.new_content("user:hana"); app.new_content("user:hana")
    app.new_content("user:karel")
    assert len(app.list_content(HANA)) == 2
    assert len(app.list_content(KAREL)) == 1
    assert len(app.list_content(ADMIN)) == 3
