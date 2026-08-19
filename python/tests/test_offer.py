"""Nabidka misto otevirani okna (D-53, D-54, D-58, D-59).

    nabidka  (deklaruje vyvojar)   prezije vsechno
       | kliknuti
    okno     (pohled)              vznika a zanika
       |
    obsah    (stav u apky)         zije podle scope

Pri startu NEEXISTUJE ZADNE OKNO. Vyvojar deklaruje jen to, co jde otevrit
kde; okna vznikaji tim, ze si je divak otevre. Workbench je prostredi, ne
scenar.

Dve pravidla drzi tvar:

  * CO JE V MANIFESTU, SE V KODU NEPISE ZNOVU - register(GraphApp()) si
    app_id, kind i scope vezme odtamtud, jinak se to da rozejit,
  * OBJEKTY MISTO RETEZCU - register(graf, content=mapa), ne app_id
    a rukojet. Retezce patri do konfigurace a na drat, ne do volani.
"""
import pytest

import viewbase as vb
from viewbase.core.identity import USERS, Caller


class GraphApp:
    """Falesna apka. Manifest je jeji vec - workbench si ho precte."""

    manifest = {"app_id": "workbench.graph", "kind": "graph", "scope": "window"}

    def open_content(self, handle, spec, subject):
        return {"handle": handle, "state": {}, "cursor": 1}

    def snapshot(self, handle, subject):
        return {"state": {}, "cursor": 1}

    def apply_event(self, handle, subject, event):
        return []

    def close_content(self, handle):
        pass


class SharedApp(GraphApp):
    manifest = {"app_id": "workbench.mapa", "kind": "graph", "scope": "app"}


HANA = Caller.for_user("hana")


def prepared():
    instance = vb.Instance(default_access=[USERS])
    graf = instance.app.register(GraphApp())
    provoz = instance.screen.open(title="Provoz", id="provoz")
    return instance, graf, provoz


# ===========================================================================
# Manifest se neopakuje (D-53)
# ===========================================================================


def test_the_app_is_registered_from_its_manifest():
    instance = vb.Instance()
    graf = instance.app.register(GraphApp())
    assert graf.app_id == "workbench.graph"
    assert graf.kind == "graph"
    assert graf.scope == "window"


def test_an_app_without_a_manifest_is_refused():
    # Chybejici manifest neni vychozi hodnota, ale chyba registrace.
    class Bezejmenna:
        pass

    with pytest.raises(ValueError, match="manifest"):
        vb.Instance().app.register(Bezejmenna())


def test_a_manifest_without_an_app_id_is_refused():
    class Nedodelana:
        manifest = {"kind": "graph"}

    with pytest.raises(ValueError, match="app_id"):
        vb.Instance().app.register(Nedodelana())


def test_a_manifest_naming_an_unknown_kind_is_refused():
    class Vymyslena:
        manifest = {"app_id": "x", "kind": "neexistuje", "scope": "window"}

    with pytest.raises(ValueError, match="kind"):
        vb.Instance().app.register(Vymyslena())


# ===========================================================================
# Sest radku: merítko, jestli je API jednoduche (D-53)
# ===========================================================================


def test_the_documented_six_line_script_runs():
    # architektura-navrh.md, dodatek - doslova, jen bez serve().
    inst = vb.Instance(default_access=["group:users"])
    graf = inst.app.register(GraphApp())
    provoz = inst.screen.open(title="Provoz")
    provoz.app.register(graf, title="Sit")

    assert provoz.window.all() == ()  # pri startu neexistuje zadne okno


def test_no_window_exists_before_a_viewer_opens_one():
    _, graf, provoz = prepared()
    provoz.app.register(graf, title="Sit")
    assert len(provoz.window) == 0


def test_the_offer_is_listed_on_the_screen():
    _, graf, provoz = prepared()
    provoz.app.register(graf, title="Sit")
    assert [o.title for o in provoz.app.all()] == ["Sit"]


def test_a_screen_gets_an_id_when_none_is_given():
    instance = vb.Instance()
    assert instance.screen.open(title="Provoz").id


# ===========================================================================
# Okno vznika tim, ze si ho divak otevre (D-54)
# ===========================================================================


def test_a_viewer_opens_a_window_from_the_offer():
    _, graf, provoz = prepared()
    nabidka = provoz.app.register(graf, title="Sit")
    okno = nabidka.open(HANA)
    assert okno.kind == "graph"
    assert provoz.window.all() == (okno,)


def test_the_window_gets_an_opaque_id():
    _, graf, provoz = prepared()
    okno = provoz.app.register(graf, title="Sit").open(HANA)
    assert okno.id and not okno.id.isdigit()


def test_the_window_takes_its_title_from_the_offer():
    _, graf, provoz = prepared()
    assert provoz.app.register(graf, title="Sit").open(HANA).title == "Sit"


def test_closing_the_window_does_not_cancel_the_offer():
    # Prave proto, aby slo otevrit znovu.
    _, graf, provoz = prepared()
    nabidka = provoz.app.register(graf, title="Sit")
    okno = nabidka.open(HANA)
    provoz.window.close(okno.id)

    assert provoz.window.all() == ()
    assert [o.title for o in provoz.app.all()] == ["Sit"]
    assert nabidka.open(HANA) is not None


def test_two_viewers_open_two_windows_from_one_offer():
    _, graf, provoz = prepared()
    nabidka = provoz.app.register(graf, title="Sit")
    prvni = nabidka.open(HANA)
    druhe = nabidka.open(Caller.for_user("petr"))
    assert prvni.address != druhe.address
    assert len(provoz.window) == 2


def test_a_viewer_who_cannot_read_the_screen_gets_no_offer():
    instance, graf, provoz = prepared()
    provoz.access.read.set(["group:ucetni"])
    provoz.app.register(graf, title="Sit")
    assert provoz.app.visible_to(Caller.for_user("petr")) == ()


def test_a_viewer_who_cannot_read_the_app_gets_no_offer():
    # Nabidku uvidi ten, kdo vidi plochu I apku - zadnou novou plochu prav to
    # nepridava.
    instance, graf, provoz = prepared()
    graf.access.read.set(["group:ucetni"])
    provoz.app.register(graf, title="Sit")
    assert provoz.app.visible_to(Caller.for_user("petr")) == ()


# ===========================================================================
# ACL se deklaruje na NABIDCE a okno ho zdedi (D-54)
# ===========================================================================


def test_the_documented_offer_with_access():
    # architektura-navrh.md, dodatek - doslova.
    instance, graf, provoz = prepared()
    nabidka = provoz.app.register(
        graf, title="Sit",
        read=["group:ucetni", "group:sklad"],
        write=["group:ucetni"],
        require_authentication=True,
    )
    okno = nabidka.open(HANA)

    assert okno.access.read.list() == ["group:sklad", "group:ucetni"]
    assert okno.access.write.list() == ["group:ucetni"]
    assert okno.access.require_authentication is True


def test_a_window_from_an_offer_without_access_inherits_from_the_screen():
    instance, graf, provoz = prepared()
    provoz.access.read.set(["group:ucetni"])
    okno = provoz.app.register(graf, title="Sit").open(HANA)
    assert okno.access.read.inherits


def test_changing_one_window_does_not_change_the_offer():
    # Prava jednoho konkretniho okna jde menit za behu - k oknu se clovek
    # dostane az tehdy, kdyz existuje.
    instance, graf, provoz = prepared()
    nabidka = provoz.app.register(graf, title="Sit", read=["group:ucetni"])
    prvni = nabidka.open(HANA)
    prvni.access.read.set(["group:sklad"])

    druhe = nabidka.open(HANA)
    assert druhe.access.read.list() == ["group:ucetni"]


# ===========================================================================
# Obsah se obvykle nevytvari - vznikne s nabidkou (D-59)
# ===========================================================================


def test_the_offer_makes_the_content_itself():
    instance, graf, provoz = prepared()
    okno = provoz.app.register(graf, title="Sit").open(HANA)
    assert okno.app.handle


def test_content_made_by_an_offer_has_no_acl_of_its_own():
    # Druha uroven se tim vubec nezapoji - vyvojar pise jednu sadu ACL.
    instance, graf, provoz = prepared()
    okno = provoz.app.register(graf, title="Sit", read=[USERS], write=[USERS]).open(HANA)
    assert okno.capabilities_for(HANA) == ["read", "write", "manage"]


def test_two_windows_from_one_offer_do_not_share_content_when_scope_is_window():
    instance, graf, provoz = prepared()
    nabidka = provoz.app.register(graf, title="Sit")
    assert nabidka.open(HANA).app.handle != nabidka.open(HANA).app.handle


def test_an_app_scoped_app_shares_content_across_windows():
    instance = vb.Instance(default_access=[USERS])
    mapa = instance.app.register(SharedApp())
    provoz = instance.screen.open(id="provoz")
    nabidka = provoz.app.register(mapa, title="Mapa")
    assert nabidka.open(HANA).app.handle == nabidka.open(HANA).app.handle


# -- pojmenovany obsah: jen kdyz prezije jedno okno --------------------------


def test_the_documented_named_content_on_two_screens():
    # architektura-navrh.md, dodatek - doslova.
    instance = vb.Instance(default_access=[USERS])
    graf = instance.app.register(GraphApp())
    hala = instance.screen.open(id="hala")
    uctarna = instance.screen.open(id="uctarna")

    mapa = graf.content.open(name="Mapa site",
                             read=["group:zamestnanci"], write=["group:site"])
    hala.app.register(graf, title="Mapa site", content=mapa)
    uctarna.app.register(graf, title="Mapa site", content=mapa)

    assert (
        hala.app.all()[0].open(HANA).app.handle
        == uctarna.app.all()[0].open(HANA).app.handle
    )


def test_named_content_keeps_its_own_access():
    # "Mapu vidi cela firma, kresli do ni jen sitari - at visi kdekoli."
    instance = vb.Instance(default_access=[USERS])
    graf = instance.app.register(GraphApp())
    hala = instance.screen.open(id="hala")

    mapa = graf.content.open(name="Mapa", read=[USERS], write=["group:site"])
    okno = hala.app.register(graf, title="Mapa", content=mapa,
                             read=[USERS], write=[USERS]).open(HANA)

    capabilities = okno.capabilities_for(Caller.for_user("petr"))
    assert "read" in capabilities
    assert "write" not in capabilities


def test_named_content_carries_its_name():
    instance = vb.Instance()
    graf = instance.app.register(GraphApp())
    assert graf.content.open(name="Mapa site").name == "Mapa site"


def test_named_content_has_a_handle_before_any_window_exists():
    # Davkova uloha ho musi umet naplnit driv, nez nekdo neco otevre.
    instance = vb.Instance()
    graf = instance.app.register(GraphApp())
    assert graf.content.open(name="Mapa").handle


# ===========================================================================
# Poradi deklarace a to, co v nem neni
# ===========================================================================


def test_an_offer_needs_an_app_that_this_instance_knows():
    instance = vb.Instance()
    jina = vb.Instance()
    graf = jina.app.register(GraphApp())
    provoz = instance.screen.open(id="provoz")
    with pytest.raises(ValueError):
        provoz.app.register(graf, title="Sit")


def test_the_declaration_path_no_longer_opens_windows():
    # D-54: zadne window.open v deklaraci. Kdyby zustalo, byly by dve cesty,
    # jak okno vyrobit - a jedna z nich by se prestala kontrolovat.
    _, _, provoz = prepared()
    assert not hasattr(provoz.window, "open")


def test_windows_are_still_reachable_at_runtime():
    # screen.window.* zustava pro beh: get, all, close.
    _, graf, provoz = prepared()
    okno = provoz.app.register(graf, title="Sit").open(HANA)
    assert provoz.window.get(okno.id) is okno
    assert okno in provoz.window.all()
