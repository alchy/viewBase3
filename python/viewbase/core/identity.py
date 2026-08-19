"""Principalove: retezce, proti kterym se vyhodnocuje ACL.

Principal je retezec s prefixem: `user:hana`, `group:ucetni`, `group:public`.
Relace jich ma mnozinu - vlastni `user:<jmeno>`, implicitni `group:<jmeno>`
(uzivatel ma vzdy skupinu pojmenovanou po sobe), skupiny ze zdroje identit
a vzdy `group:public`.

Modul je zamerne cisty: zadne I/O, zadny stav, zadny import z projektu.
Diky tomu se cela autorizace testuje bez serveru (par. 11).
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

#: Kdokoli, i nepriblaseny. Anonymni relace ma jen tohohle principala.
PUBLIC = "group:public"

#: Kdokoli overeny. Vychozi hodnota `default_access` instance.
USERS = "group:users"

#: Obdoba roota. Prochazi vsude - vedome, viz `access.allowed`.
ADMINISTRATOR = "group:administrator"

_PREFIXES = ("user:", "group:")


def principal(name: str) -> str:
    """Znormalizuj principala. Bez prefixu se doplni `group:`.

    `acl.add("users")` je tak totez co `acl.add("group:users")`. Tohle je
    API, ktere se pise rucne, a mlcky selhat kvuli chybejicimu prefixu by
    znamenalo tise otevrene (nebo tise zavrene) okno.
    """
    text = str(name).strip()
    if not text:
        raise ValueError("principal nesmi byt prazdny")
    if not text.startswith(_PREFIXES):
        text = f"group:{text}"
    value = text.split(":", 1)[1]
    if not value or ":" in value:
        raise ValueError(f"neplatny principal: {name!r}")
    return text


def user_principals(username: str | None, groups: Iterable[str] = ()) -> frozenset[str]:
    """Principalove relace: `user:<jmeno>`, `group:<jmeno>`, skupiny, public.

    Anonymni relace (bez jmena) ma JEN `group:public` - proto vidi jen to,
    co je vyslovne verejne. Souvisi to s chybou 3.5 z viewBase2: neznamé
    jmeno tam dostavalo vychozi `group:users`, takze smazany uzivatel si
    drzel pristup. "Neznam" neni "vychozi"; kdo nema jmeno, nema nic nad
    ramec verejneho.

    KAZDY OVERENY CLOVEK JE V `group:users`. Je to vyznam toho jmena a bez
    toho by vychozi `default_access=["group:users"]` neznamenalo "kdokoli
    prihlaseny", ale "kdo to ma nahodou vypsane v zaznamu".
    """
    out = {PUBLIC}
    if username:
        out.add(f"user:{username}")
        out.add(f"group:{username}")  # implicitni vlastni skupina
        out.add(USERS)  # overeny = uzivatel instance
        out.update(principal(group) for group in groups)
    return frozenset(out)


class Origin(Enum):
    """Odkud volajici prisel. Rozlisuje se kvuli auditu, ne kvuli pravum.

    Prava se ridi VYHRADNE principaly - jinak by vznikly dve vetve ve
    vynucovacim kodu a to je chyba 3.3 z viewBase2. Jedina vyjimka je
    `INTERNAL`, viz `Caller.internal`.
    """

    WS = "ws"  # relace prohlizece
    REST = "rest"  # programovy vstup
    INTERNAL = "internal"  # uzivatelsky kod knihovny ve stejnem procesu


@dataclass(frozen=True, slots=True)
class Caller:
    """Kdo se pta. Jeden typ pro relaci prohlizece i pro programovy vstup.

    Ve viewBase2 nemel REST identitu zadnou, takze `curl` bez niceho spustil
    autorsky handler na plose, kterou nikdo nemel videt. Kazdy vstup ma
    identitu, i kdyz je to "nikdo" - a vynucovaci kod diky tomu nema dve
    vetve.

    `correlation` je to, co dostane apka misto session id: neprurhledne id
    odvozene z (adresa, relace), stabilni po dobu relace. Session id je
    prihlasovaci udaj - jeho drzitel JE tou relaci - a do apky nepatri.
    """

    principals: frozenset[str]
    session: str | None = None
    correlation: str | None = None
    origin: Origin = Origin.WS
    remote: str | None = None

    @classmethod
    def anonymous(cls, origin: Origin = Origin.WS, remote: str | None = None) -> "Caller":
        """Vstup bez prihlaseni. Vidi jen to, co je vyslovne verejne."""
        return cls(principals=user_principals(None), origin=origin, remote=remote)

    @classmethod
    def for_user(
        cls,
        username: str,
        groups: Iterable[str] = (),
        session: str | None = None,
        correlation: str | None = None,
        origin: Origin = Origin.WS,
        remote: str | None = None,
    ) -> "Caller":
        return cls(
            principals=user_principals(username, groups),
            session=session,
            correlation=correlation,
            origin=origin,
            remote=remote,
        )

    @classmethod
    def internal(cls) -> "Caller":
        """Uzivatelsky kod knihovny ve stejnem procesu.

        NEPROCHAZI autorizaci - je to kod aplikace, tedy stejna duvera jako
        jadro, a delat z nej principaly by byla jen ceremonie. ALE plati pro
        nej stejna povinnost uvest publikum u zprav, ktere vyrobi. Tady je ta
        hranice: autorizace se vynechava, publikum nikdy.
        """
        return cls(principals=frozenset({ADMINISTRATOR}), origin=Origin.INTERNAL)
