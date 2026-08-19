"""Sberna nadoba auditni stopy: stav, prah a to, ze audit prahu nepodleha.

Sanace, redakce, tvar zaznamu a vykresleni radku jsou ciste funkce a leží
v `core/audit.py`. Tady je jen to, co drzi stav.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterator

from ..core.audit import (
    LEVELS,
    MAX_DETAIL,
    REDACTED_KEYS,
    SECURITY,
    SESSION_PREFIX,
    SOURCE_WIDTH,
    Record,
    build_record,
    format_record,
    redact,
    sanitize,
)

__all__ = [
    "LEVELS", "MAX_DETAIL", "REDACTED_KEYS", "SECURITY", "SESSION_PREFIX",
    "SOURCE_WIDTH", "Record", "AuditLog", "format_record", "redact", "sanitize",
]


class AuditLog:
    """Stopa instance. Prah plati na bezne zaznamy, na `security` nikdy."""

    __slots__ = ("_records", "_threshold", "_clock")

    def __init__(
        self,
        threshold: str = "info",
        clock: Callable[[], float] | None = None,
    ) -> None:
        if threshold not in LEVELS:
            raise ValueError(f"neznama uroven {threshold!r}; zname: {LEVELS}")
        self._records: list[Record] = []
        self._threshold = threshold
        self._clock = clock or time.time

    # -- zapis ------------------------------------------------------------

    def record(
        self,
        level: str,
        *,
        component: str,
        action: str,
        by: str | None = None,
        session: str | None = None,
        source: str | None = None,
        address=None,
        verb=None,
        detail: object = "",
    ) -> Record | None:
        """Bezny zaznam. Podleha prahu."""
        if component == SECURITY:
            raise ValueError(
                "komponentu 'security' zapisuje jen audit(); kdyby si ji smel "
                "vzit bezny zaznam, sel by prah obejit z druhe strany"
            )
        self._check_level(level)
        if LEVELS.index(level) < LEVELS.index(self._threshold):
            return None
        return self._append(level, component, action, by, session, source,
                            address, verb, detail)

    def security(
        self,
        level: str = "info",
        *,
        action: str,
        by: str | None = None,
        session: str | None = None,
        source: str | None = None,
        address=None,
        verb=None,
        detail: object = "",
    ) -> Record:
        """Bezpecnostni stopa. PRAHU NEPODLEHA.

        Patri sem to, co musi jit dohledat zpetne: pripojeni a odpojeni
        klienta, odemceni a zamceni okna, odmitnuty kod, odmitnuty programovy
        pokus. Nikdy sem nepatri tajemstvi - kod, QR, cele session id ani
        obsah okna.
        """
        self._check_level(level)
        return self._append(level, SECURITY, action, by, session, source,
                            address, verb, detail)

    def _append(self, level, component, action, by, session, source,
                address, verb, detail) -> Record:
        record = build_record(
            self._clock(), level, component, action, by, session, source,
            address, verb, detail,
        )
        self._records.append(record)
        return record

    def _check_level(self, level: str) -> None:
        if level not in LEVELS:
            raise ValueError(f"neznama uroven {level!r}; zname: {LEVELS}")

    # -- cteni ------------------------------------------------------------

    def format(self, record: Record) -> str:
        """Sloupcovy radek. Vykresleni samo je cista funkce v core."""
        return format_record(record)

    def lines(self) -> list[str]:
        return [self.format(record) for record in self._records]

    def __iter__(self) -> Iterator[Record]:
        return iter(self._records)

    def __len__(self) -> int:
        return len(self._records)

    def __getitem__(self, index):
        return self._records[index]
