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
screen = instance.screen(title="Provoz", id="provoz")
window = screen.html("mzdy", title="Mzdy")
```

Objekt si drží odkaz na instanci, ne na modul. Testy pak nepotřebují nic
resetovat — vyrobí si vlastní instanci.

**Adresa vzniká při narození.** Ve viewBase2 okno vzniká bezejmenné
(`HtmlWindow("mzdy")`) a adresu dostane, teprve když ho plocha přijme; do
té doby má práva „nikam nepatřící" objekt. Když se okno vyrábí přes
`screen.html(...)`, tenhle mezistav neexistuje.

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

class Audience:
    """Komu se smí doručit. Vyhodnocuje se proti principálům relace."""
    principals: frozenset[str] | None   # None = jen adresné (viz níž)
    only_session: str | None = None     # přesně jedna relace
    needs_grant: str | None = None      # kdo má krok navíc k tomuhle objektu
```

Vysílací smyčka pak **neví nic o oknech ani o právech** — jen se ptá
`audience.allows(session)`. Objekty naopak nevědí nic o soketech.

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
window.access.see.add("group:ucetni")
window.access.write.set(["user:hana"])
window.access.step_up = True          # chce kód, i když ACL projde
```

**b) ACL objektu je neměnná hodnota, měnit jde jen přes instanci.** Ve
viewBase2 se práva mění metodami na objektu (`okno.access.add(...)`) a
audit se dělá uvnitř `Acl`. Čistší je nechat `Acl` být hodnotou a změnu
vést přes instanci, která k ní může přidat kdo/kdy/proč. (Menší věc, ale
zjednoduší to auditní stopu.)

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
register("shell_input",   handler, needs=Needs.USE)      # okno: zasahovat + krok navíc
register("window_unlock", handler, needs=Needs.UNLOCK)   # okno: vidět, bez kroku navíc
register("menu_select",   handler, needs=Needs.SCREEN)   # jen brána plochy
```

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

Návrh, který drží závislosti jedním směrem:

```
core/
  identity.py     principálové; čisté funkce, žádné závislosti
  access.py       Acl, Access, allowed(); závisí jen na identity
  audience.py     komu se zpráva smí doručit
  addressing.py   opaque id, adresa rodič/dítě
runtime/
  instance.py     Instance: vlastní politiku, relace, log, zdroj identit
  sessions.py     tabulka relací, principálové, kroky navíc
  registry.py     objekty instance podle adresy
  events.py       registr událostí + JEDINÉ vynucovací místo
transport/
  protocol.py     tvar zpráv (bez logiky)
  server.py       sokety, handshake, multiplexing; nezná práva
  rest.py         programový vstup; jen převede token na Caller
providers/
  identity_file.py, identity_ldap.py     kdo je kdo
  policy_file.py, policy_db.py           co smí naše objekty
surfaces/
  screen.py, window/*.py                 obsah; nezná sokety ani práva
```

Pravidlo: **`core/` nezávisí na ničem**, takže se celá autorizační logika
testuje bez serveru. Ve viewBase2 to `access.py` splňuje a je to nejzdravější
kus projektu — stojí za to to udržet jako tvrdé pravidlo, ne náhodu.

## 12. Věci, které se rozhodnou dřív, než se začne

Otázky, na které viewBase2 odpovídal postupně a stálo to přepisování:

1. **Jeden proces, nebo víc?** Pokud se počítá s tím, že část ploch převezme
   jiný kontejner, musí být adresa objektu neprůhledná a stabilní od
   začátku a stav relace musí být přenositelný (nebo výslovně nepřenositelný
   a klient to musí umět).
2. **Kde končí knihovna a začíná aplikace?** viewBase2 došel k tomu, že
   aplikace **nezakládá identity** — jen jmenuje principály na svých
   prvcích. Je to dobré rozhodnutí, ale musí padnout dřív, protože z něj
   plyne existence samostatného nástroje správce.
3. **Jazyk identifikátorů.** Anglicky. (Komentáře v jakémkoli jazyce, ale
   jména v kódu ne.) Přejmenovávat to potom je průchod celým repozitářem
   a past se skrývá v řetězcích — jméno parametru cesty v routě, klíče
   payloadu, jména v konfiguraci.
4. **Sestavený frontend: v gitu, nebo ne?** Pokud ano, musí existovat
   kontrola, že bundle odpovídá zdrojům — jinak se dřív nebo později
   nasadí starý.
5. **Co je veřejné API.** viewBase2 to má popsané až zpětně. Rozhodnout
   dřív znamená, že se vnitřek dá měnit bez ohledů.

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
