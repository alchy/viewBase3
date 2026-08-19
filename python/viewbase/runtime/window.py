"""Okno jako RAM: adresa, typ, titulek, prava.

Obsah okna tady neni a nebude - ten zije cely v `types/` (typy-oken.md).
Runtime vlastni chrome: geometrii, z-order, titulek, zamek.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..core.addressing import Address
from .access_facade import AccessFacade, AccessOwner
from .content import ContentState


@dataclass(frozen=True, slots=True)
class WindowApp:
    """Na co je okno napojene: ktera apka a ktery jeji obsah.

    `handle` je None u scope `session` a `user` - tam se rukojet odvozuje az
    od diváka a pri otevirani okna jeste zadny neni.
    """

    id: str
    scope: str
    handle: str | None = None


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
        app: "WindowApp | None" = None,
    ) -> None:
        self._instance = instance
        self._app = app
        self.address = address
        self.kind = kind
        self.title = title
        self.access = AccessFacade(instance, address)

    @property
    def content_state(self) -> ContentState:
        """Stav obsahu z pohledu instance (D-32).

        Okno bez apky je vzdycky OK: lokalni obsah dodava kod, ktery okno
        otevrel, a nema co spadnout.
        """
        if self._app is None or self._app.handle is None:
            return ContentState.OK
        state = self._instance.content.state(self._app.handle)
        return ContentState.OK if state is None else state

    @property
    def app(self) -> "WindowApp | None":
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
