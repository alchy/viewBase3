"""Obsah je objekt s vlastni adresou a vlastnim ACL (D-52, D-57).

Je to jedina vec, ktera proti viewBase2 pribyva, a je tam kvuli konkretni
chybe: instance-wide obsah (log) se zverejnil tim, ze ho nekdo polozil na
verejnou plochu. Bez druhe urovne se ta trida chyb zavrit neda.

    efektivni pravo divaka v okne = okno prunik obsah

PRUNIK SE POCITA VYSLOVNE, ne tretim pravidlem v dedicnosti (D-57):

    pravo = pravo okna A (obsah nema ACL NEBO obsah pousti)

Nenastavene ACL obsahu tedy neni "nejaka vychozi hodnota", ale "druha uroven
se nepouzila". A OBSAH NEMA DEDICNOST VUBEC - nelezi na plose, takze neni
z ceho dedit.
"""
import pytest

import viewbase as vb
from viewbase.core.access import Acl, Verb
from viewbase.core.addressing import Address
from viewbase.core.identity import USERS, Caller
from viewbase.runtime.events import Needs, Verdict
from conftest import open_window, register_app


class FakeApp:
    def open_content(self, handle, spec, subject):
        return {"handle": handle, "state": {}, "cursor": 1}

    def snapshot(self, handle, subject):
        return {"state": {}, "cursor": 1}

    def apply_event(self, handle, subject, event):
        return []

    def close_content(self, handle):
        pass


def prepared(scope="app"):
    """Plocha i okno otevrene vsem prihlasenym; omezovat bude az obsah."""
    instance = vb.Instance(default_access=[USERS])
    register_app(instance, "workbench.graph", kind="graph", scope=scope, backend=FakeApp())
    screen = instance.screen.open(id="infra")
    screen.access.read.set([USERS])
    screen.access.write.set([USERS])
    window = open_window(screen, "graph", id="net", app="workbench.graph")
    window.access.read.set([USERS])
    window.access.write.set([USERS])
    return instance, screen, window


# ===========================================================================
# Obsah ma adresu (D-52)
# ===========================================================================


def test_content_has_an_address():
    assert str(Address.content("vb1_abc")) == "content:vb1_abc"


def test_a_content_address_round_trips():
    assert Address.parse("content:vb1_abc") == Address.content("vb1_abc")


def test_a_content_address_has_no_parent():
    # Obsah nelezi na plose - neni z ceho dedit (D-57).
    assert Address.content("vb1_abc").parent is None


def test_an_opened_content_is_an_object_of_the_instance():
    instance, _, window = prepared()
    assert Address.content(window.app.handle) in instance.objects


# ===========================================================================
# Druha uroven se plati, jen kdyz se pouzije
# ===========================================================================


def test_content_without_an_acl_adds_no_restriction():
    # Bezny pripad: vyvojar pise jednu sadu ACL a druha uroven mu nepreka.
    instance, _, window = prepared()
    assert window.capabilities_for(Caller.for_user("hana")) == ["read", "write"]


def test_content_with_its_own_acl_narrows_the_window():
    instance, _, window = prepared()
    instance.content.access(window.app.handle).read.set(["group:ucetni"])
    assert window.capabilities_for(Caller.for_user("petr")) == []


def test_the_person_in_both_acls_gets_through():
    instance, _, window = prepared()
    instance.content.access(window.app.handle).read.set(["group:ucetni"])
    assert "read" in window.capabilities_for(Caller.for_user("hana", ["ucetni"]))


def test_the_content_can_narrow_writing_alone():
    instance, _, window = prepared()
    instance.content.access(window.app.handle).write.set(["group:ucetni"])
    capabilities = window.capabilities_for(Caller.for_user("petr"))
    assert "read" in capabilities
    assert "write" not in capabilities


def test_a_wide_content_does_not_widen_a_narrow_window():
    # Prunik, ne sjednoceni: druha uroven smi jen ubirat.
    instance, _, window = prepared()
    window.access.read.set(["group:ucetni"])
    instance.content.access(window.app.handle).read.set([USERS])
    assert window.capabilities_for(Caller.for_user("petr")) == []


def test_an_explicitly_empty_content_acl_closes_it_for_everyone():
    instance, _, window = prepared()
    instance.content.access(window.app.handle).read.set([])
    assert window.capabilities_for(Caller.for_user("hana")) == []


# ===========================================================================
# Obsah nema dedicnost (D-57)
# ===========================================================================


def test_content_does_not_inherit_from_the_screen_it_is_shown_on():
    # Tohle je ta chyba, kvuli ktere druha uroven vznikla: instance-wide obsah
    # se zverejnil tim, ze ho nekdo polozil na verejnou plochu.
    instance, screen, window = prepared()
    instance.content.access(window.app.handle).read.set(["group:auditor"])
    screen.access.read.set(["group:public"])
    window.access.read.set(["group:public"])

    assert window.capabilities_for(Caller.anonymous()) == []


def test_content_does_not_inherit_the_instance_default():
    # Kdyby dedilo, "nenastaveno" by znamenalo default_access - a to je
    # TRETI chovani vychozi hodnoty, ktere jsme si nepridali (D-56).
    instance, _, window = prepared()
    assert instance.objects.access_of(Address.content(window.app.handle)).read is None


def test_the_same_content_in_two_windows_keeps_its_own_acl():
    instance, screen, window = prepared()
    druhe = open_window(screen, "graph", id="net2", app="workbench.graph")
    druhe.access.read.set([USERS])
    druhe.access.write.set([USERS])
    assert druhe.app.handle == window.app.handle

    instance.content.access(window.app.handle).read.set(["group:ucetni"])

    # Omezeni obsahu plati v OBOU oknech - je to vlastnost obsahu, ne okna.
    assert window.capabilities_for(Caller.for_user("petr")) == []
    assert druhe.capabilities_for(Caller.for_user("petr")) == []


# ===========================================================================
# Vynucovani jde touz cestou (zadna druha vetev)
# ===========================================================================


def test_an_event_is_refused_when_the_content_says_so():
    instance, _, window = prepared()
    instance.events.register("psani", lambda *a: None, needs=Needs.WRITE)
    instance.content.access(window.app.handle).write.set(["group:ucetni"])

    decision = instance.guard.check(Caller.for_user("petr"), "psani", window.address)
    assert decision.verdict is Verdict.CONTENT_CLOSED


def test_the_reason_tells_the_content_apart_from_the_window():
    # Chyba 3.7: tri ruzne priciny se hlasily stejnou hlaskou. "Na okno nemas"
    # a "na obsah nemas" jsou pri hledani chyby dve uplne jine veci.
    instance, _, window = prepared()
    instance.events.register("psani", lambda *a: None, needs=Needs.WRITE)
    window.access.write.set(["group:ucetni"])
    instance.content.access(window.app.handle).write.set(["group:sklad"])

    petr = Caller.for_user("petr")
    assert instance.guard.check(petr, "psani", window.address).verdict is Verdict.NOT_IN_ACL

    window.access.write.set([USERS])
    assert instance.guard.check(petr, "psani", window.address).verdict is Verdict.CONTENT_CLOSED


def test_an_event_passes_when_both_levels_allow():
    instance, _, window = prepared()
    instance.events.register("psani", lambda *a: None, needs=Needs.WRITE)
    instance.content.access(window.app.handle).write.set([USERS])
    assert instance.guard.check(Caller.for_user("hana"), "psani", window.address)


def test_a_window_without_content_is_not_stopped_by_the_second_level():
    instance = vb.Instance(default_access=[USERS])
    screen = instance.screen.open(id="infra")
    window = open_window(screen, "panel", id="mzdy")
    instance.events.register("psani", lambda *a: None, needs=Needs.WRITE)
    assert instance.guard.check(Caller.for_user("hana"), "psani", window.address)


def test_the_menu_obeys_the_content_too():
    # Menu se stavi pres tyz Guard, takze druha uroven se v nem projevi sama.
    instance = vb.Instance(default_access=[USERS])
    register_app(instance, "workbench.graph", kind="graph", scope="app", backend=FakeApp(),
        menu_group="Graf", menu={"prekresli": {"type": "command", "needs": "write"}},
    )
    screen = instance.screen.open(id="infra")
    window = open_window(screen, "graph", id="net", app="workbench.graph")
    instance.content.access(window.app.handle).write.set(["group:ucetni"])

    menu = window.menu_for(Caller.for_user("petr"))
    polozky = {i["id"]: i for entry in menu if entry["group"] == "Graf" for i in entry["items"]}
    assert not polozky["prekresli"]["enabled"]


# ===========================================================================
# Zmena prav obsahu je auditni udalost jako kazda jina
# ===========================================================================


def test_changing_the_content_acl_is_recorded():
    instance, _, window = prepared()
    instance.content.access(window.app.handle).read.set(["group:ucetni"])
    assert any(
        r.address == Address.content(window.app.handle) for r in instance.audit
    )


def test_the_change_survives_the_strictest_threshold():
    instance = vb.Instance(default_access=[USERS], log_level="error")
    register_app(instance, "a", kind="graph", scope="app", backend=FakeApp())
    window = open_window(instance.screen.open(id="infra"), "graph", id="net", app="a")
    instance.content.access(window.app.handle).read.set(["group:ucetni"])
    assert any(r.action == "read" for r in instance.audit)


def test_asking_about_content_that_is_not_there_is_an_error():
    instance = vb.Instance()
    with pytest.raises(KeyError):
        instance.content.access("vb1_neexistuje")


# ===========================================================================
# Treti pripad: PRAVA ZUZENA POD RUKAMA (D-69)
#
# Kazda vlastnost, ktera se dotyka prav, ma mit tri pripady, ne dva: plna
# prava, zadna prava a "nekdo zmenil ACL potom, co objekt vznikl". Tenhle
# treti stav v deklaraci nevznikne a v provozu vznika porad - a prave on
# nechytil nalez F-22, protoze vsech 549 testu testovalo jen prvni dva.
# ===========================================================================


def zalozeno_hanou():
    """Obsah zalozeny hanou, na ktery ma zatim plna prava."""
    instance = vb.Instance(default_access=[USERS])
    register_app(instance, "a", kind="graph", scope="app", backend=FakeApp())
    screen = instance.screen.open(id="infra", read=[USERS], write=[USERS])
    hana = Caller.for_user("hana")
    window = open_window(screen, "graph", id="net", app="a", by=hana)
    window.access.read.set([USERS])
    window.access.write.set([USERS])
    return instance, window, hana


def test_the_founder_starts_with_everything():
    _, window, hana = zalozeno_hanou()
    assert window.capabilities_for(hana) == ["read", "write", "manage"]


def test_a_stranger_starts_with_nothing_extra():
    instance, window, _ = zalozeno_hanou()
    assert window.capabilities_for(Caller.for_user("petr")) == ["read", "write"]


def test_the_founder_loses_manage_when_the_content_is_narrowed_under_them():
    # D-68: manage VYZADUJE read. Kdyby zustalo, vyzamknuty zakladatel by mel
    # dal pravo prejmenovat a zmenit ACL - tedy si pristup vratit. Bezpecnostni
    # ovladani, ktere vypada, ze zabralo, a nezabralo, je horsi nez zadne.
    instance, window, hana = zalozeno_hanou()
    instance.content.access(window.app.handle).read.set(["group:auditor"])
    assert window.capabilities_for(hana) == []


def test_the_founder_keeps_manage_while_they_still_have_read():
    # Zuzeni, ktere zakladatele nechava uvnitr, mu manage nebere.
    instance, window, hana = zalozeno_hanou()
    instance.content.access(window.app.handle).read.set(["user:hana"])
    assert "manage" in window.capabilities_for(hana)


def test_narrowing_the_window_alone_also_takes_manage():
    # Prunik ma dva cleny; zuzit staci kterykoli z nich.
    instance, window, hana = zalozeno_hanou()
    window.access.read.set(["group:auditor"])
    assert window.capabilities_for(hana) == []


def test_the_administrator_gets_back_in_after_a_narrowing():
    # Cesta zpatky vede pres spravce, ktery stoji nad ACL - to je ta vedome
    # prijata cena za D-68.
    instance, window, hana = zalozeno_hanou()
    instance.content.access(window.app.handle).read.set(["group:auditor"])
    spravce = Caller.for_user("spravce", ["administrator"])
    assert "manage" in window.capabilities_for(spravce)


def test_widening_it_back_restores_manage_at_once():
    # Pozdni vazba: prava se ctou pri kazdem dotazu, ne pri vzniku okna.
    instance, window, hana = zalozeno_hanou()
    instance.content.access(window.app.handle).read.set(["group:auditor"])
    instance.content.access(window.app.handle).read.set([USERS])
    assert "manage" in window.capabilities_for(hana)


def test_an_offer_disappears_when_the_content_is_narrowed_under_it():
    # Tyz treti pripad o patro vys: nabidka uz visi a nekdo zuzi obsah.
    instance = vb.Instance(default_access=[USERS])
    from tests.test_offer import GraphApp  # apka s manifestem

    app = instance.app.register(GraphApp())
    scr = instance.screen.open(id="infra", read=[USERS])
    cnt = app.content.open(title="Mapa")
    scr.app.register(cnt)
    hana = Caller.for_user("hana")

    assert len(scr.app.visible_to(hana)) == 1

    cnt.access.read.set(["group:auditor"])

    assert scr.app.visible_to(hana) == ()
