"""Model grafu: uzly, hrany, typy a jejich změny.

Vyčleněno z viewBase2 (`graph_window.py`), ale zbaveno všeho, co k modelu
nepatřilo: registru cizích oken, rozesílání klientům, relací a autorizace.
Tenhle modul neví, že existují okna, plochy nebo diváci — umí jen držet graf
a říct, co se v něm od určitého okamžiku změnilo.

KURZOR MÍSTO FRONTY. viewBase2 měl `_pending` a `drain()`: kdo si delty
vyzvedl, ten je měl, a nikdo jiný. To stačilo v jednom procesu, kde byl
odběratel jeden. Přes síť ne — divák se připojí, vyžádá si snapshot a mezitím
delty tečou dál. Proto má obsah **monotónní kurzor**: snapshot vrací stav
i kurzor a `changes_since(cursor)` doplní, co přišlo potom. Kdo se ozve moc
pozdě, dostane `None` a musí si říct o snapshot znovu — mezera se pozná,
místo aby se tiše přeskočila.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Any

#: Kolik posledních změn si obsah pamatuje. Kdo zaostane víc, dostane `None`
#: a vyžádá si snapshot — to je levnější než držet historii donekonečna.
HISTORY = 1024

_LABEL_KEY = re.compile(r"\{([^{}]+)\}")


@dataclass(frozen=True, slots=True)
class Change:
    """Jedna změna grafu i s pořadovým číslem.

    `kind` je jméno operace (`add_node`, `remove_edge`, …), `payload` její
    data. Tvar odpovídá kontraktu `graph.v1`, který konzumuje renderer.
    """

    cursor: int
    kind: str
    payload: dict[str, Any]


class GraphContent:
    """Jeden graf — to, čemu se v katalogu říká „obsah" a co má rukojeť.

    Vlastní zámek: k témuž obsahu může sahat prezentační kanál (instance) i
    klientské API (dávková úloha) současně.
    """

    def __init__(self, handle: str, name: str, owner: str) -> None:
        self.handle = handle
        self.name = name
        #: kdo obsah založil; podle toho se rozhoduje o destruktivních akcích
        self.owner = owner
        self._lock = threading.RLock()
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: dict[tuple[str, str], dict[str, Any]] = {}
        self._node_types: dict[str, dict[str, Any]] = {}
        self._label_template: str | None = None
        self._cursor = 0
        self._history: list[Change] = []

    # -- změny -------------------------------------------------------------

    def _record(self, kind: str, payload: dict[str, Any]) -> Change:
        """Zapiš změnu a posuň kurzor. Voláno vždy pod zámkem."""
        self._cursor += 1
        change = Change(self._cursor, kind, payload)
        self._history.append(change)
        if len(self._history) > HISTORY:
            del self._history[: len(self._history) - HISTORY]
        return change

    def define_type(self, name: str, **style: Any) -> None:
        """Definuj (i předefinuj) typ uzlu. Styl se **nahrazuje celý** —
        sloučení s předchozím by znamenalo, že se starý klíč nedá zrušit."""
        with self._lock:
            self._node_types[name] = dict(style)
            self._record("define_type", {"name": name, "style": dict(style)})

    def node_label(self, template: str | None) -> None:
        """Šablona popisku pro uzly bez vlastního `label` (`"{name} [{ip}]"`).

        Pořadí priorit: vlastní `label` uzlu > tahle šablona > id uzlu.
        """
        if template is not None and not isinstance(template, str):
            raise ValueError("node_label musí být řetězec nebo None")
        with self._lock:
            self._label_template = template
            for node in self._nodes.values():          # popisky se přepočítají
                self._record("update_node", self._public_node(node))

    def add_node(self, node_id: str, *, type: str | None = None,
                 label: str | None = None, **meta: Any) -> None:
        """Založ uzel. Existující id je chyba — na idempotentní zápis je
        `ensure_node`, aby se překlep nedal splést s úmyslem."""
        with self._lock:
            if node_id in self._nodes:
                raise ValueError(f"uzel '{node_id}' už existuje")
            if type is not None and type not in self._node_types:
                raise ValueError(
                    f"neznámý typ uzlu '{type}' – nejdřív zavolej define_type")
            node = {"id": node_id, "type": type,
                    "label_template": label, "meta": dict(meta)}
            self._nodes[node_id] = node
            self._record("add_node", self._public_node(node))

    def ensure_node(self, node_id: str, *, type: str | None = None,
                    label: str | None = None, **meta: Any) -> None:
        """Idempotentní `add_node`: chybějící založí, existujícímu sloučí
        metadata. Změna se zapíše jen tehdy, když se něco opravdu změnilo."""
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                self.add_node(node_id, type=type, label=label, **meta)
                return
            changed = False
            if type is not None and type != node["type"]:
                if type not in self._node_types:
                    raise ValueError(f"neznámý typ uzlu '{type}'")
                node["type"] = type
                changed = True
            if label is not None and label != node["label_template"]:
                node["label_template"] = label
                changed = True
            merged = {**node["meta"], **meta}
            if merged != node["meta"]:
                node["meta"] = merged
                changed = True
            if changed:
                self._record("update_node", self._public_node(node))

    def remove_node(self, node_id: str) -> None:
        """Odeber uzel i hrany, které na něm visí. Neznámé id je no-op —
        mazání má být idempotentní, jinak se dvojí úklid nedá napsat."""
        with self._lock:
            if node_id not in self._nodes:
                return
            for key in [k for k in self._edges if node_id in k]:
                del self._edges[key]
                self._record("remove_edge",
                             {"source": key[0], "target": key[1]})
            del self._nodes[node_id]
            self._record("remove_node", {"id": node_id})

    def add_edge(self, source: str, target: str, **meta: Any) -> None:
        """Hrana mezi existujícími uzly. Opakované volání jen sloučí meta."""
        with self._lock:
            for end in (source, target):
                if end not in self._nodes:
                    raise ValueError(f"uzel '{end}' neexistuje")
            key = (source, target)
            edge = self._edges.get(key)
            if edge is None:
                edge = {"source": source, "target": target, "meta": dict(meta)}
                self._edges[key] = edge
            else:
                merged = {**edge["meta"], **meta}
                if merged == edge["meta"]:
                    return
                edge["meta"] = merged
            self._record("add_edge", self._public_edge(edge))

    def remove_edge(self, source: str, target: str) -> None:
        with self._lock:
            if self._edges.pop((source, target), None) is None:
                return
            self._record("remove_edge", {"source": source, "target": target})

    # -- čtení -------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Celý stav a kurzor, ke kterému patří.

        Dvojice je nedělitelná: kdo dostane stav bez kurzoru, neví, odkud
        navázat deltami, a buď o změnu přijde, nebo ji použije dvakrát.
        """
        with self._lock:
            return {
                "state": {
                    "nodes": [self._public_node(n) for n in self._nodes.values()],
                    "edges": [self._public_edge(e) for e in self._edges.values()],
                    "node_types": {n: dict(s) for n, s in self._node_types.items()},
                },
                "cursor": self._cursor,
            }

    def changes_since(self, cursor: int) -> list[Change] | None:
        """Změny po daném kurzoru, nebo `None`, když je žadatel moc pozadu.

        `None` znamená „mezeru neumím doplnit, vyžádej si snapshot". Vracet
        místo toho jen to, co ještě mám, by tiše přeskočilo změny — a to je
        horší než přiznaná mezera.
        """
        with self._lock:
            if cursor > self._cursor:
                raise ValueError("kurzor je z budoucnosti")
            if cursor == self._cursor:
                return []
            if not self._history or self._history[0].cursor > cursor + 1:
                return None
            return [c for c in self._history if c.cursor > cursor]

    @property
    def cursor(self) -> int:
        with self._lock:
            return self._cursor

    # -- vnitřní ------------------------------------------------------------

    def _public_node(self, node: dict[str, Any]) -> dict[str, Any]:
        return {"id": node["id"], "type": node["type"],
                "label": self._render_label(node), "meta": dict(node["meta"])}

    @staticmethod
    def _public_edge(edge: dict[str, Any]) -> dict[str, Any]:
        return {"source": edge["source"], "target": edge["target"],
                "meta": dict(edge["meta"])}

    def _render_label(self, node: dict[str, Any]) -> str:
        template = node["label_template"] or self._label_template
        if template is None:
            return node["id"]

        def substitute(match: re.Match[str]) -> str:
            key = match.group(1)
            return str(node["meta"].get(key, ""))

        return _LABEL_KEY.sub(substitute, template)
