"""Registr apek: odkud je obsah.

`kind` a `app_id` jsou dve nezavisle osy (typy-oken.md par. 1) a nekdo je musi
SPOJIT. Dela to ten, kdo okno otevira - nikdy apka sama:

    screen.window.open("panel", id="hello", title="Hello", app="example.hello")

APKA SE NA OKNO NEPRIHLASUJE SAMA. Kdyby mohla, byl by to zpusob, jak se
prilepit na cizi plochu. Zna jen ty instance, ktere dostala; zadne "vypis
plochy" neexistuje a registrace proto nema na plochy ani okna zadny odkaz.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.access import Verb, allowed
from ..core.addressing import Address
from ..core.identity import Caller
from .access_facade import AccessFacade
from .content import SCOPES, ContentRegistry
from .events import Needs

#: Strop delky jmena skupiny v liste - kresli ho workbench a lista neni
#: nafukovaci.
MENU_GROUP_MAX = 24

#: Typy polozek menu. Vic jich neni a zamerne nepribyva.
MENU_ITEM_TYPES = ("command", "toggle", "choice")


@dataclass(frozen=True, slots=True)
class AppRegistration:
    """Co o sobe apka rekla pri registraci - a jak se s ni da mluvit.

    Zamerne tu NENI nic, cim by se apka dostala k plocham nebo oknum: zadne
    `screen`, `window` ani vypis cehokoli. Je to popis zdroje obsahu, ne
    pristupovy bod. Kdyby se apka mohla na okno prihlasit sama, byl by to
    zpusob, jak se prilepit na cizi plochu.
    """

    app_id: str
    kind: str | None = None
    scope: str = "window"
    backend_base_url: str | None = None
    granted: tuple[str, ...] = ()
    refused: tuple[str, ...] = ()
    #: Skupiny, o jejichz clenstvi si apka rekla. Introspekce vrati JEN tyhle
    #: (D-48) - jinak se kazda apka dozvi celou pozici cloveka v organizaci.
    groups_of_interest: tuple[str, ...] = ()
    #: Jmeno skupiny v liste. Kresli ho workbench, apka jen dodava text.
    menu_group: str | None = None
    #: Serverove polozky menu. Deklaruje je APKA - kdyby je smel vyhlasit
    #: renderer, urcoval by si klient vlastni autorizaci (chyby 3.1 a 3.2).
    menu: dict = field(default_factory=dict)
    _content: ContentRegistry | None = field(default=None, repr=False, compare=False)
    access: AccessFacade | None = field(default=None, repr=False, compare=False)

    @property
    def address(self) -> Address:
        return Address.app(self.app_id)

    def new_content(self, spec: dict | None = None, mint_at_app: bool = False) -> str | None:
        """Zaloz obsah BEZ OKNA a vrat jeho rukojet.

        Tohle je ta cesta, kterou davkova uloha naplni graf driv, nez ho nekdo
        otevre - okno se na nej napoji az potom.

        `mint_at_app=True` necha rukojet razit apku (D-39): obsah muze vzniknout
        na apce driv, nez existuje jakekoli viewBase.
        """
        assert self._content is not None
        handle = None if mint_at_app else self._content.mint(
            f"new:{self.app_id}:{new_handle_seed()}"
        )
        handle, _ = self._content.attach(handle, self.app_id, None, spec or {})
        return handle

    def close_content(self, handle: str) -> None:
        """Ukonci obsah. Zavreni OKNA tohle nedela - to je jen odpojeni pohledu."""
        assert self._content is not None
        self._content.close(handle)



def new_handle_seed() -> str:
    from ..core.addressing import new_id

    return new_id()


class AppCollection:
    """`instance.app` - apky, ktere tahle instance zna."""

    __slots__ = ("_registrations", "_content", "_instance")

    def __init__(self, instance) -> None:
        self._registrations: dict[str, AppRegistration] = {}
        self._instance = instance
        self._content = instance.content

    def register(
        self,
        app_id: str,
        *,
        kind: str | None = None,
        scope: str = "window",
        backend=None,
        backend_base_url: str | None = None,
        capabilities: dict | None = None,
        events: dict | None = None,
        groups_of_interest: tuple[str, ...] = (),
        menu_group: str | None = None,
        menu: dict | None = None,
        access=None,
    ) -> AppRegistration:
        """Zapis apku. Vsechno se overuje TED, ne az za behu.

        Chybejici nebo neudelitelna deklarace je chyba registrace: rozhodnuti
        se tim presune na misto, kde se da opravit (konfigurace), misto do
        prohlizece ciziho cloveka (D-40).
        """
        if app_id in self._registrations:
            raise ValueError(f"apka uz je registrovana: {app_id!r}")
        if scope not in SCOPES:
            raise ValueError(f"neznamy scope {scope!r}; zname: {', '.join(SCOPES)}")
        if kind is not None and kind not in self._instance.renderer:
            raise ValueError(
                f"apka {app_id!r} deklaruje neznamy kind {kind!r}; katalog zna: "
                f"{', '.join(self._instance.renderer.known())}"
            )

        granted, refused = self._negotiate(app_id, capabilities or {})
        menu = self._check_menu(app_id, menu_group, menu or {})
        declared = self._check_events(app_id, events or {})
        collisions = set(menu) & set(events or {})
        if collisions:
            raise ValueError(
                f"apka {app_id!r} ma polozku menu i udalost tehoz jmena: "
                f"{', '.join(sorted(collisions))}"
            )
        declared += [
            (f"{app_id}.{name}", {"needs": Needs(spec["needs"])})
            for name, spec in menu.items()
        ]

        address = Address.app(app_id)
        self._instance.objects.add(address, access)
        registration = AppRegistration(
            app_id, kind, scope, backend_base_url, granted, refused,
            tuple(groups_of_interest), menu_group, menu,
            self._content, AccessFacade(self._instance, address),
        )
        self._registrations[app_id] = registration
        self._content.bind_backend(app_id, backend)
        for name, spec in declared:
            self._instance.events.register(name, _app_handler, **spec)
        return registration

    def unregister(self, app_id: str) -> None:
        self._registrations.pop(app_id, None)
        self._instance.objects.remove(Address.app(app_id))

    def visible_to(self, caller: Caller) -> tuple[AppRegistration, ...]:
        """Apky, ktere tenhle divak vubec uvidi (D-36).

        Spoustec je vec WORKBENCHE: stavi ho z registru a filtruje nasim
        modelem. Apka do nej nevklada nic - jinak by mela nastroj, jak si
        pridat cokoli komukoli do listy.
        """
        return tuple(
            registration
            for registration in self._registrations.values()
            if allowed(
                caller.principals,
                self._instance.objects.resolve(registration.address, Verb.READ),
            )
        )

    # -- overeni deklaraci pri registraci --------------------------------

    def _negotiate(self, app_id: str, capabilities: dict) -> tuple[tuple, tuple]:
        """Schopnosti se vyjednavaji PRI REGISTRACI, nikdy za behu.

        Zadost za behu by znamenala bud dialog na divaka, nebo tiche rozsireni
        prav - a ani jedno nechceme.
        """
        grantable = self._instance.capabilities
        required = list(capabilities.get("required", ()))
        optional = list(capabilities.get("optional", ()))

        missing = [name for name in required if name not in grantable]
        if missing:
            raise ValueError(
                f"apka {app_id!r} vyzaduje schopnosti, ktere tahle instance "
                f"neudeluje: {', '.join(missing)}"
            )

        granted = tuple(required) + tuple(n for n in optional if n in grantable)
        refused = tuple(n for n in optional if n not in grantable)
        for name in refused:
            # Apka bezi osekane a VI O TOM - schopnost je nepritomna, ne chyba.
            self._instance._record(
                "app", "capability_refused", detail=f"{app_id}: {name}"
            )
        return granted, refused

    def _check_menu(self, app_id: str, group: str | None, menu: dict) -> dict:
        """Over deklaraci menu. Vsechno se rika TED, ne az v prohlizeci.

        Polozka menu JE udalost, takze musi deklarovat `needs` stejne jako
        kazda jina - jinak by existovala druha cesta k handleru a ta by se
        prestala kontrolovat (chyba 3.1).
        """
        if not menu:
            return {}
        if not group or len(group) > MENU_GROUP_MAX:
            raise ValueError(
                f"apka {app_id!r} deklaruje menu, takze potrebuje menu_group "
                f"o delce 1 az {MENU_GROUP_MAX} znaku"
            )
        for name, spec in menu.items():
            if not isinstance(spec, dict) or "needs" not in spec:
                raise ValueError(
                    f"polozka menu {name!r} apky {app_id!r} nedeklaruje 'needs'"
                )
            kind = spec.get("type")
            if kind not in MENU_ITEM_TYPES:
                raise ValueError(
                    f"polozka menu {name!r} apky {app_id!r} ma neznamy 'type' "
                    f"{kind!r}; zname: {', '.join(MENU_ITEM_TYPES)}"
                )
            if kind == "choice" and not spec.get("options"):
                raise ValueError(
                    f"polozka menu {name!r} apky {app_id!r} je 'choice' a musi "
                    f"mit 'options'"
                )
            if spec.get("destructive") and Needs(spec["needs"]) is not Needs.WRITE:
                # Nevratna akce za slabsim pozadavkem je past: divak ji vidi
                # jako dostupnou a workbench mu ji povoli.
                raise ValueError(
                    f"polozka menu {name!r} apky {app_id!r} je destructive "
                    f"a musi zadat aspon needs='write'"
                )
        return dict(menu)

    def _check_events(self, app_id: str, events: dict) -> list:
        """Udalosti apky vznikaji v REGISTRU, ne vedle nej (B-16, chyba 3.1).

        Jmenuji se `<app_id>.<udalost>`, takze si dve apky nemohou prebit
        udalost - a je z auditu poznat, ci to byla.
        """
        declared = []
        for name, spec in events.items():
            if not isinstance(spec, dict) or "needs" not in spec:
                raise ValueError(
                    f"udalost {name!r} apky {app_id!r} nedeklaruje 'needs'; "
                    f"chybejici polozka neni vychozi hodnota, ale chyba registrace"
                )
            try:
                needs = Needs(spec["needs"])
            except ValueError:
                raise ValueError(
                    f"udalost {name!r} apky {app_id!r} zada neznamy 'needs': "
                    f"{spec['needs']!r}"
                ) from None
            declared.append((f"{app_id}.{name}", {"needs": needs}))
        return declared


    def get(self, app_id: str) -> AppRegistration:
        return self._registrations[app_id]

    def all(self) -> tuple[AppRegistration, ...]:
        return tuple(self._registrations.values())

    def __contains__(self, app_id: str) -> bool:
        return app_id in self._registrations

    def __len__(self) -> int:
        return len(self._registrations)

    def known(self) -> list[str]:
        """Seznam pro chybovou hlasku - prave ten chyta preklepy."""
        return sorted(self._registrations)


def _app_handler(*args, **kwargs):  # pragma: no cover - smeruje se do apky
    """Zastupny handler: udalost se posila apce, ne mistnimu kodu."""
    return None
