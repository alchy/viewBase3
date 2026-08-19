"""Doklad, ze sestaveny frontend odpovida svym zdrojum.

Chyba 3.13 z viewBase2: bundle byl v gitu, jeho preklad se dal zapomenout -
a taky se zapomnel. E2E testy pak padaly na starem bundlu.

D-09 nechava bundle v gitu, protoze zamer je knihovna, kterou jde vlozit do
ciziho projektu jednim `pip install git+...` bez Node.js. PODMINKA je tahle
kontrola: vedle bundlu lezi `BUNDLE.sha256` s otiskem ZDROJU a test ho
prepocita. Nesoulad = cervene CI.

Kontrola vznika DRIV nez prvni bundle. Az prvni vznikne, uz na nej ceka -
kdyby vznikla az s nim, nikdo by nevedel, jestli kdy platila.

Zapsat otisk po prekladu:

    python -m viewbase.bundle --write
"""
from __future__ import annotations

import sys
from hashlib import sha256
from pathlib import Path

#: Korenove adresare. Modul lezi v python/viewbase/, repozitar je o dve vys.
_REPO = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = _REPO / "frontend"
STATIC_DIR = Path(__file__).resolve().parent / "static"
STAMP = STATIC_DIR / "BUNDLE.sha256"

#: Co ve zdrojich NENI zdroj. Kdyby se do otisku pocital vystup buildu nebo
#: zavislosti, menil by se sam od sebe po kazdem prekladu a prestal by cokoli
#: dokazovat.
_IGNORED_DIRS = {"node_modules", "dist", "build", ".vite", ".cache", "__pycache__"}


def source_files(directory: Path) -> list[Path]:
    """Zdrojove soubory frontendu v pevnem poradi.

    Poradi je soucasti otisku: dva stroje musi dojit ke stejnemu vysledku.
    """
    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        parts = set(path.relative_to(directory).parts)
        if parts & _IGNORED_DIRS or any(p.startswith(".") for p in parts):
            continue
        found.append(path)
    return found


def fingerprint(directory: Path) -> str | None:
    """Otisk zdroju, nebo None, kdyz zadne nejsou.

    None a "otisk prazdneho adresare" musi jit odlisit - jinak by prazdny
    adresar dolozil libovolny bundle.

    Do otisku jde CESTA i OBSAH: presun souboru je zmena zdroju stejne jako
    zmena jeho obsahu.
    """
    files = source_files(directory)
    if not files:
        return None
    digest = sha256()
    for path in files:
        digest.update(str(path.relative_to(directory).as_posix()).encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def bundle_files(static: Path) -> list[Path]:
    """Co v `static/` je vysledek prekladu. Samotny otisk bundle neni."""
    if not static.is_dir():
        return []
    return [
        path
        for path in sorted(static.rglob("*"))
        if path.is_file() and path.name != STAMP.name
    ]


def verify(frontend: Path = FRONTEND_DIR, static: Path = STATIC_DIR) -> str | None:
    """Vrat popis problemu, nebo None, kdyz je vsechno v poradku.

    Tri stavy, ktere musi projit:

      * zadny bundle - vyvojar, ktery jeste nestavel, neni chyba,
      * bundle s otiskem, ktery sedi na zdroje,
      * zadne zdroje a zadny bundle (dnesni stav repozitare).

    A dva, ktere projit nesmi: bundle bez zdroju (nejde overit vubec)
    a bundle s otiskem, ktery na zdroje nesedi (nekdo zmenil frontend
    a zapomnel prelozit - presne chyba 3.13).
    """
    bundle = bundle_files(static)
    if not bundle:
        return None

    current = fingerprint(frontend)
    if current is None:
        return (
            f"v {static} lezi sestaveny frontend, ale v {frontend} nejsou zadne "
            f"zdroje - takovy bundle nejde overit"
        )

    stamp = static / STAMP.name
    if not stamp.is_file():
        return (
            f"v {static} lezi sestaveny frontend bez otisku {STAMP.name} - "
            f"prelozte a spustte `python -m viewbase.bundle --write`"
        )

    recorded = stamp.read_text(encoding="utf-8").strip()
    if recorded != current:
        return (
            f"otisk v {STAMP.name} neodpovida zdrojum ve {frontend}: nekdo zmenil "
            f"frontend a zapomnel prelozit (zaznamenano {recorded[:12]}..., "
            f"spocteno {current[:12]}...)"
        )
    return None


def write_stamp(frontend: Path = FRONTEND_DIR, static: Path = STATIC_DIR) -> str:
    """Zapis otisk soucasnych zdroju. Vola se PO prekladu, ne pred nim."""
    current = fingerprint(frontend)
    if current is None:
        raise SystemExit(f"v {frontend} nejsou zadne zdroje, neni co orazitkovat")
    static.mkdir(parents=True, exist_ok=True)
    (static / STAMP.name).write_text(current + "\n", encoding="utf-8")
    return current


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--write" in argv:
        print(f"otisk zapsan: {write_stamp()}")
        return 0
    problem = verify()
    if problem:
        print(problem, file=sys.stderr)
        return 1
    print("bundle odpovida zdrojum (nebo zadny neni)")
    return 0


if __name__ == "__main__":  # pragma: no cover - vstupni bod
    raise SystemExit(main())
