"""Relace a kroky navic.

Zatim jen `Grants` - evidence kroku navic. Tabulka relaci (dve lhuty, klouzava
a absolutni strop) prijde s `Instance`.

KROK NAVIC PATRI DVOJICI (relace, objekt), ne objektu. Ve viewBase2 byl zamek
okna globalni vypinac na objektu, takze odemceni jednim divakem odhalilo obsah
vsem (chyba 3.9).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.addressing import Address


@dataclass
class Grants:
    """Kdo ma krok navic k cemu.

    Klicem je DVOJICE (relace, adresa). Zadny zaznam "objekt je odemceny" tu
    neexistuje a existovat nesmi - byl by to zase globalni vypinac.
    """

    _held: set[tuple[str, Address]] = field(default_factory=set)

    def hold(self, session: str, address: Address) -> None:
        """Zaznamenej, ze tahle relace prosla krokem navic u tohohle objektu."""
        self._held.add((session, address))

    def holds(self, session: str | None, address: Address) -> bool:
        """Ma tahle relace krok navic k tomuhle objektu?

        Volajici bez relace (programovy vstup) ho mit nemuze - krok navic se
        pta "jsi to fakt ty, ted" a bez relace neni koho se ptat.
        """
        if session is None:
            return False
        return (session, address) in self._held

    def revoke_session(self, session: str) -> None:
        """Odhlaseni nebo vyprseni relace bere vsechny jeji kroky navic."""
        self._held = {pair for pair in self._held if pair[0] != session}

    def revoke_object(self, address: Address) -> None:
        """Zanik objektu bere kroky navic k nemu."""
        self._held = {pair for pair in self._held if pair[1] != address}
