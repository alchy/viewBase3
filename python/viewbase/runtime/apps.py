"""Registr apek: odkud je obsah.

`kind` a `app_id` jsou dve nezavisle osy (typy-oken.md par. 1) a nekdo je musi
SPOJIT. Dela to ten, kdo okno otevira - nikdy apka sama:

    screen.window.open("panel", id="hello", title="Hello", app="example.hello")

APKA SE NA OKNO NEPRIHLASUJE SAMA. Kdyby mohla, byl by to zpusob, jak se
prilepit na cizi plochu. Zna jen ty instance, ktere dostala; zadne "vypis
plochy" neexistuje a registrace proto nema na plochy ani okna zadny odkaz.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .content import SCOPES, ContentRegistry


@dataclass(frozen=True, slots=True)
class AppRegistration:
    """Co o sobe apka rekla pri registraci - a jak se s ni da mluvit.

    Zamerne tu NENI nic, cim by se apka dostala k plocham nebo oknum: zadne
    `screen`, `window` ani vypis cehokoli. Je to popis zdroje obsahu, ne
    pristupovy bod. Kdyby se apka mohla na okno prihlasit sama, byl by to
    zpusob, jak se prilepit na cizi plochu.
    """

    app_id: str
    kind: str | None = None
    scope: str = "window"
    backend_base_url: str | None = None
    _content: ContentRegistry | None = field(default=None, repr=False, compare=False)

    def new_content(self, spec: dict | None = None) -> str:
        """Zaloz obsah BEZ OKNA a vrat jeho rukojet.

        Tohle je ta cesta, kterou davkova uloha naplni graf driv, nez ho nekdo
        otevre - okno se na nej napoji az potom.
        """
        assert self._content is not None
        handle = self._content.mint(f"new:{self.app_id}:{new_handle_seed()}")
        self._content.attach(handle, self.app_id, None, spec or {})
        return handle

    def close_content(self, handle: str) -> None:
        """Ukonci obsah. Zavreni OKNA tohle nedela - to je jen odpojeni pohledu."""
        assert self._content is not None
        self._content.close(handle)


def new_handle_seed() -> str:
    from ..core.addressing import new_id

    return new_id()


class AppCollection:
    """`instance.app` - apky, ktere tahle instance zna."""

    __slots__ = ("_registrations", "_content")

    def __init__(self, content: ContentRegistry) -> None:
        self._registrations: dict[str, AppRegistration] = {}
        self._content = content

    def register(
        self,
        app_id: str,
        *,
        kind: str | None = None,
        scope: str = "window",
        backend=None,
        backend_base_url: str | None = None,
    ) -> AppRegistration:
        if app_id in self._registrations:
            raise ValueError(f"apka uz je registrovana: {app_id!r}")
        if scope not in SCOPES:
            raise ValueError(
                f"neznamy scope {scope!r}; zname: {', '.join(SCOPES)}"
            )
        registration = AppRegistration(
            app_id, kind, scope, backend_base_url, self._content
        )
        self._registrations[app_id] = registration
        self._content.bind_backend(app_id, backend)
        return registration

    def get(self, app_id: str) -> AppRegistration:
        return self._registrations[app_id]

    def all(self) -> tuple[AppRegistration, ...]:
        return tuple(self._registrations.values())

    def __contains__(self, app_id: str) -> bool:
        return app_id in self._registrations

    def __len__(self) -> int:
        return len(self._registrations)

    def known(self) -> list[str]:
        """Seznam pro chybovou hlasku - prave ten chyta preklepy."""
        return sorted(self._registrations)
