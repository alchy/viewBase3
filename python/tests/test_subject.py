"""Co apka dostane misto identity - a proc se to musi stavet PER POHLED.

Ctyri nalezy z prvniho skutecneho zapojeni grafove apky (F-17 az F-20):

  F-17  interni otevreni okna poslalo apce 'anonymous', takze kazda apka,
        ktera kontroluje vlastnictvi, takove okno odmitla,
  F-18  spravce se pres okno nedostal k cizimu obsahu,
  F-19  `capabilities` byly vzdycky prazdne, a to strukturalne: "co ten divak
        smi" je vlastnost DVOJICE (volajici, okno), ale subject se stavel
        z Calleru, ktery zadne okno nezna,
  F-20  Protocol popisoval jine volani, nez se delo.
"""
import inspect

import pytest

import viewbase as vb
from viewbase.core.identity import Caller
from viewbase.runtime.content import AppBackend, ContentRefused, ContentState


class RecordingApp:
    def __init__(self):
        self.subjects = []

    def open_content(self, handle, spec, subject):
        self.subjects.append(subject)
        return {"handle": handle, "state": {}, "cursor": 1}

    def snapshot(self, handle, subject):
        self.subjects.append(subject)
        return {"state": {}, "cursor": 1}

    def apply_event(self, handle, subject, event):
        self.subjects.append(subject)
        return []

    def close_content(self, handle):
        pass

    def list_content(self, subject):
        self.subjects.append(subject)
        return []


class OwnershipApp(RecordingApp):
    """Apka, ktera si hlida vlastnictvi obsahu - tedy kazda poradna apka."""

    def open_content(self, handle, spec, subject):
        if subject["subject_id"] == "anonymous":
            raise ContentRefused("anonymnimu volajicimu obsah nezakladam")
        return super().open_content(handle, spec, subject)


def prepared(backend=None, **kwargs):
    instance = vb.Instance(**kwargs)
    instance.app.register(
        "workbench.graph", kind="graph", scope="app", backend=backend or RecordingApp()
    )
    return instance, instance.screen.open(id="infra")


# ===========================================================================
# F-17: vlastni kod musi umet otevrit okno na svuj vlastni obsah
# ===========================================================================


def test_an_internally_opened_window_is_not_anonymous_to_the_app():
    backend = RecordingApp()
    _, screen = prepared(backend)
    screen.window.open("graph", id="net", app="workbench.graph")
    assert backend.subjects[0]["subject_id"] != "anonymous"


def test_the_internal_caller_has_its_own_identity():
    # Kanal instance <-> apka je vzajemne autentizovany, takze tuhle identitu
    # smi apka brat jako duveryhodnou.
    backend = RecordingApp()
    _, screen = prepared(backend)
    screen.window.open("graph", id="net", app="workbench.graph")
    assert backend.subjects[0]["subject_id"] == "service:instance"


def test_an_app_that_refuses_anonymous_still_serves_the_library_code():
    # Tohle je ten bezny pripad, ne rohovy: kod aplikace otevre okno na svuj
    # vlastni obsah.
    _, screen = prepared(OwnershipApp())
    window = screen.window.open("graph", id="net", app="workbench.graph")
    assert window.content_state is ContentState.OK


def test_a_genuinely_anonymous_viewer_is_still_anonymous():
    # Oprava F-17 nesmi udelat z anonyma sluzbu.
    backend = RecordingApp()
    _, screen = prepared(backend)
    window = screen.window.open("graph", id="net", app="workbench.graph")
    window.access.see.set(["group:public"])
    screen.access.see.set(["group:public"])

    window.snapshot_for(Caller.anonymous())

    assert backend.subjects[-1]["subject_id"] == "anonymous"


# ===========================================================================
# F-19: subject se stavi PER POHLED, ne pro volajiciho
# ===========================================================================


def open_for(instance, screen, see, write):
    screen.access.see.set(see)
    screen.access.write.set(write)
    window = screen.window.open("graph", id="net", app="workbench.graph")
    window.access.see.set(see)
    window.access.write.set(write)
    return window


def test_a_viewer_who_may_only_look_gets_read():
    backend = RecordingApp()
    instance, screen = prepared(backend)
    window = open_for(instance, screen, ["group:users"], ["group:ucetni"])

    window.snapshot_for(Caller.for_user("petr"))

    assert backend.subjects[-1]["capabilities"] == ["read"]


def test_a_viewer_who_may_change_things_gets_write_too():
    backend = RecordingApp()
    instance, screen = prepared(backend)
    window = open_for(instance, screen, ["group:users"], ["group:users"])

    window.snapshot_for(Caller.for_user("hana"))

    assert set(backend.subjects[-1]["capabilities"]) >= {"read", "write"}


def test_capabilities_are_a_property_of_the_pair_not_of_the_caller():
    # Tyz clovek, dve okna na tyz obsah, ruzna prava - a tedy ruzne schopnosti.
    backend = RecordingApp()
    instance, screen = prepared(backend)
    screen.access.see.set(["group:users"])
    screen.access.write.set(["group:users"])

    ctouci = screen.window.open("graph", id="a", app="workbench.graph")
    ctouci.access.see.set(["group:users"])
    ctouci.access.write.set(["group:ucetni"])

    pisici = screen.window.open("graph", id="b", app="workbench.graph")
    pisici.access.see.set(["group:users"])
    pisici.access.write.set(["group:users"])

    hana = Caller.for_user("hana")
    ctouci.snapshot_for(hana)
    prvni = backend.subjects[-1]["capabilities"]
    pisici.snapshot_for(hana)
    druhy = backend.subjects[-1]["capabilities"]

    assert "write" not in prvni
    assert "write" in druhy


def test_a_viewer_who_may_not_see_the_window_gets_no_snapshot():
    instance, screen = prepared()
    window = open_for(instance, screen, ["group:ucetni"], ["group:ucetni"])
    assert window.snapshot_for(Caller.for_user("petr")) is None


def test_the_snapshot_reaches_the_app_when_the_viewer_may_see():
    instance, screen = prepared()
    window = open_for(instance, screen, ["group:users"], ["group:users"])
    assert window.snapshot_for(Caller.for_user("hana")) is not None


# ===========================================================================
# F-18: spravce se ma dostat k cizimu obsahu - ale schopnosti, ne skupinami
# ===========================================================================


def test_the_owner_of_the_content_is_told_so():
    backend = RecordingApp()
    instance, screen = prepared(backend)
    screen.access.see.set(["group:users"])
    screen.access.write.set(["group:users"])
    window = screen.window.open(
        "graph", id="net", app="workbench.graph", by=Caller.for_user("hana")
    )
    window.access.see.set(["group:users"])
    window.access.write.set(["group:users"])

    window.snapshot_for(Caller.for_user("hana"))

    assert "own" in backend.subjects[-1]["capabilities"]


def test_someone_else_is_not_told_they_own_it():
    backend = RecordingApp()
    instance, screen = prepared(backend)
    screen.access.see.set(["group:users"])
    screen.access.write.set(["group:users"])
    window = screen.window.open(
        "graph", id="net", app="workbench.graph", by=Caller.for_user("hana")
    )
    window.access.see.set(["group:users"])
    window.access.write.set(["group:users"])

    window.snapshot_for(Caller.for_user("petr"))

    assert "own" not in backend.subjects[-1]["capabilities"]


def test_the_administrator_reaches_a_foreign_content_through_a_capability():
    # F-18 navrhoval poslat apce skupiny. Tohle je tataz vec bez nich: apka
    # dostane UZ ROZHODNUTOU odpoved na otazku, kterou by jinak resila sama.
    backend = RecordingApp()
    instance, screen = prepared(backend)
    screen.access.see.set(["group:users"])
    screen.access.write.set(["group:users"])
    window = screen.window.open(
        "graph", id="net", app="workbench.graph", by=Caller.for_user("hana")
    )
    window.access.see.set(["group:users"])
    window.access.write.set(["group:users"])

    window.snapshot_for(Caller.for_user("spravce", ["administrator"]))

    assert "own" in backend.subjects[-1]["capabilities"]


def test_the_app_still_never_learns_a_group():
    # Review, vyhrada 4: apka nedostane skupiny, ale uz rozhodnute schopnosti.
    # Kdyby je dostala, vznikne druhy model prav vedle naseho a bez auditu.
    backend = RecordingApp()
    instance, screen = prepared(backend)
    window = open_for(instance, screen, ["group:users"], ["group:users"])

    window.snapshot_for(Caller.for_user("hana", ["ucetni", "administrator"]))

    subject = backend.subjects[-1]
    assert set(subject) == {"subject_id", "correlation", "capabilities"}
    assert "ucetni" not in str(subject)
    assert "administrator" not in str(subject)


# ===========================================================================
# F-20: Protocol popisuje to, co se opravdu deje
# ===========================================================================


def test_the_protocol_declares_the_subject_on_open_content():
    parameters = list(inspect.signature(AppBackend.open_content).parameters)
    assert parameters == ["self", "handle", "spec", "subject"]


def test_the_protocol_knows_about_list_content():
    assert hasattr(AppBackend, "list_content")


@pytest.mark.parametrize(
    "method,expected",
    [
        ("open_content", ["self", "handle", "spec", "subject"]),
        ("snapshot", ["self", "handle", "subject"]),
        ("apply_event", ["self", "handle", "subject", "event"]),
        ("close_content", ["self", "handle"]),
        ("list_content", ["self", "subject"]),
    ],
)
def test_every_protocol_method_matches_what_the_runtime_calls(method, expected):
    # Kdo pise apku podle Protocolu, ma podle nej napsat metodu, ktera se
    # opravdu zavola - jinak to spadne az za behu u nej, ne u nas.
    assert list(inspect.signature(getattr(AppBackend, method)).parameters) == expected
