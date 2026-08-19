"""Registr apek: odkud je obsah.

`kind` a `app_id` jsou dve nezavisle osy (typy-oken.md par. 1) a nekdo je musi
SPOJIT. Dela to ten, kdo okno otevira - nikdy apka sama:

    screen.window.open("panel", id="hello", title="Hello", app="example.hello")

APKA SE NA OKNO NEPRIHLASUJE SAMA. Kdyby mohla, byl by to zpusob, jak se
prilepit na cizi plochu. Zna jen ty instance, ktere dostala; zadne "vypis
plochy" neexistuje a registrace proto nema na plochy ani okna zadny odkaz.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppRegistration:
    """Co o sobe apka rekla pri registraci.

    Zamerne tu NENI nic, cim by se apka dostala k plocham nebo oknum - je to
    popis zdroje obsahu, ne pristupovy bod.
    """

    app_id: str
    kind: str | None = None
    content: str | None = None
    backend_base_url: str | None = None


class AppCollection:
    """`instance.app` - apky, ktere tahle instance zna."""

    __slots__ = ("_registrations",)

    def __init__(self) -> None:
        self._registrations: dict[str, AppRegistration] = {}

    def register(
        self,
        app_id: str,
        *,
        kind: str | None = None,
        content: str | None = None,
        backend_base_url: str | None = None,
    ) -> AppRegistration:
        if app_id in self._registrations:
            raise ValueError(f"apka uz je registrovana: {app_id!r}")
        registration = AppRegistration(app_id, kind, content, backend_base_url)
        self._registrations[app_id] = registration
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
