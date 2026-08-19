"""Registrace apky: objekt s pravy, deklarace, ktere se overuji, a pripojeni
k obsahu, ktere smi apka odmitnout (D-36 az D-41, B-16).
"""
import pytest

import viewbase as vb
from viewbase.core.access import Acl, Verb
from viewbase.core.addressing import Address
from viewbase.core.identity import ADMINISTRATOR, USERS, Caller
from viewbase.runtime.content import ContentState
from conftest import open_window, register_app


class FakeApp:
    def __init__(self, known=(), listing=None):
        self.known = set(known)
        self.listing = listing or []
        self.opened = []
        self.subjects = []

    def create_content(self, handle, spec, subject):
        self.subjects.append(subject)
        handle = handle or "app_minted_1"  # apka si rukojet razi sama
        self.known.add(handle)
        self.opened.append(handle)
        return {"handle": handle, "state": {}, "cursor": 1}

    def open_content(self, handle, subject):
        return self.create_content(handle, {}, subject)

    def snapshot(self, handle, subject):
        return {"state": {}, "cursor": 1}

    def apply_event(self, handle, subject, event):
        return []

    def close_content(self, handle):
        self.known.discard(handle)


class OpenApp(FakeApp):
    """Apka, ktera prijme kazdou rukojet (vytvor nebo pripoj)."""

    def create_content(self, handle, spec, subject):
        self.subjects.append(subject)
        handle = handle or "app_minted_1"
        self.known.add(handle)
        self.opened.append(handle)
        return {"handle": handle, "state": {}, "cursor": 1}


    def open_content(self, handle, subject):
        return self.create_content(handle, {}, subject)

def instance_with(app=None, **kwargs):
    instance = vb.Instance(**kwargs)
    register_app(instance, "workbench.graph", kind="graph", scope="app", backend=app or OpenApp()
    )
    return instance


# ===========================================================================
# Registrace apky je objekt - ale BEZ PRAV (D-60)
#
# Apka je jen deklarace "tenhle kod existuje a umi tenhle kind". Kdo nabidku
# uvidi, rozhoduje PLOCHA a OBSAH. Treti ACL nezaviralo nic, co ty dve
# nezavrou taky, a globalni vypinac existuje i bez nej - odregistrovana apka
# bere sve nabidky s sebou.
# ===========================================================================


def test_an_app_registration_carries_no_rights():
    instance = instance_with()
    assert not hasattr(instance.app.get("workbench.graph"), "access")


def test_registering_an_app_with_rights_is_refused():
    # Tise ignorovat by znamenalo, ze si nekdo mysli, ze apku skryl.
    class App:
        manifest = {"app_id": "x", "kind": "panel", "scope": "window"}

    with pytest.raises(TypeError):
        vb.Instance().app.register(App(), read=["group:ucetni"])


def test_the_manifest_cannot_be_overridden():
    # D-63: druhe misto, kde zije tataz hodnota, se rozejde nejtiseji.
    class App:
        manifest = {"app_id": "x", "kind": "panel", "scope": "window"}

    with pytest.raises(TypeError):
        vb.Instance().app.register(App(), scope="app")


def test_registering_an_app_puts_it_in_the_object_registry():
    instance = instance_with()
    assert Address.app("workbench.graph") in instance.objects












def test_removing_an_app_takes_its_object_away():
    instance = instance_with()
    instance.app.unregister("workbench.graph")
    assert Address.app("workbench.graph") not in instance.objects


# ===========================================================================
# Schopnosti se vyjednavaji PRI REGISTRACI (D-40)
# ===========================================================================


def test_a_required_capability_that_cannot_be_granted_fails_the_registration():
    # Rozhodnuti se tim presune na misto, kde se da opravit (konfigurace),
    # misto do prohlizece ciziho cloveka.
    instance = vb.Instance(capabilities=["canvas2d"])
    with pytest.raises(ValueError, match="fetch-origin"):
        register_app(instance, "x", kind="graph", scope="app", backend=OpenApp(),
            capabilities={"required": ["fetch-origin"]},
        )


def test_a_required_capability_that_can_be_granted_is_fine():
    instance = vb.Instance(capabilities=["canvas2d", "webgl"])
    registration = register_app(instance, "x", kind="graph", scope="app", backend=OpenApp(),
        capabilities={"required": ["webgl"]},
    )
    assert registration.granted == ("webgl",)


def test_an_optional_capability_that_cannot_be_granted_leaves_the_app_running():
    # Apka bezi osekane a VI O TOM - neudelena schopnost je nepritomna,
    # ne chyba za behu.
    instance = vb.Instance(capabilities=["canvas2d"])
    registration = register_app(instance, "x", kind="graph", scope="app", backend=OpenApp(),
        capabilities={"required": ["canvas2d"], "optional": ["webgl"]},
    )
    assert registration.granted == ("canvas2d",)
    assert registration.refused == ("webgl",)


def test_a_refused_optional_capability_is_written_to_the_audit():
    instance = vb.Instance(capabilities=["canvas2d"])
    register_app(instance, "x", kind="graph", scope="app", backend=OpenApp(),
        capabilities={"optional": ["webgl"]},
    )
    assert any(r.action == "capability_refused" for r in instance.audit)


def test_a_failed_registration_leaves_nothing_behind():
    instance = vb.Instance(capabilities=[])
    with pytest.raises(ValueError):
        register_app(instance, "x", kind="graph", scope="app", backend=OpenApp(),
            capabilities={"required": ["webgl"]},
        )
    assert "x" not in instance.app
    assert Address.app("x") not in instance.objects


# ===========================================================================
# Udalosti apky vznikaji v registru (B-16, chyba 3.1)
# ===========================================================================


def test_an_app_event_lands_in_the_event_registry():
    instance = vb.Instance()
    register_app(instance, "example.hello", kind="panel", scope="app", backend=OpenApp(),
        events={"hello_submit": {"needs": "write", "profile": "request"}},
    )
    assert instance.events.get("example.hello.hello_submit") is not None


def test_an_app_event_carries_the_needs_it_declared():
    instance = vb.Instance()
    register_app(instance, "example.hello", kind="panel", scope="app", backend=OpenApp(),
        events={"hello_submit": {"needs": "write", "profile": "request"}},
    )
    assert instance.events.get("example.hello.hello_submit").needs is vb.Needs.WRITE


def test_an_app_event_without_needs_fails_the_registration():
    # Chybejici polozka neni vychozi hodnota, ale chyba registrace - jinak by
    # udalosti apky obchazely registr (chyba 3.1).
    instance = vb.Instance()
    with pytest.raises(ValueError, match="needs"):
        register_app(instance, "example.hello", kind="panel", scope="app", backend=OpenApp(),
            events={"hello_submit": {"profile": "request"}},
        )


def test_two_apps_can_declare_the_same_event_name():
    # Jmena se jmenuji podle apky, takze si dve apky nemohou prebit udalost.
    instance = vb.Instance()
    for app_id in ("prvni", "druha"):
        register_app(instance,
            app_id, kind="panel", scope="app", backend=OpenApp(),
            events={"submit": {"needs": "write", "profile": "request"}},
        )
    assert instance.events.get("prvni.submit") is not None
    assert instance.events.get("druha.submit") is not None


def test_an_app_event_obeys_the_registry_invariant():
    # Tyz strojovy test jako u vestavenych udalosti: anonym na skryte plose
    # nedosahne na handler.
    instance = vb.Instance(default_access=[])
    register_app(instance, "example.hello", kind="panel", scope="app", backend=OpenApp(),
        events={"hello_submit": {"needs": "write", "profile": "request"}},
    )
    screen = instance.screen.open(id="tajna")
    window = open_window(screen, "panel", id="h")
    decision = instance.guard.check(
        Caller.anonymous(), "example.hello.hello_submit", window.address
    )
    assert not decision


# ===========================================================================
# Pripojeni k obsahu (D-38, D-39)
#
# ODMITANI ZANIKLO (D-52): apka o pravech nerozhoduje nic - obsah ma vlastni
# adresu a vlastni ACL a rozhodujeme my. Autor apky tim nema CO pokazit.
# ===========================================================================


def test_open_content_gets_the_subject():
    backend = OpenApp()
    instance = instance_with(backend)
    open_window(instance.screen.open(id="infra"), "graph", id="net", app="workbench.graph")
    assert "subject_id" in backend.subjects[-1]


def test_the_app_may_mint_the_handle_itself():
    # Obsah muze vzniknout na apce driv, nez existuje jakekoli viewBase.
    backend = OpenApp()
    instance = vb.Instance()
    register_app(instance, "a", kind="graph", scope="explicit", backend=backend)
    handle = instance.app.get("a").new_content(mint_at_app=True)
    assert handle == "app_minted_1"


def test_the_app_can_no_longer_refuse_a_connection():
    # Strojova kontrola skrtu: kdyby se ta cesta vratila, vratila by se s ni
    # i moznost, ze o pravech rozhoduje apka.
    import viewbase.runtime.content as content_module

    assert not hasattr(content_module, "ContentRefused")
    assert not hasattr(content_module.ContentState, "REFUSED")


def test_the_app_contract_lists_content_without_deciding_anything():
    # D-72: vypis se vratil, ale bez subjektu - apka nefiltruje. A zalozit
    # a otevrit jsou dve volani, aby si apka nemohla razit vlastni rukojeti.
    import inspect

    from viewbase.runtime.content import AppBackend

    assert list(inspect.signature(AppBackend.list_content).parameters) == ["self"]
    assert list(inspect.signature(AppBackend.create_content).parameters) == [
        "self", "handle", "spec", "subject",
    ]


# ===========================================================================
# Vlastnik obsahu (D-41, D-50)
# ===========================================================================


def test_content_records_who_created_it():
    instance = instance_with()
    w = open_window(instance.screen.open(id="infra"), "graph", id="net", app="workbench.graph")
    assert instance.content.created_by(w.app.handle) is not None


def test_the_creator_is_the_caller_who_opened_it():
    instance = instance_with()
    screen = instance.screen.open(id="infra")
    w = open_window(screen, 
        "graph", id="net", app="workbench.graph", by=Caller.for_user("hana")
    )
    assert instance.content.created_by(w.app.handle) == "user:hana"


def test_a_destructive_action_is_for_the_founder_or_the_administrator():
    # D-50: prejmenovat, zrusit a menit prava smi ZAKLADATEL objektu nebo
    # spravce - odvozene, ne deklarovane. V ACL zadne 'manage' neni.
    instance = instance_with()
    screen = instance.screen.open(id="infra")
    w = open_window(screen, 
        "graph", id="net", app="workbench.graph", by=Caller.for_user("hana")
    )
    handle = w.app.handle

    assert instance.content.may_destroy(handle, Caller.for_user("hana"))
    assert not instance.content.may_destroy(handle, Caller.for_user("petr"))
    assert instance.content.may_destroy(handle, Caller.for_user("s", ["administrator"]))
