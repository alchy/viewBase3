# viewBase3

Návrhové poznámky. Kód zatím žádný — nejdřív je potřeba mít rozhodnuté to,
co se ve [viewBase2](https://github.com/alchy/viewBase2) muselo dostavovat
a pak přepisovat.

| dokument | o čem to je |
|---|---|
| **[Architektura — poznámky](docs/architektura-navrh.md)** | pět principů a co z nich plyne: objektový model, zprávy s publikem, instance jako vlastník stavu, adresování, vynucovací místa, souběh, testovací strategie, rozvržení modulů |
| **[Kontrakt okna](docs/okno-kontrakt.md)** | co okno nabízí obsahu a kde má mantinely: tři způsoby tvorby obsahu (jen jeden z nich je JS), životní cyklus, `ctx`, co je zakázané a proč, schopnosti a stupně důvěry, zdroje, klávesy, vzhled |
| **[Modularizace typů oken](docs/typy-oken.md)** | `kind` (jak se to vykreslí) ≠ apka (odkud je obsah); z čeho se typ skládá, sada typů pro v3, rozvržení v repu, verzování, migrace |
| **[Review konceptu Workbench/apky](docs/review-workbench-apps.md)** | kritické čtení původního návrhu: co nechat, osm výhrad (tři blokující) a co doplnit, než se začne psát |
| **[Co převzít z viewBase2](docs/co-prevzit-z-viewbase2.md)** | inventura: převzít / přepsat / nechat být + 14 konkrétních chyb a pravidlo, které každou z nich zavírá |
| **[Původní koncept](docs/navrh-workbench-apps-puvodni.md)** | vstupní návrh „Workbench, apky a přístup" beze změn (předmět review) |

## Odkud začít

1. **[Architektura](docs/architektura-navrh.md)** — pět principů. Zbytek je
   jejich rozvedení.
2. **[Review](docs/review-workbench-apps.md)** — tři blokující výhrady jsou
   věci, které se po napsání scaffoldu už opravují draho.
3. **[Kontrakt okna](docs/okno-kontrakt.md)** a
   **[typy oken](docs/typy-oken.md)** — dvě části, které v původním konceptu
   chyběly.

## Jedna věta

Model přístupu se nedá dostavět, aniž by po něm zůstaly díry přesně tam,
kde data tečou ven mimo hlavní cestu — log, REST, snapshot pro nově
připojeného klienta.
