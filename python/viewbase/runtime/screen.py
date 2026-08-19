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
        app: str | None = None,
        access: Access | None = None,
    ) -> Window:
        """Otevri okno daneho typu a volitelne ho spoj s apkou.

        `kind` se proti nicemu neoveruje: registr typu zatim neexistuje
        a hlavne publikovany typ treti strany se ma otevrit stejne snadno
        jako vestaveny.

        `app` naopak overuje se, a HNED. Neznama a nedostupna apka jsou dve
        ruzne veci (D-24): `app` mimo registr je chyba autora a ma se ozvat
        okamzite se seznamem registrovanych - prave to chyta preklepy.
        Registrovana apka, ktera neodpovida, je provozni stav a resi se az
        pri volani, aby jedna mrtva apka nezastavila celou instanci.

        Bez `app` je obsah LOKALNI: dodava ho kod, ktery okno otevrel.
        """
        screen = self._screen
        instance = screen._instance
        window_id = id if id is not None else new_id()
        address = Address.window(screen.id, window_id)
        if address in instance.objects:
            raise ValueError(f"okno uz na plose je: {window_id!r}")

        # Nejdriv overit, teprve potom zapsat: polovicne otevrene okno by melo
        # adresu v registru a nikdo by o nem nevedel.
        if app is not None:
            self._check_app(app, kind)

        instance.objects.add(address, access if access is not None else Access())
        window = Window(instance, address, kind, title, app)
        screen._windows[window_id] = window
        return window

    def _check_app(self, app: str, kind: str) -> None:
        registry = self._screen._instance.app
        if app not in registry:
            raise ValueError(
                f"apka {app!r} neni registrovana. Zname apky: "
                f"{', '.join(registry.known()) or '(zadne)'}"
            )
        declared = registry.get(app).kind
        if declared is not None and declared != kind:
            raise ValueError(
                f"apka {app!r} dodava obsah pro kind {declared!r}, ale okno se "
                f"otevira jako {kind!r} - ten renderer by jeji obsah nevykreslil"
            )

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
