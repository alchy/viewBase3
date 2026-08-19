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
from viewbase.runtime.content import AppBackend, ContentState
from conftest import open_window, register_app


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


class OwnershipApp(RecordingApp):
    """Apka, ktera si vsima, kdo ji vola.

    Po D-52 uz o pravech nerozhoduje - jen si to poznamena. Duvod, proc tenhle
    dvojnik zustava: F-17 byl o tom, ze interni volani prislo jako 'anonymous',
    a to plati dal.
    """

    def open_content(self, handle, spec, subject):
        assert subject["subject_id"] != "anonymous", "interni volani neni anonym"
        return super().open_content(handle, spec, subject)


def prepared(backend=None, **kwargs):
    instance = vb.Instance(**kwargs)
    register_app(instance, "workbench.graph", kind="graph", scope="app", backend=backend or RecordingApp()
    )
    return instance, instance.screen.open(id="infra")


# ===========================================================================
# F-17: vlastni kod musi umet otevrit okno na svuj vlastni obsah
# ===========================================================================


def test_an_internally_opened_window_is_not_anonymous_to_the_app():
    backend = RecordingApp()
    _, screen = prepared(backend)
    open_window(screen, "graph", id="net", app="workbench.graph")
    assert backend.subjects[0]["subject_id"] != "anonymous"


def test_the_internal_caller_has_its_own_identity():
    # Kanal instance <-> apka je vzajemne autentizovany, takze tuhle identitu
    # smi apka brat jako duveryhodnou.
    backend = RecordingApp()
    _, screen = prepared(backend)
    open_window(screen, "graph", id="net", app="workbench.graph")
    assert backend.subjects[0]["subject_id"] == "service:instance"


def test_an_app_that_watches_who_calls_still_serves_the_library_code():
    # Tohle je ten bezny pripad, ne rohovy: kod aplikace otevre okno na svuj
    # vlastni obsah.
    _, screen = prepared(OwnershipApp())
    window = open_window(screen, "graph", id="net", app="workbench.graph")
    assert window.content_state is ContentState.OK


def test_a_genuinely_anonymous_viewer_is_still_anonymous():
    # Oprava F-17 nesmi udelat z anonyma sluzbu.
    backend = RecordingApp()
    _, screen = prepared(backend)
    window = open_window(screen, "graph", id="net", app="workbench.graph")
    window.access.read.set(["group:public"])
    screen.access.read.set(["group:public"])

    window.snapshot_for(Caller.anonymous())

    assert backend.subjects[-1]["subject_id"] == "anonymous"


# ===========================================================================
# F-19: subject se stavi PER POHLED, ne pro volajiciho
# ===========================================================================


def open_for(instance, screen, read, write):
    screen.access.read.set(read)
    screen.access.write.set(write)
    window = open_window(screen, "graph", id="net", app="workbench.graph")
    window.access.read.set(read)
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
    screen.access.read.set(["group:users"])
    screen.access.write.set(["group:users"])

    ctouci = open_window(screen, "graph", id="a", app="workbench.graph")
    ctouci.access.read.set(["group:users"])
    ctouci.access.write.set(["group:ucetni"])

    pisici = open_window(screen, "graph", id="b", app="workbench.graph")
    pisici.access.read.set(["group:users"])
    pisici.access.write.set(["group:users"])

    hana = Caller.for_user("hana")
    ctouci.snapshot_for(hana)
    prvni = backend.subjects[-1]["capabilities"]
    pisici.snapshot_for(hana)
    druhy = backend.subjects[-1]["capabilities"]

    assert "write" not in prvni
    assert "write" in druhy


def test_a_viewer_without_read_on_the_window_gets_no_snapshot():
    instance, screen = prepared()
    window = open_for(instance, screen, ["group:ucetni"], ["group:ucetni"])
    assert window.snapshot_for(Caller.for_user("petr")) is None


def test_the_snapshot_reaches_the_app_when_the_viewer_has_read():
    instance, screen = prepared()
    window = open_for(instance, screen, ["group:users"], ["group:users"])
    assert window.snapshot_for(Caller.for_user("hana")) is not None


# ===========================================================================
# F-18: spravce se ma dostat k cizimu obsahu - ale schopnosti, ne skupinami
# ===========================================================================


def test_the_owner_of_the_content_may_manage_it():
    backend = RecordingApp()
    instance, screen = prepared(backend)
    screen.access.read.set(["group:users"])
    screen.access.write.set(["group:users"])
    window = open_window(screen, 
        "graph", id="net", app="workbench.graph", by=Caller.for_user("hana")
    )
    window.access.read.set(["group:users"])
    window.access.write.set(["group:users"])

    window.snapshot_for(Caller.for_user("hana"))

    assert "manage" in backend.subjects[-1]["capabilities"]


def test_someone_else_may_not_manage_it():
    backend = RecordingApp()
    instance, screen = prepared(backend)
    screen.access.read.set(["group:users"])
    screen.access.write.set(["group:users"])
    window = open_window(screen, 
        "graph", id="net", app="workbench.graph", by=Caller.for_user("hana")
    )
    window.access.read.set(["group:users"])
    window.access.write.set(["group:users"])

    window.snapshot_for(Caller.for_user("petr"))

    assert "manage" not in backend.subjects[-1]["capabilities"]


def test_the_administrator_reaches_a_foreign_content_through_a_capability():
    # F-18 navrhoval poslat apce skupiny. Tohle je tataz vec bez nich: apka
    # dostane UZ ROZHODNUTOU odpoved na otazku, kterou by jinak resila sama -
    # a hlavne se NEDOZVI, jestli je to vlastnik, nebo spravce (D-49).
    backend = RecordingApp()
    instance, screen = prepared(backend)
    screen.access.read.set(["group:users"])
    screen.access.write.set(["group:users"])
    window = open_window(screen, 
        "graph", id="net", app="workbench.graph", by=Caller.for_user("hana")
    )
    window.access.read.set(["group:users"])
    window.access.write.set(["group:users"])

    window.snapshot_for(Caller.for_user("spravce", ["administrator"]))

    assert "manage" in backend.subjects[-1]["capabilities"]


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


def test_the_protocol_no_longer_lists_content():
    # D-52: vyber obsahu filtrovany apkou zanikl spolu s tim, ze apka
    # o pravech nerozhoduje nic.
    assert not hasattr(AppBackend, "list_content")


@pytest.mark.parametrize(
    "method,expected",
    [
        ("open_content", ["self", "handle", "spec", "subject"]),
        ("snapshot", ["self", "handle", "subject"]),
        ("apply_event", ["self", "handle", "subject", "event"]),
        ("close_content", ["self", "handle"]),
    ],
)
def test_every_protocol_method_matches_what_the_runtime_calls(method, expected):
    # Kdo pise apku podle Protocolu, ma podle nej napsat metodu, ktera se
    # opravdu zavola - jinak to spadne az za behu u nej, ne u nas.
    assert list(inspect.signature(getattr(AppBackend, method)).parameters) == expected


# ===========================================================================
# Slovnik schopnosti je uzavreny (D-49)
# ===========================================================================


def test_the_capability_vocabulary_is_exactly_three_words():
    # Testuje se SEZNAM, ne chovani: kdyz nekdo pristi rok pridá ctvrtou
    # schopnost, ma o tom padnout rozhodnuti, ne se to zjistit u apky.
    from viewbase.runtime.window import CAPABILITIES

    assert CAPABILITIES == ("read", "write", "manage")


def test_the_app_is_never_told_a_role():
    # 'own' se cte jako sloveso, 'admin' jmenuje roli. Schopnost pojmenovava,
    # co clovek smi - kdyby apka dostala "je spravce", musela by si pravidlo
    # "spravce smi i cizi" odvodit sama a to je druhe misto, kde totez zije.
    from viewbase.runtime.window import CAPABILITIES

    assert "admin" not in CAPABILITIES
    assert "own" not in CAPABILITIES


def test_capabilities_come_out_in_the_declared_order():
    backend = RecordingApp()
    instance, screen = prepared(backend)
    screen.access.read.set(["group:users"])
    screen.access.write.set(["group:users"])
    window = open_window(screen, 
        "graph", id="net", app="workbench.graph", by=Caller.for_user("hana")
    )
    window.access.read.set(["group:users"])
    window.access.write.set(["group:users"])

    assert window.capabilities_for(Caller.for_user("hana")) == ["read", "write", "manage"]
