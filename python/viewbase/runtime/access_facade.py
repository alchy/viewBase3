"""Fasada nad pristupem: citelny zapis, ktery vede zmenu pres instanci.

Par. 4b rika, ze `Acl` je NEMENNA HODNOTA a meni se pres instanci - ta k ni
muze pripojit kdo, kdy a proc. Par. 4a zaroven dokumentuje zapis, ktery se
cte jako knihovna:

    window.access.see.add("group:ucetni")
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

    def own_acl(self, address: Address, verb: Verb) -> "Acl": ...
    def set_access(self, address: Address, verb: Verb, acl: "Acl") -> None: ...
    def set_step_up(self, address: Address, value: bool) -> None: ...
    def read_step_up(self, address: Address) -> bool: ...


class AclView:
    """Jedno sloveso jednoho objektu.

    `add` a `remove` pracuji nad ACL, ktere je na objektu NASTAVENE - ne nad
    zdedenym. Jakmile na objektu neco stoji, prestava dedit; je to tataz
    hranice, kterou uz ma `effective_acl` (prvni nastaveny clen retezu
    vyhrava), jen videna z druhe strany.
    """

    __slots__ = ("_owner", "_address", "_verb")

    def __init__(self, owner: AccessOwner, address: Address, verb: Verb) -> None:
        self._owner = owner
        self._address = address
        self._verb = verb

    def list(self) -> list[str]:
        """Snimek. Zmena vraceneho seznamu prava neovlivni."""
        return list(self._owner.own_acl(self._address, self._verb))

    def set(self, names) -> None:
        self._owner.set_access(self._address, self._verb, Acl.from_iterable(names))

    def add(self, *names: str) -> None:
        current = self._owner.own_acl(self._address, self._verb)
        self._owner.set_access(self._address, self._verb, current.with_added(*names))

    def remove(self, *names: str) -> None:
        current = self._owner.own_acl(self._address, self._verb)
        self._owner.set_access(self._address, self._verb, current.without(*names))

    def __contains__(self, name: str) -> bool:
        return name in self._owner.own_acl(self._address, self._verb)

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

    __slots__ = ("_owner", "_address", "see", "write")

    def __init__(self, owner: AccessOwner, address: Address) -> None:
        object.__setattr__(self, "_owner", owner)
        object.__setattr__(self, "_address", address)
        object.__setattr__(self, "see", AclView(owner, address, Verb.SEE))
        object.__setattr__(self, "write", AclView(owner, address, Verb.WRITE))

    @property
    def require_authentication(self) -> bool:
        """Chce tenhle objekt kod z autentikatoru, i kdyz ACL projde?"""
        return self._owner.read_step_up(self._address)

    @require_authentication.setter
    def require_authentication(self, value: bool) -> None:
        self._owner.set_step_up(self._address, bool(value))
