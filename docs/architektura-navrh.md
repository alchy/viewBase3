# viewBase3 — poznámky k architektuře

*Co bych navrhl jinak, kdybych viewBase stavěl znovu. Poznámky, ne
specifikace: říkají, jaká rozhodnutí udělat dřív než se začne psát, a proč.*

---

## Odkud to je

viewBase2 funguje a je na něm postavená spousta věcí, které stojí za to
zachovat. Většina jeho problémů ale nebyla náhoda — byly to důsledky pár
raných rozhodnutí, která se dala udělat jinak skoro zadarmo, kdyby se
věděla dopředu. Tenhle dokument je jejich seznam.

Konkrétní chyby, ze kterých to plyne, jsou v
[co-prevzit-z-viewbase2.md](co-prevzit-z-viewbase2.md); tady je jen to, co
z nich plyne pro návrh.

**Souvisí:** [review konceptu Workbench/apky](review-workbench-apps.md) ·
[kontrakt okna](okno-kontrakt.md) · [modularizace typů oken](typy-oken.md)

**Jedna věta na začátek:** model přístupu se nedá dostavět, aniž by po něm
zůstaly díry přesně tam, kde data tečou ven mimo hlavní cestu — log, REST,
snapshot pro nově připojeného klienta. Všechny čtyři vážné nálezy ve
viewBase2 byly v těchhle třech místech.

## 1. Pět principů, ze kterých plyne zbytek

1. **Nic neopustí proces bez uvedení publika.** Zpráva je od narození
   dvojice `(obsah, publikum)`. Funkce, která vyrábí data pro klienta, nesmí
   existovat bez argumentu „pro koho".
2. **Instance vlastní svůj stav.** Žádné proces-wide globály. Dvě instance
   v jednom procesu musí být samozřejmost, ne otázka.
3. **Každý objekt má adresu od narození.** Neprůhledné id + cesta
   `rodič/dítě`. Touž adresou se řídí práva, log i vzdálené volání.
4. **Každé bezpečnostní rozhodnutí vrací důvod, ne ano/ne.** Diagnostika je
   součást bezpečnosti.
5. **Invariant se testuje nad registrem, ne nad jednotlivostí.** „Pro každou
   registrovanou událost platí, že…" chytí i tu desátou, kterou nikdo
   nenapsal.

Zbytek dokumentu je jen rozvedení těchhle pěti vět.

## 2. Objektový model

```
Instance                      vlastní politiku, relace, log, zdroj identit
 └── Screen        id: opaque, adresa "screen:<id>"
      ├── Window   id: opaque nebo pojmenované, "screen:<id>/window:<id>"
      ├── Window
      └── LogView  taky okno, ale s vlastním ACL (viz §7)
```

**`Instance` je skutečný objekt, ne konfigurátor globálů.** Ve viewBase2 má
`Project` parametry, ale vlastní stav leží v modulech (`log.bus`,
`sessions.store`, `identity.provider`, `access.DEFAULT_ACCESS`,
`mfa._store_override`, …). Důsledek: cesta k souboru politiky přetekla
z jednoho testu do celé sady, `reset_state()` musel postupně zapomínat čím
dál víc věcí a testy potřebovaly autouse fixturu, která instanci přepne do
známého stavu.

```python
instance = vb.Instance(policy=…, identity=…, log=…, sessions=…)
screen = instance.screen.open(title="Provoz", id="provoz")
window = screen.window.open("panel", id="mzdy", title="Mzdy")
```

**Gramatika API je `kde . objekt . co`** a drží se na každé úrovni:

```python
instance.screen.open(title=…, id=…)      instance.screen.get("provoz")
screen.window.open("panel", id=…)        screen.window.get("mzdy")
screen.window.close("mzdy")              screen.window.all()
```

Dvě věci, které z toho plynou a jsou důležitější než vzhled:

- **Typ okna je hodnota, ne jméno metody.** `screen.window.open("panel", …)`
  znamená, že jádro seznam typů **nezná** — jen ho podá registru. Kdyby
  existovalo `open_panel()`, musel by každý nový typ přidat metodu na
  `Screen` a publikovaný typ třetí strany by vlastní metodu nikdy nedostal:
  vestavěné typy by měly privilegovanou cestu (viz `typy-oken.md` §3).
  Neznámý `kind` selže **hned při volání**, se seznamem registrovaných typů.
- **Jmenný prostor je objekt, ne sloveso.** `screen.open.window(…)` by
  znamenalo `open` s jediným členem a pak `close`, `find`, `list` jako další
  prostory po jednom. Takhle roste jeden prostor o slovesa.

Jednotné číslo (`window`, ne `windows`) má jeden důsledek: procházení se
nedá napsat jako `for w in screen.window`, proto je na to výslovné
`screen.window.all()`.

Objekt si drží odkaz na instanci, ne na modul. Testy pak nepotřebují nic
resetovat — vyrobí si vlastní instanci.

**Adresa vzniká při narození.** Ve viewBase2 okno vzniká bezejmenné
(`HtmlWindow("mzdy")`) a adresu dostane, teprve když ho plocha přijme; do
té doby má práva „nikam nepatřící" objekt. Když se okno vyrábí přes
`screen.window.open(...)`, tenhle mezistav neexistuje.

**Id je neprůhledné, pořadí je něco jiného.** viewBase2 měl procesní čítač
`1, 2, 3…`, který plnil dvě role zároveň — pořadí na liště a adresu. Jako
adresa je rozbitý: dva procesy vyrobí `screen_id=1` pro dvě různé plochy.
Držet obojí zvlášť (`id` a `index`) je levné a otevírá to REST i rozdělení
mezi procesy.

## 3. Zprávy a publikum

Tohle je nejdůležitější změna oproti viewBase2.

**Špatně (v2):** okno vyrobí akci → akce se zařadí do fronty → vysílací
smyčka na ni nalepí adresní značky (`only_sid`, `grant`, `acl`) → před
odesláním se značky zase strhnou. Publikum je vlastnost *doručení*, ne
zprávy. Kdo přidá novou cestu ven (log stream, REST push), snadno na
publikum zapomene — a přesně to se stalo.

**Správně (v3):**

```python
class Message:
    payload: dict
    audience: Audience          # POVINNÉ, není default

# Publikum má dva tvary a OBA se vyhodnocují až při doručení:
Ref(address, verb)      # „kdo smí VIDĚT screen:provoz/window:mzdy"
Session(sid)            # přímá odpověď jednomu volajícímu
And(a, b)               # obojí zároveň (odpověď mně, ale jen když na to mám)
```

**Pozdní vazba je povinná, ne volitelná.** Zmrazit množinu principálů při
vzniku zprávy je lákavé (publikum by bylo čistá hodnota), ale delta vyrobená
vteřinu před odebráním práv by se doručila i po něm. Proto se publikum
neptá „kdo to byl", ale **„kdo to smí teď"**.

Množina principálů proto v `Audience` vůbec není — a to je záměr: neexistuje
tvar, kterým by šlo publikum omylem zmrazit.

Vysílací smyčka pak **neví nic o oknech ani o právech** — dostane při startu
jedinou funkci `resolve(address, verb) -> Acl` a ptá se
`audience.allows(caller, resolve)`. (Sloveso tam patří: tatáž adresa má pro
`see` a pro `write` jiné ACL.) Jedna předaná funkce, žádný import
napříč vrstvami. Objekty naopak nevědí nic o soketech.

Praktický důsledek: `LogView` je jen další zdroj zpráv s vlastním publikem.
Ve viewBase2 byl log stream doručovaný stranou a jeho ACL se braly ze
screenu, na kterém okno leželo — takže jedno log okno na veřejné ploše
rozeslalo auditní stopu celé instance všem. V tomhle modelu ta chyba nejde
napsat: zpráva bez publika nevznikne.

**Snapshot pro nového klienta je táž cesta.** Ve viewBase2 má `snapshot()`
výchozí `sid=None`, což znamená „když se nikdo neptá pro koho, dej všechno".
V3: `snapshot(for_session)` bez výchozí hodnoty. Když funkce neví, komu
odpovídá, nesmí jít zavolat.

**Okno není jen rám.** Co okno nabízí obsahu, co smí a nesmí jeho kód
v prohlížeči a jak se v něm vůbec tvoří obsah, je vlastní téma — a v původním
konceptu chybělo úplně: [okno-kontrakt.md](okno-kontrakt.md). Jak se typy
oken balí a proč většina apek nemá mít vlastní: [typy-oken.md](typy-oken.md).

## 4. Přístup

Model z viewBase2 je dobrý a přebral bych ho beze změny: **principálové**
(`user:hana`, `group:ucetni`), **ACL jako množina povolených** (žádné
„deny"), **dvě slovesa** (vidět / zasahovat), **dědičnost** objekt → plocha
→ výchozí hodnota instance, a **krok navíc** jako ortogonální vlastnost.

Celá autorizace je jedna funkce nad množinami:

```python
def allowed(principals, acl) -> bool:
    if ADMINISTRATOR in principals:      # obdoba roota, vědomě
        return True
    return bool(principals & acl)
```

Tři věci bych udělal jinak:

**a) Krok navíc patří do `access`, ne vedle něj.** viewBase2 má
`private=True` jako booleán na okně, zatímco přístup je objekt. Obojí je
politika a mělo by bydlet na jednom místě:

```python
window.access.see.set(["group:ucetni"])       # vlastní ACL okna; končí dědění
window.access.see.add("user:hana")            # …a ještě konkrétní člověk
window.access.write.set(["user:hana"])
window.access.require_authentication = True   # chce kód, i když ACL projde
```

**`add` a `remove` fungují jen na objektu, který už vlastní ACL má.** Na
objektu, který dědí, obojí **skončí chybou** s návodem — a je to schválně.
Kdyby `add` na dědícím okně prošlo, musí si vybrat mezi dvěma výklady a oba
jsou špatně:

| výklad | co udělá | proč je špatně |
|---|---|---|
| začni od **vlastního** (prázdného) | okno dědící `see=[users]` se po `add("group:ucetni")` stane viditelným **jen účetním** | slovo „přidej" viditelnost **zúžilo** |
| začni od **efektivního** | vyjde `[users, ucetni]`, jak čtenář čeká | **zmrazí dědičnost** — pozdější zúžení plochy už na okno nedosáhne, a to je cesta k úniku |

Druhý výklad selhává **tiše a otevřeně** (lidé vidí, co nemají), první
**hlučně a zavřeně** (někdo si stěžuje, že nevidí). Proto se nevybírá ani
jeden: kdo chce oknu dát vlastní ACL, napíše `set([...])` a je z toho vidět,
že dědění končí. Model zůstává „první nastavený člen řetězu vyhrává".

**b) `Acl` je neměnná hodnota, ale zápis zůstává čitelný.** Tyhle dvě věci
si na první pohled odporují (a chvíli si v tomhle dokumentu opravdu
odporovaly, viz nález F-06). Řeší se to tak, že se **rozdělí, co je hodnota,
a co je API**:

- v `core/` je `Acl` **hodnota**: `with_added()` a `without()` vracejí novou.
  Nic o auditu neví a vědět nemá,
- `window.access` v `runtime/` je **fasáda**: přečte současnou hodnotu,
  spočítá novou a **vede změnu přes instanci**, která k ní připojí kdo, kdy
  a na jakém objektu — a zapíše to do auditu.

```python
window.access.see.add("group:ucetni")     # čte se jako knihovna (D-01)
   ↓
instance.set_access(address, Verb.SEE, acl.with_added("group:ucetni"), by=caller)
   ↓  audit: access change: screen:provoz/window:mzdy see +group:ucetni by=internal
```

Fasáda **není měnitelná `Acl` v přestrojení**: čtení vrací snímek
(`window.access.see.list()`), zápis jde jedinou cestou přes instanci.

**`by` je v záznamu vždycky**, i když změnu udělal vlastní kód knihovny —
tam je hodnota `internal`. Až budou práva chodit i po drátě, ponese totéž
pole skutečného volajícího; kdyby vzniklo teprve tehdy, nedají se starší
záznamy porovnat s novějšími. Prázdné pole je horší než pole s hodnotou
„vlastní kód".
`window.access.require_authentication = True` je totéž — je to politika
a audituje se stejně jako ACL.

**Veřejné jméno říká, co se stane; vnitřní jméno pojmenovává mechanismus.**
Vývojář píše `require_authentication` (rozumí tomu, aniž by znal pojem
*step-up*); uvnitř se ta osa dál jmenuje `step_up`, protože tam jde
o mechanismus a čtenářem je knihovna, ne autor aplikace. Koncept a volání
nemusí mít stejné jméno — a veřejný povrch se pojmenovává pro toho, kdo ho
čte poprvé.

Protože je publikum vázané pozdně (§3), **změna platí na nejbližší
doručenou zprávu**. Žádná neviditelná prodleva mezi „odebral jsem právo"
a „přestalo to chodit".

**c) Dokumentovaný zápis musí mít test.** Ve viewBase2 byl
`okno.access.add(...)` v README, v docs i ve specifikaci, ale `Access` tu
metodu **neměl** — spadl by na `AttributeError`. Každý zápis, který je
v dokumentaci, patří do testu doslova.

## 5. Vynucovací místa

Mít jich **málo a pojmenovaných**. Ve viewBase2 jsou čtyři a to je dobré
číslo:

| místo | co hlídá |
|---|---|
| handshake spojení | odkud smí přijít stránka (`Origin`) |
| snapshot pro klienta | co vůbec dostane nově připojený |
| příchozí událost | co smí klient vyvolat |
| doručení zprávy | komu se která zpráva pošle |

Pravidlo, které ve viewBase2 chybělo a stálo to díru: **brána plochy platí
u každé události a nesmí jít vypnout.** Deklarace při registraci smí říkat
jen, co se žádá *navíc*:

```python
register("shell_input",   handler, needs=Needs.WRITE)
register("window_unlock", handler, needs=Needs.SEE, step_up=StepUp.EXEMPT)
register("menu_select",   handler, needs=Needs.SCREEN)
```

Enum je **úplný** a nemá hodnotu, která by kontrolu vypínala:

| `needs` | co se kontroluje | okno vidět | okno zasahovat |
|---|---|---|---|
| `INSTANCE` | **ACL instance** (`instance:`, sloveso *zasahovat*) | – | – |
| `SCREEN` | ACL plochy, *zasahovat* | – | – |
| `SEE` | ACL plochy, *vidět* | ano | – |
| `WRITE` | ACL plochy, *zasahovat* | ano | ano |

**Pomlčka znamená „netýká se", nikdy „nekontroluje se".** Každá hodnota má
proti čemu se vyhodnotit — kdyby některá neměla, je to `NONE` pod jiným
jménem, tedy přesně ta hodnota, kterou jsme z enumu vyhodili. (Přesně tahle
past v téhle tabulce byla: `INSTANCE` tu měla pomlčky ve všech sloupcích,
takže jak bylo napsané, nekontrolovala nic — nález F-11.)

**Instance je objekt jako každý jiný.** Má adresu `instance:` a vlastní ACL,
takže se `INSTANCE` vyhodnocuje **toutéž** funkcí `resolve(address, verb)`
jako všechno ostatní — žádná zvláštní cesta. Výchozí hodnota je **zavřeno**:
projde jen správce (přes výjimku v `allowed`). Správa instance — zakládání
ploch, administrativní akce — se tak nedá zavolat anonymně přes REST.

**Zasahovat implikuje vidět.** Událost s `needs=WRITE` musí projít ACL okna
pro *obě* slovesa. Není to jen opatrnost: okno, které relace nevidí, se jí
nikdy nedoručilo, takže zápis do něj může přijít jen z podvrženého klienta.

**Obě úrovně se kontrolují zvlášť, dědičnost je nesloučí.** Dědičnost
odpovídá na otázku „jaké ACL platí pro *tenhle* objekt"; brána plochy je
**samostatná** kontrola před ní. Konkrétní past: okno má `see=[users]`,
plocha má `write=[administrator]`. Nenastavené `write` okna padá na jeho
vlastní `see`, takže efektivní ACL okna pro zápis je `[users]` — a kdyby
runtime kontroloval jen okno, uživatel by psal do okna na ploše, kde smí
zasahovat jen správce. Brána plochy to zavírá, ale **jen když se zeptá
zvlášť**.

**Krok navíc je druhá, nezávislá osa**, ne pátá hodnota. `step_up` je
u registrace události vnitřní jméno téhle osy (veřejná vlastnost okna se
jmenuje `require_authentication`, viz §4b) a je
`REQUIRED` (výchozí); `EXEMPT` má **jediná** událost — `window_unlock`,
protože ta je právě tou cestou, kterou se krok navíc získává. Výjimka je
tím deklarovaná, ne schovaná v komentáři, a strojový test hlídá, že ji nemá
nikdo jiný.

Ve viewBase2 existovala hodnota `NONE` ve významu „nekontroluj nic" — a
`shell_new`, `menu_select` i každá uživatelská událost se daly zavolat na
plochu, kterou relace vůbec neviděla. Hodnota, která vypíná kontrolu, nemá
v enumu co dělat.

**Principály dosazuje vždycky server, ať v payloadu byly nebo ne.** Kdyby
se jen doplňovaly, když chybí, poslal by si je klient sám a byl by z toho
správce.

## 6. Vstupy bez relace (REST, integrace)

Každý vstup má identitu, i když je to „nikdo". Ve viewBase2 neměl REST
identitu žádnou, takže `curl` bez ničeho spustil autorský handler na ploše,
kterou nikdo neměl vidět.

```
vstup bez tokenu   → principals = {group:public}
vstup s tokenem    → principals z konfigurace instance
```

Návrhově: **jeden typ „volající" (`Caller`) pro relaci prohlížeče i pro
programový vstup.** Rozdíl je jen v tom, odkud se jeho principálové vzali.
Vynucovací kód pak nemá dvě větve.

**Programový vstup se nikdy nedostane k oknu s krokem navíc.** Krok navíc
patří dvojici *(relace, objekt)* a volající bez relace žádnou nemá — žádný
token to neobejde. Je to správně (kód z autentikátoru se ptá „jsi to fakt
ty, teď", a to stroj doložit nemůže), ale je to provozní důsledek, na který
se naráží pozdě: kdo potřebuje, aby do okna psala integrace, **nedává na to
okno krok navíc** a řeší to ACL (`rest_access`). Kdyby to šlo obejít
tokenem, přestal by krok navíc znamenat to, co znamená.

## 7. Log a audit

Log je **vlastní objekt s vlastním ACL**, ne pohled odvozený z plochy.
Auditní stopa je instance-wide; kdyby dědila práva od plochy, na které
zrovna leží okno, publikuje ji první veřejná plocha.

- výchozí ACL logu = výchozí hodnota instance (zavřeno), ne ACL plochy,
- audit **projde vždycky**, bez ohledu na práh závažnosti — bezpečnostní
  událost se nesmí dát utišit nastavením,
- audit je vlastní **komponenta**, ne úroveň: úspěšné odemčení není
  `warning` a odmítnutý kód není `error`,
- sloupcový formát (čas, úroveň, relace, zdroj, komponenta, detail), ať jde
  číst po pozicích i strojově,
- **sanace na jednom místě**: řídicí znaky (jinak cizí text přebarví
  `docker logs`), zalomení řádku (podvržený záznam), strop délky,
- **redakce podle klíčů** (`code`, `token`, `secret`, `sid`, …) na cestě do
  logu, ne v každém volajícím.

## 8. Chyby a diagnostika

**Každé bezpečnostní rozhodnutí vrací důvod.** Ve viewBase2 vracelo
ověření kódu `True`/`False` a tři různé příčiny — špatný kód, už použitý
kód, zahlcení pokusy — se hlásily stejnou hláškou. Výsledek: uživatel
nemohl odemknout okno platným kódem a z logu se nedalo poznat proč.

```python
class Verdict(Enum):
    OK, BAD_CODE, REPLAY, THROTTLED, NO_SECRET, NOT_IN_ACL, NO_GRANT, EXPIRED
```

Důvod jde do auditu **i** do hlášky pro uživatele. Hláška pro uživatele smí
být obecnější než auditní záznam, ale nesmí být zavádějící.

**Anti-replay má účel.** Týž kód z autentikátoru je legitimně potřeba
dvakrát během jednoho třicetisekundového okna — jednou na přihlášení, hned
nato na krok navíc u okna — a autentikátor mezitím žádný nový nevydá. Buď
je anti-replay per účel (`login`, `window:<id>`), nebo si to návrh musí
vyřešit jinak; společný seznam napříč vším je chyba, která se projeví až
v provozu. Použité kódy se **prořezávají** po uplynutí platnosti (šestimístná
hodnota se časem vrátí).

## 9. Vlákna, souběh a protitlak

Tři pravidla, která ve viewBase2 platí a osvědčila se:

- uživatelský handler běží v **thread poolu**, ne ve vysílací smyčce (smí
  blokovat i mutovat stav),
- dotaz do zdroje identit se dělá **mimo zámek** tabulky relací (LDAP může
  být pomalý; držet kvůli němu tabulku by zastavilo vysílání),
- soubor politiky má **jedinou autoritu**, která čte i zapisuje celý
  dokument pod zámkem. Tři vlastníci sekcí, kteří si soubor přepisují po
  svém, si sekce navzájem smažou.

Jedno pravidlo, které tam **chybí a doplnil bych ho**: **protitlak**.
Ve viewBase2 vysílací smyčka posílá klientům sekvenčně `await`em, takže
jeden zaseknutý klient zdrží doručení všem ostatním. V3: každý klient má
vlastní frontu s **konečnou** kapacitou; při přetečení se spojení zavře
(klient se připojí znovu a dostane snapshot). Zároveň strop počtu spojení
a per-IP limit — na vystavené instanci je to jinak zadarmo dostupný způsob,
jak instanci zastavit.

## 10. Testovací strategie

viewBase2 má skoro 500 testů a nechytily díru, kterou mělo chytit
pravidlo — protože každý test ověřoval jednu funkci. Co bych zavedl od
začátku:

- **invarianty nad registrem, ne nad jednotlivostmi.** „Pro každou
  registrovanou událost platí, že anonymní relace na skryté ploše
  nedosáhne na handler" je jeden test, který pokryje i tu desátou událost,
  kterou nikdo nenapsal.
- **adversariální testy jako vlastní kategorie**: co se stane, když klient
  pošle pole, které má dosazovat server; když se přihlásí a hned smaže
  uživatele; když pošle událost na cizí plochu; když předloží mrtvé sid.
- **„neodešlo se" se dokazuje kontrolní zprávou**, ne čekáním na timeout:
  vyvolej něco, o čem víš, že přijde, a ověř, že to tajné před tím
  nedorazilo. (Test, který čeká na nedoručení, buď blokuje, nebo je pomalý.)
- **konec řetězu ve skutečném prohlížeči.** Chyby, které v provozu opravdu
  bolely — Esc ve výzvě, pořadí adopce a aktivace okna, zapomenutý překlad
  frontendu — prošly zelenou jednotkovou sadou. Stačí pár e2e testů, ale
  musí být.
- **dokumentované zápisy jsou testy.** Co je v README a v docs, musí jít
  spustit.

## 11. Rozvržení modulů

Jeden strom, závislosti jdou jedním směrem:

```
python/viewbase/
  core/         identity (principálové + Caller), access, audience,
                addressing                                ← nezávisí na NIČEM
  runtime/      instance, sessions, registry, events, screen, window (rám)
  transport/    protocol, server, rest
  providers/    identity_file, identity_ldap, policy_file, policy_db
  types/<kind>/ manifest.json, model.py, schema.json, client/, tests/
  static/       sestavený frontend (viz §12.4)
frontend/       workbench: chrome, WM, registr rendererů, loader typů
python/tests/   testy jádra a integrace
examples/  docs/
```

**Typ okna je jedna složka a leží uvnitř balíčku.** Vypadá zvláštně mít JS
v pythonovém stromu, ale je to tím, že typ okna *je* jeden celek: model,
renderer, schéma i testy patří k sobě a mají se přesouvat najednou (viz
[typy-oken.md](typy-oken.md)). Python se importuje přirozeně
(`viewbase.types.panel.model`), build frontendu si posbírá
`types/*/client/` a wheel obsahuje obojí — takže **publikovaný typ třetí
strany má úplně stejný tvar jako vestavěný**, jen se instaluje zvlášť.

`Screen` a `Window` v `runtime/` jsou **rám**, ne obsah: geometrie, z-order,
titulek, zámek. Obsah okna žije celý v `types/`. (Dřívější `surfaces/`
v tomhle dokumentu byl zbytek staršího návrhu a **zaniká** — dvě rozvržení
vedle sebe byla chyba, viz nález F-01.)

Pravidlo: **`core/` nezávisí na ničem**, takže se celá autorizační logika
testuje bez serveru. Ve viewBase2 to `access.py` splňuje a je to nejzdravější
kus projektu — stojí za to to udržet jako tvrdé pravidlo, ne náhodu.

## 12. Věci, které se rozhodnou dřív, než se začne

Otázky, na které viewBase2 odpovídal postupně a stálo to přepisování:

1. **Jeden proces, nebo víc?** — ✅ **rozhodnuto: M0 je knihovna v jednom
   procesu, ale připravená na rozdělení.** Adresa objektu je od začátku
   neprůhledná a serializovatelná, hranice vrstev mají DTO a platí tvrdé
   pravidlo o směru závislostí. Kontejner kdykoli potom; nic v M0 ho nesmí
   vyloučit.

   **A zůstává to knihovna i potom.** Až část kódu poběží jako služba, je to
   jen jiný způsob *nasazení* — ne jiný způsob, jak je to napsané. Veřejné
   API se dál čte jako knihovna (`import viewbase as vb`, objekty a metody,
   ne roury a zprávy), scaffold se staví po blocích, které dávají smysl samy
   o sobě, a hranice mezi nimi jsou rozhraní, ne síťová volání. Služba se
   pak z bloku udělá tak, že se za rozhraní postaví přenos — a volající to
   nepozná.

   Praktický důsledek pro každý blok: **musí jít použít i sám**, s falešnými
   sousedy a bez serveru. Když se blok nedá vzít do ruky zvlášť, není to
   blok, ale slepenec — a to je přesně ten stav, ze kterého viewBase3
   vzniká.
2. **Kde končí knihovna a začíná aplikace?** viewBase2 došel k tomu, že
   aplikace **nezakládá identity** — jen jmenuje principály na svých
   prvcích. Je to dobré rozhodnutí, ale musí padnout dřív, protože z něj
   plyne existence samostatného nástroje správce.
3. **Jazyk.** — ✅ **rozhodnuto.** Anglicky: identifikátory, jména souborů,
   klíče payloadu, parametry cest v routách, jména v konfiguraci. Česky:
   docstringy a komentáře. Audit anglicky a sloupcově (strojově čitelný).
   Texty pro diváka anglicky, ale server posílá **klíč a parametry**, ne
   hotovou větu — jinak se to později nedá přeložit. Přejmenovávat potom je
   průchod celým repozitářem a past se skrývá v řetězcích.
4. **Sestavený frontend: v gitu, nebo ne?** — ✅ **rozhodnuto: v gitu**,
   protože záměr je knihovna, kterou jde vložit do cizího projektu jedním
   `pip install git+…` bez Node.js. **Podmínkou je kontrola**: vedle bundlu
   leží `static/BUNDLE.sha256` s otiskem zdrojů frontendu a test ho
   přepočítá. Nesoulad = červené CI. Bez té kontroly se chyba 3.13
   (nasazený starý bundle) vrátí, je to jen otázka času.

   **Frontend zůstává vanilla JS + Vite** (bez TypeScriptu). Důsledek:
   `schema/` nemůže generovat typy pro klienta, takže je **jedinou pravdou
   za běhu** — validátor na obou stranách a jedna sada fixtur, kterou
   prochází server i klient. Bez toho se strany rozejdou a nikdo si toho
   nevšimne.
5. **Co je veřejné API.** — ✅ **rozhodnuto.** Veřejné je to, co vývojář
   **napíše**, a je toho málo:

   ```python
   import viewbase as vb

   instance = vb.Instance(...)          # runtime, vlastník stavu
   vb.Needs, vb.StepUp, vb.Verb         # to, co se jmenuje při registraci
   ```

   Všechno ostatní se získává **z instance**, ne importem: plochy z
   `instance.screen.open(...)`, okna z `screen.window.open(...)`, obsah
   metodami okna.
   Vývojář nikdy neimportuje `viewbase.core.*` — to je vnitřek.

   Vynucuje to `__all__` **a test**, který porovná veřejná jména modulu
   s dokumentovaným seznamem. Bez toho se povrch rozroste náhodou a pak se
   nedá zúžit, aniž by se něco rozbilo — a přesně proto to viewBase2 nemá
   popsané dopředu, ale zpětně.

## 13. Co z viewBase2 převzít beze změny

- **`access.py`** — model přístupu jako čisté funkce nad množinami.
- **Neprůhledné session id místo podepsaného tokenu.** Pravdu drží tabulka;
  odvolání je smazání řádku a je okamžité. U aplikace, která je zároveň
  jediný ověřovatel, je JWT jen práce navíc (klíč k rotaci, generace kvůli
  odvolávání, hodiny k synchronizaci).
- **Dvě lhůty relace**: klouzavá (nečinnost) a absolutní strop.
- **Dvě nezávislé zásuvné osy**: „kdo je kdo" (identity) a „co smí naše
  objekty" (politika). Adresář nikdy nebude vědět nic o oknech téhle
  instance.
- **Soubor politiky s jedinou autoritou** a možností přebít kód — správce
  musí umět opravit špatné ACL bez nasazení nové verze.
- **Deklarace požadavku při registraci události** (s tím, že brána platí
  vždycky).
- **Audit, který nejde utišit prahem logu.**
- **Jeden registr objektů** místo několika paralelních map podle typu.

---

*Podrobná inventura — co portovat, co přepsat a které konkrétní chyby se
nesmí vrátit — je v [co-prevzit-z-viewbase2.md](co-prevzit-z-viewbase2.md).*
