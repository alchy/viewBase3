"""Jak se volajici predstavi apce.

Vlastni kod knihovny neni anonym: kanal instance <-> apka je vzajemne
autentizovany a apka smi tuhle identitu brat jako duveryhodnou (F-17).
"""
from __future__ import annotations

from ..core.identity import Caller, Origin

SERVICE_SUBJECT = "service:instance"


def subject_id_of(caller: Caller) -> str:
    """`user:<jmeno>`, `service:instance` nebo `anonymous`."""
    if caller.origin is Origin.INTERNAL:
        return SERVICE_SUBJECT
    for principal in caller.principals:
        if principal.startswith("user:"):
            return principal
    return "anonymous"
