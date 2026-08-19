"""Komu se zprava smi dorucit.

Nejdulezitejsi zmena oproti viewBase2. Tam okno vyrobilo akci, akce se
zaradila do fronty, vysilaci smycka na ni nalepila adresni znacky
(`only_sid`, `grant`, `acl`) a pred odeslanim je zase strhla. Publikum bylo
vlastnost DORUCENI, ne zpravy - a kdo pridal novou cestu ven (log stream,
REST push), snadno na nej zapomnel. Presne to se stalo: log okno na verejne
plose rozeslalo auditni stopu cele instance vsem.

Tady je publikum soucasti zpravy od jejiho vzniku (`Message` bez `audience`
nejde vyrobit) a ma jen tri tvary:

    Ref(address, verb)      kdo smi VIDET / ZASAHOVAT do objektu na te adrese
    Session(sid)            prima odpoved jednomu volajicimu
    And(left, right)        oboji zaroven

POZDNI VAZBA JE POVINNA. Tvar se zmrazenou mnozinou principalu tu zamerne
NENI - zprava vyrobena vterinu pred odebranim prav by se dorucila i po nem.
Publikum se proto nepta "kdo to byl", ale "kdo to smi TED". Kdyz ten tvar
neexistuje, nejde ho pouzit omylem.

Vysilaci smycka nevi nic o oknech ani o pravech: dostane pri startu jedinou
funkci `resolve(address, verb) -> Acl` a pta se `audience.allows(caller,
resolve)`. Jedna predana funkce, zadny import napric vrstvami.

Modul zavisi jen na `access`, `addressing` a `identity` (par. 11).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .access import Acl, Verb, allowed
from .addressing import Address
from .identity import Caller

#: Jedina vec, kterou vysilaci smycka o pravech vi.
Resolve = Callable[[Address, Verb], Acl]


class Audience:
    """Publikum zpravy. Vyhodnocuje se proti volajicimu az pri doruceni."""

    __slots__ = ()

    def allows(self, caller: Caller, resolve: Resolve) -> bool:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class Ref(Audience):
    """Kdo smi na objekt na dane adrese danym slovesem.

    Nedrzi prava, drzi ODKAZ na ne. To je cely rozdil mezi v2 a v3.
    """

    address: Address
    verb: Verb

    def allows(self, caller: Caller, resolve: Resolve) -> bool:
        return allowed(caller.principals, resolve(self.address, self.verb))


@dataclass(frozen=True, slots=True)
class Session(Audience):
    """Prima odpoved jedne relaci.

    Na prava se nepta zamerne: odpoved patri tomu, kdo se ptal, a nesmi
    zaviset na tom, jestli registr o adrese vubec neco vi. Kdyz ma byt
    odpoved zaroven podminena pravem, slozi se `And(Session(...), Ref(...))`.
    """

    session: str

    def allows(self, caller: Caller, resolve: Resolve) -> bool:
        return caller.session is not None and caller.session == self.session


@dataclass(frozen=True, slots=True)
class And(Audience):
    """Obe podminky zaroven: "odpoved mne, ale jen kdyz na to mam"."""

    left: Audience
    right: Audience

    def allows(self, caller: Caller, resolve: Resolve) -> bool:
        return self.left.allows(caller, resolve) and self.right.allows(caller, resolve)


@dataclass(frozen=True, slots=True)
class Message:
    """Obsah a publikum. Jedno bez druheho neexistuje.

    `audience` nema vychozi hodnotu a mit ji nesmi: funkce, ktera vyrabi data
    pro klienta, nesmi jit zavolat bez odpovedi na otazku "pro koho".
    """

    payload: Mapping[str, Any]
    audience: Audience

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Message):
            return NotImplemented
        return dict(self.payload) == dict(other.payload) and self.audience == other.audience

    def __hash__(self) -> int:  # pragma: no cover - payload je obecne nehashovatelny
        return hash(self.audience)
