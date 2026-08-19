"""Adresa objektu: neprurhledne id a cesta rodic/dite.

Adresa vznika PRI NAROZENI objektu, ne az kdyz ho plocha prijme. Ve viewBase2
okno vznikalo bezejmenne a do prijeti melo prava "nikam nepatriciho" objektu;
tady ten mezistav neexistuje, protoze bez adresy objekt nevznikne.

Touz adresou se ridi prava, log i vzdalene volani. Proto je id NEPRUHLEDNE:
viewBase2 mel procesni citac 1, 2, 3..., ktery plnil dve role zaroven -
poradi na liste a adresu. Jako adresa je rozbity, protoze dva procesy vyrobi
`screen_id=1` pro dve ruzne plochy. Poradi na liste je jina vlastnost
(`index`) a s adresou nema nic spolecneho.

Tvary adres:

    instance:                       sama instance (vlastni ACL, sprava)
    instance:<jmeno>                objekt instance (log, audit)
    app:<app_id>                    registrace apky (kdo ji vubec uvidi)
    content:<rukojet>               obsah u apky (druha uroven prav)
    screen:<id>                     plocha
    screen:<id>/window:<id>         okno na plose

Instance je objekt jako kazdy jiny - ma adresu a vlastni ACL. Diky tomu se
udalosti spravy instance vyhodnocuji TOUZ funkci `resolve(address, verb)` jako
vsechno ostatni a nevznika pro ne zvlastni cesta (D-17). Co ma privilegovanou
zkratku, to se prestane testovat jako vsechno ostatni.

Modul nezavisi na nicem (par. 11).
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass

#: Znaky, ktere adresu rozdeluji. V id nesmi byt, jinak se parsovani rozpadne.
_SEPARATORS = (":", "/")

#: Delka nepruhledneho id v bajtech pred zakodovanim do base64url.
_ID_BYTES = 9

#: Co smi stat pod cim. Adresa mimo tenhle strom je chyba, ne novy tvar.
_ALLOWED_CHILDREN = {"screen": ("window",)}
_ALLOWED_ROOTS = ("instance", "screen", "app", "content")


def new_id() -> str:
    """Vyrob nepruhledne id, ktere se da vlozit do adresy.

    `token_urlsafe` vraci jen [A-Za-z0-9_-], tedy zadny z oddelovacu adresy.
    """
    return secrets.token_urlsafe(_ID_BYTES)


def _validate(part: str, what: str) -> str:
    """Id, ktere by rozbilo adresu, je chyba pri vzniku objektu - ne az pri
    prvnim parsovani nekde v transportu."""
    if not part:
        raise ValueError(f"{what} nesmi byt prazdne")
    for separator in _SEPARATORS:
        if separator in part:
            raise ValueError(f"{what} nesmi obsahovat {separator!r}: {part!r}")
    return part


@dataclass(frozen=True, slots=True)
class Address:
    """Adresa objektu jako hodnota: porovnatelna, hashovatelna, serializovatelna.

    Je to hodnota zamerne - adresa se posila po drate, pouziva jako klic
    v registru a musi prezit rozdeleni do vic procesu beze zmeny vyznamu.

    Uvnitr je to posloupnost dvojic (typ, id); tovarny nize jsou jediny
    schvaleny zpusob, jak ji vyrobit.
    """

    segments: tuple[tuple[str, str], ...]

    # -- tovarny ---------------------------------------------------------

    @classmethod
    def instance_root(cls) -> "Address":
        """Sama instance. Koren, pod kterym visi jeji objekty."""
        return cls((("instance", ""),))

    @classmethod
    def instance(cls, name: str) -> "Address":
        """Objekt, ktery patri instanci, ne plose (typicky log).

        Visi pod `instance:`, takze bez vlastniho ACL dedi ACL instance -
        nikdy ACL plochy, na ktere se zrovna zobrazuje (chyba 3.4).
        """
        return cls((("instance", _validate(name, "jmeno objektu")),))

    @classmethod
    def app(cls, app_id: str) -> "Address":
        """Registrace apky.

        Je to objekt jako kazdy jiny, takze se na nej da povesit ACL a nas
        model rozhodne, kdo apku vubec uvidi ve spousteci (D-36). Nepatri pod
        plochu - existuje driv, nez je jake okno.
        """
        return cls((("app", _validate(app_id, "id apky")),))

    @classmethod
    def content(cls, handle: str) -> "Address":
        """Obsah u apky.

        Ma vlastni ACL a NEMA DEDICNOST (D-57): nelezi na plose, takze neni
        z ceho dedit. Efektivni pravo divaka je prunik okna a obsahu a pocita
        se vyslovne, ne tretim pravidlem v dedicnosti.
        """
        return cls((("content", _validate(handle, "rukojet obsahu")),))

    @classmethod
    def screen(cls, screen_id: str) -> "Address":
        return cls((("screen", _validate(screen_id, "id plochy")),))

    @classmethod
    def window(cls, screen_id: str, window_id: str) -> "Address":
        return cls(
            (
                ("screen", _validate(screen_id, "id plochy")),
                ("window", _validate(window_id, "id okna")),
            )
        )

    # -- cteni -----------------------------------------------------------

    @property
    def kind(self) -> str:
        """Typ posledniho clenu: 'instance', 'screen' nebo 'window'."""
        return self.segments[-1][0]

    @property
    def screen_id(self) -> str | None:
        first = self.segments[0]
        return first[1] if first[0] == "screen" else None

    @property
    def window_id(self) -> str | None:
        last = self.segments[-1]
        return last[1] if last[0] == "window" else None

    @property
    def parent(self) -> "Address | None":
        """Nadrazeny objekt, nebo None.

        Nad plochou uz adresa neni: dedicnost pokracuje vychozi hodnotou
        instance a ta se do stromu adres neplete (par. 4).

        Objekt instance (`instance:log`) ma za rodice SAMU INSTANCI
        (`instance:`), takze bez vlastniho ACL dedi ACL instance - nikdy ACL
        plochy, na ktere se zrovna zobrazuje (chyba 3.4). Zapisuje se porad
        jako `instance:log`; dvouclenna adresa by jen zdvojila prefix.
        """
        if len(self.segments) > 1:
            return Address(self.segments[:-1])
        kind, value = self.segments[0]
        if kind == "instance" and value:
            return Address.instance_root()
        return None

    def __str__(self) -> str:
        return "/".join(f"{kind}:{value}" for kind, value in self.segments)

    def __repr__(self) -> str:  # pragma: no cover - jen pro ladeni
        return f"Address({str(self)!r})"

    # -- parsovani -------------------------------------------------------

    @classmethod
    def parse(cls, text: str) -> "Address":
        """Adresa z retezce. Nesrozumitelny tvar je chyba, ne None.

        Parsovani je zaroven kontrola tvaru: 'screen:a/screen:b' neni adresa
        s nezname urovni, ale chyba.
        """
        segments = tuple(_split_pair(part, text) for part in text.split("/"))

        if segments[0][0] not in _ALLOWED_ROOTS:
            raise ValueError(f"neznamy typ objektu v adrese: {text!r}")

        for parent, child in zip(segments, segments[1:]):
            if child[0] not in _ALLOWED_CHILDREN.get(parent[0], ()):
                raise ValueError(
                    f"{child[0]!r} nesmi stat pod {parent[0]!r}: {text!r}"
                )

        for kind, value in segments:
            if kind == "instance" and not value:
                continue  # koren instance nema jmeno
            _validate(value, f"id v casti {kind!r}")
        return cls(segments)


def _split_pair(part: str, whole: str) -> tuple[str, str]:
    kind, separator, value = part.partition(":")
    if not separator or not kind:
        raise ValueError(f"cast adresy nema tvar 'typ:id': {whole!r}")
    # Prazdna hodnota je platna jen u korene instance ("instance:").
    if not value and kind != "instance":
        raise ValueError(f"cast adresy nema tvar 'typ:id': {whole!r}")
    return kind, value
