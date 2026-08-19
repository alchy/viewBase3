"""Model grafu vyčleněný z viewBase2 — chování, které musí zůstat."""
import pytest

from graph_app.model import GraphContent


@pytest.fixture
def g():
    return GraphContent("vb1_test", "Graph #1", "user:hana")


def test_popisek_ma_poradi_priorit(g):
    """vlastní label > šablona obsahu > id uzlu."""
    g.add_node("a", name="Alfa")
    assert g.snapshot()["state"]["nodes"][0]["label"] == "a"
    g.node_label("{name}")
    assert g.snapshot()["state"]["nodes"][0]["label"] == "Alfa"
    g.add_node("b", label="{name} !", name="Beta")
    labels = {n["id"]: n["label"] for n in g.snapshot()["state"]["nodes"]}
    assert labels == {"a": "Alfa", "b": "Beta !"}


def test_chybejici_klic_v_sablone_nespadne(g):
    g.node_label("{name} [{ip}]")
    g.add_node("a", name="Alfa")
    assert g.snapshot()["state"]["nodes"][0]["label"] == "Alfa []"


def test_neznamy_typ_se_odmitne(g):
    with pytest.raises(ValueError):
        g.add_node("a", type="server")
    g.define_type("server", color="#f00")
    g.add_node("a", type="server")


def test_dvakrat_tyz_uzel_je_chyba_ale_ensure_je_idempotentni(g):
    g.add_node("a", name="Alfa")
    with pytest.raises(ValueError):
        g.add_node("a")
    g.ensure_node("a", name="Alfa")              # beze změny
    assert g.cursor == 1
    g.ensure_node("a", role="db")                # sloučí meta
    assert g.cursor == 2


def test_smazani_uzlu_vezme_i_jeho_hrany(g):
    g.add_node("a"); g.add_node("b"); g.add_edge("a", "b")
    g.remove_node("a")
    assert g.snapshot()["state"]["edges"] == []


def test_hrana_potrebuje_oba_konce(g):
    g.add_node("a")
    with pytest.raises(ValueError):
        g.add_edge("a", "neexistuje")


def test_mazani_je_idempotentni(g):
    g.remove_node("neni")                        # no-op, ne výjimka
    g.remove_edge("a", "b")
    assert g.cursor == 0
