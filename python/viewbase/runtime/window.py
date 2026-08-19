"""Okno jako RAM: adresa, typ, titulek, prava.

Obsah okna tady neni a nebude - ten zije cely v `types/` (typy-oken.md).
Runtime vlastni chrome: geometrii, z-order, titulek, zamek.
"""
from __future__ import annotations

from ..core.addressing import Address
from .access_facade import AccessFacade, AccessOwner


class Window:
    """Ram okna na plose.

    Vznika uz s adresou a uz zapsany v registru objektu (par. 2). Mezistav,
    kdy okno existuje, ale jeste nema adresu - a tedy ani prava - tu neni.
    """

    __slots__ = ("_instance", "_app", "address", "kind", "title", "access")

    def __init__(
        self,
        instance: AccessOwner,
        address: Address,
        kind: str,
        title: str | None,
        app: str | None = None,
    ) -> None:
        self._instance = instance
        self._app = app
        self.address = address
        self.kind = kind
        self.title = title
        self.access = AccessFacade(instance, address)

    @property
    def app(self) -> str | None:
        """Odkud je obsah, nebo None pro lokalni obsah.

        Cte se, ale nenastavuje: vazbu zaklada ten, kdo okno otevira. Kdyby
        sla prepsat za behu, byl by to druhy zpusob, jak okno spojit s apkou -
        a jeden z nich by se prestal kontrolovat.
        """
        return self._app

    @property
    def id(self) -> str:
        return self.address.window_id  # type: ignore[return-value]

    @property
    def screen_id(self) -> str:
        return self.address.screen_id  # type: ignore[return-value]

    def __repr__(self) -> str:  # pragma: no cover - jen pro ladeni
        return f"<Window {self.address} kind={self.kind!r}>"
