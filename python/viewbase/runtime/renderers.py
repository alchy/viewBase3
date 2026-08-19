"""Katalog rendereru: `kind` je nase vec, ne vec apky.

Byly tri moznosti, jak resit renderer dodany apkou:

  1. verit mu - nevynutitelne (kdo zaregistruje apku, spousti kod v prohlizeci
     kazdeho divaka, ve stejnem originu jako workbench),
  2. izolovat ho v iframe se sandboxem - u grafu vykonove neunosne,
  3. zadny cizi renderer nemit.

Prvni dve se plati porad, treti jednou pri navrhu. Proto APKA NEDODAVA
JAVASCRIPT NIKDY (D-44) a `kind` je jmeno rendereru z tohohle katalogu.

KURATOROVANY NENI ZADRATOVANY: renderer zustava samostatny balik, takze se do
katalogu da pridat i odebrat - jen se to deje pri buildu a projde to review.

Kazdy renderer publikuje svoje DATOVE API (D-45): tvar snapshotu a delt,
udalosti, lokalni volby a co potrebuje. Apka produkuje data v tom tvaru,
renderer je konzumuje, ani jeden o tom druhem nevi nic vic. Prijemny dusledek:
tataz data muze umet zobrazit vic rendereru - kdo posle `graph.v1`, divaji se
grafem, a az nekdo napise `table`, ktery `graph.v1` taky prijme, je z toho
"Zobrazit jako tabulku" bez zasahu do apky.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True, eq=False)
class Renderer:
    """Jeden renderer v katalogu a jeho datove API."""

    kind: str
    #: Jmeno a verze datoveho API, ktere umi cist (`graph.v1`).
    contract: str
    #: Co k behu POTREBUJE. Kdyz to instance neudeluje, okno se neotevre.
    capabilities: tuple[str, ...] = ()
    #: Co pouzije, kdyz to dostane, a jinak se degraduje (webgl -> 2D ustup).
    optional_capabilities: tuple[str, ...] = ()
    #: Volby, ktere meni JEN MUJ POHLED a na server nechodi (skupina "View").
    #: Mapa jmeno -> {"type": toggle|choice, "options": [...], "value": vychozi}.
    view_options: dict = field(default_factory=dict)


#: Sada, se kterou se viewBase dodava (typy-oken.md par. 4).
def _toggle(value=True):
    return {"type": "toggle", "value": value}


def _choice(options, value):
    return {"type": "choice", "options": list(options), "value": value}


BUILTIN = (
    Renderer("panel", contract="panel.v1",
             view_options={"density": _choice(["compact", "comfortable"], "comfortable")}),
    Renderer("doc", contract="doc.v1",
             view_options={"width": _choice(["narrow", "wide"], "narrow")}),
    Renderer("console", contract="console.v1",
             view_options={"wrap": _toggle(True), "font_size": _choice(["s", "m", "l"], "m")}),
    Renderer(
        "shell",
        contract="shell.v1",
        capabilities=("keyboard-capture",),
        view_options={"font_size": _choice(["s", "m", "l"], "m")},
    ),
    Renderer("log", contract="log.v1",
             view_options={"wrap": _toggle(False), "columns": _toggle(True)}),
    Renderer(
        "graph",
        contract="graph.v1",
        optional_capabilities=("webgl",),
        view_options={
            "physics": _toggle(True),
            "dimensions": _choice(["2D", "3D"], "3D"),
            "splines": _toggle(False),
            "highlight": _toggle(True),
        },
    ),
)

BUILTIN_KINDS = tuple(renderer.kind for renderer in BUILTIN)


class RendererCatalogue:
    """`instance.renderer` - co tahle instance umi vykreslit."""

    __slots__ = ("_renderers",)

    def __init__(self) -> None:
        self._renderers: dict[str, Renderer] = {r.kind: r for r in BUILTIN}

    def register(
        self,
        kind: str,
        *,
        contract: str,
        capabilities: tuple[str, ...] = (),
        optional_capabilities: tuple[str, ...] = (),
        view_options: dict | None = None,
    ) -> Renderer:
        """Pridej renderer do katalogu.

        Deje se to pri buildu, ne za behu z registrace apky - ale je to obycejny
        zapis do kolekce, aby slo renderer pridat i odebrat v celku.
        """
        if kind in self._renderers:
            raise ValueError(f"renderer uz v katalogu je: {kind!r}")
        renderer = Renderer(
            kind, contract, capabilities, optional_capabilities, dict(view_options or {})
        )
        self._renderers[kind] = renderer
        return renderer

    def get(self, kind: str) -> Renderer:
        return self._renderers[kind]

    def all(self) -> tuple[Renderer, ...]:
        return tuple(self._renderers.values())

    def speaking(self, contract: str) -> tuple[Renderer, ...]:
        """Renderery, ktere umi cist dane datove API."""
        return tuple(r for r in self._renderers.values() if r.contract == contract)

    def known(self) -> list[str]:
        return sorted(self._renderers)

    def __contains__(self, kind: str) -> bool:
        return kind in self._renderers

    def require(self, kind: str, granted: frozenset[str]) -> Renderer:
        """Over, ze renderer existuje a ze mu instance umi dat, co potrebuje.

        Neznamy `kind` je preklep a ma se ozvat hned - zadny cizi renderer
        neexistuje, takze se neni na co odvolat.
        """
        renderer = self._renderers.get(kind)
        if renderer is None:
            raise ValueError(
                f"neznamy kind {kind!r}; katalog zna: {', '.join(self.known())}"
            )
        missing = [c for c in renderer.capabilities if c not in granted]
        if missing:
            raise ValueError(
                f"renderer {kind!r} potrebuje schopnosti, ktere tahle instance "
                f"neudeluje: {', '.join(missing)}"
            )
        return renderer
