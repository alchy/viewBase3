# appkit: vývojář apky píše logiku, nic jiného

*Co je knihovna, co je vývojářova práce, a proč je normativní knihovna
a ne drát.*

---

## 1. Cíl

Autor apky vymýšlí **jen logiku**. Komunikaci s workbenchem neřeší.

Měřítko je konkrétní: v dnešní grafové apce je `backend.py` sto padesát
řádků, ze kterých je doménová logika **jedna metoda**. Zbytek je transport,
rukojeti, schopnosti, kurzor a mapování chyb — a je to v každé apce totéž.

| vývojář apky | appkit |
|---|---|
| jaký je stav obsahu | transport obou kanálů |
| jaké operace nad ním jdou | tokeny, introspekce, cache, fail-closed |
| **co každá operace vyžaduje** | **vynucení toho požadavku** |
| co se pošle rendereru | kurzor, historie, `changes_since`, přiznaná mezera |
| — | manifest, routy, tři stavy výpadku, mapování chyb |

## 2. Jak to vypadá

```python
from viewbase_app import App, Content

class Graph(Content):
    """Jediné, co vývojář píše: co ten obsah je a co s ním jde dělat."""

    def created(self):
        self.nodes, self.edges = {}, {}

    def state(self):                              # co uvidí renderer
        return {"nodes": [...], "edges": [...]}

    @Content.needs("write")                       # co to vyžaduje
    def add_node(self, id, type=None, **meta):
        self.nodes[id] = {...}
        self.changed("add_node", {...})           # zapíše změnu, posune kurzor

    @Content.needs("manage")
    def rename(self, title):
        self.title = title

App(Graph, manifest="manifest.json").serve()
```

Ta jedna dekorace dělá čtyři věci naráz:

1. **vynutí sloveso** — porovná ho s `capabilities`,
2. vygeneruje **routu klientského kanálu** (`POST /content/{handle}/add_node`),
3. namapuje **událost z okna** na tutéž metodu,
4. doplní `events` do **manifestu**.

Bod 4 je důvod, proč se `events` nepíšou ručně: manifest pak nemůže tvrdit
něco jiného než kód. Manifest deklaruje **identitu a nasazení** (`app_id`,
`kind`, `scope`, `backend_base_url`, `appkit`); co apka umí, plyne z kódu.

## 3. Tři vlastnosti, kvůli kterým to stojí za to postavit

DRY je až čtvrtá v pořadí.

**Požadavek se deklaruje, nikdy nekontroluje.** Je to doslova pravidlo,
kterým jsme zavřeli nález 3.1 z viewBase2 — autorizace se psala v každém
handleru zvlášť a pět z devíti událostí ji nemělo. Teď platí i pro apky:
`if "write" not in capabilities` se v apce neobjeví ani jednou.

**Subjekt nejde získat bez pojmenování zdroje.** `app.caller(request)`
neexistuje — jen `app.caller(request, resource=...)`. A `Subject` si
pamatuje, pro co byl vydán; použít ho na jiný obsah vyhodí výjimku. Tím
zmizí „zeptal jsem se, ale na něco jiného".

**Kurzor je vlastnost protokolu, ne apky.** Když si každá apka napíše
vlastní historii a mezeru, jedna z nich to udělá subtilně jinak a instance
to nepozná — sešije delty přes díru. Tohle musí být jeden kód.

## 4. Co v appkitu nesmí být nikdy

**Žádné vyhodnocování ACL.** Žádní principálové, žádné „skupina → právo",
žádná dědičnost. Dovnitř jdou hotové `capabilities` a jediné, co se s nimi
děje, je porovnání s deklarovaným slovesem — na jednom místě, v jedné
funkci.

Introspekce navíc `groups` nevrací vůbec, takže z čeho by si appkit práva
odvozoval, ani neexistuje (viz [apka-kontrakt.md](apka-kontrakt.md) §9).

Bez tohohle pravidla by F-23 nevznikl v jedné apce, ale rovnou ve všech.

## 5. Normativní je appkit, ne drát

Tenhle protokol mluví **jenom viewBase se svými apkami**. „Drát je
normativní" by tedy kupovalo jedinou svobodu — napsat si klienta ručně —
a to je přesně ta svoboda, ze které vzejde jinak spočítaný kurzor
a znovuvymyšlená autorizace. Dva normativní popisy téhož protokolu
(dokument + knihovna) jsou navíc druhý zdroj pravdy.

Z toho plynou tři věci:

- **Verze jdou spolu.** Manifest nese `appkit: "1"` a instance apku
  s neslučitelnou major verzí **odmítne při registraci**, ne až za provozu.
  Tahle kontrola je možná jen tehdy, když obě strany vlastní tentýž popis.
- **Drát se smí měnit bez ceremonie**, dokud se obě strany hýbou spolu.
  Není co deprekovat.
- **Jiný jazyk znamená port appkitu**, ne ručně psaného klienta. A ten port
  je práce viewBase, ne autora apky — jen viewBase ví, jak se s ní mluví.
  Dokud port není, ten jazyk není podporovaný. Je to skutečný závazek,
  ne detail.

## 6. Balíčkování: vlastní artefakt, jednosměrná šipka

`viewbase-appkit` se distribuuje **samostatně** — ze stejného repa a ve
stejné verzi, ale jako vlastní balíček, který nezávisí na `viewbase.runtime`.

Důvod je F-21: import `viewbase.core` tehdy tahal celý runtime, takže
„autorizace se testuje bez serveru" přestávalo platit. U apky v kontejneru
je to horší — neměla by mít v závislostech FastAPI a uvicorn workbenche jen
proto, že chce mluvit s instancí.

```
appkit  ──zná──►  drát  ◄──zná──  runtime
```

Šipky se nikdy neotočí: **runtime appkit nezná.**

## 7. Apka v procesu appkit nepotřebuje

Když apka běží v témže procesu (`inst.app.register(ExcelApp())`), žádný
transport ani introspekce v cestě nejsou — instance volá metody přímo
a `subject` předává jako argument. Sdílí se jen typy kontraktu.

Proto má appkit dvě vrstvy a druhá je volitelná:

| vrstva | co je v ní | kdo ji potřebuje |
|---|---|---|
| `viewbase_app.contract` | `Content`, `Subject`, `needs`, kurzor, stavy výpadku | obě |
| `viewbase_app.http` | manifest, routy, introspekce, cache, `caller()` | apka v kontejneru |

---

*Kontrakt, který appkit implementuje: [apka-kontrakt.md](apka-kontrakt.md) ·
architektura: [architektura-navrh.md](architektura-navrh.md)*
