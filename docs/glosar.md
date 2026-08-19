# Glosář: jedno jméno na pojem

*Kanonická jména pro obě strany drátu i pro kód. Kdo píše kód, docs nebo
schéma, používá tahle jména a žádná jiná.*

---

Dokumenty vznikaly postupně a mísí pojmy z různých vrstev (Workbench,
screen-manager, Instance, apka, content provider, slupka). Pro kód je to
past: dvě jména pro totéž se později srovnávají průchodem celého
repozitáře. Tenhle soubor je proto **závazný** — když je potřeba jméno
změnit, změní se tady a pak všude.

## Základ

| pojem | co to je | co to NENÍ |
|---|---|---|
| **Instance** | serverový runtime: vlastní politiku, relace, log, registr objektů a typů. To, co vzniká jako `vb.Instance(...)`. | není to proces ani kontejner — v jednom procesu jich může běžet víc |
| **Workbench** | **klientská** část: chrome, správce oken, registr rendererů, loader typů | není to server; v původním konceptu to znamenalo celého hostitele — tenhle význam **zaniká** |
| **Screen** | plocha (Amiga screen): titulek, téma, pořadí na liště, ACL | není to okno ani obrazovka prohlížeče |
| **Window** | **rám** okna: geometrie, z-order, titulek, minimalizace, zámek. Vlastní ho runtime. | není to obsah okna |
| **WindowType** (`kind`) | *jak se to vykreslí*: renderer + model obsahu + schéma + manifest | není to apka |
| **App** | *odkud je obsah*: model, stav, doménová logika. In-process nebo kontejner. | neřídí chrome, nezakládá plochy, neautentizuje |
| **Caller** | volající: relace prohlížeče i programový vstup, jeden typ pro obojí | není to uživatel — anonymní volající je taky Caller |
| **Session** | relace prohlížeče (neprůhledné id v `localStorage`) | není to přihlášení — relace může být anonymní |
| **Subject** | kdo je přihlášený (`user:hana`), nebo `anonymous` | není to Caller ani Session |

**Zaniklé pojmy:** `screen-manager` (je to Instance/runtime), `slupka`
(je to Window jako rám), `content provider` (je to App), `Project`
(je to Instance).

## Přístup

| pojem | význam |
|---|---|
| **principál** | `user:hana`, `group:ucetni` — to, proti čemu se vyhodnocuje ACL |
| **ACL** | množina povolených principálů. Žádné „deny". |
| **sloveso** | `read` (vidět) / `write` (zasahovat) — **jen tyhle dvě**. Platí `write ⟹ read`, takže efektivní čtení je `read ∪ write`. |
| **manage** | není sloveso ACL: **odvozené** právo zakladatele objektu nebo správce (přejmenovat, zrušit, změnit ACL). Platí `manage ⟹ write ⟹ read` a **jen tímhle směrem** — `write` nikoho nepovyšuje na `manage` (D-70). |
| **nabídka** | „tuhle apku jde na téhle ploše otevřít" — přežije zavření okna |
| **krok navíc** (step-up) | „jsi to fakt ty, teď?" — kód z autentikátoru u soukromého okna. Ortogonální k ACL. |
| **adresa** | `screen:<id>`, `screen:<id>/window:<id>`, `instance:log`. Klíč pro práva, log i vzdálené volání. |
| **publikum** (Audience) | komu se zpráva smí doručit. `Ref(adresa, sloveso)` nebo `Session(sid)`. |
| **schopnost** (capability) | co smí renderer nad rámec základu (`webgl`, `keyboard-capture`, …) |
| **stupeň důvěry** (trust) | `core` / `trusted` / `sandboxed` |

## Anglická jména v kódu

Docstringy a komentáře jsou české, **identifikátory anglické**. Tabulka
proto uvádí, jak se pojem jmenuje v kódu:

| česky v textu | v kódu |
|---|---|
| plocha | `screen` |
| okno (rám) | `window` |
| typ okna | `window_type`, `kind` |
| apka | `app` |
| relace | `session` |
| volající | `caller` |
| principál | `principal` |
| práva / přístup | `access`, `acl` |
| publikum | `audience` |
| krok navíc | `require_authentication` (veřejná vlastnost okna), `step_up` (vnitřní osa registrace události) |
| adresa | `address` |
| stupeň důvěry | `trust` |
| schopnost | `capability` |
| plocha je brána | `screen_gate` |
| lidský popisek čehokoli | `title` — plochy, okna, obsahu i nabídky. `name` v tomhle významu **neexistuje**. |

Totéž platí pro klíče payloadu, jména souborů, parametry cest v routách
a jména v konfiguraci — anglicky. Texty pro diváka jdou ze serveru jako
**klíč a parametry**, ne jako hotová věta; překlad je na klientovi.

## Kolekce versus vlastnost

Dva různé tvary a nemíchají se:

| co to je | tvar | příklad |
|---|---|---|
| **kolekce** — věcí je víc a dělají se s nimi operace | `kde.objekt.co` | `instance.screen.open(…)`, `screen.window.get("hello")`, `screen.window.all()` |
| **vlastnost** jednoho objektu | prostý atribut | `w.title`, `w.closable`, `w.access.require_authentication` |

Žádné `w.set.*` ani `w.get.*`: čtení a zápis mají být symetrické a to, co by
od jmenného prostoru někdo čekal (že zápis něco udělá — projde přes instanci
a zapíše se do auditu), obstará property setter sám. Jmenný prostor by přidal
jen slova a rozbil symetrii.

## Prefixy proměnných v příkladech a testech

V dokumentaci i v testech mají proměnné prefix podle druhu objektu. Není
to kosmetika: bez něj je na řádku `uctarna.app.register(graf, …)` potřeba
dohledat, které z těch dvou jmen je plocha a které apka.

| druh | prefix | příklad |
|---|---|---|
| instance | `inst` | `inst = vb.Instance(...)` |
| plocha | `scr_` | `scr_uctarna`, `scr_zasedacka` |
| apka | `app_` | `app_excel`, `app_graf` |
| obsah | `cnt_` | `cnt_mzdy`, `cnt_rizika` |
| okno (za běhu) | `win_` | `win_log = scr_uctarna.window.get("log")` |

Nabídka vlastní proměnnou obvykle nepotřebuje — `register` se volá pro
efekt. Když je potřeba (test, pozdější změna práv), je to `off_`.

## Pojmenování v protokolu

Na drátě se používají tatáž jména jako v kódu (`screen_id`, `window_id`,
`kind`, `seq`). Žádné zkratky navíc a žádná druhá sada jmen: co se pošle,
se musí dát najít v kódu grepem.
