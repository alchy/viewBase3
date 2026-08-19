"""Instance, plocha, okno - a verejne API, kterym se to pise.

Tri veci se tu drzi zaroven:

  * GRAMATIKA "kde . objekt . co" (D-19). Typ okna je HODNOTA prvniho
    argumentu, ne jmeno metody: kdyby existovalo `open_panel()`, jadro by
    muselo znat seznam typu a publikovany typ treti strany by vlastni metodu
    nikdy nedostal (typy-oken.md par. 3).
  * INSTANCE VLASTNI SVUJ STAV (princip 2). Dve instance v jednom procesu
    musi byt samozrejmost; ve viewBase2 lezel stav v modulech a cesta
    k souboru politiky pretekla z jednoho testu do cele sady (chyba 3.14).
  * ADRESA VZNIKA PRI NAROZENI (par. 2). Zadny mezistav, kdy uz objekt
    existuje, ale jeste nema adresu, a tedy ani prava.
"""
import pytest

import viewbase as vb
from viewbase.core.access import Acl, Verb
from viewbase.core.addressing import Address
from viewbase.core.identity import ADMINISTRATOR, USERS


# ===========================================================================
# Verejne API (D-13, B-09)
# ===========================================================================


def test_the_public_names_are_exactly_the_documented_ones():
    # Povrch, ktery se rozroste nahodou, uz nejde zuzit bez rozbiti.
    # viewBase2 ma verejne API popsane az zpetne - presne proto.
    assert set(vb.__all__) == {"Instance", "Needs", "StepUp", "Verb"}


def test_nothing_else_leaks_out_of_the_package():
    # Zamerne se NEPTAME pres dir(): balicek si `__dir__` prepisuje na `__all__`
    # kvuli napovede, takze pres nej by tenhle test nesel nikdy shodit. Ptame se
    # na skutecny jmenny prostor modulu.
    public = {name for name in vars(vb) if not name.startswith("_")}
    # `core` a `runtime` jsou podbalicky - Python je do jmenneho prostoru vlozi
    # sam, jakmile se z nich neco importuje. Nic jineho tam byt nesmi.
    assert public - set(vb.__all__) - {"core", "runtime"} == set()


def test_the_developer_never_imports_from_core():
    # Vsechno ostatni se ziskava Z INSTANCE, ne importem.
    assert not hasattr(vb, "Acl")
    assert not hasattr(vb, "Access")
    assert not hasattr(vb, "Address")


# ===========================================================================
# Gramatika: kde . objekt . co (D-19)
# ===========================================================================


def test_instance_opens_a_screen():
    instance = vb.Instance()
    screen = instance.screen.open(title="Provoz", id="provoz")
    assert screen.title == "Provoz"


def test_screen_can_be_looked_up_by_its_id():
    instance = vb.Instance()
    opened = instance.screen.open(id="provoz")
    assert instance.screen.get("provoz") is opened


def test_screens_can_be_listed():
    instance = vb.Instance()
    instance.screen.open(id="provoz")
    instance.screen.open(id="sklad")
    assert {screen.id for screen in instance.screen.all()} == {"provoz", "sklad"}


def test_screen_opens_a_window_of_a_kind_given_as_a_value():
    # `open(kind, ...)`, ne `open_panel(...)`: jadro nesmi znat seznam typu.
    instance = vb.Instance()
    screen = instance.screen.open(id="provoz")
    window = screen.window.open("panel", id="mzdy", title="Mzdy")
    assert window.kind == "panel"
    assert window.title == "Mzdy"


def test_a_kind_the_core_never_heard_of_opens_just_the_same():
    # Publikovany typ treti strany nema mit horsi cestu nez vestaveny.
    instance = vb.Instance()
    screen = instance.screen.open(id="provoz")
    assert screen.window.open("nekdo.jineho.mapa", id="m").kind == "nekdo.jineho.mapa"


def test_window_can_be_looked_up_and_closed():
    instance = vb.Instance()
    screen = instance.screen.open(id="provoz")
    screen.window.open("panel", id="mzdy")
    assert screen.window.get("mzdy").id == "mzdy"
    screen.window.close("mzdy")
    assert screen.window.all() == ()


def test_windows_are_listed_explicitly_not_by_iterating_the_collection():
    # Jednotne cislo a vyslovne .all(): `for w in screen.window` by svadelo
    # k tomu, ze `screen.window` je seznam, a ono je to jmeno kolekce.
    instance = vb.Instance()
    screen = instance.screen.open(id="provoz")
    screen.window.open("panel", id="mzdy")
    assert len(screen.window.all()) == 1


def test_asking_for_a_window_that_is_not_there_is_an_error():
    instance = vb.Instance()
    screen = instance.screen.open(id="provoz")
    with pytest.raises(KeyError):
        screen.window.get("neexistuje")


def test_two_screens_cannot_share_an_id():
    instance = vb.Instance()
    instance.screen.open(id="provoz")
    with pytest.raises(ValueError):
        instance.screen.open(id="provoz")


def test_two_windows_on_one_screen_cannot_share_an_id():
    instance = vb.Instance()
    screen = instance.screen.open(id="provoz")
    screen.window.open("panel", id="mzdy")
    with pytest.raises(ValueError):
        screen.window.open("panel", id="mzdy")


def test_the_same_window_id_on_two_screens_is_fine():
    # Klic je (plocha, okno), ne okno samo.
    instance = vb.Instance()
    prvni = instance.screen.open(id="provoz")
    druha = instance.screen.open(id="sklad")
    prvni.window.open("panel", id="mzdy")
    assert druha.window.open("panel", id="mzdy").address != prvni.window.get("mzdy").address


# ===========================================================================
# Id je nepruhledne, poradi je neco jineho (par. 2)
# ===========================================================================


def test_screen_without_an_id_gets_an_opaque_one():
    instance = vb.Instance()
    generated = instance.screen.open(title="Provoz").id
    assert not generated.isdigit()


def test_generated_ids_do_not_repeat():
    instance = vb.Instance()
    assert len({instance.screen.open().id for _ in range(50)}) == 50


def test_order_on_the_bar_is_a_separate_property_from_the_id():
    # viewBase2 mel procesni citac, ktery plnil obe role zaroven; jako adresa
    # je rozbity, protoze dva procesy vyrobi screen_id=1 pro dve ruzne plochy.
    instance = vb.Instance()
    prvni = instance.screen.open(id="provoz")
    druha = instance.screen.open(id="sklad")
    assert (prvni.index, druha.index) == (0, 1)


# ===========================================================================
# Adresa vznika pri narozeni (par. 2)
# ===========================================================================


def test_window_has_its_address_from_the_start():
    instance = vb.Instance()
    screen = instance.screen.open(id="provoz")
    window = screen.window.open("panel", id="mzdy")
    assert str(window.address) == "screen:provoz/window:mzdy"


def test_window_is_in_the_object_registry_immediately():
    # Ve viewBase2 okno vzniklo bezejmenne a adresu dostalo, teprve kdyz ho
    # plocha prijala; do te doby melo prava "nikam nepatriciho" objektu.
    instance = vb.Instance()
    screen = instance.screen.open(id="provoz")
    window = screen.window.open("panel", id="mzdy")
    assert window.address in instance.objects


def test_closing_a_window_takes_it_out_of_the_registry():
    instance = vb.Instance()
    screen = instance.screen.open(id="provoz")
    address = screen.window.open("panel", id="mzdy").address
    screen.window.close("mzdy")
    assert address not in instance.objects


# ===========================================================================
# Instance vlastni svuj stav (princip 2, chyba 3.14)
# ===========================================================================


def test_two_instances_in_one_process_share_nothing():
    prvni = vb.Instance()
    druha = vb.Instance()
    prvni.screen.open(id="provoz")
    assert druha.screen.all() == ()


def test_two_instances_have_their_own_object_registries():
    prvni = vb.Instance()
    druha = vb.Instance()
    prvni.screen.open(id="provoz")
    assert Address.screen("provoz") not in druha.objects


def test_two_instances_can_have_different_defaults():
    otevrena = vb.Instance(default_access=["group:public"])
    zavrena = vb.Instance(default_access=[])
    otevrena.screen.open(id="provoz")
    zavrena.screen.open(id="provoz")
    assert otevrena.objects.resolve(Address.screen("provoz"), Verb.SEE) == Acl.of("group:public")
    assert zavrena.objects.resolve(Address.screen("provoz"), Verb.SEE) == Acl.empty()


def test_a_test_does_not_have_to_reset_anything():
    # Kdyz stav vlastni instance, testy si vyrobi vlastni a nic neresetuji.
    for _ in range(3):
        instance = vb.Instance()
        assert instance.screen.all() == ()


# ===========================================================================
# Fasada window.access (D-14) - zapis z dokumentace patri DOSLOVA do testu
# ===========================================================================


def prepared():
    instance = vb.Instance(default_access=["group:users"])
    screen = instance.screen.open(id="provoz")
    window = screen.window.open("panel", id="mzdy", title="Mzdy")
    return instance, screen, window


def test_documented_line_window_access_see_add():
    # architektura-navrh.md par. 4a, doslova.
    instance, _, window = prepared()
    window.access.see.add("group:ucetni")
    assert "group:ucetni" in instance.objects.resolve(window.address, Verb.SEE)


def test_documented_line_window_access_write_set():
    instance, _, window = prepared()
    window.access.write.set(["user:hana"])
    assert instance.objects.resolve(window.address, Verb.WRITE) == Acl.of("user:hana")


def test_documented_line_window_access_require_authentication():
    # architektura-navrh.md par. 4a, doslova. Verejne jmeno rika, co se stane;
    # vnitrni osa se dal jmenuje step_up, protoze pojmenovava mechanismus.
    instance, _, window = prepared()
    window.access.require_authentication = True
    assert instance.objects.step_up_at(window.address) is True


def test_the_public_property_reads_back():
    _, _, window = prepared()
    window.access.require_authentication = True
    assert window.access.require_authentication is True


def test_the_public_surface_does_not_use_the_internal_name():
    # Kdyby fasada nabizela obe jmena, dokumentace by prestala byt zavazna
    # a v kodu aplikaci by se objevila obe.
    _, _, window = prepared()
    assert not hasattr(window.access, "step_up")


def test_removing_a_principal_is_removal_from_the_allowed_not_a_ban():
    instance, _, window = prepared()
    window.access.see.set(["group:ucetni", "group:public"])
    window.access.see.remove("group:public")
    assert instance.objects.resolve(window.address, Verb.SEE) == Acl.of("group:ucetni")


def test_reading_the_access_gives_a_snapshot():
    # Cteni vraci snimek, ne zivou mnozinu - jinak by sla prava zmenit mimo
    # instanci a auditni stopa by o tom nevedela.
    _, _, window = prepared()
    window.access.see.set(["group:ucetni"])
    snapshot = window.access.see.list()
    snapshot.append("user:vetrelec")
    assert window.access.see.list() == ["group:ucetni"]


def test_screens_have_the_same_facade():
    instance = vb.Instance()
    screen = instance.screen.open(id="provoz")
    screen.access.see.add("group:ucetni")
    assert "group:ucetni" in instance.objects.resolve(screen.address, Verb.SEE)


def test_a_bare_name_becomes_a_group_here_too():
    instance, _, window = prepared()
    window.access.see.add("ucetni")
    assert "group:ucetni" in instance.objects.resolve(window.address, Verb.SEE)


# -- kazda zmena prav je auditni udalost ------------------------------------


def test_changing_access_is_recorded():
    instance, _, window = prepared()
    window.access.see.add("group:ucetni")
    assert any(record.address == window.address for record in instance.audit)


def test_the_record_says_what_changed_and_on_which_verb():
    instance, _, window = prepared()
    window.access.write.set(["user:hana"])
    record = instance.audit[-1]
    assert record.verb is Verb.WRITE
    assert "user:hana" in record.detail


def test_the_require_authentication_change_is_recorded_too():
    instance, _, window = prepared()
    window.access.require_authentication = True
    assert instance.audit[-1].action == "require_authentication"


def test_reading_the_access_is_not_an_audit_event():
    instance, _, window = prepared()
    before = len(instance.audit)
    window.access.see.list()
    assert len(instance.audit) == before


# -- B-08: principal, ktereho nezna zdroj identit --------------------------


def test_an_unknown_principal_is_written_but_flagged():
    # Tichy preklep v ACL znamena okno, ktere nikdo neuvidi, nebo pravidlo,
    # ktere nikdy nezabere. Zapis se ale NEODMITNE - identita muze vzniknout
    # pozdeji, treba v adresari.
    seen = {"group:ucetni"}
    instance = vb.Instance(knows_principal=lambda name: name in seen)
    window = instance.screen.open(id="provoz").window.open("panel", id="mzdy")

    window.access.see.add("group:ucetnii")  # preklep

    assert "group:ucetnii" in instance.objects.resolve(window.address, Verb.SEE)
    assert any(record.action == "unknown_principal" for record in instance.audit)


def test_a_known_principal_raises_no_flag():
    instance = vb.Instance(knows_principal=lambda name: name == "group:ucetni")
    window = instance.screen.open(id="provoz").window.open("panel", id="mzdy")
    window.access.see.add("group:ucetni")
    assert not any(record.action == "unknown_principal" for record in instance.audit)


def test_without_an_identity_source_nothing_is_flagged():
    # Zdroj identit, ktery odpovedet neumi, nesmi vyrabet varovani.
    instance, _, window = prepared()
    window.access.see.add("group:kdokoli")
    assert not any(record.action == "unknown_principal" for record in instance.audit)


# ===========================================================================
# Instance je objekt jako kazdy jiny (D-17)
# ===========================================================================


def test_the_instance_itself_is_in_its_own_registry():
    instance = vb.Instance()
    assert Address.instance_root() in instance.objects


def test_administering_the_instance_is_closed_by_default():
    instance = vb.Instance(default_access=["group:users"])
    assert instance.objects.resolve(Address.instance_root(), Verb.WRITE) == Acl.empty()


def test_administering_the_instance_can_be_opened_deliberately():
    instance = vb.Instance(admin_access=["group:operator"])
    acl = instance.objects.resolve(Address.instance_root(), Verb.WRITE)
    assert acl == Acl.of("group:operator")


def test_the_administrator_gets_in_even_when_nobody_opened_it():
    from viewbase.core.access import allowed

    instance = vb.Instance()
    acl = instance.objects.resolve(Address.instance_root(), Verb.WRITE)
    assert allowed({ADMINISTRATOR}, acl)
    assert not allowed({USERS}, acl)
