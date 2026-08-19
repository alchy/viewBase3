# Modularizace typů oken

*Druhá chybějící část návrhu. Co je „typ okna", z čeho se skládá, jak se
balí, jak se registruje — a proč většina apek nemá mít vlastní typ ani
vlastní JavaScript.*

---

## 1. Oprava, ze které plyne zbytek: `kind` ≠ apka

Původní návrh zavádí `kind` a `app_id` skoro jako dvojče — `example.hello`
má `kind: "hello-app"` a vlastní `ui.js`. To je nešťastné, protože hello-app
je ve skutečnosti **formulář a řádek textu**. Kdyby každá apka dostala
vlastní `kind` a vlastní modul, skončí i triviální okno ve vlastním
sandboxu, s vlastním rendererem a vlastní verzí kontraktu — a nikdo z toho
nic nemá.

**Oddělit dvě různé věci:**

| pojem | co to je | kdo to dodává |
|---|---|---|
| **`kind`** | *jak se to vykreslí* — renderer v prohlížeči | typ okna (vestavěný nebo publikovaný) |
| **`app_id`** | *odkud je obsah* — model, stav, business logika | apka (in-process nebo kontejner) |

Jsou to **dvě nezávislé osy** (stejně jako „kdo je kdo" a „co smí naše
objekty" v přístupovém modelu). Vztah je N:1 — mnoho apek sdílí jeden
`kind`:

```
kind: panel      ←  hello-app, ticketing, dashboard, nastavení, …
kind: graph      ←  viewbase.graph, topologie-sítě, závislosti-balíčků
kind: shell      ←  viewbase.shell
```

**Důsledek:** hello-app nepotřebuje `kind` ani JS. Zaregistruje se jako
apka, která dodává obsah pro `kind: panel`, a pošle strom prvků. Žádný
sandbox, žádný modul, žádná verze kontraktu.

Vlastní `kind` si žádá jen ten, kdo opravdu potřebuje **jiný způsob
vykreslení** — plátno, terminál, editor, mapu. To je vzácné.

## 2. Z čeho se typ okna skládá

Typ okna je jeden balík se čtyřmi částmi. Nic z toho nesmí být „na půl":

```
kind: graph
├── manifest        metadata: kind, verze kontraktu, schopnosti, důvěra,
│                   profil provozu, sdílený/soukromý obsah
├── server/         model obsahu: snapshot, delty, události, validace
├── client/         renderer: mount/update/resize/unmount (viz okno-kontrakt.md)
└── schema/         tvar zpráv oběma směry (jedna pravda pro obě strany)
```

### Manifest

```json
{
  "kind": "graph",
  "version": "1.4.0",
  "contract": 1,
  "content": "shared",
  "trust": "core",
  "capabilities": ["webgl"],
  "events": {
    "node_click":  { "needs": "screen", "profile": "request" },
    "node_hover":  { "needs": "screen", "profile": "local" },
    "view_change": { "needs": "screen", "profile": "local" }
  },
  "resources": { "frame_budget_ms": 12 }
}
```

Manifest je **jediné místo**, kde se o typu něco deklaruje. Workbench
z něj ví, co povolit, jak zprávy směrovat a co má testovat. Chybějící
položka není výchozí hodnota, ale chyba registrace.

Tři pole stojí za vysvětlení:

- **`content: shared | per-session`** — viz [review](review-workbench-apps.md),
  výhrada 1. Sdílený obsah vidí všichni, kdo okno vidí; soukromý má instanci
  per relaci. Shell a formuláře jsou soukromé, graf a log sdílené. Bez
  téhle deklarace nejde bezpečně rozeslat deltu.
- **`events[].needs`** — co událost žádá o přístup (brána plochy platí
  vždycky; `needs` říká, co navíc). Povinné, jinak registrace selže.
- **`events[].profile`** — `request` (HTTP na apku) / `stream` (trvalý kanál)
  / `local` (nikdy neopustí prohlížeč). Hover a pohyb kamery nemají na
  serveru co dělat.

## 3. Vestavěné typy: stejná pravidla, jiná cena

**Vestavěný typ používá tentýž veřejný kontrakt jako publikovaný.** Rozdíl
je jen v tom, že se u něj neplatí za izolaci (`trust: core`, jeden bundle,
žádný iframe) — ne v tom, co umí.

Je to tvrdé pravidlo, ne estetika: ve viewBase2 bylo log okno speciální
případ mimo běžnou cestu a přesně tam vznikl únik auditní stopy. Co má
privilegovanou zkratku, to se přestane testovat jako všechno ostatní.

## 4. Sada typů pro v3

Návrh sady na zelené louce, včetně toho, co z viewBase2 sloučit:

| `kind` | k čemu | obsah | schopnosti | poznámka |
|---|---|---|---|---|
| **`panel`** | prvky ze serveru: nadpisy, tabulky, pole, tlačítka, grafy hodnot | podle apky | – | **výchozí typ**; sloučení dnešního `HtmlWindow` + `ControlWindow` |
| **`doc`** | sanovaný HTML/Markdown dokument | sdílený | – | reporty, nápověda |
| **`graph`** | živý 2D/3D graf | sdílený | `webgl` | fyzika běží v prohlížeči, server posílá topologii |
| **`console`** | aplikační konzole: řádky + vstup | per-session | – | dnešní `TerminalWindow` |
| **`shell`** | skutečný terminál nad procesem | per-session | `keyboard-capture` | dnešní `ShellWindow`; vždy krok navíc |
| **`log`** | proud auditní stopy instance | sdílený | – | obsah dodává **runtime**, ne apka; vlastní ACL |

Čtyři poznámky k tomu:

1. **`HtmlWindow` a `ControlWindow` se slévají.** Ve viewBase2 jsou to dva
   typy, které dělají totéž jinak: jeden strom prvků, druhý typovaná pole.
   Rozdělení nedává smysl — formulář je jen panel, který má pole a tlačítko.
2. **Detailní okno uzlu není typ.** Je to `panel`, který otevře graf apka.
   Ve viewBase2 je zadrátované do jádra a nedá se nahradit.
3. **Zamčený rám není typ.** Je to **stav rámu**, který kreslí Workbench
   (`kind: "locked"` ve viewBase2 je hack, který mísí chrome a obsah).
   Okno bez kroku navíc se prostě nevykreslí a jeho obsah po drátě
   neputuje.
4. **`log` má obsah od runtimu.** Je to jediný typ, jehož zdrojem není
   apka, a proto jediný, u kterého se ACL nedědí z plochy (auditní stopa je
   instance-wide).

## 5. Rozvržení v repozitáři

Typ okna je **jedna složka**, ne kus rozprostřený mezi backend a frontend:

```
types/
  panel/
    manifest.json
    server/model.py          snapshot, apply_event, delty
    client/index.js          mount/update/resize/unmount
    schema/messages.json     tvar zpráv (generuje typy pro obě strany)
    tests/                   kontraktové testy typu
  graph/
    manifest.json
    server/{model.py,layout.py}
    client/{index.js,render/,physics/}
    schema/messages.json
    tests/
  shell/ console/ doc/ log/  …
```

Proti viewBase2, kde je model okna v `python/viewbase/controls.py`,
renderer v `frontend/src/plugins/*` a chování v `windows_mixin.py`, má
tohle jednu výhodu: **typ okna se dá přidat, odebrat i přenést jinam v celku
a nic po něm nezůstane.** A druhou: co drží pohromadě, je vidět pohromadě.

Jádro pak zná jen registr:

```python
registry.register(load_type("types/graph"))     # vestavěné při startu
registry.register(fetch_type(url, token))       # publikované, po ověření
```

## 6. Jak se typ dostane do prohlížeče

```
init pro klienta
  → seznam oken s `kind`
  → klient se podívá do registru rendererů
       zná?      → vykreslí
       nezná?    → vyžádá si modul podle manifestu (lazy import / iframe)
       neznámá verze kontraktu → okno se neotevře, jde to do logu
```

- **Vestavěné typy** jsou v hlavním bundlu, ale načítají se **líně**: graf
  se stáhne, až když se otevře grafové okno. viewBase2 to takhle má
  a osvědčilo se to.
- **Publikované typy** jde stáhnout jen přes Workbench (proxy), ne z cizího
  originu — kvůli CSP i kvůli tomu, aby se dala vynutit izolace.
- **Neznámý `kind`** není chyba klienta: rám se otevře s hláškou „tenhle typ
  okna neumím" a jde to do logu. Divák nemá koukat na prázdný obdélník.

## 7. Verzování

- **`contract`** — verze rozhraní mezi Workbenchem a rendererem. Mění se
  zřídka; neznámou verzi Workbench odmítne.
- **`version`** typu — jeho vlastní. Dva typy v různých verzích mohou žít
  vedle sebe, protože renderer se adresuje `kind@version`.
- **`schema`** — tvar zpráv. Přidání volitelného pole je zpětně slučitelné;
  cokoli jiného je nová `version` typu.

Pravidlo: **schéma je jedna pravda pro obě strany.** Server i klient si
z něj generují typy nebo si podle něj validují — ne dvě ručně udržované
definice, které se rozejdou.

## 8. Co typ okna musí doložit testy

Kontraktové testy jsou součástí balíku typu, ne volitelný extra:

1. **snapshot → render**: z ukázkového snapshotu vznikne obsah bez chyby,
2. **delta → update**: řada delt vede ke stejnému stavu jako snapshot po nich
   (idempotence a pořadí),
3. **úklid**: po `unmount` nezůstane posluchač ani takt,
4. **mantinely**: modul nesáhne mimo `ctx.root` ani na zakázané API,
5. **schopnosti**: bez povolené schopnosti se okno degraduje, nespadne,
6. **soukromý obsah**: u `content: per-session` se delta jedné relace
   neobjeví u druhé (u `shared` naopak musí),
7. **autorizace**: každá událost z manifestu má `needs` a projde strojovým
   testem registru.

Sedmý bod je ten, který ve viewBase2 chyběl a stálo to díru: testy ověřovaly
jednotlivé funkce, ale ne pravidlo nad celým registrem.

## 9. Migrace ze současného stavu

Pořadí, které nezablokuje vývoj:

1. **`panel`** jako první typ v novém balení (sloučení `HtmlWindow` +
   `ControlWindow`). Pokryje většinu oken a hned se na něm ověří manifest,
   schéma i kontraktové testy.
2. **`log`** jako druhý — je malý, ale vynutí si vyřešení publika
   a vlastního ACL, tedy tu nejnepříjemnější část.
3. **`console`** a **`shell`** — vynutí si `per-session` obsah, profil
   `stream` a `keyboard-capture`.
4. **`graph`** jako poslední. Je největší a nejvíc se od něj bude chtít
   výkon; do té doby už bude kontrakt prověřený třemi typy.
5. **hello-app** jako první *publikovaná apka* — a měla by vyjít jako
   `kind: panel` **bez jediného řádku JS**. Když to nepůjde, je to nález
   o kontraktu, ne o hello-app.

Poslední bod je zároveň nejlepší akceptační kritérium celého modelu.
