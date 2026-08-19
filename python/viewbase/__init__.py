"""viewBase: plochy a okna v prohlizeci jako knihovna.

    import viewbase as vb

    instance = vb.Instance()
    screen = instance.screen.open(title="Provoz", id="provoz")
    window = screen.window.open("panel", id="mzdy", title="Mzdy")
    window.access.see.add("group:ucetni")

VEREJNE JE JEN TO, CO VYVOJAR PISE (D-13): `Instance` a enumy, ktere se
jmenuji pri registraci udalosti. Vsechno ostatni se ziskava Z INSTANCE, ne
importem - `viewbase.core.*` neni pro vyvojare aplikace. Povrch, ktery se
rozroste nahodou, uz nejde zuzit bez rozbiti; viewBase2 ma verejne API
popsane az zpetne a stalo to presne tohle.
"""
from .core.access import Verb
from .runtime.events import Needs, StepUp
from .runtime.instance import Instance

__all__ = ["Instance", "Needs", "StepUp", "Verb"]


def __dir__() -> list[str]:
    """Napovida a `dir()` ukazuji verejny povrch, ne vnitrek balicku."""
    return list(__all__)
