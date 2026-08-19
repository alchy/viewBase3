"""Plocha (Amiga screen) a kolekce jejich oken.

Gramatika verejneho API je "kde . objekt . co" (D-19):

    screen.window.open("panel", id="mzdy", title="Mzdy")
    screen.window.get("mzdy")
    screen.window.close("mzdy")
    screen.window.all()

Typ okna je HODNOTA prvniho argumentu, ne jmeno metody. Kdyby existovalo
`open_panel()`, jadro by muselo znat seznam typu a publikovany typ treti
strany by vlastni metodu nikdy nedostal - vestavene typy by mely
privilegovanou cestu (typy-oken.md par. 3).
"""
from __future__ import annotations

from ..core.access import Access
from ..core.addressing import Address, new_id
from .access_facade import AccessFacade, AccessOwner
from .window import Window


class WindowCollection:
    """`screen.window` - okna jedne plochy.

    Jednotne cislo je zamer: je to jmeno kolekce, ne seznam. Prochazeni je
    proto vyslovne `.all()`.
    """

    __slots__ = ("_screen",)

    def __init__(self, screen: "Screen") -> None:
        self._screen = screen

    def open(
        self,
        kind: str,
        *,
        id: str | None = None,
        title: str | None = None,
        access: Access | None = None,
    ) -> Window:
        """Otevri okno daneho typu.

        `kind` se proti nicemu neoveruje: registr typu zatim neexistuje
        a hlavne publikovany typ treti strany se ma otevrit stejne snadno
        jako vestaveny.
        """
        screen = self._screen
        window_id = id if id is not None else new_id()
        address = Address.window(screen.id, window_id)
        if address in screen._instance.objects:
            raise ValueError(f"okno uz na plose je: {window_id!r}")

        screen._instance.objects.add(address, access if access is not None else Access())
        window = Window(screen._instance, address, kind, title)
        screen._windows[window_id] = window
        return window

    def get(self, window_id: str) -> Window:
        return self._screen._windows[window_id]

    def close(self, window_id: str) -> None:
        """Zavri okno: zmizi z plochy, z registru i z evidence kroku navic."""
        window = self._screen._windows.pop(window_id)
        instance = self._screen._instance
        instance.objects.remove(window.address)
        instance.grants.revoke_object(window.address)

    def all(self) -> tuple[Window, ...]:
        return tuple(self._screen._windows.values())

    def __contains__(self, window_id: str) -> bool:
        return window_id in self._screen._windows

    def __len__(self) -> int:
        return len(self._screen._windows)


class Screen:
    """Plocha: titulek, poradi na liste, prava, okna.

    `id` a `index` jsou dve RUZNE veci. viewBase2 mel jeden procesni citac,
    ktery plnil obe role zaroven; jako adresa je rozbity, protoze dva procesy
    vyrobi `screen_id=1` pro dve ruzne plochy (par. 2).
    """

    __slots__ = ("_instance", "_windows", "address", "title", "index", "access", "window")

    def __init__(
        self, instance: AccessOwner, address: Address, title: str | None, index: int
    ) -> None:
        self._instance = instance
        self._windows: dict[str, Window] = {}
        self.address = address
        self.title = title
        self.index = index
        self.access = AccessFacade(instance, address)
        self.window = WindowCollection(self)

    @property
    def id(self) -> str:
        return self.address.screen_id  # type: ignore[return-value]

    def __repr__(self) -> str:  # pragma: no cover - jen pro ladeni
        return f"<Screen {self.address} title={self.title!r}>"
