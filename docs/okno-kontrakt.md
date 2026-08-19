# Kontrakt okna: co okno nabízí a kde má mantinely

*Chybějící část návrhu. Co smí a nesmí kód apky v prohlížeči, jak se v okně
tvoří obsah, co dostane k dispozici a kdo hlídá, že si nevezme víc.*

---

## Proč to musí být napsané dřív než scaffold

Původní návrh říká, že apka dodá `ui.js` a Workbench ho načte
(`await import("/apps/…/ui.js")`). Tím ale mlčky vzniká nejsilnější
oprávnění v celém systému: **kdo zaregistruje apku, spouští kód
v prohlížeči každého diváka**, ve stejném origin jako Workbench. Takový kód
si přečte session id, sáhne do cizích oken, odposlechne klávesy.

Otázka „co okno nabízí" a otázka „co okno **ne**smí" jsou tedy jedna otázka.
Tenhle dokument na ni odpovídá.

## 1. Tři způsoby, jak dělat obsah (a jen jeden z nich je JS)

Většina oken žádný vlastní JavaScript nepotřebuje a **nemá ho mít**.

| úroveň | co to je | kdo to píše | kdy |
|---|---|---|---|
| **A. Prvky** | strom typovaných prvků ze serveru (`heading`, `table`, `input`, `button`, `chart`) | jen backend, žádný JS | výchozí volba; formuláře, přehledy, dashboardy |
| **B. Dokument** | HTML/Markdown ze serveru, sanovaný, bez skriptů | jen backend | dokumentace, reporty, e-maily |
| **C. Modul** | vlastní JS renderer v okně | autor apky | canvas/WebGL, terminál, editor, mapa |

Úroveň A pokryje odhadem devět z deseti oken. Je to zároveň jediná úroveň,
u které je bezpečnost triviální (server posílá data, klient je renderuje
známými komponentami) a která **funguje stejně pro sdílený i soukromý
obsah**.

```python
# úroveň A – vývojář nepíše řádek JS
w = screen.window.open("panel", id="mzdy", title="Mzdy")
w.heading("Výplaty")
w.table(["měsíc", "částka"], rows)
w.button("export", "Exportovat", on_click=export)
```

Úroveň C je výjimka, ne výchozí stav. Kdo ji chce, musí ji při registraci
**vyžádat** a Workbench ji povolí na základě stupně důvěry (§5).

## 2. Životní cyklus okna

Jeden objekt, čtyři povinné momenty. Nic jiného modul neimplementuje.

```js
export default {
  contract: 1,                       // verze kontraktu, viz §9
  mount(ctx)   { /* postav obsah do ctx.root */ },
  update(msg)  { /* přišla delta ze serveru */ },
  resize(size) { /* okno se změnilo; volitelné */ },
  unmount()    { /* ukliď: časovače, listenery, GPU */ },
}
```

- `mount` dostane **`ctx`** (§3) a musí být rychlý; dlouhá práce patří do
  `requestIdleCallback` nebo na server.
- `update` dostane už ověřenou a rozparsovanou zprávu — modul nikdy
  nezpracovává syrový rámec z drátu.
- `unmount` **musí** uklidit. Workbench po něm stejně strhne `ctx.root`
  a odpojí kanál, ale časovač, který si modul založil jinde, by přežil —
  proto §6 (mantinely) neposílá timery, ale takt.

Navíc dva stavy, které Workbench hlásí, protože je zná jen on:

```js
  visible(on)  { /* okno je vidět / je schované za jiným screenem */ },
  focus(on)    { /* okno je aktivní (klávesy chodí sem) */ },
```

Okno, které není vidět, **nedostává takt** (§6). To není doporučení — je to
mechanismus.

## 3. Co okno dostane: `ctx`

`ctx` je **jediná** cesta ven. Co v něm není, modul nemá.

```js
ctx = {
  root,                  // DOM uzel, který okno VLASTNÍ (a nic víc)
  id,                    // window_id v rámci plochy
  size: {w, h},
  theme,                 // barvy a metriky workbenche (jen ke čtení)
  locale,

  send(event, payload),  // zpráva na server (jde přes Workbench, ne přímo)
  on(action, handler),   // zprávy ze serveru mimo `update`
  state,                 // KLIENTSKÁ MEZIPAMĚŤ (viz níž) – ne stav aplikace

  frame(callback),       // takt místo requestAnimationFrame (viz §6)
  idle(callback),
  log(level, message),   // do log okna a auditu; sanované

  ui: { … },             // sdílené komponenty workbenche (tlačítka, tabulka…)
  capability: { … },     // jen to, co bylo při registraci povoleno (§5)
}
```

Tři věci na tom stojí za zdůraznění:

- **`ctx.state` není stav aplikace.** Je to klientská mezipaměť pro věci,
  které se dají kdykoli zahodit a znovu spočítat: pozice scrollbaru,
  rozbalený uzel stromu, poslední zvolená záložka. Přežije překreslení,
  **nepřežije reload** a **není sdílená mezi diváky**. Pravda o stavu žije
  na serveru; co si autor uloží sem, po reloadu zmizí — a u sdíleného obsahu
  bude mít každý divák něco jiného, aniž by se to nějak projevilo.

- **`ctx.root` je hranice.** Modul smí sahat pod něj, nikam jinam. Rám,
  lišta, menu, ostatní okna a `document` nejsou jeho.
- **`ctx.send` nechodí na apku přímo.** Jde přes Workbench, který doplní
  subjekt a autorizuje. Modul nemá jak poslat zprávu „jménem někoho jiného",
  protože identitu nikdy nedrží.

## 4. Co okno nesmí — a proč

Není to seznam doporučení. U izolovaného okna (§5) to vynucuje prohlížeč,
u důvěryhodného to hlídá review a testy.

| zakázáno | proč |
|---|---|
| `localStorage` / `sessionStorage` / cookies | leží tam **session id**; jeho držitel *je* tou relací |
| `document` mimo `ctx.root` | jinak si okno přečte obsah cizích oken a přepíše chrome |
| `fetch` / `XMLHttpRequest` / `WebSocket` na cokoli | druhá cesta ven obchází autorizaci i publikum; navíc exfiltrace |
| vlastní `import()` z cizího původu | totéž o úroveň výš — kód, který nikdo neschválil |
| globální posluchače na `document`/`window` | klávesy a fokus arbitruje WM (§7); jinak si okno vezme Esc všem |
| měnit z-order, velikost, titulek, zavřít se | to je chrome, ten patří Workbenchi |
| otevřít screen, jiné okno nebo dialog | okno není správce plochy |
| `eval`, `new Function`, `innerHTML` z dat serveru | z obsahu se nesmí stát kód |
| `alert` / `confirm` / `prompt` | zablokují celý Workbench, ne jen okno |
| trvale běžící smyčka (`setInterval`, vlastní rAF) | okno mimo obraz musí opravdu spát (§6) |

**Co okno naopak smí bez ptaní:** kreslit do `ctx.root`, používat `ctx.ui`,
posílat události, odkládat si do `ctx.state` zahoditelnou mezipaměť, číst
téma a velikost, logovat.

## 5. Schopnosti a stupně důvěry

Cokoli nad rámec §4 se **vyžaduje při registraci** a Workbench to buď
povolí, nebo ne. Nepovolená schopnost v `ctx.capability` prostě **není** —
modul se to dozví jako `undefined`, ne jako runtime chyba uprostřed práce.

```json
"client_module": {
  "url": "/apps/example.hello/ui.js",
  "contract": 1,
  "trust": "sandboxed",
  "capabilities": ["canvas2d", "keyboard-capture"]
}
```

| schopnost | k čemu | riziko |
|---|---|---|
| `canvas2d` / `webgl` | grafy, mapy, vizualizace | výkon, GPU paměť |
| `keyboard-capture` | terminál, editor (chce i Esc a Ctrl-C) | ukradne klávesy workbenchi |
| `clipboard-write` | „zkopírovat výsledek" | exfiltrace do schránky |
| `file-drop` | přetažení souboru do okna | vstup zvenčí |
| `download` | vygenerovaný soubor | únik dat |
| `fetch-origin` | volání na **vlastní** backend apky, přes proxy Workbenche | další cesta ven |

### Která schopnost je dostupná kterému stupni

Bez téhle tabulky by se registrace izolované apky se schopností
`fetch-origin` buď tiše povolila, nebo selhala bez srozumitelného důvodu.
Je to vynucovací místo, a ta mají být pojmenovaná:

| schopnost | `core` | `trusted` | `sandboxed` |
|---|---|---|---|
| `canvas2d` | ano | ano | ano |
| `webgl` | ano | ano | ano (vlastní kontext, vyšší cena) |
| `keyboard-capture` | ano | ano | ano (mimo klávesy rezervované WM, §7) |
| `clipboard-write` | ano | ano | jen na přímé gesto diváka |
| `file-drop` | ano | ano | ano |
| `download` | ano | ano | jen na přímé gesto diváka |
| `fetch-origin` | ano | ano | **ne** — izolované okno nemá druhou cestu ven |

Nedostupná kombinace se odmítne **při registraci**, ne za běhu, a s důvodem
v logu. Kdo `fetch-origin` opravdu potřebuje, žádá zároveň o `trusted` — a to
je vědomé rozhodnutí správce.

Stupně důvěry (viz [review](review-workbench-apps.md), výhrada 3):

| stupeň | izolace | kdo o něm rozhoduje |
|---|---|---|
| `core` | žádná, jeden bundle | typy dodané s Workbenchem |
| `trusted` | stejný origin, ale API jen přes `ctx` | **správce**, výslovně |
| `sandboxed` | `iframe sandbox="allow-scripts"`, CSP bez `connect-src`, most přes `postMessage` | výchozí pro publikované apky |

Izolace stojí výkon (vlastní kontext, žádné sdílené WebGL, kopírování zpráv
přes strukturovaný klon). Proto tři stupně a ne dva: **vestavěné typy
oken musí jet plnou rychlostí a přitom používat tentýž `ctx`.** Kdyby
`core` mělo vlastní privilegovanou cestu, veřejné API zakrní — a přesně
to se ve viewBase2 stalo s log oknem, které bylo speciální případ, a proto
v něm vznikl únik.

**Pravidlo:** vestavěné okno smí použít jen to, co je dostupné i apce.
Rozdíl je v tom, že se u něj neplatí za izolaci — ne v tom, co umí.

## 6. Mantinely na zdroje

- **Takt místo vlastní smyčky.** Modul nekreslí přes `requestAnimationFrame`,
  ale přes `ctx.frame()`. Workbench takt **nedodá** oknu, které není vidět,
  je minimalizované nebo je pod jiným screenem. Osm otevřených oken tak
  nestojí osm animačních smyček.
- **Rozpočet na snímek.** Když callback opakovaně přetáhne (např. 16 ms),
  Workbench oknu sníží takt a zaloguje to. Divák pozná, že okno je pomalé,
  ne že je pomalý celý workbench.
- **Hlídač.** Izolované okno, které přestane odpovídat na `postMessage`
  (nekonečná smyčka), se **ukončí** a rám ukáže „obsah přestal odpovídat"
  s možností nechat ho nastartovat znovu. Důvěryhodné okno tohle udělat
  nejde, proto je stupeň `trusted` vědomé rozhodnutí správce.
- **Strop na zprávy.** Server → okno i okno → server má limit velikosti
  a frekvence; překročení se zaloguje a zprávy se zahodí. Bez toho je
  jedno pokažené okno způsob, jak zastavit spojení všem ostatním.
- **Paměť.** Explicitně mimo záruky prohlížeče: modul se má chovat slušně,
  ale vynutit to nejde. Proto `unmount` a proto izolace — zabít iframe je
  jediná spolehlivá cesta, jak paměť vrátit.

## 7. Klávesy, fokus a Esc

Ve viewBase2 tohle bylo zdrojem skutečné chyby: vstupní pole si klávesu
zastavilo dřív, než dorazila k posluchači, a `Esc` ve výzvě přestal fungovat.
Arbitráž proto musí být pravidlo, ne zvyk.

1. Klávesy dostává **jen aktivní okno** a chodí přes `ctx`, ne přes
   `document`.
2. Workbench si **rezervuje** klávesy pro sebe (přepínání oken a screenů,
   `Esc` pro zavření výzev). Okno je nedostane ani se schopností
   `keyboard-capture` — jinak by šlo zablokovat cestu ven.
3. `keyboard-capture` znamená „chci i `Tab`, `Ctrl-C`, `F1`" (terminál,
   editor). I tak platí bod 2.
4. Fokus přiděluje WM a hlásí ho přes `focus(on)`. Okno si ho nebere samo.

## 8. Vzhled

Okno má vypadat jako součást workbenche, ne jako cizí web v rámečku.

- `ctx.theme` dává barvy, metriky a písmo **jen ke čtení**; modul z nich
  staví svůj obsah.
- `ctx.ui` nabízí hotové komponenty (tlačítko, tabulka, pole, oddělovač) —
  kdo je použije, dostane vzhled zdarma a při změně tématu se překreslí sám.
- Vlastní CSS je omezené na `ctx.root` (u izolovaného okna to plyne
  z iframe, u ostatních z ohraničení stylů).
- **Chrome kreslí Workbench.** Rám, titulek, gadgety, zvýraznění aktivního
  okna — do toho modul nesahá; jinak se osm apek rozejde v tom, jak vypadá
  zavírací křížek.

## 9. Verzování kontraktu

`contract: 1` je součást registrace. Workbench načte jen modul s verzí,
kterou umí; neznámá verze = okno se neotevře a je to vidět v logu, ne
záhadná chyba v runtime.

Rozšíření `ctx` o novou volitelnou vlastnost verzi nezvyšuje. Zvyšuje ji
odebrání, změna významu nebo nová povinnost pro modul.

## 10. Jak se okno testuje

Kontrakt je testovatelný, a proto má být otestovaný:

- **falešný `ctx`** (headless DOM) — modul se dá spustit bez serveru
  i bez Workbenche a ověřit `mount`/`update`/`unmount`,
- **test úklidu**: po `unmount` nesmí zůstat posluchač ani takt (počítadlo
  v testovacím `ctx`),
- **test mantinelů**: modul, který sáhne mimo `ctx.root` nebo na
  `localStorage`, musí v testu selhat — u izolovaného stupně to zajistí
  prohlížeč, u ostatních statická kontrola v CI,
- **test taktu**: schované okno nedostane ani jeden `frame()`,
- **konec řetězu v prohlížeči**: otevřít, poslat událost, dostat deltu,
  zavřít. Chyby ve spojení vrstev jinak než v prohlížeči nenajdete.

---

## Shrnutí jednou větou

**Okno dostane obdélník, kanál a hodiny; identitu, chrome, klávesové
zkratky ani druhou cestu ven nedostane nikdy — a co nad rámec obdélníku
potřebuje, si musí vyžádat při registraci, ne si to vzít za běhu.**
