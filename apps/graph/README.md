# workbench.graph

První apka postavená proti kontraktu (`docs/apka-kontrakt.md`). Leží
**záměrně mimo balíček `viewbase`** — kdyby byla uvnitř, nedokázali bychom,
že hranice mezi workbenchem a apkou je skutečná a ne jen nakreslená.

```
graph_app/model.py     graf: uzly, hrany, typy, popisky — a kurzor
graph_app/backend.py   obě API plochy: prezentační (instance) a klientská (dávka)
manifest.json          kind graph / contract graph.v1 / scope explicit / menu
tests/                 model, kontrakt a IZOLACE OBSAHŮ
```

Vyčleněno z viewBase2 (`graph_window.py`) a zbaveno všeho, co k modelu
nepatřilo: registru cizích oken, rozesílání klientům, relací a autorizace.

**Apka nedodává žádný JavaScript** — posílá data ve tvaru `graph.v1`, který
umí renderer z katalogu workbenche.

```bash
PYTHONPATH=. python -m pytest tests -q
```
