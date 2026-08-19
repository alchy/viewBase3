# Kontrakt apky: dva kanály, stav a co se stane, když spadne

*Jak instance mluví s apkou — a co z toho platí i tehdy, když apka běží
v jiném procesu. Zadání pro `AppBackend`.*

[← architektura](architektura-navrh.md) · [typy oken](typy-oken.md) ·
[kontrakt okna](okno-kontrakt.md)

---

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
| `explicit` | nic; `handle=` je povinný | dávkové plnění zvenčí |

`session` a `user` **nejsou totéž** a splynutí je chyba: shell chce
per-session (dva terminály jsou dva terminály), osobní graf chce per-user
(dva taby jsou jedno okno do téhož).

### `AppBackend` — apka o oknech neví

```python
open_content(handle, spec)          -> Snapshot
snapshot(handle, subject)           -> Snapshot
apply_event(handle, subject, event) -> list[Delta]
close_content(handle)               -> None
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
                        └─► POST /auth/introspect { token, audience }
                            ← { subject_id, groups, expires_at }   nebo 401
```

| kdo volá | co předloží | co apka zjistí |
|---|---|---|
| instance (okno se otevírá) | token subjektu, `audience: app:workbench.graph` | `user:jindra` |
| dávková úloha, cron | token vydaný správcem pro subjekt | `user:jindra` nebo `service:nightly-import` |

**Rukojeť v tokenu není.** Token říká *kdo*, požadavek říká *co*
(`/content/vb1_9f2c…/nodes`). Tím zůstává v platnosti věta „rukojeť
identifikuje, neopravňuje" — a zároveň je z každého volání jednoznačné
**obojí**: která instance obsahu a který člověk.

### `audience` je povinná

Token vydaný pro `app:workbench.graph` **nesmí projít** u jiné apky. Bez
toho by kompromitovaná apka mohla přehrát tokeny svých diváků kamkoli
jinam. Apka `audience` ověřuje, ne jen čte.

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

### Skupiny se sdílejí — a je hranice, kde se smí použít

Introspekce vrací i `groups`, protože bez nich by apka uměla psát jen
pravidla na jméno („hana smí"), a to se nedá udržet.

| kde | smí se použít |
|---|---|
| **vlastní pravidla apky nad jejím obsahem** („účetní smí zapisovat") | **ano** — na to tam jsou |
| **rozhodnutí, co vrátit v `snapshot`** | **ne** — to jsme už autorizovali my |

Rozdíl proti poli `capabilities` v `subject`: `capabilities` říká, **co ten
divák smí v tomhle okně** (naše rozhodnutí, `read`/`write`); `groups` jsou
**vstup pro doménová pravidla apky**. Odpovídají na jiné otázky a nemají se
zaměňovat.

**Skupiny se tím stávají sdíleným slovníkem.** Když se `group:ucetni`
v adresáři přejmenuje, tiše přestanou platit pravidla ve všech apkách, které
na něm stojí. Přejmenování skupiny je proto **rušící změna napříč systémem**,
ne kosmetika v konfiguraci.

**Minimum, které stačí:** apka při registraci deklaruje, které skupiny ji
zajímají, a introspekce vrací **jen členství mezi nimi**:

```json
"groups_of_interest": ["group:ucetni", "group:mzdy"]
```

Bez toho se každá apka, kterou si člověk otevře, dozví celou jeho pozici
v organizaci — a u apek třetích stran je to únik struktury firmy, který
s jejich funkcí nemá nic společného.

### Autentizace ano, autorizace ne

Sdílí se **„kdo je kdo"**. **„Co kdo smí se svým obsahem" zůstává apce** —
vlastnictví obsahu jsou její data. Kdyby si apka vyhodnocovala i naše ACL,
slijí se dvě osy zpátky do jedné a vzniknou dvě odpovědi na jednu otázku.

A opačně: apka si v `snapshot` **znovu neověřuje**, jestli divák na obsah má.
Když ji instance zavolala, už autorizovala; druhá kontrola jiným modelem by
dřív nebo později dala jinou odpověď.

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
