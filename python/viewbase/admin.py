"""Nastroj spravce: zalozeni identity.

KNIHOVNA NEZAKLADA IDENTITY z aplikacniho kodu - jen jmenuje principaly na
svych prvcich (par. 12.2). Zalozit uzivatele je spravcovsky ukon a ma na nej
byt nastroj:

    python -m viewbase.admin adduser hana

Bez nej se do instance neda prihlasit vubec, protoze TOTP tajemstvi se rukou
nenapise.

Tri zvyklosti prevzate z viewBase2 doslova, protoze se osvedcily:

  * ARTEFAKTY NA DISK, ne do logu. Tajemstvi a QR lezi v
    ~/.viewbase/user-<jmeno>/ s pravy 0600 (adresar 0700); do logu jde jen
    UKAZATEL, kde je vyzvednout. Vypsat tajemstvi na obrazovku znamena mit ho
    v historii terminalu, ve scrollbacku a v `docker logs`.
  * STITEK `viewBase:user:<jmeno>`, tedy stejna syntaxe jako principal v ACL.
    V autentikatoru se to pozna od ostatnich polozek a clovek se v pravech
    jmenuje stejne jako ve svem telefonu.
  * EXISTUJICI TAJEMSTVI SE NEPREPISUJE. Prepsat ho znamena zamknout cloveka
    ven: jeho autentikator dal vydava kody, ktere uz nikam nepatri.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pyotp
import qrcode
import qrcode.image.svg

#: Kde artefakty leží, kdyz se nerekne jinak. Kontejnery a testy si to
#: presmeruji.
DEFAULT_HOME = Path(os.environ.get("VIEWBASE_HOME", "~/.viewbase")).expanduser()

#: Prava. Tajemstvi je ctitelne jen vlastnikem, a adresar se nedá ani projit.
FILE_MODE = 0o600
DIR_MODE = 0o700

#: Vydavatel ve stitku. Stejna syntaxe jako principal: `viewBase:user:hana`.
ISSUER = "viewBase"

#: Jmeno se sklada do cesty i do stitku, takze je to VSTUP a chova se jako
#: vstup: jen pismena, cislice, tecka uvnitr, pomlcka a podtrzitko.
_NAME = re.compile(r"^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*$")


@dataclass(frozen=True, slots=True)
class Registration:
    """Vysledek zalozeni. TAJEMSTVI TU NENI a nebude.

    Repr konci v logu, v tracebacku a v ladicim vypisu - kdyby v nem tajemstvi
    bylo, unikne prvni vyjimkou. Kdo ho potrebuje, prectě si soubor.
    """

    name: str
    directory: Path
    label: str

    @property
    def principal(self) -> str:
        """Jak se ten clovek jmenuje v ACL."""
        return f"user:{self.name}"


def check_name(name: str) -> str:
    """Over jmeno driv, nez se z nej stane cesta.

    `user-<jmeno>` se sklada do cesty; jmeno s lomitkem nebo teckami by
    zalozilo adresar uplne jinde. Kontrola je tady, ne u volajiciho - jinak by
    ji jedno volaci misto vynechalo.
    """
    text = str(name).strip()
    if not _NAME.match(text):
        raise ValueError(
            f"neplatne jmeno uzivatele {name!r}: povolena jsou pismena, cislice, "
            f"'-', '_' a tecka uvnitr"
        )
    return text


def user_dir(name: str, home: Path | None = None) -> Path:
    return (Path(home) if home is not None else DEFAULT_HOME) / f"user-{check_name(name)}"


def add_user(
    name: str, home: Path | None = None, secret: str | None = None
) -> Registration:
    """Zaloz uzivatele: tajemstvi, URI pro autentikator a QR.

    Vraci ukazatel na to, kde artefakty lezi - ne jejich obsah.
    """
    name = check_name(name)
    directory = user_dir(name, home)
    if directory.exists():
        raise ValueError(
            f"uzivatel {name!r} uz existuje ({directory}); prepsat jeho tajemstvi "
            f"by ho zamklo ven - smazte adresar rucne, kdyz to opravdu chcete"
        )

    secret = secret or pyotp.random_base32()
    label = f"{ISSUER}:user:{name}"
    uri = pyotp.TOTP(secret).provisioning_uri(name=label, issuer_name=ISSUER)

    directory.mkdir(parents=True, mode=DIR_MODE)
    os.chmod(directory, DIR_MODE)  # mkdir podleha umask, chmod ne
    _write(directory / "totp.secret", secret)
    _write(directory / "totp.uri", uri)
    _write(directory / "totp.svg", _qr_svg(uri))
    return Registration(name=name, directory=directory, label=label)


def _write(path: Path, text: str) -> None:
    """Zapis s pravy 0600 uz pri VZNIKU souboru.

    Kdyby se prava nastavovala az po zapisu, existuje okamzik, kdy je
    tajemstvi ctitelne komukoli - kratky, ale skutecny.
    """
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        out.write(text if text.endswith("\n") else text + "\n")
    os.chmod(path, FILE_MODE)


def _qr_svg(uri: str) -> str:
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgImage)
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode("utf-8")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv:
        print("pouziti: python -m viewbase.admin adduser <jmeno> [--home CESTA]",
              file=sys.stderr)
        return 2
    command, *rest = argv
    if command != "adduser":
        print(f"neznamy prikaz {command!r}; zname: adduser", file=sys.stderr)
        return 2
    if not rest:
        print("adduser potrebuje jmeno uzivatele", file=sys.stderr)
        return 2

    name = rest[0]
    home = None
    if "--home" in rest:
        home = Path(rest[rest.index("--home") + 1])

    try:
        registration = add_user(name, home=home)
    except ValueError as problem:
        print(str(problem), file=sys.stderr)
        return 1

    # UKAZATEL, ne obsah: tajemstvi ani URI se na obrazovku nedostanou.
    print(f"uzivatel {registration.name} zalozen")
    print(f"  principal:  {registration.principal}")
    print(f"  stitek:     {registration.label}")
    print(f"  artefakty:  {registration.directory}")
    print("  QR nactete z totp.svg; tajemstvi je v totp.secret (prava 0600)")
    return 0


if __name__ == "__main__":  # pragma: no cover - vstupni bod
    raise SystemExit(main())
