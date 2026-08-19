"""Nastroj spravce: zalozeni identity (D-11, B-22).

Knihovna NEZAKLADA IDENTITY z aplikacniho kodu - jen jmenuje principaly na
svych prvcich. Zalozit uzivatele je spravcovsky ukon a ma na nej byt nastroj.
Bez nej se do instance neda prihlasit vubec, protoze TOTP tajemstvi se rukou
nenapise.

Tri zvyklosti prevzate z viewBase2 doslova:

  * artefakty patri do ~/.viewbase/user-<jmeno>/ s pravy 0600 (adresar 0700),
  * do logu jde JEN UKAZATEL, kde je vyzvednout - nikdy tajemstvi ani QR,
  * stitek v autentikatoru je `viewBase:user:<jmeno>`, tedy stejna syntaxe
    jako principal v ACL; v autentikatoru se to pozna od ostatnich polozek.
"""
import stat

import pytest

from viewbase.admin import DIR_MODE, FILE_MODE, add_user, main, user_dir


def mode_of(path):
    return stat.S_IMODE(path.stat().st_mode)


# ===========================================================================
# Kam to patri a s jakymi pravy
# ===========================================================================


def test_the_user_gets_a_directory_of_their_own(tmp_path):
    add_user("hana", home=tmp_path)
    assert (tmp_path / "user-hana").is_dir()


def test_the_directory_is_readable_only_by_its_owner(tmp_path):
    add_user("hana", home=tmp_path)
    assert mode_of(tmp_path / "user-hana") == DIR_MODE


def test_every_artefact_is_readable_only_by_its_owner(tmp_path):
    registration = add_user("hana", home=tmp_path)
    for path in registration.directory.iterdir():
        assert mode_of(path) == FILE_MODE, path.name


def test_the_home_can_be_pointed_elsewhere(tmp_path):
    # Kontejnery a testy potrebuji jine misto nez domovsky adresar.
    assert user_dir("hana", home=tmp_path).parent == tmp_path


# ===========================================================================
# Co v tech souborech je
# ===========================================================================


def test_the_secret_file_holds_a_base32_secret(tmp_path):
    registration = add_user("hana", home=tmp_path)
    secret = (registration.directory / "totp.secret").read_text().strip()
    assert len(secret) >= 16
    assert set(secret) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567=")


def test_the_uri_is_the_one_an_authenticator_understands(tmp_path):
    registration = add_user("hana", home=tmp_path)
    uri = (registration.directory / "totp.uri").read_text().strip()
    assert uri.startswith("otpauth://totp/")


def test_the_label_uses_the_same_syntax_as_a_principal(tmp_path):
    # `viewBase:user:hana` - v autentikatoru se to pozna od ostatnich polozek
    # a v ACL se ten clovek jmenuje stejne.
    registration = add_user("hana", home=tmp_path)
    assert registration.label == "viewBase:user:hana"
    assert "viewBase%3Auser%3Ahana" in (registration.directory / "totp.uri").read_text()


def test_a_qr_code_is_written_next_to_it(tmp_path):
    registration = add_user("hana", home=tmp_path)
    qr = registration.directory / "totp.svg"
    assert qr.is_file()
    assert qr.read_text().lstrip().startswith("<?xml") or "<svg" in qr.read_text()


def test_the_code_from_the_secret_verifies(tmp_path):
    # Nejlepsi doklad, ze tajemstvi je pouzitelne: vyrobit z nej kod.
    import pyotp

    registration = add_user("hana", home=tmp_path)
    secret = (registration.directory / "totp.secret").read_text().strip()
    assert pyotp.TOTP(secret).verify(pyotp.TOTP(secret).now())


# ===========================================================================
# Tajemstvi se nesmi dostat ven jinak nez tim souborem
# ===========================================================================


def test_the_result_does_not_carry_the_secret_in_its_repr(tmp_path):
    # Repr konci v logu, v tracebacku a v ladicim vypisu.
    registration = add_user("hana", home=tmp_path)
    secret = (registration.directory / "totp.secret").read_text().strip()
    assert secret not in repr(registration)


def test_the_printed_output_says_where_to_look_not_what_it_is(tmp_path, capsys):
    main(["adduser", "hana", "--home", str(tmp_path)])
    printed = capsys.readouterr().out
    secret = (tmp_path / "user-hana" / "totp.secret").read_text().strip()

    assert str(tmp_path / "user-hana") in printed
    assert secret not in printed


def test_the_printed_output_does_not_carry_the_uri_either(tmp_path, capsys):
    # URI obsahuje tajemstvi cele; je to totez jako vypsat ho.
    main(["adduser", "hana", "--home", str(tmp_path)])
    assert "otpauth://" not in capsys.readouterr().out


# ===========================================================================
# Jmeno je vstup a chova se jako vstup
# ===========================================================================


@pytest.mark.parametrize("bad", ["../../etc", "a/b", "a:b", "", "   ", "."])
def test_a_name_that_would_escape_the_directory_is_refused(tmp_path, bad):
    # `user-<jmeno>` se sklada do cesty; jmeno s lomitkem nebo teckami by
    # zalozilo adresar uplne jinde.
    with pytest.raises(ValueError):
        add_user(bad, home=tmp_path)


def test_a_refused_name_leaves_nothing_behind(tmp_path):
    with pytest.raises(ValueError):
        add_user("../uteklo", home=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_an_existing_user_is_not_overwritten(tmp_path):
    # Prepsat tajemstvi znamena zamknout cloveka ven - jeho autentikator
    # pak vydava kody, ktere uz nikam nepatri.
    add_user("hana", home=tmp_path)
    with pytest.raises(ValueError, match="uz existuje"):
        add_user("hana", home=tmp_path)


def test_the_existing_secret_survives_a_second_attempt(tmp_path):
    registration = add_user("hana", home=tmp_path)
    before = (registration.directory / "totp.secret").read_text()
    with pytest.raises(ValueError):
        add_user("hana", home=tmp_path)
    assert (registration.directory / "totp.secret").read_text() == before


# ===========================================================================
# Prikazova radka
# ===========================================================================


def test_adduser_returns_success(tmp_path):
    assert main(["adduser", "hana", "--home", str(tmp_path)]) == 0


def test_adduser_twice_returns_a_failure_code(tmp_path, capsys):
    main(["adduser", "hana", "--home", str(tmp_path)])
    assert main(["adduser", "hana", "--home", str(tmp_path)]) == 1


def test_an_unknown_command_returns_a_failure_code(capsys):
    assert main(["neexistuje"]) == 2


def test_no_command_prints_usage(capsys):
    main([])
    assert "adduser" in capsys.readouterr().err
