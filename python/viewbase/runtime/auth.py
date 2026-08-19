"""Jedno povinne autentizacni API pro oba kanaly apky (D-47).

Apka nema vymyslet vlastni autentizaci - to je misto, kde se to obvykle
pokazi. Volajici predlozi TOKEN, apka ho overi INTROSPEKCI a dostane, kdo to
je:

    POST /auth/introspect  {token, audience}
    -> {subject_id, groups, expires_at}   nebo nic

Tri veci, ktere se tim ziskaji:

  * klic k apce prestane byt mocny jako vsechna jeji data,
  * davkova uloha bezi JAKO NEKDO - tyz subjekt v okne i v cronu, takze se
    to v auditu spoji,
  * odvolani je smazani radku a je okamzite.

INTROSPEKCE, NE PODPIS. Podepsany token by prinesl klic k rotaci, generace
kvuli odvolavani a hodiny k synchronizaci - a nic by neresil, protoze
autentizuje tyz proces, ktery token vydal. Je to tataz uvaha jako u
nepruhledneho session id ve viewBase2. Kratka cache na strane apky (desitky
sekund) je v poradku; delsi uz ne, protoze prodluzuje okno mezi odvolanim
a jeho ucinkem.

AUDIENCE JE POVINNA. Bez ni je token pro apku X klicem k apce Y, jakmile ho X
ziska - a apky si navzajem duverovat nemaji.

RUKOJET V TOKENU NENI. Token rika KDO, pozadavek rika CO. Kdyby v nem rukojet
byla, splynulo by identifikovani s opravnovanim - presne to, cemu se cely
model vyhyba.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from ..core.addressing import new_id
from ..core.identity import Caller, principal

#: Jak dlouho token plati, kdyz se nerekne jinak. Kratce zamerne: davkovy
#: ukol si o novy rekne, clovek u prohlizece ho nevidi vubec.
DEFAULT_TTL = 3600.0


@dataclass(frozen=True, slots=True)
class Token:
    """Radek v tabulce vydanych tokenu. Pravdu drzi tahle tabulka, ne retezec."""

    subject_id: str
    principals: frozenset[str]
    audience: str
    expires_at: float


class AuthService:
    """`instance.auth` - vydavani a introspekce tokenu pro apky."""

    __slots__ = ("_tokens", "_instance", "_clock")

    def __init__(self, instance, clock: Callable[[], float] | None = None) -> None:
        self._tokens: dict[str, Token] = {}
        self._instance = instance
        self._clock = clock or time.time

    # -- vydani ----------------------------------------------------------

    def issue(self, caller: Caller, *, audience: str, ttl: float = DEFAULT_TTL) -> str:
        """Vydej token pro konkretniho volajiciho a konkretni apku.

        `audience` je POVINNA a musi to byt adresa registrovane apky - token
        vydany pro nikoho by byl univerzalni klic.
        """
        from .content import subject_of

        if audience not in self._known_audiences():
            raise ValueError(
                f"audience {audience!r} neni registrovana apka; zname: "
                f"{', '.join(sorted(self._known_audiences())) or '(zadne)'}"
            )
        token = f"vbt1_{new_id()}{new_id()}"
        self._tokens[token] = Token(
            subject_id=subject_of(caller)["subject_id"],
            principals=caller.principals,
            audience=audience,
            expires_at=self._clock() + ttl,
        )
        return token

    # -- introspekce -----------------------------------------------------

    def introspect(self, token: str, *, audience: str) -> dict | None:
        """Kdo je drzitel tokenu, kdyz se pta prave tahle apka?

        Vraci None pro neznamy, odvolany, vyprsely i cizi token. Rozlisovat je
        navenek by potvrzovalo existenci; duvod jde do auditu.
        """
        record = self._tokens.get(token)
        if record is None:
            return None
        if record.expires_at <= self._clock():
            del self._tokens[token]
            return None
        if record.audience != audience:
            # Pokus pouzit token jinde, nez byl vydan. Do auditu vzdycky.
            self._instance._record(
                "auth", "token_wrong_audience",
                detail=f"vydan pro {record.audience}, predlozen u {audience}",
            )
            return None
        return {
            "subject_id": record.subject_id,
            "groups": self._groups_for(audience, record.principals),
            "expires_at": record.expires_at,
        }

    # -- odvolani --------------------------------------------------------

    def revoke(self, token: str) -> None:
        self._tokens.pop(token, None)

    def revoke_subject(self, subject_id: str) -> None:
        """Smazany nebo odhlaseny clovek nesmi dal chodit do apek (chyba 3.5)."""
        self._tokens = {
            value: record
            for value, record in self._tokens.items()
            if record.subject_id != subject_id
        }

    def __len__(self) -> int:
        return len(self._tokens)

    # -- skupiny: jen ty, o ktere si apka rekla (D-48) -------------------

    def _groups_for(self, audience: str, principals: frozenset[str]) -> list[str]:
        """Clenstvi JEN mezi skupinami, ktere apka deklarovala.

        Bez filtru by se kazda apka dozvedela celou pozici cloveka v
        organizaci. Skupiny se timhle stavaji SDILENYM SLOVNIKEM: prejmenovani
        skupiny je rusici zmena napric systemem, ne kosmetika.

        Apka je smi pouzit pro VLASTNI pravidla nad svym obsahem, ne pro
        rozhodnuti, co vratit v snapshotu - to uz jsme autorizovali my.
        """
        app_id = audience.split(":", 1)[1]
        registration = self._instance.app.get(app_id)
        wanted = {principal(name) for name in registration.groups_of_interest}
        return sorted(wanted & principals)

    def _known_audiences(self) -> set[str]:
        return {str(r.address) for r in self._instance.app.all()}
