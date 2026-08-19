"""Grafová apka: obsahy, jejich data a obě API plochy.

Apka má dvoje dveře a chodí se do nich jinak (viz docs/apka-kontrakt.md §1):

- **prezentační** — volá instance viewBase: `create_content`, `open_content`,
  `snapshot`, `apply_event`, `close_content`, `list_content`.
- **klientská** — volá kdokoli s tokenem: `add_node`, `add_edge`, … adresované
  **rukojetí**. Tudy plní graf dávková úloha, která o oknech neví nic.

Apka **nedodává žádný JavaScript**: posílá data ve tvaru `graph.v1`, který
umí renderer z katalogu workbenche.

CO TU VĚDOMĚ NENÍ: okna, plochy, session id, ACL — a **žádné vlastní
autorizační rozhodnutí**. Autorizuje instance a apka dostává jen hotovou
odpověď v `capabilities`. Dřív si tenhle modul rozhodoval sám podle
vlastnictví obsahu; byla to druhá autorizace jiným modelem a dávala jiné
odpovědi než ta první (F-23).

Vlastník obsahu tu proto zůstává jako **údaj**, ne jako právo: čísluje se
podle něj „Graph #1" a instance podle něj umí ve spouštěči oddělit moje od
sdílených.
"""
from __future__ import annotations

import itertools
import threading
from typing import Any

from .model import GraphContent

#: Schopnost pro nevratné zásahy (přejmenovat, zrušit). Instance ji spočítá
#: (zakladatel nebo správce, a jen když na obsah platí `write` — D-70) a apka
#: se **nedozví, kdo z nich to je** — jen že na to má.
MANAGE = "manage"
WRITE = "write"


class ContentRefused(Exception):
    """Připojení k obsahu se odmítá. Není to výpadek — divákovi se to říká
    jinak (viz apka-kontrakt.md §8), takže to musí jít odlišit."""


class GraphApp:
    """Backend grafové apky. Drží obsahy podle rukojeti.

    Instance ho dostane jako `backend` při registraci; dávková úloha volá
    tytéž metody přes REST vrstvu nad ním.
    """

    #: co apka produkuje — renderer z katalogu, který to umí, je `graph`
    CONTRACT = "graph.v1"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._contents: dict[str, GraphContent] = {}
        #: čísluje titulky PER VLASTNÍKA, takže „Graph #1" má každý svoje
        self._counters: dict[str, itertools.count] = {}

    # -- prezentační kanál (volá instance) ---------------------------------

    def create_content(self, handle: str, spec: dict[str, Any],
                       subject: dict[str, Any]) -> dict[str, Any]:
        """Založ obsah pod rukojetí, kterou **razí instance** (D-29).

        Známá rukojeť je chyba, ne připojení: kdyby se sem dalo připojit,
        „založ nový" a „otevři existující" by byly jedno volání a překlep
        v rukojeti by tiše otevřel cizí graf.
        """
        owner = str(subject.get("subject_id") or "anonymous")
        with self._lock:
            if handle in self._contents:
                raise ContentRefused(f"rukojeť {handle} už obsah má")
            content = self._create(handle, owner, spec.get("title"))
            return {**content.snapshot(), "title": content.title,
                    "handle": content.handle}

    def open_content(self, handle: str, subject: dict[str, Any]) -> dict[str, Any]:
        """Připoj se k existujícímu obsahu.

        Neznámá rukojeť se **odmítá, nikdy tiše nezakládá**. Tiché založení
        by po překlepu nebo po zastaralém odkazu dalo divákovi prázdný graf
        a on by si myslel, že přišel o data.

        NEAUTORIZUJE SE TU. Že tenhle člověk na obsah má, rozhodla instance
        průnikem okno × obsah dřív, než apku zavolala.
        """
        content = self._require(handle)
        return {**content.snapshot(), "title": content.title,
                "handle": content.handle}

    def snapshot(self, handle: str, subject: dict[str, Any]) -> dict[str, Any]:
        """Stav pro daného diváka. Autorizaci má za sebou (viz §9 kontraktu)."""
        content = self._require(handle)
        return {**content.snapshot(), "title": content.title}

    def apply_event(self, handle: str, subject: dict[str, Any],
                    event: dict[str, Any]) -> list[dict[str, Any]]:
        """Událost od diváka. Vrací změny; publikum určuje instance."""
        content = self._require(handle)
        name = event.get("event")
        if name == "reload":
            return [{"kind": c.kind, "cursor": c.cursor, **c.payload}
                    for c in self._reload(content)]
        if name == "rename":
            # Přejmenování je nevratný zásah do cizí věci (D-50), takže se
            # ptáme na `manage`. Neptáme se ale, PROČ ho ten člověk má.
            if MANAGE not in (subject.get("capabilities") or ()):
                raise ContentRefused("přejmenovat smí jen zakladatel nebo správce")
            with self._lock:
                content.title = str(event.get("title") or content.title)
            return [{"kind": "renamed", "title": content.title}]
        return []                       # neznámou událost apka mlčky ignoruje

    def close_content(self, handle: str) -> None:
        """Obsah zaniká. Volá instance podle `scope`, nebo vlastník výslovně.

        Zavření OKNA sem nevede — to je odpojení pohledu (apka-kontrakt.md §2).
        """
        with self._lock:
            self._contents.pop(handle, None)

    def list_content(self) -> list[dict[str, Any]]:
        """Všechny obsahy, které apka drží — **bez filtrování**.

        Filtruje instance, protože ACL obsahů drží ona. Kdyby filtrovala
        apka podle vlastnictví, dala by jinou odpověď než průnik: kdo má
        na sdílený dokument `read` a nezaložil ho, by ho ve spouštěči
        neviděl (F-23). `owner` je tu proto, aby spouštěč uměl oddělit
        moje od sdílených — je to údaj, ne právo.
        """
        with self._lock:
            return [{"handle": c.handle, "title": c.title, "owner": c.owner}
                    for c in self._contents.values()]

    # -- klientský kanál (volá dávka, cron, jiná služba) --------------------

    def content(self, handle: str, subject: dict[str, Any]) -> GraphContent:
        """Obsah pro doménové volání (`add_node`, `add_edge`, …).

        Subjekt sem přichází z **introspekce tokenu**, ne z důvěry ve
        volajícího: token říká kdo, rukojeť říká co. `capabilities` jsou
        odpověď instance na „co s tímhle obsahem smí" — apka je použije,
        neodvozuje si je.
        """
        content = self._require(handle)
        if WRITE not in (subject.get("capabilities") or ()):
            raise ContentRefused(f"bez práva zápisu k obsahu {handle}")
        return content

    # -- vnitřní ------------------------------------------------------------

    def _create(self, handle: str, owner: str, title: str | None) -> GraphContent:
        if title is None:
            counter = self._counters.setdefault(owner, itertools.count(1))
            title = f"Graph #{next(counter)}"
        content = GraphContent(handle, title, owner)
        self._contents[handle] = content
        return content

    def _require(self, handle: str) -> GraphContent:
        with self._lock:
            content = self._contents.get(handle)
            if content is None:
                raise ContentRefused(f"neznámá rukojeť: {handle}")
            return content

    @staticmethod
    def _reload(content: GraphContent) -> list:
        """Znovunačtení ze zdroje. Zatím nemá odkud — vrací prázdno, ale je
        to místo, kam to patří, a je vidět v menu jako `Reload from source`.
        """
        return []
