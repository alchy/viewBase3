"""Sestaveny frontend v gitu smi byt jen s dokladem, ze odpovida zdrojum.

Chyba 3.13 z viewBase2: bundle byl v gitu, jeho preklad se dal zapomenout -
a taky se zapomnel. E2E testy padaly na starem bundlu a nikdo dlouho nevedel
proc.

D-09 to povoluje pod PODMINKOU: vedle bundlu lezi otisk zdroju a test ho
prepocita. Nesoulad = cervene CI. Kontrola vznika DRIV nez prvni bundle -
tenhle soubor je proto napsany ve chvili, kdy zadny frontend jeste neexistuje.
Az vznikne, uz na nej bude cekat.
"""
import pytest

from viewbase.bundle import (
    FRONTEND_DIR,
    STAMP,
    STATIC_DIR,
    bundle_files,
    fingerprint,
    source_files,
    verify,
)


# ===========================================================================
# Otisk zdroju
# ===========================================================================


def write(directory, name, text):
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_the_same_sources_give_the_same_fingerprint(tmp_path):
    write(tmp_path, "src/main.js", "console.log(1)")
    prvni = fingerprint(tmp_path)
    assert fingerprint(tmp_path) == prvni


def test_changing_a_source_changes_the_fingerprint(tmp_path):
    write(tmp_path, "src/main.js", "console.log(1)")
    before = fingerprint(tmp_path)
    write(tmp_path, "src/main.js", "console.log(2)")
    assert fingerprint(tmp_path) != before


def test_adding_a_source_changes_the_fingerprint(tmp_path):
    write(tmp_path, "src/main.js", "console.log(1)")
    before = fingerprint(tmp_path)
    write(tmp_path, "src/wm.js", "export {}")
    assert fingerprint(tmp_path) != before


def test_removing_a_source_changes_the_fingerprint(tmp_path):
    write(tmp_path, "src/main.js", "console.log(1)")
    doplnek = write(tmp_path, "src/wm.js", "export {}")
    before = fingerprint(tmp_path)
    doplnek.unlink()
    assert fingerprint(tmp_path) != before


def test_moving_a_source_changes_the_fingerprint(tmp_path):
    # Otisk nesmi byt jen soucet obsahu: presun souboru je zmena zdroju.
    write(tmp_path, "src/main.js", "console.log(1)")
    before = fingerprint(tmp_path)
    (tmp_path / "src/main.js").rename(tmp_path / "src/index.js")
    assert fingerprint(tmp_path) != before


def test_build_output_does_not_count_as_a_source(tmp_path):
    # Jinak by se otisk menil sam od sebe po kazdem buildu a prestal by
    # cokoli dokazovat.
    write(tmp_path, "src/main.js", "console.log(1)")
    before = fingerprint(tmp_path)
    write(tmp_path, "node_modules/vite/index.js", "// zavislost")
    write(tmp_path, "dist/bundle.js", "// vysledek")
    assert fingerprint(tmp_path) == before


def test_an_empty_or_missing_frontend_has_no_fingerprint(tmp_path):
    # "Zadne zdroje" musi jit odlisit od "zdroje s nejakym otiskem" - jinak by
    # prazdny adresar dolozil libovolny bundle.
    assert fingerprint(tmp_path) is None
    assert fingerprint(tmp_path / "neexistuje") is None


def test_source_files_are_listed_in_a_stable_order(tmp_path):
    write(tmp_path, "src/b.js", "b")
    write(tmp_path, "src/a.js", "a")
    listed = [p.name for p in source_files(tmp_path)]
    assert listed == sorted(listed)


# ===========================================================================
# Overeni bundlu proti zdrojum
# ===========================================================================


def test_sources_without_a_bundle_are_fine(tmp_path):
    # Vyvojar, ktery jeste nestavel, neni chyba.
    write(tmp_path / "frontend", "src/main.js", "console.log(1)")
    (tmp_path / "static").mkdir()
    assert verify(tmp_path / "frontend", tmp_path / "static") is None


def test_a_bundle_without_any_sources_is_refused(tmp_path):
    # Bundle, ke kteremu neexistuji zdroje, nejde nijak overit - a presne
    # takovy se ve viewBase2 nasadil.
    (tmp_path / "frontend").mkdir()
    write(tmp_path / "static", "bundle.js", "// odnekud")
    assert "zdroj" in verify(tmp_path / "frontend", tmp_path / "static")


def test_a_bundle_without_a_stamp_is_refused(tmp_path):
    write(tmp_path / "frontend", "src/main.js", "console.log(1)")
    write(tmp_path / "static", "bundle.js", "// vysledek")
    assert "BUNDLE.sha256" in verify(tmp_path / "frontend", tmp_path / "static")


def test_a_bundle_stamped_from_these_sources_passes(tmp_path):
    frontend = tmp_path / "frontend"
    static = tmp_path / "static"
    write(frontend, "src/main.js", "console.log(1)")
    write(static, "bundle.js", "// vysledek")
    write(static, "BUNDLE.sha256", fingerprint(frontend))
    assert verify(frontend, static) is None


def test_a_bundle_stamped_from_older_sources_is_refused(tmp_path):
    # Tohle je ta chyba: nekdo zmenil frontend a zapomnel prelozit.
    frontend = tmp_path / "frontend"
    static = tmp_path / "static"
    write(frontend, "src/main.js", "console.log(1)")
    write(static, "bundle.js", "// vysledek")
    write(static, "BUNDLE.sha256", fingerprint(frontend))

    write(frontend, "src/main.js", "console.log(2)")  # zmena bez prekladu

    assert "neodpovida" in verify(frontend, static)


def test_the_stamp_alone_is_not_a_bundle(tmp_path):
    # Samotny otisk bez vystupu neni bundle a nema co hlidat.
    frontend = tmp_path / "frontend"
    static = tmp_path / "static"
    write(frontend, "src/main.js", "console.log(1)")
    write(static, "BUNDLE.sha256", fingerprint(frontend))
    assert bundle_files(static) == []


# ===========================================================================
# Tentyz invariant nad SKUTECNYM repozitarem
# ===========================================================================


def test_this_repository_ships_no_unverifiable_bundle():
    # Dnes tu zadny frontend ani bundle neni a test projde trivialne. To je
    # zamer: az prvni bundle vznikne, uz na nej tahle kontrola ceka. Kdyby
    # vznikla az s nim, nikdo by nevedel, jestli kdy platila.
    problem = verify(FRONTEND_DIR, STATIC_DIR)
    assert problem is None, problem


def test_the_stamp_lives_next_to_the_bundle():
    # Otisk patri k tomu, co dokazuje - ne do jineho adresare, kde se na nej
    # zapomene.
    assert STAMP.parent == STATIC_DIR
