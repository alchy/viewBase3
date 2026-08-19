"""Sanace, redakce a sloupce auditni stopy - ciste funkce a hodnota zaznamu.

Ctyri pravidla z par. 7 a u kazdeho duvod z provozu viewBase2:

  * SANACE NA JEDNOM MISTE. Do logu tecou cizi vstupy - prikazy ze shellu,
    payloady udalosti, syrove zpravy od klienta. Nejde o log4j (Python nic
    nevyhodnocuje), ale o tri skutecne veci: ESC sekvence prebarvi terminal
    toho, kdo cte `docker logs`; `\\n` v cizim textu vyrobi zaznam, ktery
    vypada jako od serveru; jedna dlouha zprava utopi zbytek.
  * REDAKCE PODLE KLICU na ceste do logu, ne v kazdem volajicim. Chyba 3.10:
    payload udalosti se logoval cely a kod z autentikatoru se objevil
    v ladicim logu.
  * SLOUPCOVY FORMAT, at jde stopa cist po pozicich i strojove.
  * AUDIT PROJDE VZDYCKY. Bezpecnostni udalost se nesmi dat utisit
    nastavenim `log_level`.

A jedno rozliseni, ktere je snadne splest: UROVEN rika, jak je to zle.
KOMPONENTA rika, ze jde o bezpecnostni stopu. Uspesne odemceni neni
`warning` a odmitnuty kod neni `error` - proto je `security` komponenta,
ne pata uroven.

Tady je jen to, co NEZAVISI NA NICEM: sanace, redakce, tvar zaznamu a
vykresleni radku. Sberna nadoba se stavem a prahem (`AuditLog`) zije
v runtime - drzet cistou funkci jinde jen proto, ze seznam modulu byl
uplny, by bylo horsi nez ten seznam opravit (par. 11).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

#: Ctyri urovne, ani o jednu vic. Audit neni pata.
LEVELS = ("debug", "info", "warning", "error")

#: Komponenta bezpecnostni stopy. Nesmi si ji vzit obycejny zaznam - jinak by
#: sel prah obejit z druhe strany.
SECURITY = "security"

#: Kolik znaku session id smi do logu. Cele je prihlasovaci udaj a jeho
#: drzitel JE tou relaci.
SESSION_PREFIX = 8

#: Sirka sloupce "odkud", at jdou radky cist po pozicich.
SOURCE_WIDTH = 15

#: Strop delky detailu. Jedna zprava nesmi utopit zbytek stopy.
MAX_DETAIL = 2000

#: Ridici znaky, ktere se do logu nesmi dostat syrove: ESC (prebarvi a prepise
#: terminal), CR (prepise radek), NUL a spol.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

#: Slova v klici, ktera znamenaji "tohle se neloguje". Hleda se PODRETEZEC,
#: ne presna shoda: `access_token` a `user_secret` jsou tataz vec a cekat na
#: uplny seznam jmen znamena ho nikdy nemit uplny.
REDACTED_KEYS = ("code", "token", "secret", "sid", "password", "passwd", "otp", "key")


def sanitize(message: object, limit: int = MAX_DETAIL) -> str:
    """Ocisti text, ktery jde do logu. JEDNO misto pro vsechny cesty."""
    text = _CONTROL.sub(lambda m: f"\\x{ord(m.group()):02x}", str(message))
    text = text.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    if len(text) > limit:
        text = f"{text[:limit]}...(+{len(text) - limit} znaku)"
    return text


def redact(payload, keys: tuple[str, ...] = REDACTED_KEYS):
    """Nahrad hodnoty u nebezpecnych klicu jejich delkou.

    Delka je uzitecna pri hledani chyb ("prisel prazdny kod") a neprozradi nic.
    Prochazi se DO HLOUBKY: payload udalosti byva zanoreny a redakce jen na
    prvni urovni by byla jen zdanim.
    """
    if isinstance(payload, dict):
        out = {}
        for key, value in payload.items():
            lowered = str(key).lower()
            if any(word in lowered for word in keys):
                out[key] = f"<redacted:{len(str(value))}>"
            else:
                out[key] = redact(value, keys)
        return out
    if isinstance(payload, (list, tuple)):
        return type(payload)(redact(item, keys) for item in payload)
    return payload


@dataclass(frozen=True, slots=True)
class Record:
    """Jeden radek stopy.

    Poradi poli je zaroven poradim ve vypisu: KDY, jak zle (level), KDO
    (session), ODKUD (source), CO je to zac (component), co se stalo (action)
    a teprve pak detail. Driv byvalo "kdo" a "odkud" nalepene v textu zpravy,
    takze se to spatne cetlo i parsovalo.
    """

    at: float
    level: str
    component: str
    action: str
    by: str | None = None
    session: str | None = None
    source: str | None = None
    address: object | None = None
    verb: object | None = None
    detail: str = ""



def format_record(record: Record) -> str:
    """Sloupcovy radek: kdy, jak zle, kdo, odkud, co, detail.

    Chybejici hodnota drzi misto pomlckou, aby sla stopa cist po pozicich
    i strojove.
    """
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(record.at))
    return (
        f"{stamp} {record.level.upper():<7} "
        f"{(record.session or '-'):<{SESSION_PREFIX}} "
        f"{(record.source or '-'):<{SOURCE_WIDTH}} "
        f"{('[' + record.component + ']'):<12} "
        f"{record.action} {record.detail or '-'}"
    )


def build_record(
    at: float, level: str, component: str, action: str, by=None, session=None,
    source=None, address=None, verb=None, detail: object = "",
) -> Record:
    """Poskladej zaznam. VSECHNA textova pole projdou sanaci prave tady.

    Je to jedine misto, kde zaznam vznika - kdyby jich bylo vic, jedno by na
    sanaci drive nebo pozdeji zapomnelo.
    """
    return Record(
        at=at,
        level=level,
        component=sanitize(component, 32),
        action=sanitize(action, 64),
        by=sanitize(by, 64) if by is not None else None,
        # Do stopy jde jen PREFIX session id; cele je prihlasovaci udaj.
        session=sanitize(session, SESSION_PREFIX)[:SESSION_PREFIX] if session else None,
        source=sanitize(source, SOURCE_WIDTH) if source else None,
        address=address,
        verb=verb,
        detail=sanitize(detail),
    )
