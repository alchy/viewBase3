# Kontrakt apky: dva kanály, stav a co se stane, když spadne

*Jak instance mluví s apkou — a co z toho platí i tehdy, když apka běží
v jiném procesu. Zadání pro `AppBackend`.*

[← architektura](architektura-navrh.md) · [typy oken](typy-oken.md) ·
[kontrakt okna](okno-kontrakt.md)

---

## 0. Co je na tomhle dokumentu závazné

**Závazný je [appkit](appkit.md), ne tvar zpráv.** Tenhle dokument popisuje,
co apka musí umět a proč — tvary zpráv v něm jsou **internals**, které se
mění s verzí knihovny. Autor apky je nečte a nepotřebuje: implementuje
`Content`, deklaruje u operací sloveso a zbytek dělá appkit.

Důvod je v [appkit.md](appkit.md) §5: tenhle protokol mluví jenom viewBase
se svými apkami, takže volný drát by kupoval jedinou svobodu — napsat si
klienta ručně — a přesně z ní vzejde jinak spočítaný kurzor a znovu
vymyšlená autorizace.

## 1. Dva kanály, které se nesmí slévat

```
AUTORSKÝ KANÁL          kód aplikace  ──────────────►  apka
  add_node, add_edge…      vlastní API apky
  „co je v obsahu"         WORKBENCH O TOM NEVÍ NIC

PREZENTAČNÍ KANÁL       instance  ◄──────────────────►  apka
  snapshot, apply_event    kontrakt níž
  „co uvidí tenhle divák"  tudy jde subjekt a práva
       │
       └───────────────►  prohlížeč
```

**Workbench není brána pro doménové příkazy.** Nemá vědět, co je uzel,
faktura nebo řádek tabulky. Kdyby `add_node` procházelo instancí, musela by
znát seznam příkazů každé apky — a modularita by skončila.

Klienta autorského kanálu dodává **balíček apky**, ne workbench:

```python
w = screen.window.open("graph", id="net", title="Síť", app="viewbase.graph")
w.app.add_node("a", name="Alfa")      # vlastní API apky; instance to jen drží
```

Autorský kanál si apka **autentizuje sama**. Naše pravidla platí na to, co
teče skrz workbench: kdo plochu a okno uvidí a kdo do něj smí poslat
událost.

## 2. Obsah má vlastní identitu; okno je pohled

**Tohle je jádro celého kontraktu a stálo to jednu opravu návrhu.** Původně
tu instance obsahu splývala s oknem — obsah vznikal otevřením okna a umíral
jeho zavřením. Tři běžné situace to porušují:

- naplnit graf dávkovou úlohou **dřív, než ho někdo otevře** (okno ještě není),
- dvě okna, která mají ukazovat **týž** obsah,
- jeden člověk ve dvou tabech, který chce **týž** obsah (`per-session` mu dá dva).

```
OBSAH  (u apky)      rukojeť "vb1_9f2c…"     ← stav; žije vlastním životem
   ▲        ▲
   │ pohled │ pohled
OKNO A    OKNO B     (u workbenche)          ← kde se to ukazuje; má adresu a ACL
```

Okno se při otevření na obsah **napojí** — na nový, nebo na existující:

```python
w  = screen.window.open("graph", id="net", app="workbench.graph")
w.app.handle                                  # "vb1_9f2c…" – nový obsah

w2 = screen2.window.open("graph", id="net2", app="workbench.graph",
                         handle="vb1_9f2c…")  # druhé okno, TÝŽ obsah
```

A obsah může vzniknout **bez okna**:

```python
h = instance.app.get("workbench.graph").new_content()
# …dávková úloha ho odjinud plní přes API apky…
w = screen.window.open("graph", id="net", app="workbench.graph", handle=h)
```

### `scope`: jak se rukojeť odvodí, když ji nezadáte

Nahrazuje dřívější `content: shared | per-session | instance` a zobecňuje ho:

| `scope` | rukojeť se odvodí z | typický případ |
|---|---|---|
| `window` | plocha + okno | dashboard vázaný na to okno |
| `session` | okno + relace | **shell** — dva taby, dva terminály |
| `user` | okno + uživatel | **osobní graf** — dva taby, jeden obsah |
| `instance` | instance **+ app_id** | **log** — jeden proud na apku; dvě apky si nesmí sdílet rukojeť |
| `app` | nic (jedna rukojeť) | společná mapa sítě pro všechny |
| `explicit` | nic; nabídka bez obsahu razí **čerstvou** rukojeť, přímá vazba zvenčí vyžaduje `handle=` | dávkové plnění zvenčí, „Nový sešit" |

`session` a `user` **nejsou totéž** a splynutí je chyba: shell chce
per-session (dva terminály jsou dva terminály), osobní graf chce per-user
(dva taby jsou jedno okno do téhož).

### `AppBackend` — apka o oknech neví

```python
create_content(handle, spec, subject) -> Snapshot   # rukojeť razí INSTANCE
open_content(handle, subject)         -> Snapshot   # neznámá rukojeť = odmítnutí
snapshot(handle, subject)             -> Snapshot
apply_event(handle, subject, event)   -> list[Delta]
close_content(handle)                 -> None
list_content()                        -> list[ContentInfo]  # BEZ subjektu
```

```python
subject  = {"subject_id": "user:42" | "anonymous",
            "correlation": "c9f1…",
            "capabilities": ["read", "write", "manage"]}   # UŽ ROZHODNUTÉ
Snapshot = {"state": {...}, "cursor": 271}
```

**Žádné `screen` ani `window` v API apky.** Mapu *okno → rukojeť* si drží
instance; apka řeší jen svůj obsah. Hranice je tím ostřejší, ne volnější —
a apka se stává použitelnou i tam, kde žádná okna nejsou.

**`subject` nikdy nenese session id ani skupiny.** Session id je přihlašovací
údaj; skupiny by z apky udělaly druhé místo, kde se rozhoduje o právech.

### Schopnosti jsou hotová odpověď, ne podklad k rozhodování

| schopnost | co znamená |
|---|---|
| `read` | smí obsah vidět |
| `write` | smí do něj zasahovat |
| `manage` | smí i to, co jinak přísluší **vlastníkovi** — destruktivní akce (D-41) |

**Schopnosti jsou vždycky předpona řetězu, nikdy s dírou** (D-70):

```
[]   ["read"]   ["read","write"]   ["read","write","manage"]
```

Platí `manage ⟹ write ⟹ read` — a jen tímhle směrem. `write` nikoho
nepovyšuje na `manage`; ten je pořád odvozený ze zakladatelství nebo
správcovství a `write` je jen jeho nutná podmínka. Apka se tedy může ptát
na nejvyšší stupeň, který potřebuje, a nemusí kontrolovat ty pod ním.

Je to jednořádkový invariantní test — a přesně ten druh, který v sadě
chyběl, když vznikl F-22.

`manage` dostane vlastník obsahu **a správce**. Apka se ale nedozví, **kdo
z nich to je** — jen že na to má. Je to schválně:

- kdyby apka dostala „je správce", musela by si pravidlo *správce smí i cizí*
  odvodit sama, a to je druhé místo, kde stejné pravidlo žije. Dřív nebo
  později se rozejde s naším,
- schopnost pojmenovává **co ten člověk smí**, ne **kdo je**. Role je
  informace navíc, kterou apka k práci nepotřebuje — a co nepotřebuje,
  nemá dostat.

Na **klientském kanálu** si totéž apka odvodí z introspekce (kde skupiny má,
viz §9). Tvar je tedy na obou kanálech stejný: `manage` in `capabilities`.

**V `open_content` schopnosti nejsou** a je to správně: vazba okna na obsah
se děje **jednou**, kdežto dívání se děje **per divák**. Schopnosti chodí
tam, kde na nich záleží — v `snapshot` a `apply_event`.

### Sdílení obsahu není sdílení přístupu

Jeden obsah, dvě okna, **různá ACL**. Každé okno doručuje svým divákům podle
**svého** ACL; apka o tom neví a vědět nemusí. Delta z obsahu se rozešle přes
všechna okna, která na něj koukají, a každé si ji přefiltruje sámo — pořád je
to `Ref(adresa okna, READ)`, model publika se nemění.

Intuice říká opak, proto je to napsané výslovně.

## 2b. Rukojeť instance: jak volat API apky odjinud

Vazba *plocha → okno → apka* musí jít **vzít s sebou**. Typický případ:
okno se otevře při startu instance, ale uzly do grafu sype dávkový úkol,
cron nebo úplně jiná služba — a ta o viewBase nemusí vědět nic.

Proto má každá běžící instance obsahu **rukojeť**: neprůhledný řetězec,
který jednoznačně určuje trojici *(plocha, okno, apka)*.

```python
w = screen.window.open("graph", id="net", app="workbench.graph")
w.app.handle          # "vb1_9f2c7a…"  ← tohle si můžete uložit kamkoli
```

```bash
# odkudkoli jinud, bez viewBase v procesu
curl -X POST https://graph-app:8080/instances/vb1_9f2c7a…/nodes \
     -H "Authorization: Bearer $GRAPH_API_KEY" \
     -d '{"id": "a", "name": "Alfa"}'
```

### Rukojeť razí instance, ne apka

Vypadá to jako detail, ale rozhoduje o použitelnosti:

- **razí ji instance** a předá ji apce v `open_content` → apka ji používá
  jako svůj klíč. Když apka spadne a znovu se zaregistruje, instance obnoví
  své vazby **s toutéž rukojetí** (§6) — a řetězec, který si někdo uložil
  do konfigurace před měsícem, **dál platí**;
- kdyby ji razila apka, každý její restart by zneplatnil všechny uložené
  rukojeti a dávkový úkol by přestal fungovat bez varování.

Hodnota je náhodná nebo odvozená (HMAC z tajemství instance a adresy) —
v každém případě **neuhodnutelná**, aby nešly instance vyjmenovat.

### Rukojeť IDENTIFIKUJE, neopravňuje

Tohle je ta část, kterou je snadné splést, a spletení je únik:

| | co to dělá |
|---|---|
| **rukojeť** | říká **které** instanci obsahu voláte |
| **pověření apky** (API klíč, mTLS) | říká, jestli **smíte** |

Rukojeť není bearer token. Kdo ji získá, neumí s ní nic — pořád potřebuje
pověření k API té apky. Kdyby stačila sama, únik jednoho řetězce z logu nebo
konfigurace znamená, že kdokoli píše do cizího okna.

Naše ACL se tady **neuplatňuje** a je to záměr: je to autorský kanál a ten si
apka autentizuje sama (§1). Workbench rozhoduje o tom, kdo obsah **uvidí** —
ne o tom, kdo ho smí do apky nalít.

### Životnost

**Zavření okna je odpojení pohledu, ne smrt obsahu.** Obsah zaniká podle
`scope` (konec relace u `session`, konec instance u `instance`) nebo
výslovně přes `close_content`. U `explicit` přežije všechno a smaže ho jen
ten, kdo ho založil — jinak by dávkové plnění mizelo pod rukama.

Volání se zaniklou rukojetí apka odmítne; nemusí se nikoho ptát, protože
seznam živých rukojetí dostala.

## 3. Kurzor: snapshot a delty se musí sejít

Divák se připojí → instance si vyžádá snapshot → mezitím apka posílá delty.
Bez kurzoru se delta buď ztratí, nebo použije dvakrát.

```
snapshot() → {state, cursor: 271}
delty      → {cursor: 272, …}, {cursor: 273, …}

instance pošle klientovi stav a doplní delty OD 272 dál;
starší zahodí, mezeru pozná a vyžádá si snapshot znovu.
```

V jednom procesu to viewBase2 obcházel idempotentními upserty. Přes síť to
nestačí — pořadí a ztráta jsou reálné.

**`cursor` je monotónní per instance obsahu** a vlastní ho **apka** (ví, kolik
změn na svém modelu udělala). **`seq` v protokolu ke klientovi přiděluje
instance** — jsou to dvě různá čísla a nesmí se plést: instance je jediné
místo, kde se schází víc producentů (apka, zamykání okna, systémové akce).

## 4. Delty tečou zpátky trvalým spojením

Spojení otevírá **instance** směrem k apce (přežije NAT, drží pořadí a dá se
na něm uplatnit protitlak). Apka na něj posílá delty **v pořadí pro danou
instanci obsahu**.

**Publikum neurčuje apka.** Instance ho odvodí z manifestu (`shared` /
`per-session` / `instance`) a z ACL objektu. Apka nikdy nejmenuje principály
— kdyby mohla, vznikne druhý model práv.

## 5. Co se stane, když apka nespolupracuje

Tři různé stavy a každý se řeší jinak:

| stav | kdo to pozná | co se stane |
|---|---|---|
| **neznámá** (`app=` není v registru) | `window.open()` | selže **hned**, se seznamem registrovaných — chytá překlepy |
| **nedostupná** (spadlá, restartuje se) | instance při volání | okno je rám s hláškou „obsah není dostupný"; instance **nečeká** |
| **pomalá** | časový limit | totéž co nedostupná, ale jen pro to okno |

**Stav „nedostupná" drží instance, ne apka** — apka o něm z definice nemůže
říct nic. Je to stav okna, ne chyba: divák vidí rám, ostatní okna běží dál.

Výchozí limity (nastavitelné): `open_content` a `snapshot` 2 s,
`apply_event` 5 s, fronta delt **1000 zpráv na instanci obsahu**. Při
přetečení fronty se spojení k apce zavře a okna té apky spadnou do stavu
„nedostupná" — pomalá apka smí zdržet sebe, ne vysílací smyčku.

## 6. Restart apky: instance obnoví, co bylo

U obsahu, který nevzniká znovu sám, žije model v apce. Restart ho smaže — a vazby
*(screen, window) → app* zná **instance**. Proto:

```
apka se znovu zaregistruje
  → instance projde své vazby na tuhle apku
  → pro každou zavolá open_content znovu
  → okna se vrátí ze stavu „nedostupná" do provozu
```

Bez toho zůstanou okna prázdná až do restartu celé instance.

## 7. Konec relace: `close_content`, jinak teče paměť

U `scope: session` vzniká obsah **na každého diváka**. Instance musí poslat
`close_content` nejen při zavření posledního okna, ale i při **vypršení nebo
odhlášení relace**. Apka nemá jak se dozvědět, že divák odešel.

U `scope: user` platí totéž s koncem poslední relace toho člověka; u
`explicit` neplatí nikdy.

## 8. Apka nedodává JavaScript

**Renderery jsou výhradně naše, z kurátorovaného katalogu** (viz
[typy-oken.md](typy-oken.md) §1). Apka posílá data v tvaru, který renderer
umí, a žádný kód do prohlížeče neposílá — takže odpadá připínání modulu
otiskem, stupně důvěry i sandbox.

Kdo potřebuje vizualizaci, kterou žádný renderer neumí, **přispěje renderer
do katalogu** (build-time, review), ne modul k apce.

## 9. Jedno povinné autentizační API pro oba kanály

Apka má dvě dveře — instance přes prezentační kanál a kdokoli přes klientské
REST — a **do obojích se chodí stejným způsobem**. Není to nabídka, je to
požadavek: apka si vlastní schéma ověřování nevymýšlí.

```
volající ──► token ──► apka
                        │
                        └─► POST /auth/introspect { token, resource }
                            ← { subject_id, capabilities, expires_at }  nebo 401
```

| kdo volá | co předloží | co apka zjistí |
|---|---|---|
| instance (okno se otevírá) | token subjektu s `audience: app:workbench.graph` | `user:jindra` **a jeho `capabilities` k tomu obsahu** |
| dávková úloha, cron | token vydaný správcem pro subjekt | `user:jindra` nebo `service:nightly-import`, **a `capabilities`** |

**Rukojeť v tokenu není.** Token říká *kdo*, požadavek říká *co*
(`/content/vb1_9f2c…/nodes`). Tím zůstává v platnosti věta „rukojeť
identifikuje, neopravňuje" — a zároveň je z každého volání jednoznačné
**obojí**: která instance obsahu a který člověk.

### Dvě různá pole, dvě různé otázky

Dřív se obojímu říkalo `audience` a splývalo to. Jsou to dvě věci:

| pole | kde je | co říká |
|---|---|---|
| `audience` | **v tokenu** | která apka ho smí přijmout — `app:workbench.graph` |
| `resource` | **v dotazu na introspekci** | na co se ptáme — `content:vb1_9f2c…` |

`audience` v tokenu je povinná: token vydaný pro jednu apku **nesmí projít**
u jiné, jinak by kompromitovaná apka přehrála tokeny svých diváků kamkoli
jinam. Apka ji ověřuje, ne jen čte.

`resource` je to, co dělá odpověď použitelnou. **Apka nemá ACL** (D-60),
takže z `app:<id>` se nedá spočítat vůbec nic — práva jsou na obsahu. Bez
`resource` by introspekce vrátila jen „tenhle člověk existuje" a apka by si
zbytek musela dopočítat sama. To je F-23 znovu, jen o jeden kanál vedle.

Token tím pořád říká **jen kdo** — rukojeť v něm není. Úzká je až ta
otázka.

### Ověřuje se dotazem, ne podpisem

Introspekce místo podepsaného tokenu, ze stejného důvodu jako u relací:
**pravdu drží tabulka, takže odvolání je okamžité.** Apka si smí odpověď
krátce cachovat (řádově desítky sekund) — to je celá úleva, kterou
podepsaný token nabízel, bez ceny v podobě nezrušitelnosti.

### Co to vyřeší

- **klíč k apce přestane být mocný jako všechna její data** — místo jednoho
  sdíleného hesla je z každého volání vidět konkrétní subjekt,
- **dávková úloha běží *jako někdo*** — `user:jindra` v okně i v cronu je
  týž subjekt a v auditu se to spojí,
- **autor apky nevymýšlí autentizaci**, což je místo, kde se to obvykle
  pokazí.

### Skupiny se apce neposílají

Introspekce vrací `capabilities`, ne `groups`. Apka se nedozví, kde je ten
člověk v organizaci, protože to k práci nepotřebuje.

Dřív tu stálo, že apka smí psát vlastní pravidla nad skupinami („účetní smí
zapisovat"). Odůvodňovalo se to řádkovými právy — každý vidí jen řádky svého
střediska. **Ta potřeba neexistuje: jednotkou přístupu je obsah**, ne řádek
a ne buňka. Kdo chce, aby dvě skupiny lidí viděly jiná čísla, udělá **dva
dokumenty** s vlastními ACL — přesně jako `Mzdy.xls` a `Rizika.xls`
v dodatku architektury. Je to o patro výš, kde na to model existuje.

Co tím odpadlo:

- `groups_of_interest` v manifestu,
- poslední místo, kde si apka mohla postavit **druhý autorizační model**
  (F-23 ukázal, jak to dopadá),
- a hlavně: **skupiny přestávají být sdílený slovník napříč apkami.**
  Přejmenování `group:ucetni` v adresáři už není rušící změna napříč
  systémem — je to změna uvnitř instance a ven z ní nesahá.

### Autentizace ano, autorizace ne

Apka **neautorizuje vůbec**. Ani na prezentačním kanálu (tam rozhodla
instance dřív, než apku zavolala), ani na klientském (tam si o rozhodnutí
řekne introspekcí). Jediné, co s právy dělá, je **porovnání deklarovaného
slovesa s tím, co přišlo v `capabilities`** — a to za ni obstará appkit.

Vlastnictví obsahu jí zůstává jako **údaj**, ne jako právo: čísluje se podle
něj „Graph #1" a spouštěč podle něj umí oddělit moje od sdílených. Když
z něj apka udělá autorizační vstup, dostane jinou odpověď než instance —
přesně to byl F-23.

### Cena, kterou to má

Apka je tím **závislá na běžící autentizační komponentě**. Je to vědomý
obchod: jednotná identita a okamžité odvolání za jeden bod, který musí
běžet. Zmírňuje to krátká cache a to, že ta komponenta je malá a oddělená —
ale je poctivé to napsat, ne to schovat.

## 10. Události apky jdou do téhož registru

Registrační dokument nese `events` s `needs` a `profile`. Ty se **zapíšou do
téhož registru událostí** jako vestavěné a platí pro ně tytéž brány.

Kdyby si apka události obsluhovala mimo registr, vrátí se chyba 3.1
z viewBase2 — autorizace psaná zvlášť u každého handleru, kterou si pět
z devíti nevzpomnělo udělat.

## 11. Autorský kanál přes síť: co musí být vidět v API

Tvar API zůstává stejný, ale dvě věci se nesmí schovávat:

- **dávkování** — `with w.app.batch(): …` pošle jednu zprávu místo tisíce
  round-tripů,
- **selhání** — volání přes síť může selhat a fasáda to nesmí polykat.

Klient, který předstírá, že je lokální, je horší než přiznaný síťový klient.

---

## Pořadí

**hello-app jako první remote** — nemá stav ani vlastní JS, takže prověří
kanál, autentizaci a stav „nedostupná" bez ostatních proměnných.
**Graf až potom** — ten prověří kurzor, dávkování a připnutí modulu.
