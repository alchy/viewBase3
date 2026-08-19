"""Izolace obsahů — test, který si vyžádal kontrakt (D-43).

Workbench tuhle chybu NEPOZNÁ ani v principu: když apka odpoví na rukojeť A
daty od B, z jeho pohledu odpověděla na to, na co byla dotázána. Proto to
musí doložit apka sama — a POKUSEM O PROLNUTÍ, ne tvrzením, že dva obsahy
jsou různé objekty.
"""
import pytest

from graph_app import ContentRefused

from conftest import CTENAR, HANA, KAREL, SPRAVCE


def test_stejna_id_uzlu_ve_dvou_obsazich_se_neprolnou(app, zaloz):
    """Nejpravděpodobnější podoba té chyby: klíč je id uzlu, ne dvojice
    (obsah, uzel)."""
    a, b = zaloz(), zaloz()

    app.content(a, HANA).add_node("srv", name="A")
    app.content(b, HANA).add_node("srv", name="B")
    app.content(a, HANA).add_node("jen-v-a", name="X")

    stav_a = app.snapshot(a, HANA)["state"]
    stav_b = app.snapshot(b, HANA)["state"]
    assert [n["meta"]["name"] for n in stav_a["nodes"] if n["id"] == "srv"] == ["A"]
    assert [n["meta"]["name"] for n in stav_b["nodes"] if n["id"] == "srv"] == ["B"]
    assert {n["id"] for n in stav_b["nodes"]} == {"srv"}      # X se nepřelil


def test_smazani_v_jednom_obsahu_nesahne_do_druheho(app, zaloz):
    a, b = zaloz(), zaloz()
    for h in (a, b):
        app.content(h, HANA).add_node("srv")
    app.content(a, HANA).remove_node("srv")
    assert app.snapshot(a, HANA)["state"]["nodes"] == []
    assert len(app.snapshot(b, HANA)["state"]["nodes"]) == 1


def test_typy_uzlu_se_neprolnou(app, zaloz):
    """Typy jsou slovník na obsahu; sdílený by znamenal, že jeden graf
    přebarví druhý."""
    a, b = zaloz(), zaloz()
    app.content(a, HANA).define_type("server", color="#f00")
    with pytest.raises(ValueError):
        app.content(b, HANA).add_node("x", type="server")   # v B typ neexistuje


def test_kurzory_jsou_nezavisle(app, zaloz):
    """Sdílený čítač by způsobil, že si klient jednoho obsahu vyžádá změny
    a dostane mezeru, kterou nikdo nezpůsobil."""
    a, b = zaloz(), zaloz()
    for i in range(5):
        app.content(a, HANA).add_node(f"n{i}")
    assert app.content(a, HANA).cursor == 5
    assert app.content(b, HANA).cursor == 0


def test_rukojet_neopravnuje_na_klientskem_kanalu(app, zaloz):
    """Rukojeť identifikuje, neopravňuje (D-29).

    Na klientském kanálu nemá apka za sebou průnik instance — má jen to,
    co vrátila introspekce tokenu. Kdo z ní vyjde bez `write`, dovnitř
    nesmí, i když rukojeť zná.
    """
    h = zaloz()
    with pytest.raises(ContentRefused):
        app.content(h, CTENAR)                       # jen read
    with pytest.raises(ContentRefused):
        app.content(h, {"subject_id": "user:kdokoli", "capabilities": []})


def test_apka_neautorizuje_podruhe_podle_vlastnictvi(app, zaloz):
    """F-23: dřív se tu rozhodovalo podle vlastníka obsahu.

    Sdílený dokument má číst i ten, kdo ho nezaložil — a jestli na něj má,
    rozhodl průnik okno × obsah v instanci. Kdyby si to apka rozhodovala
    znovu podle vlastnictví, dala by jinou odpověď než ta první.
    """
    h = zaloz(HANA)
    assert app.snapshot(h, KAREL)["state"] == {"nodes": [], "edges": [],
                                               "node_types": {}}
    assert app.open_content(h, KAREL)["handle"] == h


def test_prejmenovat_smi_jen_kdo_ma_manage(app, zaloz):
    """Nevratný zásah do cizí věci (D-50). Apka se ptá na schopnost,
    ne na to, jestli je někdo správce."""
    h = zaloz(HANA)
    with pytest.raises(ContentRefused):
        app.apply_event(h, KAREL, {"event": "rename", "title": "Cizí"})
    zmeny = app.apply_event(h, SPRAVCE, {"event": "rename", "title": "Nové"})
    assert zmeny == [{"kind": "renamed", "title": "Nové"}]


def test_vypis_nefiltruje_a_nese_vlastnika(app, zaloz):
    """Filtruje instance, protože ACL obsahů drží ona (F-23). Apka vrací
    `owner`, aby spouštěč uměl oddělit moje od sdílených."""
    zaloz(HANA); zaloz(HANA); zaloz(KAREL)
    vypis = app.list_content()
    assert len(vypis) == 3
    assert sorted(p["owner"] for p in vypis) == ["user:hana", "user:hana",
                                                 "user:karel"]
