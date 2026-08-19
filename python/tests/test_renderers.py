"""Katalog rendereru (D-44, D-45).

Byly tri moznosti, jak resit cizi renderer: verit mu (nevynutitelne),
izolovat ho (u grafu vykonove neunosne), nebo zadny cizi nemit. Prvni dve se
plati porad, treti jednou pri navrhu - a tak APKA NEDODAVA JAVASCRIPT.
`kind` je jmeno rendereru z kuratorovaneho katalogu, ne neco, co si apka
prinese.

Kuratorovany ale neznamena zadratovany: renderer zustava samostatny balik,
takze se do katalogu da pridat i odebrat, jen se to deje pri buildu a projde
to review.
"""
import pytest

import viewbase as vb
from viewbase.core.identity import Caller
from viewbase.runtime.renderers import BUILTIN_KINDS
from conftest import open_window, register_app


class FakeApp:
    def create_content(self, handle, spec, subject):
        return {"handle": handle, "state": {}, "cursor": 1}

    def open_content(self, handle, subject):
        return self.create_content(handle, {}, subject)

    def snapshot(self, handle, subject):
        return {"state": {}, "cursor": 1}

    def apply_event(self, handle, subject, event):
        return []

    def close_content(self, handle):
        pass


# ===========================================================================
# Katalog existuje a je nas (D-44)
# ===========================================================================


def test_the_builtin_kinds_are_in_the_catalogue():
    instance = vb.Instance()
    assert {r.kind for r in instance.renderer.all()} == set(BUILTIN_KINDS)


def test_the_catalogue_matches_the_documented_set():
    # typy-oken.md par. 4. Kdyz do dokumentu pribude typ, ma spadnout tenhle
    # test, ne se to zjistit az u prvniho okna.
    assert set(BUILTIN_KINDS) == {"panel", "doc", "console", "shell", "log", "graph"}


def test_a_renderer_declares_its_data_api():
    # D-45: renderer publikuje datove API a apka produkuje data v tom tvaru.
    instance = vb.Instance()
    assert instance.renderer.get("graph").contract == "graph.v1"


def test_a_renderer_declares_what_it_needs():
    # shell chce klavesy vcetne Esc a Ctrl-C; bez toho nema smysl.
    instance = vb.Instance()
    assert "keyboard-capture" in instance.renderer.get("shell").capabilities


def test_a_renderer_may_declare_a_capability_as_optional():
    # graf: "potrebuje webgl (volitelne; jinak 2D ustup)" - je to volba
    # kvality, ne podminka behu.
    instance = vb.Instance()
    graph = instance.renderer.get("graph")
    assert "webgl" in graph.optional_capabilities
    assert "webgl" not in graph.capabilities


def test_a_renderer_declares_its_local_view_options():
    # Volby, ktere meni jen muj pohled a na server nechodi.
    instance = vb.Instance()
    assert "physics" in instance.renderer.get("graph").view_options


def test_the_catalogue_is_not_hardwired():
    # Kuratorovany != zadratovany: renderer je samostatny balik.
    instance = vb.Instance()
    instance.renderer.register("table", contract="graph.v1")
    assert instance.renderer.get("table").contract == "graph.v1"


def test_the_same_data_can_be_shown_by_more_than_one_renderer():
    # "Zobrazit jako tabulku" bez zasahu do apky.
    instance = vb.Instance()
    instance.renderer.register("table", contract="graph.v1")
    able = {r.kind for r in instance.renderer.speaking("graph.v1")}
    assert able == {"graph", "table"}


def test_two_instances_have_their_own_catalogues():
    prvni = vb.Instance()
    prvni.renderer.register("table", contract="graph.v1")
    assert "table" not in vb.Instance().renderer


# ===========================================================================
# Neznamy kind se odmita (obraceni proti drivejsimu chovani)
# ===========================================================================


def test_a_window_of_an_unknown_kind_is_refused():
    # DRIVE to bylo naopak: kind se neoveroval, aby publikovany typ treti
    # strany nemel horsi cestu. D-44 to obraci - zadny cizi renderer neni,
    # takze neznamy kind je preklep a ma se ozvat hned.
    instance = vb.Instance()
    screen = instance.screen.open(id="infra")
    with pytest.raises(ValueError, match="kind"):
        open_window(screen, "nekdo.jineho.mapa", id="m")


def test_the_refusal_lists_the_catalogue():
    instance = vb.Instance()
    screen = instance.screen.open(id="infra")
    with pytest.raises(ValueError, match="graph"):
        open_window(screen, "neexistuje", id="m")


def test_a_failed_open_on_an_unknown_kind_leaves_no_window_behind():
    instance = vb.Instance()
    screen = instance.screen.open(id="infra")
    with pytest.raises(ValueError):
        open_window(screen, "neexistuje", id="m")
    assert screen.window.all() == ()


def test_an_app_declaring_an_unknown_kind_fails_the_registration():
    # Chyba autora se ma ozvat pri registraci, ne az kdyz nekdo otevre okno.
    instance = vb.Instance()
    with pytest.raises(ValueError, match="kind"):
        register_app(instance, "x", kind="neexistuje", scope="app", backend=FakeApp())


def test_an_app_may_register_for_a_kind_added_to_the_catalogue():
    instance = vb.Instance()
    instance.renderer.register("table", contract="graph.v1")
    register_app(instance, "x", kind="table", scope="app", backend=FakeApp())
    assert "x" in instance.app


# ===========================================================================
# Schopnosti rendereru vs. co instance udeluje (D-40 + D-44)
# ===========================================================================


def test_a_renderer_needing_a_capability_the_instance_refuses_is_refused_at_open():
    # Instance, ktera neudeluje keyboard-capture, nema jak shell vykreslit -
    # a rict to ma pri otevirani, ne az divakovi prestanou chodit klavesy.
    instance = vb.Instance(capabilities=["canvas2d"])
    screen = instance.screen.open(id="infra")
    with pytest.raises(ValueError, match="keyboard-capture"):
        open_window(screen, "shell", id="term")


def test_an_optional_capability_does_not_block_the_window():
    # "webgl volitelne; jinak 2D ustup" - renderer se degraduje, nespadne.
    instance = vb.Instance(capabilities=["canvas2d"])
    screen = instance.screen.open(id="infra")
    assert open_window(screen, "graph", id="net").kind == "graph"


# ===========================================================================
# Co D-44 zrusilo
# ===========================================================================


def test_a_registration_cannot_bring_its_own_client_module():
    # Padly stupne duvery, sandbox i pripinani modulu otiskem (D-33):
    # kdyz apka JS nedodava, neni co pripinat ani co izolovat.
    instance = vb.Instance()
    with pytest.raises(TypeError):
        register_app(instance, "x", kind="panel", scope="app", backend=FakeApp(),
            client_module={"url": "/apps/x/ui.js", "sha256": "abc"},
        )


def test_there_is_no_trust_level_on_a_registration():
    instance = vb.Instance()
    registration = register_app(instance, "x", kind="panel", scope="app", backend=FakeApp())
    assert not hasattr(registration, "trust")
