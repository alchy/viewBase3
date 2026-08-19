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

from ..core.access import Access, Acl, Verb
from ..core.addressing import Address, new_id
from .access_facade import AccessFacade, AccessOwner
from .window import Window, WindowApp


class Offer:
    """Nabidka: "tuhle apku jde na tehle plose otevrit" (D-54).

    Nabidka prezije vsechno - zavreni okna ji nerusi, prave proto, aby slo
    otevrit znovu. Je to tyz vztah jako obsah vs. pohled, o patro vys:

        nabidka  (deklaruje vyvojar)   prezije vsechno
           | kliknuti
        okno     (pohled)              vznika a zanika
           |
        obsah    (stav u apky)         zije podle scope

    ACL se deklaruje TADY a okno, ktere z nabidky vznikne, ho zdedi.
    """

    __slots__ = ("_screen", "app", "title", "_access", "_content")

    def __init__(self, screen, app, title, access, content) -> None:
        self._screen = screen
        self.app = app
        self.title = title
        self._access = access
        self._content = content

    @property
    def id(self) -> str:
        return self.app.app_id

    def _readable_by(self, caller) -> bool:
        """Pousti obsah, ke kteremu je nabidka pripnuta, tohohle divaka?

        Nabidka bez obsahu se neptá nikoho: obsah vznikne az kliknutim.
        """
        if self._content is None:
            return True
        return self._screen._instance.content.allows_handle(
            self._content.handle, Verb.READ, caller
        )

    def open(self, caller) -> Window:
        """Divak si otevrel okno z nabidky.

        Tohle je JEDINA cesta, jak okno vznikne. Kdyby vedle ni zustalo
        `window.open` v deklaraci, byly by dve cesty - a jedna z nich by se
        drive nebo pozdeji prestala kontrolovat.
        """
        return self._screen.window._create(
            kind=self.app.kind,
            title=self.title,
            app=self.app.app_id,
            handle=self._content.handle if self._content is not None else None,
            access=self._access,
            by=caller,
        )

    def __repr__(self) -> str:  # pragma: no cover - jen pro ladeni
        return f"<Offer {self.app.app_id} on {self._screen.id} title={self.title!r}>"


class OfferCollection:
    """`screen.app` - co jde na tehle plose otevrit."""

    __slots__ = ("_screen", "_offers")

    def __init__(self, screen) -> None:
        self._screen = screen
        self._offers: list[Offer] = []

    def register(
        self,
        app,
        *,
        title: str | None = None,
        read=None,
        write=None,
        require_authentication: bool = False,
        content=None,
    ) -> Offer:
        """Nabidni apku na tehle plose.

        Nesaha se pritom na zadne okno, protoze zadne jeste neni. Bez
        `content=` si obsah vyrobi nabidka sama pri otevreni a zadne vlastni
        ACL nedostane - druha uroven se tim vubec nezapoji (D-59).
        """
        instance = self._screen._instance
        if getattr(app, "instance", None) is not instance:
            raise ValueError(
                f"apka {getattr(app, 'app_id', app)!r} neni registrovana v teto instanci"
            )
        access = Access(
            read=Acl.from_iterable(read) if read is not None else None,
            write=Acl.from_iterable(write) if write is not None else None,
            step_up=require_authentication,
        )
        offer = Offer(self._screen, app, title, access, content)
        self._offers.append(offer)
        return offer

    def all(self) -> tuple[Offer, ...]:
        return tuple(self._offers)

    def get(self, app_id: str) -> Offer:
        for offer in self._offers:
            if offer.app.app_id == app_id:
                return offer
        raise KeyError(app_id)

    def visible_to(self, caller) -> tuple[Offer, ...]:
        """Nabidky, ktere tenhle divak uvidi.

        Rozhoduje PLOCHA a OBSAH - apka ne (D-60). Registrace apky je jen
        deklarace "tenhle kod existuje"; treti ACL nezaviralo nic, co ty dve
        nezavrou taky.

        Nabidka pripnuta k obsahu, na ktery divak nema, se NEUKAZE. Je to ten
        rozdil, ktery dela cely model: tataz nabidka na tez plose se dvema
        lidem chova jinak, protoze rozhodl obsah. A polozit dokument na
        verejnou plochu ho tim nezverejni.
        """
        from ..core.access import Verb, allowed

        instance = self._screen._instance
        if not allowed(
            caller.principals, instance.objects.resolve(self._screen.address, Verb.READ)
        ):
            return ()
        return tuple(
            offer for offer in self._offers if offer._readable_by(caller)
        )

    def __len__(self) -> int:
        return len(self._offers)


class WindowCollection:
    """`screen.window` - okna jedne plochy ZA BEHU.

    Otevirani tu neni: okno vznika tim, ze si ho divak otevre z nabidky
    (`screen.app.register(...)`, pak `offer.open(caller)`). Zustava `get`,
    `all` a `close`.

    Jednotne cislo je zamer: je to jmeno kolekce, ne seznam. Prochazeni je
    proto vyslovne `.all()`.
    """

    __slots__ = ("_screen",)

    def __init__(self, screen: "Screen") -> None:
        self._screen = screen

    def _create(
        self,
        kind: str,
        *,
        id: str | None = None,
        title: str | None = None,
        app: str | None = None,
        handle: str | None = None,
        by=None,
        access: Access | None = None,
    ) -> Window:
        """Vyrob okno. Vola se JEN z nabidky (`Offer.open`).

        Neni to verejna cesta: deklarace okna nevytvari, okno vznika az tim,
        ze si ho divak otevre.

        `kind` je jmeno rendereru z naseho katalogu a overuje se HNED: apka
        JavaScript nedodava, takze neznamy `kind` je preklep a neni na co se
        odvolat (D-44). Zaroven se overi, ze instance umi rendereru dat, co
        potrebuje.

        `app` se overuje taky, a taky hned. Neznama a nedostupna apka jsou dve
        ruzne veci (D-24): `app` mimo registr je chyba autora a ma se ozvat
        okamzite se seznamem registrovanych - prave to chyta preklepy.
        Registrovana apka, ktera neodpovida, je provozni stav a resi se az
        pri volani, aby jedna mrtva apka nezastavila celou instanci.

        Bez `app` je obsah LOKALNI: dodava ho kod, ktery okno otevrel.

        `handle` napoji okno na UZ EXISTUJICI obsah - dve okna pak koukaji na
        totez (D-26). Bez nej se rukojet odvodi ze `scope` apky; u `explicit`
        je povinny, protoze tam obsah zaklada nekdo jiny.
        """
        screen = self._screen
        instance = screen._instance
        window_id = id if id is not None else new_id()
        address = Address.window(screen.id, window_id)
        if address in instance.objects:
            raise ValueError(f"okno uz na plose je: {window_id!r}")

        # Nejdriv overit, teprve potom zapsat: polovicne otevrene okno by melo
        # adresu v registru a nikdo by o nem nevedel.
        instance.renderer.require(kind, instance.capabilities)
        if app is not None:
            self._check_app(app, kind)

        window_app = None
        if app is not None:
            window_app = self._bind_content(app, address, handle, by)

        instance.objects.add(address, access if access is not None else Access())
        window = Window(instance, address, kind, title, window_app)
        screen._windows[window_id] = window
        return window

    def _bind_content(self, app: str, address, handle: str | None, by=None) -> WindowApp:
        """Zjisti rukojet obsahu a napoj na nej pohled."""
        instance = self._screen._instance
        registration = instance.app.get(app)
        scope = registration.scope

        if handle is None:
            if scope == "explicit":
                # Nabidka bez obsahu u `explicit`: dokument vznikne az
                # kliknutim a patri tomu, kdo klikl. Kazde kliknuti je novy
                # dokument - proto se rukojet razi cerstva, ne odvozuje.
                handle = instance.content.mint(f"new:{app}:{new_id()}")
            else:
                handle = instance.content.handle_for(app, scope, address)

        if handle is not None or scope not in ("session", "user"):
            handle, _ = instance.content.attach(
                handle, app, address, {"kind": registration.kind}, by
            )
            self._check_view_defaults(app, address, handle, registration.kind)
        return WindowApp(id=app, scope=scope, handle=handle)

    def _check_view_defaults(self, app: str, address, handle, kind: str | None) -> None:
        """Apka smi nastavit vychozi hodnoty voleb rendereru, ne vymyslet nove.

        Tise zahodit neznamou volbu by znamenalo, ze autor apky hleda, proc se
        jeho nastaveni neprojevilo. Zapisuje se jednou, pri otevirani.
        """
        instance = self._screen._instance
        if handle is None or kind is None or kind not in instance.renderer:
            return
        known = instance.renderer.get(kind).view_options
        for name in instance.content.view_defaults(handle):
            if name not in known:
                instance._record(
                    "app", "unknown_view_option", address,
                    detail=f"{app}: renderer {kind!r} nema volbu {name!r}",
                )

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
        # Zavreni okna je ODPOJENI POHLEDU, ne smrt obsahu (D-26).
        if window.app is not None and window.app.handle is not None:
            instance.content.detach(window.app.handle, window.address)

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

    __slots__ = ("_instance", "_windows", "address", "title", "index", "access",
                 "window", "app")

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
        self.app = OfferCollection(self)

    @property
    def id(self) -> str:
        return self.address.screen_id  # type: ignore[return-value]

    def __repr__(self) -> str:  # pragma: no cover - jen pro ladeni
        return f"<Screen {self.address} title={self.title!r}>"
