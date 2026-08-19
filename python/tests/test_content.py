"""Obsah ma vlastni identitu; okno je pohled (D-26 az D-32).

Puvodne instance obsahu splyvala s oknem - obsah vznikal otevrenim okna
a umiral jeho zavrenim. Tri bezne situace to porusuji: naplnit obsah davkovou
ulohou driv, nez ho nekdo otevre; dve okna na tyz obsah; jeden clovek ve dvou
tabech. Proto ma obsah RUKOJET a okno je jen pohled na nej.
"""
import time

import pytest

import viewbase as vb
from viewbase.core.identity import Caller
from viewbase.runtime.content import ContentState


class FakeApp:
    """Falesna apka. Zaznamenava, co ji instance zavolala."""

    def __init__(self, cursor: int = 271):
        self.opened: list[tuple[str, dict]] = []
        self.closed: list[str] = []
        self.subjects: list[dict] = []
        self._cursor = cursor

    def open_content(self, handle, spec, subject):
        self.opened.append((handle, spec))
        self.subjects.append(subject)
        return {"handle": handle, "state": {"nodes": []}, "cursor": self._cursor}

    def snapshot(self, handle, subject):
        self.subjects.append(subject)
        return {"state": {"nodes": []}, "cursor": self._cursor}

    def apply_event(self, handle, subject, event):
        self.subjects.append(subject)
        return []

    def close_content(self, handle):
        self.closed.append(handle)


class BrokenApp(FakeApp):
    """Spadly kontejner: neodpovi na nic, ne jen na otevreni."""

    def open_content(self, handle, spec, subject):
        raise ConnectionError("kontejner spadl")

    def snapshot(self, handle, subject):
        raise ConnectionError("kontejner spadl")

    def apply_event(self, handle, subject, event):
        raise ConnectionError("kontejner spadl")


class SlowApp(FakeApp):
    def open_content(self, handle, spec, subject):
        time.sleep(0.4)
        return super().open_content(handle, spec, subject)


def with_graph(scope="app", backend=None, **kwargs):
    instance = vb.Instance(**kwargs)
    instance.app.register(
        "workbench.graph", kind="graph", scope=scope, backend=backend or FakeApp()
    )
    return instance, instance.screen.open(id="infra")


# ===========================================================================
# Rukojet: obsah ma identitu nezavislou na okne (D-26)
# ===========================================================================


def test_a_window_bound_to_an_app_gets_a_handle():
    _, screen = with_graph()
    w = screen.window.open("graph", id="net", app="workbench.graph")
    assert w.app.handle


def test_the_handle_is_opaque():
    # Neuhodnutelna, aby neslo instance obsahu vyjmenovat.
    _, screen = with_graph()
    handle = screen.window.open("graph", id="net", app="workbench.graph").app.handle
    assert "net" not in handle
    assert "infra" not in handle


def test_documented_line_two_windows_one_content():
    # apka-kontrakt.md par. 2, doslova.
    instance, screen = with_graph()
    screen2 = instance.screen.open(id="druha")

    w = screen.window.open("graph", id="net", app="workbench.graph")
    w2 = screen2.window.open("graph", id="net2", app="workbench.graph",
                             handle=w.app.handle)

    assert w2.app.handle == w.app.handle


def test_documented_line_content_without_a_window():
    # apka-kontrakt.md par. 2, doslova - davkova uloha plni obsah driv, nez
    # ho nekdo otevre.
    instance, screen = with_graph(scope="explicit")
    h = instance.app.get("workbench.graph").new_content()
    w = screen.window.open("graph", id="net", app="workbench.graph", handle=h)
    assert w.app.handle == h


def test_content_created_without_a_window_is_opened_at_the_app():
    backend = FakeApp()
    instance, _ = with_graph(scope="explicit", backend=backend)
    handle = instance.app.get("workbench.graph").new_content()
    assert backend.opened[0][0] == handle


def test_two_instances_mint_different_handles_for_the_same_address():
    prvni, screen1 = with_graph()
    druha, screen2 = with_graph()
    a = screen1.window.open("graph", id="net", app="workbench.graph").app.handle
    b = screen2.window.open("graph", id="net", app="workbench.graph").app.handle
    assert a != b


def test_a_handle_survives_reopening_the_same_window():
    # Retezec ulozeny v konfiguraci pred mesicem ma dal platit (D-29).
    instance, screen = with_graph(scope="window", secret="tajemstvi")
    first = screen.window.open("graph", id="net", app="workbench.graph").app.handle
    screen.window.close("net")
    second = screen.window.open("graph", id="net", app="workbench.graph").app.handle
    assert second == first


def test_two_instances_with_the_same_secret_agree_on_handles():
    # Az instance restartuje, ulozene rukojeti musi dal platit - proto se da
    # tajemstvi nastavit zvenci.
    def make():
        instance = vb.Instance(secret="tajemstvi")
        instance.app.register("workbench.graph", kind="graph", scope="window",
                              backend=FakeApp())
        return instance.screen.open(id="infra")

    assert (
        make().window.open("graph", id="net", app="workbench.graph").app.handle
        == make().window.open("graph", id="net", app="workbench.graph").app.handle
    )


# ===========================================================================
# scope: jak se rukojet odvodi, kdyz ji nezadate (D-27)
# ===========================================================================


def test_window_scope_gives_each_window_its_own_content():
    _, screen = with_graph(scope="window")
    a = screen.window.open("graph", id="net", app="workbench.graph").app.handle
    b = screen.window.open("graph", id="net2", app="workbench.graph").app.handle
    assert a != b


def test_app_scope_gives_every_window_the_same_content():
    # Spolecna mapa site pro vsechny.
    _, screen = with_graph(scope="app")
    a = screen.window.open("graph", id="net", app="workbench.graph").app.handle
    b = screen.window.open("graph", id="net2", app="workbench.graph").app.handle
    assert a == b


def test_instance_scope_is_one_stream_for_the_whole_instance():
    instance, screen = with_graph(scope="instance")
    druha = instance.screen.open(id="druha")
    a = screen.window.open("graph", id="net", app="workbench.graph").app.handle
    b = druha.window.open("graph", id="jiny", app="workbench.graph").app.handle
    assert a == b


def test_session_and_user_scopes_have_no_handle_at_open_time():
    # Rukojet se u nich odvozuje az od diváka; pri otevirani okna jeste zadny
    # neni. Splynuti session a user je chyba: shell chce dva terminaly, osobni
    # graf jedno okno do tehoz.
    for scope in ("session", "user"):
        _, screen = with_graph(scope=scope)
        w = screen.window.open("graph", id="net", app="workbench.graph")
        assert w.app.handle is None, scope
        assert w.app.scope == scope


def test_explicit_scope_demands_a_handle():
    _, screen = with_graph(scope="explicit")
    with pytest.raises(ValueError, match="handle"):
        screen.window.open("graph", id="net", app="workbench.graph")


def test_an_unknown_scope_is_refused_at_registration():
    instance = vb.Instance()
    with pytest.raises(ValueError):
        instance.app.register("x", kind="graph", scope="kdovico", backend=FakeApp())


# ===========================================================================
# Sdileni obsahu neni sdileni pristupu (D-30)
# ===========================================================================


def test_two_windows_on_one_content_keep_their_own_access():
    instance, screen = with_graph()
    verejne = screen.window.open("graph", id="net", app="workbench.graph")
    tajne = screen.window.open("graph", id="net2", app="workbench.graph")

    verejne.access.see.set(["group:public"])
    tajne.access.see.set(["group:ucetni"])

    assert verejne.app.handle == tajne.app.handle
    assert instance.objects.resolve(verejne.address, vb.Verb.SEE) != instance.objects.resolve(
        tajne.address, vb.Verb.SEE
    )


def test_the_instance_knows_which_windows_look_at_a_content():
    # Delta z obsahu se rozesle pres vsechna okna, ktera na nej koukaji, a
    # kazde si ji prefiltruje samo.
    instance, screen = with_graph()
    a = screen.window.open("graph", id="net", app="workbench.graph")
    b = screen.window.open("graph", id="net2", app="workbench.graph")
    assert set(instance.content.views(a.app.handle)) == {a.address, b.address}


def test_closing_a_window_is_detaching_a_view_not_killing_the_content():
    instance, screen = with_graph()
    a = screen.window.open("graph", id="net", app="workbench.graph")
    handle = a.app.handle
    screen.window.close("net")
    assert instance.content.state(handle) is not None
    assert instance.content.views(handle) == ()


def test_closing_a_window_does_not_call_close_content():
    backend = FakeApp()
    _, screen = with_graph(backend=backend)
    screen.window.open("graph", id="net", app="workbench.graph")
    screen.window.close("net")
    assert backend.closed == []


def test_content_is_closed_only_when_someone_says_so():
    backend = FakeApp()
    instance, screen = with_graph(scope="explicit", backend=backend)
    handle = instance.app.get("workbench.graph").new_content()
    instance.app.get("workbench.graph").close_content(handle)
    assert backend.closed == [handle]


# ===========================================================================
# AppBackend: apka o oknech nevi (D-28)
# ===========================================================================


def test_opening_a_window_opens_the_content_at_the_app():
    backend = FakeApp()
    _, screen = with_graph(backend=backend)
    w = screen.window.open("graph", id="net", app="workbench.graph")
    assert backend.opened[0][0] == w.app.handle


def test_a_second_view_does_not_open_the_content_twice():
    backend = FakeApp()
    _, screen = with_graph(backend=backend)
    screen.window.open("graph", id="net", app="workbench.graph")
    screen.window.open("graph", id="net2", app="workbench.graph")
    assert len(backend.opened) == 1


def test_the_app_never_learns_about_screens_or_windows():
    # ZADNE screen ani window v API apky - mapu okno -> rukojet drzi instance.
    backend = FakeApp()
    _, screen = with_graph(backend=backend)
    screen.window.open("graph", id="net", app="workbench.graph")
    handle, spec = backend.opened[0]
    assert "screen" not in spec
    assert "window" not in spec


def test_the_subject_carries_no_session_id_and_no_groups():
    # Session id je prihlasovaci udaj; skupiny by z apky udelaly druhe misto,
    # kde se rozhoduje o pravech (review, vyhrada 2 a 4).
    backend = FakeApp()
    instance, screen = with_graph(backend=backend)
    w = screen.window.open("graph", id="net", app="workbench.graph")
    caller = Caller.for_user("hana", ["ucetni"], session="s1", correlation="c9f1")

    backend.subjects.clear()
    instance.content.snapshot_for(w.app.handle, caller)

    subject = backend.subjects[-1]
    assert set(subject) == {"subject_id", "correlation", "capabilities"}
    assert "s1" not in str(subject)
    assert "group:ucetni" not in str(subject)


def test_the_subject_says_who_it_is():
    backend = FakeApp()
    instance, screen = with_graph(backend=backend)
    w = screen.window.open("graph", id="net", app="workbench.graph")
    instance.content.snapshot_for(w.app.handle, Caller.for_user("hana", session="s1"))
    assert backend.subjects[-1]["subject_id"] == "user:hana"


def test_an_anonymous_caller_is_anonymous_to_the_app_too():
    backend = FakeApp()
    instance, screen = with_graph(backend=backend)
    w = screen.window.open("graph", id="net", app="workbench.graph")
    instance.content.snapshot_for(w.app.handle, Caller.anonymous())
    assert backend.subjects[-1]["subject_id"] == "anonymous"


def test_the_snapshot_carries_a_cursor():
    # Bez kurzoru se delta bud ztrati, nebo pouzije dvakrat (D-31).
    instance, screen = with_graph(backend=FakeApp(cursor=271))
    w = screen.window.open("graph", id="net", app="workbench.graph")
    assert instance.content.snapshot_for(w.app.handle, Caller.anonymous())["cursor"] == 271


# ===========================================================================
# Kdyz apka nespolupracuje (D-32)
# ===========================================================================


def test_a_healthy_app_leaves_the_content_ok():
    _, screen = with_graph()
    w = screen.window.open("graph", id="net", app="workbench.graph")
    assert w.content_state is ContentState.OK


def test_a_broken_app_does_not_stop_the_window_from_opening():
    # Okno je ram s hlaskou "obsah neni dostupny"; instance neceka.
    _, screen = with_graph(backend=BrokenApp())
    w = screen.window.open("graph", id="net", app="workbench.graph")
    assert w.content_state is ContentState.UNAVAILABLE


def test_a_broken_app_does_not_stop_the_other_windows():
    instance = vb.Instance()
    instance.app.register("rozbita", kind="graph", scope="app", backend=BrokenApp())
    instance.app.register("zdrava", kind="graph", scope="app", backend=FakeApp())
    screen = instance.screen.open(id="infra")

    screen.window.open("graph", id="a", app="rozbita")
    zdrave = screen.window.open("graph", id="b", app="zdrava")
    assert zdrave.content_state is ContentState.OK


def test_a_slow_app_is_treated_like_an_unavailable_one():
    # Pomala apka smi zdrzet sebe, ne vysilaci smycku.
    instance = vb.Instance(app_timeouts={"open_content": 0.05})
    instance.app.register("pomala", kind="graph", scope="app", backend=SlowApp())
    screen = instance.screen.open(id="infra")

    started = time.monotonic()
    w = screen.window.open("graph", id="net", app="pomala")
    elapsed = time.monotonic() - started

    assert w.content_state is ContentState.UNAVAILABLE
    assert elapsed < 0.3, "instance na pomalou apku cekala"


def test_an_unavailable_content_is_written_to_the_audit():
    instance = vb.Instance()
    instance.app.register("rozbita", kind="graph", scope="app", backend=BrokenApp())
    screen = instance.screen.open(id="infra")
    screen.window.open("graph", id="net", app="rozbita")
    assert any(record.action == "content_unavailable" for record in instance.audit)


def test_a_window_without_an_app_is_never_unavailable():
    # Lokalni obsah dodava kod, ktery okno otevrel - nema co spadnout.
    instance = vb.Instance()
    w = instance.screen.open(id="infra").window.open("panel", id="mzdy")
    assert w.content_state is ContentState.OK


def test_asking_a_broken_app_for_a_snapshot_does_not_raise():
    # Vypadek je STAV OKNA, ne chyba: divak vidi ram, ostatni okna bezi dal.
    instance, screen = with_graph(backend=BrokenApp())
    w = screen.window.open("graph", id="net", app="workbench.graph")
    assert instance.content.snapshot_for(w.app.handle, Caller.anonymous()) is None
