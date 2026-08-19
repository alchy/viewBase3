"""Instance: skutecny vlastnik stavu.

Ve viewBase2 mel `Project` parametry, ale vlastni stav lezel v modulech
(`log.bus`, `sessions.store`, `identity.provider`, `access.DEFAULT_ACCESS`, ...).
Dusledek: cesta k souboru politiky pretekla z jednoho testu do cele sady,
`reset_state()` musel postupne zapominat cim dal vic veci a testy potrebovaly
autouse fixturu (chyba 3.14).

Tady instance vlastni VSECHNO: registr objektu, registr udalosti, evidenci
kroku navic, auditni stopu i vychozi prava. Dve instance v jednom procesu jsou
samozrejmost a testy si vyrobi vlastni misto resetovani (princip 2).

Instance je zaroven OBJEKT JAKO KAZDY JINY: ma adresu `instance:` a vlastni
ACL, takze se udalosti jeji spravy vyhodnocuji touz funkci `resolve()` jako
vsechno ostatni (D-17).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ..core.access import Access, Acl, Verb
from ..core.addressing import Address, new_id
from ..core.identity import USERS
from .access_facade import AccessFacade
from .apps import AppCollection
from .audit import AuditLog
from .auth import AuthService
from .content import ContentRegistry

#: Schopnosti, ktere instance udeluje, kdyz se nerekne jinak. `fetch-origin`
#: tu zamerne NENI: je to druha cesta ven a chce vedome rozhodnuti spravce
#: (okno-kontrakt.md par. 5).
DEFAULT_CAPABILITIES = ("canvas2d", "webgl", "keyboard-capture", "file-drop")
from .events import EventRegistry, Guard
from .registry import ObjectRegistry
from .renderers import RendererCatalogue
from .screen import Screen
from .sessions import Grants


class ScreenCollection:
    """`instance.screen` - plochy instance."""

    __slots__ = ("_instance",)

    def __init__(self, instance: "Instance") -> None:
        self._instance = instance

    def open(
        self,
        *,
        id: str | None = None,
        title: str | None = None,
        access: Access | None = None,
    ) -> Screen:
        instance = self._instance
        screen_id = id if id is not None else new_id()
        address = Address.screen(screen_id)
        if address in instance.objects:
            raise ValueError(f"plocha uz existuje: {screen_id!r}")

        instance.objects.add(address, access if access is not None else Access())
        screen = Screen(instance, address, title, index=len(instance._screens))
        instance._screens[screen_id] = screen
        return screen

    def get(self, screen_id: str) -> Screen:
        return self._instance._screens[screen_id]

    def close(self, screen_id: str) -> None:
        screen = self._instance._screens.pop(screen_id)
        for window_id in list(screen._windows):
            screen.window.close(window_id)
        self._instance.objects.remove(screen.address)

    def all(self) -> tuple[Screen, ...]:
        return tuple(self._instance._screens.values())

    def __contains__(self, screen_id: str) -> bool:
        return screen_id in self._instance._screens

    def __len__(self) -> int:
        return len(self._instance._screens)


class Instance:
    """Bezici viewBase: plochy, okna, prava, udalosti, audit.

        instance = vb.Instance()
        screen = instance.screen.open(title="Provoz", id="provoz")
        window = screen.window.open("panel", id="mzdy", title="Mzdy")
        window.access.read.add("group:ucetni")

    `default_access` plati pro plochy a okna, ktera zadne ACL nemaji.
    `admin_access` je ACL pro spravu instance a je VYCHOZE ZAVRENE - dostane
    se skrz jen `group:administrator` (vedoma obdoba roota, viz `allowed`).
    """

    def __init__(
        self,
        *,
        default_access: Iterable[str] = (USERS,),
        admin_access: Iterable[str] = (),
        knows_principal: Callable[[str], bool | None] | None = None,
        audit: AuditLog | None = None,
        log_level: str = "info",
        secret: str | bytes | None = None,
        app_timeouts: dict[str, float] | None = None,
        capabilities: Iterable[str] = DEFAULT_CAPABILITIES,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.objects = ObjectRegistry(default_access=Acl.from_iterable(default_access))
        self.events = EventRegistry()
        self.grants = Grants()
        #: Auditni stopa instance. Sanace, redakce a sloupce resi ona; prah
        #: plati na bezne zaznamy, na bezpecnostni nikdy (par. 7).
        self.audit = audit if audit is not None else AuditLog(log_level, clock)
        self._knows_principal = knows_principal
        self._screens: dict[str, Screen] = {}

        # Instance sama sebe zapise jako objekt - ma adresu a vlastni ACL.
        self.objects.add(
            Address.instance_root(), Access(write=Acl.from_iterable(admin_access))
        )
        self.access = AccessFacade(self, Address.instance_root())
        self.screen = ScreenCollection(self)
        # Tajemstvi instance razi rukojeti obsahu. Kdyz se ulozi a predа pri
        # startu, prezijou ulozene rukojeti i restart instance (D-29).
        self._secret = (
            secret.encode("utf-8") if isinstance(secret, str)
            else secret if secret is not None
            else new_id().encode("utf-8")
        )
        self.content = ContentRegistry(
            self._secret, app_timeouts, audit=self._record_from_content, owner=self
        )
        #: Co tahle instance vubec umi udelit. Rozhoduje se pri REGISTRACI
        #: apky, ne za behu v cizim prohlizeci (D-40).
        self.capabilities = frozenset(capabilities)
        #: Co tahle instance umi vykreslit. `kind` je nase vec - apka
        #: JavaScript nedodava nikdy (D-44).
        self.renderer = RendererCatalogue()
        self.app = AppCollection(self)
        #: Jedine autentizacni API pro apky - autor apky ho nevymysli (D-47).
        self.auth = AuthService(self, clock)
        self.guard = Guard(
            events=self.events, objects=self.objects, grants=self.grants,
            contents=self.content,
        )

    # -- jedina cesta ke zmene prav (D-14) -------------------------------

    def own_acl(self, address: Address, verb: Verb) -> Acl | None:
        """ACL NASTAVENE primo na objektu, nebo None, kdyz se dedi.

        Zamerne se NEPTA pres `for_verb`: ten u nenastaveneho `write` padne na
        `read`, coz je spravne pro CTENI prav, ale tady by to znamenalo, ze
        `write.add()` tise zmrazi hodnotu prectenou z `read`.
        """
        access = self.objects.access_of(address)
        return access.read if verb is Verb.READ else access.write

    def set_access(self, address: Address, verb: Verb, new: Acl) -> None:
        """Zmen ACL objektu a zapis o tom auditni zaznam.

        Hodnota `Acl` o auditu nevi nic a vedet nema; kdo/kdy/co pripoji az
        instance, ktera jako jedina vidi cely obraz (par. 4b).
        """
        for name in new:
            self._flag_unknown(name, address)

        current = self.objects.access_of(address)
        replacement = (
            Access(read=new, write=current.write, step_up=current.step_up)
            if verb is Verb.READ
            else Access(read=current.read, write=new, step_up=current.step_up)
        )
        self.objects.replace_access(address, replacement)
        self._security(verb.value, address, verb, ", ".join(sorted(new)))

    def set_step_up(self, address: Address, value: bool) -> None:
        current = self.objects.access_of(address)
        self.objects.replace_access(
            address, Access(read=current.read, write=current.write, step_up=value)
        )
        self._security("require_authentication", address, None, str(value).lower())

    def read_step_up(self, address: Address) -> bool:
        return self.objects.access_of(address).step_up

    # -- audit ------------------------------------------------------------

    #: Kdo zmenu udelal, kdyz to byl vlastni kod knihovny (D-10, par. 4b).
    INTERNAL = "internal"

    def _record(
        self,
        component: str,
        action: str,
        address: Address | None = None,
        verb: Verb | None = None,
        detail: str = "",
        by: str | None = None,
        level: str = "info",
    ) -> None:
        """Bezny auditni zaznam. Podleha prahu.

        `by` je v zaznamu VZDYCKY. U vlastniho kodu knihovny je to `internal`.
        Az budou prava chodit po drate, ponese totez pole skutecneho
        volajiciho; kdyby vzniklo teprve tehdy, nedaji se starsi zaznamy
        porovnat s novejsimi. Prazdne pole je horsi nez pole s hodnotou
        "vlastni kod".
        """
        self.audit.record(
            level, component=component, action=action, by=by or self.INTERNAL,
            address=address, verb=verb, detail=detail,
        )

    def _security(
        self,
        action: str,
        address: Address | None = None,
        verb: Verb | None = None,
        detail: str = "",
        by: str | None = None,
        level: str = "info",
    ) -> None:
        """Bezpecnostni stopa. PRAHU NEPODLEHA.

        Zmena prav sem patri: "kdo co komu otevrel" musi jit dohledat i na
        instanci, ktera bezi s `log_level='error'`.
        """
        self.audit.security(
            level, action=action, by=by or self.INTERNAL,
            address=address, verb=verb, detail=detail,
        )

    def _flag_unknown(self, name: str, address: Address) -> None:
        """Principal, ktereho nezna zdroj identit, je skoro vzdycky preklep.

        Zapis se ale NEODMITNE - identita muze vzniknout pozdeji, treba
        v adresari. Tichy preklep by znamenal okno, ktere nikdo neuvidi, nebo
        pravidlo, ktere nikdy nezabere (B-08).
        """
        if self._knows_principal is None:
            return
        if self._knows_principal(name) is False:
            self._record(
                "access", "unknown_principal", address, None,
                f"{name} neni znam zdroji identit - preklep?", level="warning",
            )

    def _record_from_content(
        self, component: str, action: str, detail: str = "", security: bool = False
    ) -> None:
        """Stopa z obsahu.

        Odmitnuty pristup k obsahu je BEZPECNOSTNI zaznam (pokus sahnout na
        cizi), nedostupny obsah je provozni stav a podleha prahu.
        """
        if security:
            self._security(action, detail=detail, level="warning")
        else:
            self._record(component, action, detail=detail, level="warning")

    def __repr__(self) -> str:  # pragma: no cover - jen pro ladeni
        return f"<Instance screens={len(self._screens)}>"
