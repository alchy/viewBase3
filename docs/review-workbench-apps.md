# Kritické review návrhu „Workbench, apky a přístup"

*Recenze [`navrh-workbench-apps-puvodni.md`](navrh-workbench-apps-puvodni.md).
Co je správně a nechal bych to, co je vážná mezera, a co je potřeba
rozhodnout dřív, než se začne psát scaffold.*

---

## Shrnutí

Návrh je dobrý. Tři velká rozhodnutí — **chrome patří Workbenchi, obsah
apce**, **prohlížeč mluví jen se screen-managerem** a **klíč je
`(screen_id, window_id)`** — jsou správná a stojí za to je držet i tehdy,
když se kvůli nim něco zkomplikuje. Fázování (in-process scaffold → remote)
je rozumné a seznam anti-patternů v §18 je přesně ten, který by mě napadl.

Mám ale **osm výhrad**, z toho **tři blokující** (bez nich se scaffold
psát nemá, protože by se pak přepisoval) a pět, které stačí rozhodnout před
fází C.

| # | výhrada | závažnost |
|---|---|---|
| 1 | Zprávy nemají publikum — u víc relací na jedné ploše to teče | **blokující** |
| 2 | `session_id` se posílá apkám; to je přihlašovací údaj | **blokující** |
| 3 | Načtení JS apky je vzdálené spuštění kódu bez modelu důvěry | **blokující** |
| 4 | `groups` v `SubjectContext` = druhé místo, kde se rozhoduje o právech | vysoká |
| 5 | `authorize(subject, action, resource)` nad řetězci se nedá vynutit ani otestovat | vysoká |
| 6 | „Deny → chyba klientovi" prozrazuje existenci | střední |
| 7 | Vysokofrekvenční události přes HTTP na apku (klávesy, hover) | střední |
| 8 | Registrace apky bez autentizace; chybí chování při výpadku apky | střední |

Navíc dvě věci, které v návrhu **chybí úplně** a mají vlastní dokumenty:

- **co okno vlastně umožňuje** — co smí a nesmí JS, jak se v okně tvoří
  obsah, jaké má mantinely → [okno-kontrakt.md](okno-kontrakt.md),
- **modularizace typů oken** → [typy-oken.md](typy-oken.md).

---

## 1. Zprávy nemají publikum (blokující)

§13 popisuje dvě relace na jedné ploše a říká: *„Workbench rozhoduje **zda**
volat; apka může jemně škrtat **co** vrátí."* To ale platí jen pro
`snapshot`. Druhá cesta ven — `EventResult.deltas` — **žádného adresáta
nemá**:

```json
→ EventResult
{ "deltas": [ { "op": "set_text", "text": "nazdar MojeJmeno" } ] }
```

Workbench to podle §9 „přeloží na zprávy ke klientovi". Ke **kterému**?
Událost přišla od relace B, ale delta se rozešle všem, kdo okno vidí. Pro
sdílený graf je to správně; pro hello-app, kde si každý napsal svoje jméno,
je to únik. A jakmile apka podle §4.4 „smí filtrovat data podle
`subject_id`", je model rozporný: `snapshot` je per-subject, ale delty jsou
instance-wide. Snapshot a delty pak popisují **jiný stav**.

Přesně tahle třída chyb se ve viewBase2 stala u logu: log stream vznikl
dřív než pojem „komu", doručoval se stranou a jedno log okno na veřejné
ploše rozeslalo auditní stopu celé instance všem.

### Oprava

Rozhodnout, a to explicitně, dva různé druhy obsahu:

| druh | klíč instance | co to znamená |
|---|---|---|
| **sdílený** | `(screen, window)` | všichni, kdo okno vidí, vidí totéž (graf, log, dashboard) |
| **soukromý** | `(screen, window, session)` | každá relace má vlastní stav (formulář, hello, shell) |

Apka to deklaruje **při registraci** (`content: "shared" | "per-session"`),
ne za běhu. U soukromého obsahu Workbench zakládá instanci per relaci a
`snapshot` i delty patří té jedné relaci — bez dalšího uvažování.

A nezávisle na tom: **zpráva bez publika nesmí jít vyrobit.**

```python
class Message:
    payload: dict
    audience: Audience        # POVINNÉ, žádná výchozí hodnota
```

`EventResult` pak vrací `[(delta, audience)]`, kde apka smí zvolit jen mezi
`ALL_WHO_SEE` a `ONLY_CALLER` — širší publikum, než má sama povolené,
nastavit nemůže. Vysílací vrstva nezná okna ani práva; jen se ptá
`audience.allows(session)`.

*Poznámka k `shell`:* shell je učebnicový příklad soukromého obsahu, který
by ve sdíleném režimu byl bezpečnostní incident. Ať to model umí říct.

## 2. `session_id` se posílá apkám (blokující)

§4 posílá do apky `SubjectContext { subject_id, session_id, groups }`.
`session_id` je **přihlašovací údaj prohlížeče** — ve viewBase2 je to
neprůhledné id, jehož držitel je tou relací, a proto se ani do logu nepíše
celé, jen prefix. Poslat ho do kontejneru třetí strany znamená, že
kompromitovaná apka získá plnou identitu diváků.

### Oprava

- Apka dostane **korelační id instance a volání**, ne session id:

  ```text
  SubjectContext
    subject_id:    "user:42" | "anonymous"
    correlation:   "c9f1…"      # neprůhledné, per (instance, session), rotuje
    capabilities:  ["read", "write"]      # viz výhrada 4
  ```

- Korelační id slouží apce k tomu, aby si udržela stav per relace a aby se
  její log dal spojit s auditem Workbenche. Nic víc s ním nesvede.
- Kanál Workbench → apka musí být **autentizovaný** (sdílené tajemství nebo
  mTLS) a to patří do specifikace, ne do „provozních detailů". Bez toho si
  `SubjectContext` pošle kdokoli, kdo na apku dosáhne, a §4.3 („apka nevěří
  klientovi na slovo") tím ztrácí smysl — apka věří komukoli.

## 3. Načtení JS apky je vzdálené spuštění kódu (blokující)

§15.2:

```js
await import("/apps/example.hello/ui.js")
```

Kdo zaregistruje apku, spouští **libovolný JS v prohlížeči každého diváka**,
ve stejném origin jako Workbench. Takový modul si přečte `localStorage`
(kde leží session id), sáhne do DOMu cizích oken, odposlechne klávesy,
otevře vlastní spojení. Návrh o tom nemluví vůbec a §6.2 přitom dovoluje
registraci prostým `POST` z kontejneru.

Tohle není detail nasazení — je to hlavní bezpečnostní hranice celého
modelu apek. Buď se rozhodne, že **apky jsou důvěryhodné jako jádro** (a pak
to musí být napsané, registrace autentizovaná a moduly podepsané), nebo se
**izolují**. Nedá se to nechat otevřené.

### Oprava

Tři stupně důvěry, deklarované při registraci a vynucené Workbenchem:

| stupeň | kdo | izolace | co dostane |
|---|---|---|---|
| **core** | typy dodané s Workbenchem | žádná (jeden bundle) | plné API okna |
| **trusted** | apky výslovně povolené správcem | stejný origin, ale API jen přes `ctx` | plné API okna |
| **sandboxed** | výchozí pro publikované apky | `iframe sandbox="allow-scripts"` + CSP, `postMessage` most | jen deklarované schopnosti |

**Výchozí stav publikované apky je `sandboxed`.** Povýšení na `trusted` je
vědomý krok správce, ne důsledek toho, že se apka umí zaregistrovat.

Podrobný kontrakt (co `ctx` nabízí a co je výslovně zakázané) je
v [okno-kontrakt.md](okno-kontrakt.md).

## 4. `groups` v `SubjectContext` je druhé místo rozhodování

§4.4: *„Apka **smí** filtrovat data podle `subject_id` / `groups`."*
Tím vzniká druhý model práv — vedle access-manageru, s jinou sémantikou
a bez auditu. Za rok budou dvě odpovědi na otázku „proč tohle vidí".

### Oprava

Apka nedostane skupiny, ale **už rozhodnuté schopnosti pro tuhle
instanci**:

```text
capabilities: ["read", "write", "admin"]     # co Workbench pro tenhle subjekt povolil
```

Apka se rozhoduje podle nich, ne podle členství. Když potřebuje jemnější
řez („obchodník vidí jen své zakázky"), je to **doménové** pravidlo a patří
do apky výslovně jako doménové — ne jako druhá interpretace skupin.
Kdo chce policy, ať si o rozhodnutí řekne (`authorize` jako služba), místo
aby si ho odvozoval.

## 5. `authorize(subject, action, resource)` nad řetězci

Řetězcové akce (`"content.event"`) a zdroje (`"window:1/h1"`) jsou pružné,
ale **nedají se vynutit ani otestovat**. Nic nezaručí, že nové volací místo
autorizaci vůbec zavolá — a přesně to je chyba, která se ve viewBase2
stala dvakrát: nejdřív pět z devíti událostí kontrolu nemělo (psala se
v každém handleru zvlášť), podruhé existovala hodnota `Needs.NONE`, která
kontrolu vypínala úplně, takže se daly volat události na plochu, kterou
relace vůbec neviděla.

### Oprava

Ne zrušit `authorize`, ale doplnit ho o **deklaraci u registrace** a jeden
strojový test:

```python
register("hello_submit", handler, needs=Needs.USE)     # povinné, jinak výjimka
```

- `needs` je povinný parametr; bez něj registrace **skončí chybou**,
- **brána plochy platí vždycky** a žádná hodnota ji nevypíná — `needs` říká
  jen, co se žádá navíc o okno,
- test projde registr strojově: „pro každou registrovanou událost platí, že
  anonymní relace na skryté ploše nedosáhne na handler". Jeden test pokryje
  i tu desátou událost, kterou nikdo nenapsal.

Řetězcové `resource` je pro externí apky v pořádku, ale uvnitř Workbenche
má být cesta jedna a typovaná.

## 6. „Deny → chyba klientovi" prozrazuje existenci

§10 posílá při zamítnutí chybu klientovi. Rozlišitelná odpověď „na tohle
nemáš právo" potvrzuje, že objekt **existuje** — a u ploch a oken, které
subjekt nemá vidět, je to samo o sobě únik.

### Oprava

- objekt mimo ACL **není v snapshotu** a chová se, jako by neexistoval,
- událost na něj se **zahodí a zaudituje**, klient nedostane rozlišitelnou
  odpověď,
- srozumitelná chyba se posílá jen tam, kde subjekt objekt **vidí**, ale
  nesmí na něj sáhnout (typicky read-only divák) — tam je to naopak
  užitečné.

Zároveň platí opačné pravidlo pro diagnostiku: **do auditu jde vždycky
důvod**, a to konkrétní. Ve viewBase2 se tři různé příčiny odmítnutí kódu
hlásily stejnou hláškou a stálo to hodinu hledání v provozu.

## 7. Vysokofrekvenční události přes HTTP

`apply_event` jako HTTP volání na apku je v pořádku pro `hello_submit`.
Pro `shell_input` (jedna klávesa = jedno volání), `node_hover` nebo
`view_change` (~10×/s na klienta) je to neúnosné — latence i režie.

### Oprava

Typ okna při registraci deklaruje **profil provozu** a Workbench podle toho
vybere kanál:

| profil | příklad | kanál |
|---|---|---|
| `request` | `hello_submit`, `window_submit` | HTTP volání na apku |
| `stream` | `shell_input`, `terminal_output` | trvalé spojení Workbench ↔ apka (WS/gRPC), dávkování |
| `local` | `node_hover`, `view_change` | **nikdy neopustí prohlížeč**, řeší client module |

Třetí řádek je důležitý: spousta interaktivity nemá na server co dělat.
viewBase2 to má správně u fyziky grafu (běží v prohlížeči, server posílá jen
topologii) — ať je to v modelu pojmenované jako vlastnost typu okna, ne
náhoda.

## 8. Registrace a výpadek apky

- **Registrace bez autentizace** (§6.2, „apka POST na registry") znamená, že
  kdo dosáhne na Workbench, může zaregistrovat `kind` a — viz výhrada 3 —
  spustit JS u všech diváků. Registry musí mít token a povolený seznam.
- **Výpadek apky** není v návrhu vůbec. Musí být definované, co uvidí divák
  (okno s hláškou „obsah není dostupný", ne zaseknutý rám), jak dlouho se
  čeká a co se stane s instancemi. Bez toho jedna mrtvá apka zdrží celý
  Workbench.
- **Pořadí zpráv**: viewBase2 má invariant „patch dřív než akce, která na
  něj odkazuje". S deltami, které přicházejí z apky asynchronně, musí být
  pořadí definované — monotónní sekvence **per instance**, ne globální.

---

## Co bych z návrhu naopak nechal beze změny

- **Chrome vlastní Workbench, obsah apka.** Apka neotevírá screen, nemění
  z-order, neimplementuje výzvu k odemčení. §11.6 a §18 to říkají přesně.
- **Prohlížeč mluví jen se screen-managerem.** Jedna cesta ven znamená
  jedno místo, kde se dá vynutit publikum, a žádný cizí origin.
- **Klíč `(screen_id, window_id)`** místo „jednoho grafu procesu".
- **Krok navíc (`secured`/`private`) drží Workbench**, ne apka (§14).
- **Fázování**: nejdřív in-process scaffold za stabilními rozhraními, remote
  až potom. A `hello-app` jako první remote, ne graf — správné pořadí.
- **§12.8 (co musí pryč z `GraphWindow`)** je dobrý seznam a odpovídá tomu,
  co jsme ve viewBase2 dělali postupně a bolelo to.

## Co doplnit do specifikace, než se začne

1. **Instance je sdílená, nebo per relace?** Deklarovat při registraci.
2. **Zpráva nese publikum.** Bez výchozí hodnoty.
3. **Stupeň důvěry client modulu.** Výchozí `sandboxed`.
4. **Kanál Workbench ↔ apka je autentizovaný**, session id se neposílá.
5. **`needs` u registrace události** + strojový test registru.
6. **Profil provozu události** (`request` / `stream` / `local`).
7. **Chování při výpadku apky** a pořadí zpráv per instance.
8. **Kontrakt okna** — co `ctx` nabízí a co je zakázané
   ([okno-kontrakt.md](okno-kontrakt.md)).
9. **Modularizace typů oken** ([typy-oken.md](typy-oken.md)).
