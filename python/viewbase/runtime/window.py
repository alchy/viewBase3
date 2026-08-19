"""Okno jako RAM: adresa, typ, titulek, prava.

Obsah okna tady neni a nebude - ten zije cely v `types/` (typy-oken.md).
Runtime vlastni chrome: geometrii, z-order, titulek, zamek.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..core.addressing import Address
from .access_facade import AccessFacade, AccessOwner
from .content import ContentState


@dataclass(frozen=True, slots=True)
class WindowApp:
    """Na co je okno napojene: ktera apka a ktery jeji obsah.

    `handle` je None u scope `session` a `user` - tam se rukojet odvozuje az
    od diváka a pri otevirani okna jeste zadny neni.
    """

    id: str
    scope: str
    handle: str | None = None


class Window:
    """Ram okna na plose.

    Vznika uz s adresou a uz zapsany v registru objektu (par. 2). Mezistav,
    kdy okno existuje, ale jeste nema adresu - a tedy ani prava - tu neni.
    """

    __slots__ = ("_instance", "_app", "address", "kind", "title", "access")

    def __init__(
        self,
        instance: AccessOwner,
        address: Address,
        kind: str,
        title: str | None,
        app: "WindowApp | None" = None,
    ) -> None:
        self._instance = instance
        self._app = app
        self.address = address
        self.kind = kind
        self.title = title
        self.access = AccessFacade(instance, address)

    @property
    def content_state(self) -> ContentState:
        """Stav obsahu z pohledu instance (D-32).

        Okno bez apky je vzdycky OK: lokalni obsah dodava kod, ktery okno
        otevrel, a nema co spadnout.
        """
        if self._app is None or self._app.handle is None:
            return ContentState.OK
        state = self._instance.content.state(self._app.handle)
        return ContentState.OK if state is None else state

    def menu_for(self, caller) -> list[dict]:
        """Menu okna pro konkretniho divaka: dve skupiny a nic navic.

            View        volby RENDEREU - meni jen muj pohled, na server
                        nechodi, NIKDY zasedle,
            <jmeno>     polozky APKY - meni obsah vsem, jdou pres brany
                        a muzou byt zasedle.

        Rozdil mezi "meni jen muj pohled" a "meni obsah vsem, a muze mi byt
        zakazane" je skutecny a ma byt videt. Dve skupiny zaroven rusi potrebu
        oddelovace, poradi a jmennych kolizi.

        `Options` zustava workbenchi a v tomhle seznamu nikdy neni.

        Objekt mimo ACL se chova, jako by neexistoval - vcetne sveho menu.
        """
        from .events import Needs

        instance = self._instance
        if not instance.guard.may(caller, Needs.SEE, self.address):
            return []

        groups = []
        view = self._view_items()
        if view:
            groups.append({"group": "View", "items": view})
        app_items = self._app_items(caller)
        if app_items:
            groups.append({"group": self._registration().menu_group, "items": app_items})
        return groups

    def _registration(self):
        return self._instance.app.get(self._app.id) if self._app else None

    def _view_items(self) -> list[dict]:
        """Volby rendereru s vychozimi hodnotami, ktere smela nastavit apka.

        Apka smi hodnoty NASTAVIT, ne volby odebirat: co pro dana data nedava
        smysl, schova si renderer sam (D-46). Neznama volba se zahodi; zapsala
        se uz pri otevirani okna, ne tady - je to chyba deklarace apky a ma se
        ozvat jednou, ne pri kazdem vykresleni listy.
        """
        renderer = self._instance.renderer.get(self.kind)
        defaults = (
            self._instance.content.view_defaults(self._app.handle) if self._app else {}
        )
        items = []
        for name, spec in renderer.view_options.items():
            item = {"id": name, "type": spec["type"], "enabled": True,
                    "value": defaults.get(name, spec.get("value"))}
            if "options" in spec:
                item["options"] = list(spec["options"])
            items.append(item)
        return items

    def _app_items(self, caller) -> list[dict]:
        """Polozky apky. O kazde rozhoduje TYZ Guard jako o udalostech.

        Zasedla polozka rika "tohle jde, ale ne tobe" - a to je uzitecne prave
        tam, kde objekt divak vidi. Skryt ji by znamenalo, ze se lide ptaji,
        proc to jde kolegovi a jim ne.
        """
        registration = self._registration()
        if registration is None or not registration.menu:
            return []

        instance = self._instance
        items = []
        for name, spec in registration.menu.items():
            enabled = bool(
                instance.guard.check(caller, f"{self._app.id}.{name}", self.address)
            )
            if enabled and spec.get("destructive"):
                # Jeden obsah muze byt ve dvou oknech s ruznymi ACL: pravo psat
                # v jednom nesmi znamenat pravo znicit obsah videny v druhem.
                enabled = self._app.handle is None or instance.content.may_destroy(
                    self._app.handle, caller
                )
            item = {"id": name, "type": spec["type"], "enabled": enabled}
            if "options" in spec:
                item["options"] = list(spec["options"])
            items.append(item)
        return items

    @property
    def app(self) -> "WindowApp | None":
        """Odkud je obsah, nebo None pro lokalni obsah.

        Cte se, ale nenastavuje: vazbu zaklada ten, kdo okno otevira. Kdyby
        sla prepsat za behu, byl by to druhy zpusob, jak okno spojit s apkou -
        a jeden z nich by se prestal kontrolovat.
        """
        return self._app

    @property
    def id(self) -> str:
        return self.address.window_id  # type: ignore[return-value]

    @property
    def screen_id(self) -> str:
        return self.address.screen_id  # type: ignore[return-value]

    def __repr__(self) -> str:  # pragma: no cover - jen pro ladeni
        return f"<Window {self.address} kind={self.kind!r}>"
