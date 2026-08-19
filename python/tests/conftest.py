"""Pomocnici pro testy, ktere zkousi MECHANIKU okna, ne cestu k nemu.

Po D-54 vznika okno JEDINE tim, ze si ho divak otevre z nabidky:

    graf   = instance.app.register(GraphApp())
    nabidka = screen.app.register(graf, title="Sit")
    okno    = nabidka.open(caller)

Testy, ktere overuji prave tohle, tu cestu pisou celou - jsou v
`test_offer.py`. Testy, ktere zkousi neco jineho (fasadu prav, menu, audit,
adresovani), by tim jen zhoustly, takze pouzivaji `open_window` - tenky obal
nad TOUTEZ runtime tovarnou, kterou vola `Offer.open`. Zadna druha cesta tim
nevznika: `_create` je jedina tovarna a verejne API k ni vede pres nabidku.
"""
from __future__ import annotations


def register_app(instance, app_id, *, kind="panel", scope="window", backend=None,
                 **manifest):
    """Zaregistruj apku popsanou rovnou tady, ne manifestem na objektu.

    Pravidlo "co je v manifestu, se v kodu nepise znovu" (D-53) ma vlastni
    testy v `test_offer.py`; tady jde o to, aby si test mohl apku poridit
    jednim radkem.
    """
    if backend is None:
        backend = _Nic()
    return instance.app._register(
        app_id, kind=kind, scope=scope, backend=backend, **manifest
    )


def open_window(screen, kind="panel", **kwargs):
    """Vyrob okno touz tovarnou, kterou pouziva `Offer.open`."""
    return screen.window._create(kind, **kwargs)


class _Nic:
    """Apka, ktera nedela nic - pro testy, kde jde jen o ram okna."""

    def open_content(self, handle, spec, subject):
        return {"handle": handle, "state": {}, "cursor": 1}

    def snapshot(self, handle, subject):
        return {"state": {}, "cursor": 1}

    def apply_event(self, handle, subject, event):
        return []

    def close_content(self, handle):
        pass
