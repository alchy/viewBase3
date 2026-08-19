"""Registr udalosti a JEDINE vynucovaci misto.

Ve viewBase2 se autorizace psala v kazdem handleru zvlast a pet z devitI
udalosti ji nemelo (chyba 3.1). Tady se pozadavek DEKLARUJE pri registraci,
je povinny a vynucuje se na jednom miste - tady.

Dve pravidla, ktera se nesmi ohnout:

1. BRANA PLOCHY PLATI U KAZDE UDALOSTI a nejde vypnout. `needs` rika jen, co
   se zada NAVIC o okno. Ve viewBase2 existovala hodnota `NONE` ve vyznamu
   "nekontroluj nic" a slo pak volat udalosti na plochu, kterou relace vubec
   nevidela (chyba 3.2). Takova hodnota tu neni.

2. BRANA PLOCHY A ACL OKNA SE KONTROLUJI ZVLAST (D-15). Dedicnost odpovida na
   otazku "jake ACL plati pro TENHLE objekt" - neslucuje dve urovne. Past
   z nalezu F-09: okno se `read=[users]` a nenastavenym `write` ma efektivni
   ACL pro zapis [users]; kdyby se kontrolovalo jen okno, uzivatel by psal do
   okna na plose, kde smi zasahovat jen spravce.

KAZDE ROZHODNUTI VRACI DUVOD, ne ano/ne (par. 8). Ve viewBase2 se tri ruzne
priciny hlasily stejnou hlaskou a stalo to hodinu hledani v provozu. Duvod jde
vzdycky do auditu; divakovi se posila tak, aby neprozradil vic, nez ma.

Zavisi na `core` a na `runtime.registry` / `runtime.sessions` (par. 11).
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum

from ..core.access import Verb, allowed
from ..core.addressing import Address
from ..core.identity import Caller
from .registry import ObjectRegistry
from .sessions import Grants


class Needs(Enum):
    """Co udalost zada NAVIC. Brana plochy plati vzdycky a neni tu.

    Enum je UPLNY a nema hodnotu, ktera by kontrolu vypinala.

        INSTANCE  sprava instance; netyka se plochy, ridi se ACL instance
        SCREEN    zasahovat do plochy (menu, otevreni okna)
        READ      videt plochu + videt okno
        WRITE     zasahovat do plochy + videt okno + zasahovat do okna
    """

    INSTANCE = "instance"
    SCREEN = "screen"
    READ = "read"
    WRITE = "write"


class StepUp(Enum):
    """Krok navic jako druha, nezavisla osa - ne pata hodnota `Needs`.

    `EXEMPT` ma JEDINA udalost, `window_unlock`, protoze prave ona je tou
    cestou, kterou se krok navic ziskava. Vyjimka je tim deklarovana a da se
    otestovat; vyjimka schovana v komentari zetli.
    """

    REQUIRED = "required"
    EXEMPT = "exempt"


class Verdict(Enum):
    """Duvod rozhodnuti. Do auditu jde vzdycky."""

    OK = "ok"
    UNKNOWN_EVENT = "unknown_event"  # udalost neni v registru
    WRONG_TARGET = "wrong_target"  # adresa neodpovida tomu, co udalost zada
    SCREEN_CLOSED = "screen_closed"  # brana plochy neprosla
    NOT_IN_ACL = "not_in_acl"  # ACL objektu neprolo
    NO_GRANT = "no_grant"  # chybi krok navic k teto dvojici
    INSTANCE_CLOSED = "instance_closed"  # sprava instance je zavrena


@dataclass(frozen=True, slots=True)
class Decision:
    """Vysledek vynucovani: duvod, ne ano/ne.

    `bool(decision)` je zkratka pro "prosla", aby se volajici kod cetl
    prirozene - ale duvod je porad po ruce pro audit.
    """

    verdict: Verdict

    def __bool__(self) -> bool:
        return self.verdict is Verdict.OK


@dataclass(frozen=True, slots=True)
class Registration:
    """Jeden zaznam v registru udalosti."""

    event: str
    handler: Callable
    needs: Needs
    step_up: StepUp = StepUp.REQUIRED


@dataclass
class EventRegistry:
    """Co se smi volat a co k tomu clovek potrebuje.

    `needs` je POVINNY pojmenovany parametr. Bez nej registrace skonci chybou;
    kdyby mel vychozi hodnotu, byla by to ta nejtissi mozna cesta zpatky
    k chybe 3.1.
    """

    _registrations: dict[str, Registration] = field(default_factory=dict)

    def register(
        self,
        event: str,
        handler: Callable,
        *,
        needs: Needs,
        step_up: StepUp = StepUp.REQUIRED,
    ) -> Registration:
        if event in self._registrations:
            raise ValueError(f"udalost uz je registrovana: {event!r}")
        registration = Registration(event, handler, needs, step_up)
        self._registrations[event] = registration
        return registration

    def registration(self, event: str) -> Registration:
        return self._registrations[event]

    def get(self, event: str) -> Registration | None:
        return self._registrations.get(event)

    def __iter__(self) -> Iterator[Registration]:
        """Prochazeni registru je to, co umozni invarianty nad celkem."""
        return iter(self._registrations.values())

    def __len__(self) -> int:
        return len(self._registrations)


@dataclass
class Guard:
    """Jedine misto, kde se rozhoduje, jestli udalost smi na handler.

    Dostane registr udalosti, registr objektu a evidenci kroku navic. Nic
    jineho nepotrebuje - a proto se da otestovat bez serveru.

    ACL pro spravu instance zvlast NEDOSTAVA: instance je objekt jako kazdy
    jiny, ma adresu `instance:` a jeji prava se ctou touz funkci
    `objects.resolve()` (D-17). Zvlastni pole by byla privilegovana cesta,
    a co ma privilegovanou zkratku, to se prestane testovat jako vsechno
    ostatni (chyba 3.4).
    """

    events: EventRegistry
    objects: ObjectRegistry
    grants: Grants

    def check(
        self, caller: Caller, event: str, target: Address | None = None
    ) -> Decision:
        """Smi tenhle volajici vyvolat tuhle udalost na tehle adrese?"""
        registration = self.events.get(event)
        if registration is None:
            return Decision(Verdict.UNKNOWN_EVENT)

        if registration.needs is Needs.INSTANCE:
            # Pomlcka v tabulce par. 5 znamena "netyka se", nikdy
            # "nekontroluje se": udalost se neptá na plochu, ale ACL instance
            # projit musi. Bez toho by INSTANCE byla `NONE` pod jinym jmenem
            # (nalez F-11, chyba 3.2).
            instance_acl = self.objects.resolve(Address.instance_root(), Verb.WRITE)
            if not allowed(caller.principals, instance_acl):
                return Decision(Verdict.INSTANCE_CLOSED)
            return Decision(Verdict.OK)

        decision = self._check_object(caller, registration.needs, target)
        if not decision:
            return decision
        return self._check_step_up(caller, registration, target)

    def may(self, caller: Caller, needs: Needs, target: Address) -> Decision:
        """Smel by tenhle volajici na tenhle objekt, kdyby o to slo?

        Pouziva se tam, kde neni udalost - typicky pri skladani menu. Vede to
        TOUZ funkci jako `check`, aby nevznikla druha vetev vynucovani: presne
        na tom ve viewBase2 stala chyba 3.1.
        """
        return self._check_object(caller, needs, target)

    # -- dve urovne, kazda zvlast ----------------------------------------

    def _check_object(
        self, caller: Caller, needs: Needs, target: Address | None
    ) -> Decision:
        if target is None:
            return Decision(Verdict.WRONG_TARGET)

        if needs is Needs.SCREEN:
            if target.kind != "screen":
                return Decision(Verdict.WRONG_TARGET)
            screen = target
        else:
            if target.kind != "window":
                return Decision(Verdict.WRONG_TARGET)
            screen = target.parent  # type: ignore[assignment]

        # 1. Brana plochy - vzdycky, jako prvni a proti ACL PLOCHY.
        #    Vidoucí udalost chce videt plochu, zasahujici do ni zasahovat.
        gate = Verb.READ if needs is Needs.READ else Verb.WRITE
        if not allowed(caller.principals, self.objects.resolve(screen, gate)):
            return Decision(Verdict.SCREEN_CLOSED)

        if needs is Needs.SCREEN:
            return Decision(Verdict.OK)

        # 2. Az potom okno, proti ACL OKNA. Slucovat to s bodem 1 nejde:
        #    dedicnost resi jeden objekt, ne dve urovne (F-09).
        if not allowed(caller.principals, self.objects.resolve(target, Verb.READ)):
            return Decision(Verdict.NOT_IN_ACL)
        if needs is Needs.WRITE and not allowed(
            caller.principals, self.objects.resolve(target, Verb.WRITE)
        ):
            return Decision(Verdict.NOT_IN_ACL)
        return Decision(Verdict.OK)

    def _check_step_up(
        self, caller: Caller, registration: Registration, target: Address | None
    ) -> Decision:
        """Krok navic: druha, nezavisla osa.

        Neplati pro nej vyjimka spravce - `allowed` pousti administratora skrz
        ACL, ale krok navic se pta na neco jineho ("jsi to fakt ty, ted").
        """
        if registration.step_up is StepUp.EXEMPT:
            return Decision(Verdict.OK)
        assert target is not None  # zaruceno _check_object
        if not self.objects.step_up_at(target):
            return Decision(Verdict.OK)
        if not self.grants.holds(caller.session, target):
            return Decision(Verdict.NO_GRANT)
        return Decision(Verdict.OK)
