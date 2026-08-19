"""Registrace apky: objekt s pravy, deklarace, ktere se overuji, a pripojeni
k obsahu, ktere smi apka odmitnout (D-36 az D-41, B-16).
"""
import pytest

import viewbase as vb
from viewbase.core.access import Acl, Verb
from viewbase.core.addressing import Address
from viewbase.core.identity import ADMINISTRATOR, USERS, Caller
from viewbase.runtime.content import ContentState


class FakeApp:
    def __init__(self, known=(), listing=None):
        self.known = set(known)
        self.listing = listing or []
        self.opened = []
        self.subjects = []

    def open_content(self, handle, spec, subject):
        self.subjects.append(subject)
        handle = handle or "app_minted_1"  # apka si rukojet razi sama
        self.known.add(handle)
        self.opened.append(handle)
        return {"handle": handle, "state": {}, "cursor": 1}

    def snapshot(self, handle, subject):
        return {"state": {}, "cursor": 1}

    def apply_event(self, handle, subject, event):
        return []

    def close_content(self, handle):
        self.known.discard(handle)


class OpenApp(FakeApp):
    """Apka, ktera prijme kazdou rukojet (vytvor nebo pripoj)."""

    def open_content(self, handle, spec, subject):
        self.subjects.append(subject)
        handle = handle or "app_minted_1"
        self.known.add(handle)
        self.opened.append(handle)
        return {"handle": handle, "state": {}, "cursor": 1}


def instance_with(app=None, **kwargs):
    instance = vb.Instance(**kwargs)
    instance.app.register(
        "workbench.graph", kind="graph", scope="app", backend=app or OpenApp()
    )
    return instance


# ===========================================================================
# Registrace apky je objekt s vlastnim ACL (D-36)
# ===========================================================================


def test_registering_an_app_puts_it_in_the_object_registry():
    instance = instance_with()
    assert Address.app("workbench.graph") in instance.objects


def test_an_app_can_be_hidden_from_most_people():
    instance = instance_with()
    instance.app.get("workbench.graph").access.read.set(["group:ucetni"])
    acl = instance.objects.resolve(Address.app("workbench.graph"), Verb.READ)
    assert acl == Acl.of("group:ucetni")


def test_the_launcher_shows_only_apps_the_viewer_may_read():
    # Spoustec je vec WORKBENCHE - stavi ho z registru apek a filtruje nasim
    # modelem. Apka do nej nic nevklada.
    instance = instance_with()
    instance.app.register("tajna", kind="panel", scope="app", backend=OpenApp())
    instance.app.get("tajna").access.read.set(["group:ucetni"])

    visible = {r.app_id for r in instance.app.visible_to(Caller.for_user("petr"))}
    assert visible == {"workbench.graph"}


def test_the_launcher_shows_the_hidden_app_to_those_who_may_read_it():
    instance = instance_with()
    instance.app.get("workbench.graph").access.read.set(["group:ucetni"])
    visible = instance.app.visible_to(Caller.for_user("hana", ["ucetni"]))
    assert [r.app_id for r in visible] == ["workbench.graph"]


def test_the_administrator_sees_every_app():
    instance = instance_with()
    instance.app.get("workbench.graph").access.read.set([])
    visible = instance.app.visible_to(Caller.for_user("spravce", ["administrator"]))
    assert [r.app_id for r in visible] == ["workbench.graph"]


def test_an_anonymous_viewer_sees_no_app_by_default():
    instance = vb.Instance(default_access=[USERS])
    instance.app.register("workbench.graph", kind="graph", scope="app", backend=OpenApp())
    assert instance.app.visible_to(Caller.anonymous()) == ()


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
        instance.app.register(
            "x", kind="graph", scope="app", backend=OpenApp(),
            capabilities={"required": ["fetch-origin"]},
        )


def test_a_required_capability_that_can_be_granted_is_fine():
    instance = vb.Instance(capabilities=["canvas2d", "webgl"])
    registration = instance.app.register(
        "x", kind="graph", scope="app", backend=OpenApp(),
        capabilities={"required": ["webgl"]},
    )
    assert registration.granted == ("webgl",)


def test_an_optional_capability_that_cannot_be_granted_leaves_the_app_running():
    # Apka bezi osekane a VI O TOM - neudelena schopnost je nepritomna,
    # ne chyba za behu.
    instance = vb.Instance(capabilities=["canvas2d"])
    registration = instance.app.register(
        "x", kind="graph", scope="app", backend=OpenApp(),
        capabilities={"required": ["canvas2d"], "optional": ["webgl"]},
    )
    assert registration.granted == ("canvas2d",)
    assert registration.refused == ("webgl",)


def test_a_refused_optional_capability_is_written_to_the_audit():
    instance = vb.Instance(capabilities=["canvas2d"])
    instance.app.register(
        "x", kind="graph", scope="app", backend=OpenApp(),
        capabilities={"optional": ["webgl"]},
    )
    assert any(r.action == "capability_refused" for r in instance.audit)


def test_a_failed_registration_leaves_nothing_behind():
    instance = vb.Instance(capabilities=[])
    with pytest.raises(ValueError):
        instance.app.register(
            "x", kind="graph", scope="app", backend=OpenApp(),
            capabilities={"required": ["webgl"]},
        )
    assert "x" not in instance.app
    assert Address.app("x") not in instance.objects


# ===========================================================================
# Udalosti apky vznikaji v registru (B-16, chyba 3.1)
# ===========================================================================


def test_an_app_event_lands_in_the_event_registry():
    instance = vb.Instance()
    instance.app.register(
        "example.hello", kind="panel", scope="app", backend=OpenApp(),
        events={"hello_submit": {"needs": "write", "profile": "request"}},
    )
    assert instance.events.get("example.hello.hello_submit") is not None


def test_an_app_event_carries_the_needs_it_declared():
    instance = vb.Instance()
    instance.app.register(
        "example.hello", kind="panel", scope="app", backend=OpenApp(),
        events={"hello_submit": {"needs": "write", "profile": "request"}},
    )
    assert instance.events.get("example.hello.hello_submit").needs is vb.Needs.WRITE


def test_an_app_event_without_needs_fails_the_registration():
    # Chybejici polozka neni vychozi hodnota, ale chyba registrace - jinak by
    # udalosti apky obchazely registr (chyba 3.1).
    instance = vb.Instance()
    with pytest.raises(ValueError, match="needs"):
        instance.app.register(
            "example.hello", kind="panel", scope="app", backend=OpenApp(),
            events={"hello_submit": {"profile": "request"}},
        )


def test_two_apps_can_declare_the_same_event_name():
    # Jmena se jmenuji podle apky, takze si dve apky nemohou prebit udalost.
    instance = vb.Instance()
    for app_id in ("prvni", "druha"):
        instance.app.register(
            app_id, kind="panel", scope="app", backend=OpenApp(),
            events={"submit": {"needs": "write", "profile": "request"}},
        )
    assert instance.events.get("prvni.submit") is not None
    assert instance.events.get("druha.submit") is not None


def test_an_app_event_obeys_the_registry_invariant():
    # Tyz strojovy test jako u vestavenych udalosti: anonym na skryte plose
    # nedosahne na handler.
    instance = vb.Instance(default_access=[])
    instance.app.register(
        "example.hello", kind="panel", scope="app", backend=OpenApp(),
        events={"hello_submit": {"needs": "write", "profile": "request"}},
    )
    screen = instance.screen.open(id="tajna")
    window = screen.window.open("panel", id="h")
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
    instance.screen.open(id="infra").window.open("graph", id="net", app="workbench.graph")
    assert "subject_id" in backend.subjects[-1]


def test_the_app_may_mint_the_handle_itself():
    # Obsah muze vzniknout na apce driv, nez existuje jakekoli viewBase.
    backend = OpenApp()
    instance = vb.Instance()
    instance.app.register("a", kind="graph", scope="explicit", backend=backend)
    handle = instance.app.get("a").new_content(mint_at_app=True)
    assert handle == "app_minted_1"


def test_the_app_can_no_longer_refuse_a_connection():
    # Strojova kontrola skrtu: kdyby se ta cesta vratila, vratila by se s ni
    # i moznost, ze o pravech rozhoduje apka.
    import viewbase.runtime.content as content_module

    assert not hasattr(content_module, "ContentRefused")
    assert not hasattr(content_module.ContentState, "REFUSED")


def test_the_app_contract_no_longer_lists_content():
    import inspect

    from viewbase.runtime.content import AppBackend

    assert not hasattr(AppBackend, "list_content")
    assert list(inspect.signature(AppBackend.open_content).parameters) == [
        "self", "handle", "spec", "subject",
    ]


# ===========================================================================
# Vlastnik obsahu (D-41, D-50)
# ===========================================================================


def test_content_records_who_created_it():
    instance = instance_with()
    w = instance.screen.open(id="infra").window.open("graph", id="net", app="workbench.graph")
    assert instance.content.created_by(w.app.handle) is not None


def test_the_creator_is_the_caller_who_opened_it():
    instance = instance_with()
    screen = instance.screen.open(id="infra")
    w = screen.window.open(
        "graph", id="net", app="workbench.graph", by=Caller.for_user("hana")
    )
    assert instance.content.created_by(w.app.handle) == "user:hana"


def test_a_destructive_action_is_for_the_founder_or_the_administrator():
    # D-50: prejmenovat, zrusit a menit prava smi ZAKLADATEL objektu nebo
    # spravce - odvozene, ne deklarovane. V ACL zadne 'manage' neni.
    instance = instance_with()
    screen = instance.screen.open(id="infra")
    w = screen.window.open(
        "graph", id="net", app="workbench.graph", by=Caller.for_user("hana")
    )
    handle = w.app.handle

    assert instance.content.may_destroy(handle, Caller.for_user("hana"))
    assert not instance.content.may_destroy(handle, Caller.for_user("petr"))
    assert instance.content.may_destroy(handle, Caller.for_user("s", ["administrator"]))
