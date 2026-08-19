"""Registrace apky: objekt s pravy, deklarace, ktere se overuji, a pripojeni
k obsahu, ktere smi apka odmitnout (D-36 az D-41, B-16).
"""
import pytest

import viewbase as vb
from viewbase.core.access import Acl, Verb
from viewbase.core.addressing import Address
from viewbase.core.identity import ADMINISTRATOR, USERS, Caller
from viewbase.runtime.content import ContentRefused, ContentState


class FakeApp:
    def __init__(self, known=(), listing=None):
        self.known = set(known)
        self.listing = listing or []
        self.opened = []
        self.subjects = []

    def open_content(self, handle, spec, subject):
        self.subjects.append(subject)
        if handle is None:  # apka si rukojet razi sama
            handle = "app_minted_1"
            self.known.add(handle)
        elif handle not in self.known:
            raise ContentRefused(f"rukojet {handle} neznam")
        self.opened.append(handle)
        return {"handle": handle, "state": {}, "cursor": 1}

    def snapshot(self, handle, subject):
        return {"state": {}, "cursor": 1}

    def apply_event(self, handle, subject, event):
        return []

    def close_content(self, handle):
        self.known.discard(handle)

    def list_content(self, subject):
        self.subjects.append(subject)
        return self.listing


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
    instance.app.get("workbench.graph").access.see.set(["group:ucetni"])
    acl = instance.objects.resolve(Address.app("workbench.graph"), Verb.SEE)
    assert acl == Acl.of("group:ucetni")


def test_the_launcher_shows_only_apps_the_viewer_may_see():
    # Spoustec je vec WORKBENCHE - stavi ho z registru apek a filtruje nasim
    # modelem. Apka do nej nic nevklada.
    instance = instance_with()
    instance.app.register("tajna", kind="panel", scope="app", backend=OpenApp())
    instance.app.get("tajna").access.see.set(["group:ucetni"])

    visible = {r.app_id for r in instance.app.visible_to(Caller.for_user("petr"))}
    assert visible == {"workbench.graph"}


def test_the_launcher_shows_the_hidden_app_to_those_who_may_see_it():
    instance = instance_with()
    instance.app.get("workbench.graph").access.see.set(["group:ucetni"])
    visible = instance.app.visible_to(Caller.for_user("hana", ["ucetni"]))
    assert [r.app_id for r in visible] == ["workbench.graph"]


def test_the_administrator_sees_every_app():
    instance = instance_with()
    instance.app.get("workbench.graph").access.see.set([])
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
# Pripojeni k obsahu: subjekt a odmitnuti (D-38, D-39)
# ===========================================================================


def test_open_content_gets_the_subject():
    # Bez subjektu plati "kdo zna rukojet, dostane obsah" - a to rusi vetu
    # "rukojet identifikuje, neopravnuje".
    backend = OpenApp()
    instance = instance_with(backend)
    instance.screen.open(id="infra").window.open("graph", id="net", app="workbench.graph")
    assert "subject_id" in backend.subjects[-1]


def test_an_app_may_refuse_the_connection():
    backend = FakeApp(known=())  # nezna zadnou rukojet
    instance = instance_with(backend)
    w = instance.screen.open(id="infra").window.open("graph", id="net", app="workbench.graph")
    assert w.content_state is ContentState.REFUSED


def test_a_refusal_is_not_the_same_as_an_outage():
    # Odmitnuti je normalni odpoved, ne chyba - a ram ma rict neco jineho.
    backend = FakeApp(known=())
    instance = instance_with(backend)
    w = instance.screen.open(id="infra").window.open("graph", id="net", app="workbench.graph")
    assert w.content_state is not ContentState.UNAVAILABLE


def test_an_unknown_handle_is_refused_never_silently_created():
    # Tiche zalozeni by po preklepu dalo divakovi prazdny obsah a on si mysli,
    # ze prisel o data.
    backend = FakeApp(known={"vb1_znama"})
    instance = instance_with(backend)
    w = instance.screen.open(id="infra").window.open(
        "graph", id="net", app="workbench.graph", handle="vb1_preklep"
    )
    assert w.content_state is ContentState.REFUSED
    assert backend.opened == []


def test_a_known_handle_is_attached():
    backend = FakeApp(known={"vb1_znama"})
    instance = instance_with(backend)
    w = instance.screen.open(id="infra").window.open(
        "graph", id="net", app="workbench.graph", handle="vb1_znama"
    )
    assert w.content_state is ContentState.OK


def test_the_app_may_mint_the_handle_itself():
    # Obsah muze vzniknout na apce driv, nez existuje jakekoli viewBase.
    backend = OpenApp()
    instance = vb.Instance()
    instance.app.register("a", kind="graph", scope="explicit", backend=backend)
    handle = instance.app.get("a").new_content(mint_at_app=True)
    assert handle == "app_minted_1"


def test_a_refused_content_is_written_to_the_audit():
    instance = instance_with(FakeApp(known=()))
    instance.screen.open(id="infra").window.open("graph", id="net", app="workbench.graph")
    assert any(r.action == "content_refused" for r in instance.audit)


# ===========================================================================
# Vyber obsahu ze seznamu (D-37) a jeho vlastnik (D-41)
# ===========================================================================


def test_the_app_lists_what_the_viewer_may_pick():
    backend = OpenApp()
    backend.listing = [{"handle": "vb1_a", "name": "Graph #1", "last_used_at": 1}]
    instance = instance_with(backend)
    listed = instance.app.get("workbench.graph").list_content(Caller.for_user("hana"))
    assert listed[0]["name"] == "Graph #1"


def test_listing_passes_the_subject_so_the_app_can_filter():
    # Vlastnictvi obsahu jsou data APKY; my rozhodujeme o oknech.
    backend = OpenApp()
    instance = instance_with(backend)
    instance.app.get("workbench.graph").list_content(Caller.for_user("hana"))
    assert backend.subjects[-1]["subject_id"] == "user:hana"


def test_listing_from_a_broken_app_is_an_empty_list_not_a_crash():
    class Dead(OpenApp):
        def list_content(self, subject):
            raise ConnectionError("spadla")

    instance = instance_with(Dead())
    assert instance.app.get("workbench.graph").list_content(Caller.for_user("hana")) == []


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


def test_a_destructive_action_is_for_the_owner_or_the_administrator():
    # Jeden obsah muze byt ve dvou oknech s ruznymi ACL (D-30). Bez vlastnika
    # by pravo psat v jednom okne znamenalo pravo znicit obsah videny v druhem.
    instance = instance_with()
    screen = instance.screen.open(id="infra")
    w = screen.window.open(
        "graph", id="net", app="workbench.graph", by=Caller.for_user("hana")
    )
    handle = w.app.handle

    assert instance.content.may_destroy(handle, Caller.for_user("hana"))
    assert not instance.content.may_destroy(handle, Caller.for_user("petr"))
    assert instance.content.may_destroy(handle, Caller.for_user("s", ["administrator"]))
