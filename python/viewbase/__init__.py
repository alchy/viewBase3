"""viewBase: plochy a okna v prohlizeci jako knihovna.

    import viewbase as vb

    instance = vb.Instance()
    screen = instance.screen.open(title="Provoz", id="provoz")
    window = screen.window.open("panel", id="mzdy", title="Mzdy")
    window.access.read.add("group:ucetni")

VEREJNE JE JEN TO, CO VYVOJAR PISE (D-13): `Instance` a enumy, ktere se
jmenuji pri registraci udalosti. Vsechno ostatni se ziskava Z INSTANCE, ne
importem - `viewbase.core.*` neni pro vyvojare aplikace. Povrch, ktery se
rozroste nahodou, uz nejde zuzit bez rozbiti; viewBase2 ma verejne API
popsane az zpetne a stalo to presne tohle.
"""
__all__ = ["Instance", "Needs", "StepUp", "Verb"]

#: Kde verejna jmena skutecne zijou. Nacitaji se AZ PRI PRVNIM SAHNUTI.
_PUBLIC = {
    "Instance": ("viewbase.runtime.instance", "Instance"),
    "Needs": ("viewbase.runtime.events", "Needs"),
    "StepUp": ("viewbase.runtime.events", "StepUp"),
    "Verb": ("viewbase.core.access", "Verb"),
}


def __getattr__(name: str):
    """Lene nacitani verejnych jmen (PEP 562).

    Kdyby se tady importovalo natvrdo, `from viewbase.core.access import Acl`
    by pri behu naimportoval CELY runtime - protoze import podmodulu spusti
    `__init__` balicku. Pravidlo z par. 11 ("core nezavisi na nicem") by pak
    platilo na urovni modulu, ale ne na urovni balicku, a jakmile transport
    pritahne server, potreboval by ho i ten, kdo chce jen `Acl`.

    Tohle to drzi na obou urovnich zaroven: `import viewbase as vb;
    vb.Instance(...)` funguje stejne jako driv, ale samotny `core` zustane
    sam.
    """
    where = _PUBLIC.get(name)
    if where is None:
        raise AttributeError(f"modul 'viewbase' nema {name!r}")
    import importlib

    value = getattr(importlib.import_module(where[0]), where[1])
    globals()[name] = value  # priste uz primo, bez hledani
    return value


def __dir__() -> list[str]:
    """Napovida a `dir()` ukazuji verejny povrch, ne vnitrek balicku."""
    return list(__all__)
