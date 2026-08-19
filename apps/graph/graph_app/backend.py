"""Grafová apka: obsahy, jejich vlastnictví a obě API plochy.

Apka má dvoje dveře a chodí se do nich jinak (viz docs/apka-kontrakt.md §1):

- **prezentační** — volá instance viewBase: `open_content`, `snapshot`,
  `apply_event`, `close_content`, `list_content`. Nese `subject`.
- **klientská** — volá kdokoli s tokenem: `add_node`, `add_edge`, … adresované
  **rukojetí**. Tudy plní graf dávková úloha, která o oknech neví nic.

Apka **nedodává žádný JavaScript**: posílá data ve tvaru `graph.v1`, který
umí renderer z katalogu workbenche.

CO TU VĚDOMĚ NENÍ: okna, plochy, session id, ACL. Apka o nich neví a vědět
nemá — instance autorizuje před ní. Jediné, co apka rozhoduje sama, je
vlastnictví svých obsahů.
"""
from __future__ import annotations

import itertools
import secrets
import threading
from typing import Any

from .model import GraphContent

#: Schopnost, která pouští i k cizím obsahům. Instance ji spočítá (vlastník
#: nebo správce, D-41) a apka se **nedozví, kdo z nich to je** — jen že na to
#: má. Kdyby apka dostala „je správce", musela by si pravidlo *správce smí
#: i cizí* odvodit sama, a to je druhé místo, kde stejné pravidlo žije.
MANAGE = "manage"


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

    def open_content(self, handle: str | None, spec: dict[str, Any],
                     subject: dict[str, Any]) -> dict[str, Any]:
        """Vytvoř nebo se připoj. Tři případy a třetí je ten důležitý:

        - **bez rukojeti** → nový obsah, apka mu dá jméno,
        - **známá rukojeť** → připojení, pokud na ni subjekt má,
        - **neznámá rukojeť** → **odmítnutí**, nikdy tiché založení.

        Tiché založení by po překlepu nebo po zastaralém odkazu dalo divákovi
        prázdný graf a on by si myslel, že přišel o data.
        """
        owner = str(subject.get("subject_id") or "anonymous")
        with self._lock:
            if handle is None:
                content = self._create(owner, spec.get("title"))
            else:
                content = self._contents.get(handle)
                if content is None:
                    raise ContentRefused(f"neznámá rukojeť: {handle}")
                if not self._may_touch(content, subject):
                    raise ContentRefused(
                        f"'{owner}' nemá přístup k obsahu {handle}")
            return {**content.snapshot(), "title": content.title,
                    "handle": content.handle}

    def snapshot(self, handle: str, subject: dict[str, Any]) -> dict[str, Any]:
        """Stav pro daného diváka.

        ZNOVU SE TU NEAUTORIZUJE, jestli divák na okno má — to už udělala
        instance, než apku zavolala. Druhá kontrola jiným modelem by dřív nebo
        později dala jinou odpověď než ta první (viz apka-kontrakt.md §9).
        Kontroluje se jen vlastnictví obsahu, což je doména apky.
        """
        content = self._require(handle, subject)
        return {**content.snapshot(), "title": content.title}

    def apply_event(self, handle: str, subject: dict[str, Any],
                    event: dict[str, Any]) -> list[dict[str, Any]]:
        """Událost od diváka. Vrací změny; publikum určuje instance."""
        content = self._require(handle, subject)
        name = event.get("event")
        if name == "reload":
            return [{"kind": c.kind, "cursor": c.cursor, **c.payload}
                    for c in self._reload(content)]
        if name == "rename":
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

    def list_content(self, subject: dict[str, Any]) -> list[dict[str, Any]]:
        """Obsahy, ze kterých si tenhle člověk může vybrat ve spouštěči.

        Filtruje **apka**, protože vlastnictví obsahu jsou její data.
        Workbench rozhoduje o oknech, ne o tom, čí je který graf.
        """
        with self._lock:
            return [{"handle": c.handle, "title": c.title}
                    for c in self._contents.values()
                    if self._may_touch(c, subject)]

    # -- klientský kanál (volá dávka, cron, jiná služba) --------------------

    def new_content(self, owner: str, name: str | None = None) -> str:
        """Založ obsah BEZ OKNA a vrať rukojeť.

        Tohle je ta cesta, kvůli které obsah nesmí být svázaný s oknem:
        dávková úloha ho naplní dřív, než ho někdo otevře.
        """
        with self._lock:
            return self._create(owner, name).handle

    def content(self, handle: str, subject: dict[str, Any]) -> GraphContent:
        """Obsah pro doménové volání (`add_node`, `add_edge`, …).

        Subjekt sem přichází z **introspekce tokenu**, ne z důvěry ve
        volajícího: token říká kdo, rukojeť říká co.
        """
        return self._require(handle, subject)

    # -- vnitřní ------------------------------------------------------------

    def _create(self, owner: str, title: str | None) -> GraphContent:
        handle = "vb1_" + secrets.token_hex(8)
        if title is None:
            counter = self._counters.setdefault(owner, itertools.count(1))
            title = f"Graph #{next(counter)}"
        content = GraphContent(handle, title, owner)
        self._contents[handle] = content
        return content

    def _require(self, handle: str, subject: dict[str, Any]) -> GraphContent:
        with self._lock:
            content = self._contents.get(handle)
            if content is None:
                raise ContentRefused(f"neznámá rukojeť: {handle}")
            if not self._may_touch(content, subject):
                raise ContentRefused(f"nemá přístup k obsahu {handle}")
            return content

    @staticmethod
    def _may_touch(content: GraphContent, subject: dict[str, Any]) -> bool:
        """Vlastník obsahu, nebo kdo má schopnost `manage`.

        Vlastnictví je doména apky, takže první podmínku vyhodnocuje sama.
        Druhou dostane **hotovou** — instance už rozhodla; apka se neptá,
        jestli je někdo správce, protože to k práci nepotřebuje.
        """
        if subject.get("subject_id") == content.owner:
            return True
        return MANAGE in (subject.get("capabilities") or ())

    @staticmethod
    def _reload(content: GraphContent) -> list:
        """Znovunačtení ze zdroje. Zatím nemá odkud — vrací prázdno, ale je
        to místo, kam to patří, a je vidět v menu jako `Reload from source`.
        """
        return []
