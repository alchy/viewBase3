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


def test_the_documented_script_runs_verbatim():
    """architektura-navrh.md, dodatek - doslova vcetne prefixu (D-64).

    Pet radku, zadna id (pridelí se), zadna ACL (dedi se), zadna rukojet
    (obsah vznikne s nabidkou). To je meritko, jestli je API jednoduche.
    """
    inst       = vb.Instance(default_access=["group:users"])
    app_excel  = inst.app.register(GraphApp())      # app_id, kind i scope z manifestu
    scr_provoz = inst.screen.open(title="Provoz")
    scr_provoz.app.register(app_excel, title="Sesit")   # nabidni ji na tehle plose

    assert scr_provoz.window.all() == ()  # pri startu neexistuje zadne okno

    # Posledni radek skriptu. Transport jeste neni (D-55), takze serve()
    # rekne PROC - kdyby chybel, spadl by dokumentovany skript na
    # AttributeError a to je doslova nalez 3.11. Az prijde transport, tenhle
    # test se otoci.
    with pytest.raises(NotImplementedError, match="transport"):
        inst.serve()


def test_serve_exists_even_though_it_does_not_work_yet():
    # Greppable mezera je lepsi nez chybejici metoda: AttributeError vypada
    # jako preklep, NotImplementedError s duvodem vypada jako plan.
    assert callable(vb.Instance().serve)


def test_the_public_package_offers_no_way_to_open_a_window():
    # D-61: kazde okno vznika z nabidky. Kdyby vedle toho existoval verejny
    # symbol, ktery okno vyrobi, byly by dve cesty - a jedna ze dvou se drive
    # nebo pozdeji prestane kontrolovat (presne tak vznikl nalez 3.1).
    import types

    # Balicek nacita verejna jmena lene, takze `vars` je zpocatku prazdne;
    # ptame se proto na to, co NEMA byt uvnitr.
    verejne = {
        name for name, value in vars(vb).items()
        if not name.startswith("_") and not isinstance(value, types.ModuleType)
    }
    assert verejne - set(vb.__all__) == set()
    assert not any("window" in name.lower() for name in vb.__all__)
    assert not any("open" in name.lower() for name in vb.__all__)

    _, graf, provoz = prepared()
    assert not hasattr(provoz.window, "open")
    assert not hasattr(provoz, "open_window")


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


def test_a_viewer_who_cannot_read_the_content_gets_no_offer():
    # Nabidku zavira PLOCHA a OBSAH, apka ne (D-60). Tohle je ten rozdil,
    # ktery dela cely model: tataz nabidka na tez plose se dvema lidem chova
    # jinak, protoze rozhodl obsah.
    instance, graf, provoz = prepared()
    cnt = graf.content.open(title="Mzdy", read=["group:ucetni"])
    provoz.app.register(cnt)

    assert provoz.app.visible_to(Caller.for_user("petr")) == ()
    assert len(provoz.app.visible_to(Caller.for_user("hana", ["ucetni"]))) == 1


def test_an_offer_without_content_asks_nobody():
    # Obsah vznikne az kliknutim, takze neni na co se ptat.
    instance, graf, provoz = prepared()
    provoz.app.register(graf, title="Novy")
    assert len(provoz.app.visible_to(Caller.for_user("petr"))) == 1


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
    # architektura-navrh.md, dodatek - doslova. Apka se odvodi z obsahu (D-67)
    # a titulek taky (D-66), takze se nic neopakuje.
    inst = vb.Instance(default_access=[USERS])
    app_graf = inst.app.register(GraphApp())
    scr_hala = inst.screen.open(id="hala")
    scr_uctarna = inst.screen.open(id="uctarna")

    cnt_mapa = app_graf.content.open(title="Mapa site",
                                     read=["group:zamestnanci"], write=["group:site"])
    scr_hala.app.register(cnt_mapa)
    scr_uctarna.app.register(cnt_mapa)

    assert (
        scr_hala.app.all()[0].open(HANA).app.handle
        == scr_uctarna.app.all()[0].open(HANA).app.handle
    )


def test_the_offer_takes_its_title_from_the_content():
    inst = vb.Instance(default_access=[USERS])
    app_graf = inst.app.register(GraphApp())
    scr = inst.screen.open(id="hala")
    cnt = app_graf.content.open(title="Mapa site")
    assert scr.app.register(cnt).title == "Mapa site"


def test_an_unset_title_is_a_reference_not_a_copy():
    # Prejmenovani dokumentu za behu se ma projevit v menu.
    inst = vb.Instance(default_access=[USERS])
    app_graf = inst.app.register(GraphApp())
    cnt = app_graf.content.open(title="Mapa site")
    off = inst.screen.open(id="hala").app.register(cnt)

    cnt.title = "Topologie"

    assert off.title == "Topologie"


def test_a_set_title_is_a_value_not_a_reference():
    # Pevny stitek jedne plochy: `content.title` patri dokumentu,
    # `offer.title` polozce menu. Kdyby to bylo jedno pole, prejmenovani
    # dokumentem by prepsalo vyvojarovo menu vsude.
    inst = vb.Instance(default_access=[USERS])
    app_graf = inst.app.register(GraphApp())
    cnt = app_graf.content.open(title="Mapa site")
    off = inst.screen.open(id="hala").app.register(cnt, title="Rizika")

    cnt.title = "Topologie"

    assert off.title == "Rizika"


def test_an_offer_without_content_must_be_named():
    inst = vb.Instance(default_access=[USERS])
    app_graf = inst.app.register(GraphApp())
    with pytest.raises(ValueError, match="title"):
        inst.screen.open(id="hala").app.register(app_graf)


def test_the_app_is_never_named_twice():
    # D-67: jmenovat apku i obsah jde napsat NESOUHLASNE. Kdyz se apka odvodi,
    # ta chyba prestane byt vyjadritelna - to je silnejsi nez ji kontrolovat.
    import inspect

    from viewbase.runtime.screen import OfferCollection

    assert "content" not in inspect.signature(OfferCollection.register).parameters


def test_named_content_keeps_its_own_access():
    # "Mapu vidi cela firma, kresli do ni jen sitari - at visi kdekoli."
    instance = vb.Instance(default_access=[USERS])
    graf = instance.app.register(GraphApp())
    hala = instance.screen.open(id="hala")

    mapa = graf.content.open(title="Mapa", read=[USERS], write=["group:site"])
    okno = hala.app.register(mapa, read=[USERS], write=[USERS]).open(HANA)

    capabilities = okno.capabilities_for(Caller.for_user("petr"))
    assert "read" in capabilities
    assert "write" not in capabilities


def test_named_content_carries_its_title():
    # D-65: popisek se u VSECH objektu jmenuje title - plocha, okno, obsah
    # i nabidka. `name` v tomhle vyznamu neexistuje.
    instance = vb.Instance()
    graf = instance.app.register(GraphApp())
    assert graf.content.open(title="Mapa site").title == "Mapa site"


def test_content_has_no_name_field_any_more():
    instance = vb.Instance()
    graf = instance.app.register(GraphApp())
    assert not hasattr(graf.content.open(title="Mapa"), "name")


def test_named_content_has_a_handle_before_any_window_exists():
    # Davkova uloha ho musi umet naplnit driv, nez nekdo neco otevre.
    instance = vb.Instance()
    graf = instance.app.register(GraphApp())
    assert graf.content.open(title="Mapa").handle


def test_named_content_knows_its_own_app():
    instance = vb.Instance()
    graf = instance.app.register(GraphApp())
    assert graf.content.open(title="Mapa").app is graf


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
