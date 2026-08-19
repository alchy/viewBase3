"""Kdo smi co: ACL jako mnozina povolenych, dve slovesa, dedicnost.

ZADNE "DENY". ACL je mnozina POVOLENYCH principalu a vyhodnoceni je prunik.
Zaporna pravidla by si vynutila precedenci ("co kdyz je v obojim?") a model
by prestal byt citelny; `acl.without("group:public")` je odebrani
z povolenych, ne zakaz.

DVE SLOVESA, protoze "videt" a "zasahovat" jsou ruzne veci - verejne log
okno, ktere smi vyprazdnit jen spravce:

    read   ... kdo vidi obsah (co se vubec odesle po drate)
    write  ... kdo smi menit obsah; nenastavene = totez co `read`

DEDICNOST misto vychoziho `group:public`: objekt bez ACL bere ACL sve plochy,
plocha bere vychozi hodnotu instance. Default-open by znamenal, ze log okno
s auditni stopou je verejne driv, nez si toho kdokoli vsimne.

Proti viewBase2 se meni dve veci (par. 4):

a) KROK NAVIC bydli tady, ne vedle. viewBase2 mel `private=True` jako boolean
   na okne, zatimco pristup byl objekt; oboji je politika.
b) `Acl` JE HODNOTA. Ve viewBase2 se prava menila metodami na objektu a audit
   se delal uvnitr `Acl`. Tady se zmena vede pres instanci, ktera k ni muze
   pripojit kdo/kdy/proc - a hodnota o auditu nemusi vedet nic.

Modul zavisi jen na `identity` (par. 11).
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum

from .identity import ADMINISTRATOR, principal


class Verb(Enum):
    """Dve slovesa pristupu. Vic jich neni a zamerne nepribyva."""

    READ = "read"
    WRITE = "write"


@dataclass(frozen=True, slots=True)
class Acl:
    """Mnozina povolenych principalu jako nemenna hodnota.

    Zmena vraci NOVOU Acl. Vest zmenu pres instanci (a ne pres metodu na
    objektu) je to, co umozni auditni stopu "kdo komu co otevrel".
    """

    principals: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def empty(cls) -> "Acl":
        """Zavreno. Rozhodnuti "nikdo", ne "nenastaveno"."""
        return cls(frozenset())

    @classmethod
    def of(cls, *names: str) -> "Acl":
        """Acl z vyctu jmen; bez prefixu se doplni `group:`."""
        return cls(frozenset(principal(name) for name in names))

    @classmethod
    def from_iterable(cls, names: Iterable[str]) -> "Acl":
        return cls(frozenset(principal(name) for name in names))

    def with_added(self, *names: str) -> "Acl":
        return Acl(self.principals | {principal(name) for name in names})

    def without(self, *names: str) -> "Acl":
        """Odebrani z povolenych. Neni to zakaz - zadne "deny" model nema."""
        return Acl(self.principals - {principal(name) for name in names})

    def __contains__(self, name: str) -> bool:
        return principal(name) in self.principals

    def __iter__(self):
        return iter(sorted(self.principals))

    def __bool__(self) -> bool:
        return bool(self.principals)


@dataclass(frozen=True, slots=True)
class Access:
    """Politika jednoho objektu: dve ACL a krok navic.

    `None` u slovesa znamena NENASTAVENO (dedi se), ne "nikdo". Prazdna
    `Acl` naopak znamena rozhodnuti "nikdo" a dedicnost ji neprepise.
    """

    read: Acl | None = None
    write: Acl | None = None
    step_up: bool = False

    def for_verb(self, verb: Verb) -> Acl | None:
        """ACL pro sloveso, nebo None kdyz se ma dedit.

        Nenastavene `write` padne na `read`: jinak by kazdy objekt potreboval
        obe ACL a vetsina by je mela stejne.
        """
        if verb is Verb.WRITE:
            return self.write if self.write is not None else self.read
        return self.read


def allowed(principals: Iterable[str], acl: Acl) -> bool:
    """Prunik principalu volajiciho s ACL objektu.

    Cela autorizace je tahle jedna funkce - vsechno ostatni je jen otazka,
    KTERE ACL se ptat.

    JEDINA VYJIMKA: `group:administrator` projde vzdycky. Je to obdoba roota
    a je to vedome - instance musi mit nekoho, kdo se dostane vsude, jinak by
    spatne nastavene ACL zamklo spravce z jeho vlastniho workbenche a neslo
    by to opravit zevnitr. KROK NAVIC tim dotceny NENI: ten se porad chce,
    protoze se pta na neco jineho ("jsi to fakt ty, ted").
    """
    principals = set(principals)
    if ADMINISTRATOR in principals:
        return True
    return bool(principals & acl.principals)


def effective_acl(verb: Verb, chain: Sequence[Access], default: Acl) -> Acl:
    """Projdi dedicnost objekt -> plocha -> vychozi hodnota instance.

    `chain` zacina u objektu a pokracuje k jeho rodicum. Prvni clen, ktery
    ma sloveso NASTAVENE, vyhrava; kdyz ho nema nikdo, plati `default`.

    Prazdna `Acl` je nastavena hodnota: kdo napsal "nikdo", nechce, aby se
    to dedicnosti prepsalo na "kdokoli".
    """
    for access in chain:
        acl = access.for_verb(verb)
        if acl is not None:
            return acl
    return default
