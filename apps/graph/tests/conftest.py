"""Sdílené kusy pro testy grafové apky.

`zaloz` zastupuje **instanci**: razí rukojeť (D-29) a zavolá `create_content`.
Apka si rukojeť razit nesmí, takže ji v testech musí razit něco jiného —
a to něco je schválně tady, ne v apce, aby se to nedalo omylem použít
jako druhá cesta.
"""
import itertools

import pytest

from graph_app import GraphApp

HANA = {"subject_id": "user:hana", "capabilities": ["read", "write"]}
KAREL = {"subject_id": "user:karel", "capabilities": ["read", "write"]}
SPRAVCE = {"subject_id": "user:workbench",
           "capabilities": ["read", "write", "manage"]}
#: divák, kterému instance dala jen čtení
CTENAR = {"subject_id": "user:novak", "capabilities": ["read"]}

_handles = itertools.count(1)


@pytest.fixture
def app():
    return GraphApp()


@pytest.fixture
def zaloz(app):
    """Zastupuje instanci: orazí rukojeť a založí pod ní obsah."""
    def _zaloz(subject=HANA, **spec):
        handle = f"vb1_test{next(_handles):04d}"
        app.create_content(handle, spec, subject)
        return handle
    return _zaloz
