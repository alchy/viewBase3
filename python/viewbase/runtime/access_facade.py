"""Fasada nad pristupem: citelny zapis, ktery vede zmenu pres instanci.

Par. 4b rika, ze `Acl` je NEMENNA HODNOTA a meni se pres instanci - ta k ni
muze pripojit kdo, kdy a proc. Par. 4a zaroven dokumentuje zapis, ktery se
cte jako knihovna:

    window.access.read.add("group:ucetni")
    window.access.write.set(["user:hana"])
    window.access.step_up = True

Oboji plati zaroven prave diky teto fasade (D-14): cteni vraci SNIMEK, zapis
jde JEDINOU cestou pres instanci. Fasada neni menitelna `Acl` v prestrojeni -
zadnou `Acl` ven nevydava.

Zavisi na `core`; instanci zna jen jako protokol se dvema metodami, aby
nevznikl kruhovy import.
"""
from __future__ import annotations

from typing import Protocol

from ..core.access import Acl, Verb
from ..core.addressing import Address


class AccessOwner(Protocol):
    """To jedine, co fasada od instance potrebuje."""

    def own_acl(self, address: Address, verb: Verb) -> "Acl | None": ...
    def set_access(self, address: Address, verb: Verb, acl: "Acl") -> None: ...
    def set_step_up(self, address: Address, value: bool) -> None: ...
    def read_step_up(self, address: Address) -> bool: ...


class AclView:
    """Jedno sloveso jednoho objektu.

    `add` a `remove` funguji JEN na objektu, ktery uz vlastni ACL ma. Na
    objektu, ktery dedi, skonci chybou - a je to schvalne (D-25). Kdyby `add`
    na dedicim okne proslo, musi si vybrat mezi dvema vyklady a oba jsou
    spatne:

      * zacit od VLASTNIHO (prazdneho): okno dedici read=[users] se po
        add("group:ucetni") stane viditelnym JEN ucetnim - slovo "pridej"
        viditelnost zuzilo,
      * zacit od EFEKTIVNIHO: vyjde [users, ucetni], jak ctenar ceka, ale
        ZMRAZI SE DEDICNOST a pozdejsi uzeni plochy uz na okno nedosahne.

    Druhy vyklad selhava TISE a OTEVRENE (lide vidi, co nemaji), prvni HLUCNE
    a ZAVRENE. Nevybira se ani jeden: dvojznacnost nezmizi vykladem, zmizi
    tim, ze se v tom miste nedá napsat.
    """

    __slots__ = ("_owner", "_address", "_verb")

    def __init__(self, owner: AccessOwner, address: Address, verb: Verb) -> None:
        self._owner = owner
        self._address = address
        self._verb = verb

    def list(self) -> list[str]:
        """Snimek toho, co na objektu STOJI. Cteni nikdy nevybuchne.

        Objekt, ktery dedi, vraci prazdny seznam - ne zdedene hodnoty. Je to
        odpoved na otazku "co jsem tady nastavil", ne "kdo to vidi".
        """
        own = self._owner.own_acl(self._address, self._verb)
        return [] if own is None else list(own)

    @property
    def inherits(self) -> bool:
        """Bere tenhle objekt prava od rodice?

        `list()` sama o sobe dva ruzne stavy nerozlisi: prazdny seznam vrati
        jak objekt, ktery DEDI, tak objekt s vyslovne prazdnym ACL ("nikdo").
        Model je ale rozlisuje a maji opacne chovani (nalez F-14). `list()`
        proto dal vraci vzdycky seznam - iterovat pres None by bylo horsi nez
        ta nejednoznacnost - a odpoved na "dedis?" je vlastni otazka.
        """
        return self._owner.own_acl(self._address, self._verb) is None

    def set(self, names) -> None:
        """Dej objektu vlastni ACL. Tim mu konci dedeni - a je to videt."""
        self._owner.set_access(self._address, self._verb, Acl.from_iterable(names))

    def add(self, *names: str) -> None:
        self._owner.set_access(self._address, self._verb, self._own().with_added(*names))

    def remove(self, *names: str) -> None:
        self._owner.set_access(self._address, self._verb, self._own().without(*names))

    def _own(self) -> Acl:
        own = self._owner.own_acl(self._address, self._verb)
        if own is None:
            raise ValueError(
                f"{self._address} nema vlastni ACL pro '{self._verb.value}' a dedi ho. "
                f"add/remove by tu muselo hadat, jestli zacit od zdedeneho, nebo od "
                f"prazdneho - a oba vyklady jsou spatne. Napis "
                f"access.{self._verb.value}.set([...]), kdyz chces objektu dat vlastni "
                f"ACL (dedeni tim konci), nebo zmen ACL plochy, kdyz ma zmena platit "
                f"pro celou plochu."
            )
        return own

    def __contains__(self, name: str) -> bool:
        return name in self.list()

    def __repr__(self) -> str:  # pragma: no cover - jen pro ladeni
        return f"<access.{self._verb.value} {self.list()}>"


class AccessFacade:
    """`window.access` / `screen.access`.

    Krok navic je obycejny atribut, protoze se tak i pise
    (`window.access.require_authentication = True`) - ale zapis pod nim vede
    touz cestou a auditue se stejne jako zmena ACL.

    VEREJNE JMENO RIKA, CO SE STANE; VNITRNI JMENO POJMENOVAVA MECHANISMUS.
    Vyvojar pise `require_authentication` a rozumi tomu, aniz by znal pojem
    step-up; uvnitr se ta osa dal jmenuje `step_up`, protoze tam jde
    o mechanismus a ctenarem je knihovna, ne autor aplikace (par. 4b).
    """

    __slots__ = ("_owner", "_address", "read", "write")

    def __init__(self, owner: AccessOwner, address: Address) -> None:
        object.__setattr__(self, "_owner", owner)
        object.__setattr__(self, "_address", address)
        object.__setattr__(self, "read", AclView(owner, address, Verb.READ))
        object.__setattr__(self, "write", AclView(owner, address, Verb.WRITE))

    @property
    def require_authentication(self) -> bool:
        """Chce tenhle objekt kod z autentikatoru, i kdyz ACL projde?"""
        return self._owner.read_step_up(self._address)

    @require_authentication.setter
    def require_authentication(self, value: bool) -> None:
        self._owner.set_step_up(self._address, bool(value))
