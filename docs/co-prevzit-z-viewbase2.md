# Co převzít z viewBase2, co přepsat a co nechat být

*Inventura. Ke každé položce důvod — a v druhé části konkrétní chyby, které
se v novém návrhu nesmí zopakovat, s pravidlem, které je zavírá.*

---

## 1. Převzít beze změny

| co | proč |
|---|---|
| **model přístupu** (`access.py`) | principálové, ACL jako množina povolených, dvě slovesa, dědičnost objekt → plocha → instance. Celá autorizace je jedna funkce nad množinami a modul nezávisí na ničem — testuje se bez serveru. Nejzdravější kus projektu. |
| **neprůhledné session id** | pravdu drží tabulka; odvolání je smazání řádku a je okamžité. Podepsaný token (JWT) by přinesl klíč k rotaci, generace kvůli odvolávání a hodiny k synchronizaci — a nic by nevyřešil, protože aplikace je zároveň jediný ověřovatel. |
| **dvě lhůty relace** | klouzavá (nečinnost) i absolutní strop. Kdo odejde od stroje, přijde o přístup; nikdo nedrží relaci naživo donekonečna klikáním. |
| **dvě nezávislé zásuvné osy** | „kdo je kdo" (identity) a „co smí naše objekty" (politika). Adresář nikdy nebude vědět nic o oknech téhle instance — výměnou LDAPu se mění jen první osa. |
| **soubor politiky přebíjí kód** | správce musí umět opravit špatné ACL bez nasazení nové verze aplikace. |
| **jediná autorita nad souborem politiky** | tři vlastníci sekcí, kteří si soubor přepisují po svém, si sekce navzájem smažou. Čtení i zápis celého dokumentu pod jedním zámkem. |
| **audit, který nejde utišit prahem logu** | bezpečnostní událost se nesmí dát schovat nastavením `log_level`. |
| **audit jako komponenta, ne úroveň** | úspěšné odemčení není `warning` a odmítnutý kód není `error`. |
| **sanace vstupů do logu na jednom místě** | řídicí znaky (jinak cizí text přebarví `docker logs`), zalomení řádku (podvržený záznam), strop délky. |
| **redakce podle klíčů** | `code`, `token`, `secret`, `sid` se na cestě do logu nahradí délkou — ne v každém volajícím zvlášť. |
| **rate limit + anti-replay u kódů** | 5 pokusů / 30 s, použitý kód se pamatuje. Ale **anti-replay musí mít účel**, viz §3.6. |
| **jeden registr objektů** | místo několika paralelních map podle typu. Ve viewBase2 byly čtyři a každá otázka „mám okno s tímhle id?" se musela ptát čtyřikrát. |
| **fyzika grafu v prohlížeči** | server posílá topologii, ne pozice. Ať je to v novém modelu deklarovaná vlastnost typu okna (`profile: local`), ne náhoda. |
| **líné načítání těžkých typů** | graf se stáhne, až když se otevře grafové okno. |
| **TOTP se štítkem `viewBase:user:<jméno>`** | stejná syntaxe jako principál v ACL; v autentikátoru se to pozná od ostatních položek. |
| **artefakty registrace na disku, ne v logu** | QR a tajemství leží v `~/.viewbase/user-<jméno>/` s právy 0600; do logu jde jen ukazatel, kde je vzít. |

## 2. Převzít, ale přepsat

| co | co změnit |
|---|---|
| **`Project`** | ať skutečně **vlastní** stav (politiku, relace, log, zdroj identit), místo aby nastavoval proces-wide globály. Dvě instance v jednom procesu musí být samozřejmost. |
| **deklarace `needs` u registrace události** | myšlenka je správná, ale **brána plochy musí platit vždycky** a žádná hodnota ji nesmí vypnout. Ve viewBase2 existovala `NONE` ve významu „nekontroluj nic". |
| **adresní značky zpráv** (`only_sid`, `grant`, `acl`) | správný nápad na špatném místě: publikum se lepí až při doručení. V3 je publikum součástí zprávy od jejího vzniku. |
| **`snapshot(sid=None)`** | zrušit výchozí hodnotu. „Když se nikdo neptá pro koho, dej všechno" je přesně ta cesta, kterou obsah unikne. |
| **`private=True` jako booleán na okně** | krok navíc je politika a patří k ostatní politice: `window.access.step_up = True`. |
| **mixiny se sdíleným stavem** | `WindowsMixin`/`EventsMixin` očekávají `self._lock`, `self._actions`, `self._reg` — je to dohoda, ne rozhraní. Kompozice místo dědičnosti. |
| **`HtmlWindow` + `ControlWindow`** | sloučit do jednoho typu `panel` (viz [typy-oken.md](typy-oken.md)). |
| **log okno** | nesmí být speciální případ mimo běžnou cestu. Je to typ okna jako každý jiný, jen jeho obsah dodává runtime — a jeho ACL se **nedědí z plochy**. |
| **ověření kódu** | vracet **důvod**, ne `True`/`False`. |
| **id plochy** | neprůhledné a stabilní od začátku; pořadí na liště je jiná vlastnost (`index`). |

## 3. Chyby, které se nesmí vrátit

Skutečné nálezy z viewBase2. U každého pravidlo, které ho v novém návrhu
zavírá — pokud to pravidlo v návrhu není, nález se vrátí.

### 3.1 Grant se nekontroloval u vstupu do shellu

Autorizace se psala v každém handleru zvlášť a **pět z devíti událostí ji
nemělo**. Stačilo se připojit a psát do shellu, který odemkl někdo jiný.

**Pravidlo:** požadavek se deklaruje při **registraci** události, je
povinný a vynucuje se centrálně. Strojový test projde registr.

### 3.2 `Needs.NONE` obcházelo bránu plochy

„Nic navíc" se v implementaci četlo jako „nic vůbec", takže `shell_new`,
`menu_select` i každá uživatelská událost šly zavolat na plochu, kterou
relace vůbec neviděla.

**Pravidlo:** brána plochy platí u každé události; enum nesmí obsahovat
hodnotu, která vypíná kontrolu.

### 3.3 `curl` bez identity spustil autorský handler

REST neměl identitu žádnou.

**Pravidlo:** každý vstup má identitu, i když je to „nikdo"
(`group:public`). Jeden typ volajícího pro relaci prohlížeče i pro
programový vstup, aby vynucovací kód neměl dvě větve.

### 3.4 Log okno na veřejné ploše rozeslalo auditní stopu všem

ACL se bralo ze screenu, na kterém okno leželo, ale sběrnice logu je jedna
pro celý proces.

**Pravidlo:** co je instance-wide, nesmí dědit práva od lokálního objektu.
A obecněji: **zpráva bez publika nesmí jít vyrobit.**

### 3.5 Smazaný uživatel si držel přístup

Neznámé jméno dostávalo výchozí `group:users`.

**Pravidlo:** „neznám" není „výchozí". Relace smazaného uživatele padá na
anonymní při první obnově, s auditním záznamem.

### 3.6 Platný kód neodemkl okno

Přihlášení kód spotřebovalo a anti-replay byl společný pro celého uživatele
— přitom je týž kód potřeba dvakrát během jednoho třicetisekundového okna
(přihlášení + krok navíc) a autentikátor mezitím žádný nový nevydá.

**Pravidlo:** anti-replay má **účel** (`login`, `window:<id>`); týž kód
nejde použít dvakrát na totéž, ale dva různé účely jsou dva různé seznamy.
Použité kódy se prořezávají po uplynutí platnosti.

### 3.7 Tři různé příčiny se hlásily stejnou hláškou

Ověření vracelo ano/ne, takže se špatný kód nedal odlišit od už použitého
ani od zahlcení pokusy.

**Pravidlo:** každé bezpečnostní rozhodnutí vrací důvod; do auditu jde vždy,
divákovi tak, aby neprozradil víc, než má.

### 3.8 První zápis uživatelů smazal skupiny i práva

Tři vlastníci sekcí, tři zápisy celého souboru.

**Pravidlo:** jeden dokument = jedna autorita, která ho čte i zapisuje celý
pod zámkem.

### 3.9 Odemčení jedním divákem odhalilo obsah všem

Zámek okna byl globální vypínač na objektu.

**Pravidlo:** přístup patří **dvojici** (relace, objekt), ne objektu.

### 3.10 Kód z autentikátoru se objevil v ladicím logu

Payload události se logoval celý.

**Pravidlo:** redakce podle klíčů na jednom místě, na cestě do logu.

### 3.11 Dokumentovaný zápis v kódu neexistoval

`okno.access.add(...)` byl v README, v docs i ve specifikaci — a `Access`
tu metodu neměl. Spadl by na `AttributeError`.

**Pravidlo:** co je v dokumentaci, je doslova v testu.

### 3.12 Esc ve výzvě nefungoval

Vstupní pole si klávesu zastavilo dřív, než dorazila k posluchači.

**Pravidlo:** klávesy a fokus arbitruje správce oken; okno je dostává přes
svůj kontext, ne přes `document`, a workbench si rezervuje cestu ven.

### 3.13 Nasadil se starý frontend

Sestavený bundle je v gitu a jeho překlad se dá zapomenout (stalo se —
e2e testy padaly na starém bundlu).

**Pravidlo:** buď se staví při balení, nebo existuje kontrola, že bundle
odpovídá zdrojům.

### 3.14 Globální stav přetekl mezi testy

Cesta k souboru politiky se nastavovala proces-wide; jeden test ji změnil
a ovlivnil celou sadu.

**Pravidlo:** stav vlastní instance. Testy si vyrobí vlastní a nic
neresetují.

## 4. Nechat být

| co | proč ne |
|---|---|
| **`legacy/` prototyp** | historie, ne základ. |
| **čtyři paralelní mapy oken podle typu** | nahrazeno jedním registrem už ve viewBase2. |
| **`kind: "locked"` jako typ okna** | mísí chrome a obsah; zamčenost je **stav rámu**. |
| **detailní okno zadrátované v jádře** | je to obyčejný `panel`, který si otevře grafová apka. |
| **české identifikátory** | jména v kódu anglicky (komentáře v jakémkoli jazyce). Přejmenovávat to potom je průchod celým repozitářem a past se skrývá v řetězcích — jméno parametru cesty v routě, klíče payloadu, jména v konfiguraci. |
| **výchozí `screen_id` jako procesní čítač** | dva procesy vyrobí stejné id pro dvě různé plochy. |

---

*Návrh architektury: [architektura-navrh.md](architektura-navrh.md) ·
review původního konceptu: [review-workbench-apps.md](review-workbench-apps.md)*
