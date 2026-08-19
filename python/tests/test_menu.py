"""Menu okna: dve skupiny a rozdil, ktery ma byt videt (D-46, D-35).

    View        volby RENDEREU - meni jen muj pohled, na server nechodi,
                nikdy zasedle
    <jmeno>     polozky APKY - meni obsah vsem, jdou pres brany, muzou byt
                zasedle
    Options     zustava workbenchi

Rozdil mezi "meni jen muj pohled" a "meni obsah vsem, a muze mi byt zakazane"
je skutecny a ma byt videt. Dve skupiny zaroven rusi potrebu oddelovace,
poradi a jmennych kolizi.

Serverove polozky deklaruje APKA pri registraci - kdyby je smel vyhlasit
renderer, urcoval by si klient vlastni autorizaci (rodina chyb 3.1 a 3.2).
"""
import pytest

import viewbase as vb
from viewbase.core.identity import Caller
from conftest import open_window, register_app


class FakeApp:
    def __init__(self, view=None):
        self.view = view

    def open_content(self, handle, spec, subject):
        answer = {"handle": handle, "state": {}, "cursor": 1}
        if self.view is not None:
            answer["view"] = self.view
        return answer

    def snapshot(self, handle, subject):
        return {"state": {}, "cursor": 1}

    def apply_event(self, handle, subject, event):
        return []

    def close_content(self, handle):
        pass


MENU = {
    "refresh": {"type": "command", "needs": "read"},
    "autosave": {"type": "toggle", "needs": "write"},
    "mode": {"type": "choice", "needs": "write", "options": ["rychly", "presny"]},
}


def prepared(menu=None, group="Hello", backend=None, **kwargs):
    instance = vb.Instance(**kwargs)
    register_app(instance, "example.hello", kind="graph", scope="app", backend=backend or FakeApp(),
        menu_group=group, menu=menu if menu is not None else dict(MENU),
    )
    screen = instance.screen.open(id="infra")
    window = open_window(screen, "graph", id="net", app="example.hello")
    return instance, screen, window


def groups(menu):
    return [group["group"] for group in menu]


def items_of(menu, group):
    for entry in menu:
        if entry["group"] == group:
            return {item["id"]: item for item in entry["items"]}
    return {}


# ===========================================================================
# Dve skupiny (D-46)
# ===========================================================================


def test_a_window_with_an_app_has_both_groups():
    instance, _, window = prepared()
    assert groups(window.menu_for(Caller.for_user("hana"))) == ["View", "Hello"]


def test_the_app_group_is_named_from_the_registration():
    instance, _, window = prepared(group="Mzdy")
    assert "Mzdy" in groups(window.menu_for(Caller.for_user("hana")))


def test_a_window_without_an_app_has_only_the_view_group():
    instance = vb.Instance()
    window = open_window(instance.screen.open(id="infra"), "graph", id="net")
    assert groups(window.menu_for(Caller.for_user("hana"))) == ["View"]


def test_an_app_without_menu_items_shows_no_group_of_its_own():
    # Prazdna skupina se nezobrazi.
    instance, _, window = prepared(menu={})
    assert groups(window.menu_for(Caller.for_user("hana"))) == ["View"]


def test_a_renderer_without_view_options_shows_no_view_group():
    instance = vb.Instance()
    instance.renderer.register("holy", contract="holy.v1")
    window = open_window(instance.screen.open(id="infra"), "holy", id="w")
    assert groups(window.menu_for(Caller.for_user("hana"))) == []


def test_options_stays_with_the_workbench():
    # Workbench si svou skupinu kresli sam; do menu okna nepatri.
    instance, _, window = prepared()
    assert "Options" not in groups(window.menu_for(Caller.for_user("hana")))


# ===========================================================================
# View: lokalni volby rendereru, nikdy zasedle
# ===========================================================================


def test_the_view_group_comes_from_the_renderer():
    instance, _, window = prepared()
    view = items_of(window.menu_for(Caller.for_user("hana")), "View")
    assert "physics" in view and "dimensions" in view


def test_view_items_are_never_greyed_out_even_for_an_anonymous_viewer():
    # Meni jen muj pohled. Neni co zakazovat a neni koho se ptat.
    instance, _, window = prepared()
    view = items_of(window.menu_for(Caller.anonymous()), "View")
    assert all(item["enabled"] for item in view.values())


def test_a_view_choice_offers_its_options():
    instance, _, window = prepared()
    assert items_of(window.menu_for(Caller.for_user("hana")), "View")["dimensions"][
        "options"
    ] == ["2D", "3D"]


def test_the_app_may_set_a_default_for_a_view_option():
    # "view blok v open_content": apka smi rict, jak ma okno zacit.
    instance, _, window = prepared(backend=FakeApp(view={"physics": False}))
    assert items_of(window.menu_for(Caller.for_user("hana")), "View")["physics"][
        "value"
    ] is False


def test_the_app_cannot_remove_a_view_option():
    # Smi nastavit vychozi hodnoty, ne je odebirat; co pro dana data nedava
    # smysl, schova si renderer sam.
    instance, _, window = prepared(backend=FakeApp(view={"physics": False}))
    view = items_of(window.menu_for(Caller.for_user("hana")), "View")
    assert {"physics", "dimensions", "splines", "highlight"} <= set(view)


def test_a_default_for_something_the_renderer_does_not_have_is_ignored():
    instance, _, window = prepared(backend=FakeApp(view={"vymysleno": True}))
    assert "vymysleno" not in items_of(window.menu_for(Caller.for_user("hana")), "View")


def test_a_default_for_something_the_renderer_does_not_have_is_audited():
    # Tise to zahodit by znamenalo, ze autor apky hleda, proc se jeho volba
    # neprojevila.
    instance, _, window = prepared(backend=FakeApp(view={"vymysleno": True}))
    assert any(r.action == "unknown_view_option" for r in instance.audit)


# ===========================================================================
# Skupina apky: jde pres brany a muze byt zasedla
# ===========================================================================


def test_an_app_item_the_viewer_may_use_is_enabled():
    instance, screen, window = prepared()
    window.access.write.set(["group:users"])
    screen.access.write.set(["group:users"])
    items = items_of(window.menu_for(Caller.for_user("hana")), "Hello")
    assert items["autosave"]["enabled"]


def test_an_app_item_the_viewer_may_not_use_is_greyed_out_not_hidden():
    # Zasedla polozka rika "tohle jde, ale ne tobe" - a to je uzitecne prave
    # tam, kde objekt divak VIDI.
    instance, screen, window = prepared()
    screen.access.read.set(["group:users"])
    window.access.read.set(["group:users"])
    window.access.write.set(["group:ucetni"])
    items = items_of(window.menu_for(Caller.for_user("hana")), "Hello")
    assert "autosave" in items
    assert not items["autosave"]["enabled"]


def test_the_read_only_item_stays_usable_when_writing_does_not():
    instance, screen, window = prepared()
    screen.access.read.set(["group:users"])
    window.access.read.set(["group:users"])
    window.access.write.set(["group:ucetni"])
    items = items_of(window.menu_for(Caller.for_user("hana")), "Hello")
    assert items["refresh"]["enabled"]


def test_a_viewer_without_read_on_the_screen_gets_no_menu_at_all():
    # Objekt mimo ACL se chova, jako by neexistoval - vcetne jeho menu.
    instance, screen, window = prepared()
    screen.access.read.set(["group:ucetni"])
    assert window.menu_for(Caller.for_user("petr")) == []


def test_the_app_group_is_computed_through_the_same_guard_as_events():
    # Zadna druha vetev: polozka menu JE udalost a rozhoduje o ni tyz Guard.
    instance, screen, window = prepared()
    screen.access.write.set(["group:users"])
    window.access.write.set(["group:users"])
    caller = Caller.for_user("hana")
    assert bool(instance.guard.check(caller, "example.hello.autosave", window.address))
    assert items_of(window.menu_for(caller), "Hello")["autosave"]["enabled"]


# ===========================================================================
# Destruktivni polozky (D-35, D-41)
# ===========================================================================


DESTRUCTIVE = {
    "wipe": {"type": "command", "needs": "write", "destructive": True},
}


def test_a_destructive_item_needs_at_least_write():
    instance = vb.Instance()
    with pytest.raises(ValueError, match="destructive"):
        register_app(instance, "x", kind="graph", scope="app", backend=FakeApp(), menu_group="X",
            menu={"wipe": {"type": "command", "needs": "read", "destructive": True}},
        )


def test_a_destructive_item_is_for_the_owner_of_the_content():
    # Jeden obsah muze byt ve dvou oknech s ruznymi ACL: pravo psat v jednom
    # okne nesmi znamenat pravo znicit obsah videny v druhem.
    instance = vb.Instance()
    register_app(instance, "example.hello", kind="graph", scope="app", backend=FakeApp(),
        menu_group="Hello", menu=dict(DESTRUCTIVE),
    )
    screen = instance.screen.open(id="infra")
    screen.access.write.set(["group:users"])
    window = open_window(screen, 
        "graph", id="net", app="example.hello", by=Caller.for_user("hana")
    )
    window.access.write.set(["group:users"])

    assert items_of(window.menu_for(Caller.for_user("hana")), "Hello")["wipe"]["enabled"]
    assert not items_of(window.menu_for(Caller.for_user("petr")), "Hello")["wipe"]["enabled"]


def test_the_administrator_may_use_a_destructive_item_on_a_foreign_content():
    instance = vb.Instance()
    register_app(instance, "example.hello", kind="graph", scope="app", backend=FakeApp(),
        menu_group="Hello", menu=dict(DESTRUCTIVE),
    )
    screen = instance.screen.open(id="infra")
    window = open_window(screen, 
        "graph", id="net", app="example.hello", by=Caller.for_user("hana")
    )
    admin = Caller.for_user("spravce", ["administrator"])
    assert items_of(window.menu_for(admin), "Hello")["wipe"]["enabled"]


# ===========================================================================
# Deklarace se overuje pri registraci, ne az v prohlizeci
# ===========================================================================


def test_a_menu_item_without_needs_fails_the_registration():
    instance = vb.Instance()
    with pytest.raises(ValueError, match="needs"):
        register_app(instance, "x", kind="graph", scope="app", backend=FakeApp(), menu_group="X",
            menu={"neco": {"type": "command"}},
        )


def test_a_menu_item_of_an_unknown_type_fails_the_registration():
    instance = vb.Instance()
    with pytest.raises(ValueError, match="type"):
        register_app(instance, "x", kind="graph", scope="app", backend=FakeApp(), menu_group="X",
            menu={"neco": {"type": "posuvnik", "needs": "write"}},
        )


def test_a_choice_without_options_fails_the_registration():
    instance = vb.Instance()
    with pytest.raises(ValueError, match="options"):
        register_app(instance, "x", kind="graph", scope="app", backend=FakeApp(), menu_group="X",
            menu={"mode": {"type": "choice", "needs": "write"}},
        )


def test_a_menu_without_a_group_name_fails_the_registration():
    instance = vb.Instance()
    with pytest.raises(ValueError, match="menu_group"):
        register_app(instance, "x", kind="graph", scope="app", backend=FakeApp(), menu=dict(MENU),
        )


def test_a_group_name_that_would_not_fit_the_bar_fails_the_registration():
    # Strop delky: jmeno kresli workbench a lista neni nafukovaci.
    instance = vb.Instance()
    with pytest.raises(ValueError, match="menu_group"):
        register_app(instance, "x", kind="graph", scope="app", backend=FakeApp(),
            menu_group="P" * 100, menu=dict(MENU),
        )


def test_a_menu_item_becomes_an_event_in_the_registry():
    # Polozka menu JE udalost - jinak by existovala druha cesta k handleru
    # a ta by se prestala kontrolovat (chyba 3.1).
    instance, _, _ = prepared()
    assert instance.events.get("example.hello.autosave") is not None


def test_a_menu_item_cannot_collide_with_a_declared_event():
    instance = vb.Instance()
    with pytest.raises(ValueError):
        register_app(instance, "x", kind="graph", scope="app", backend=FakeApp(), menu_group="X",
            events={"submit": {"needs": "write", "profile": "request"}},
            menu={"submit": {"type": "command", "needs": "write"}},
        )


def test_a_failed_menu_declaration_leaves_no_app_behind():
    instance = vb.Instance()
    with pytest.raises(ValueError):
        register_app(instance, "x", kind="graph", scope="app", backend=FakeApp(), menu_group="X",
            menu={"neco": {"type": "posuvnik", "needs": "write"}},
        )
    assert "x" not in instance.app
    assert instance.events.get("x.neco") is None
