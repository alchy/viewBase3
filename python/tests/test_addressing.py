"""Adresa vznika pri narozeni objektu a je klicem pro prava, log i vzdalene
volani (architektura-navrh.md par. 2). Tyhle testy drzi jeji tvar."""
import pytest

from viewbase.core.addressing import Address, new_id


def test_screen_address_renders_with_prefix():
    assert str(Address.screen("provoz")) == "screen:provoz"


def test_window_address_hangs_under_its_screen():
    assert str(Address.window("provoz", "mzdy")) == "screen:provoz/window:mzdy"


def test_instance_address_is_top_level():
    assert str(Address.instance("log")) == "instance:log"


def test_address_round_trips_through_string():
    original = Address.window("provoz", "mzdy")
    assert Address.parse(str(original)) == original


def test_window_parent_is_its_screen():
    assert Address.window("provoz", "mzdy").parent == Address.screen("provoz")


def test_screen_has_no_parent():
    # Nad plochou uz neni adresa, ale vychozi hodnota instance (dedicnost
    # objekt -> plocha -> instance, par. 4).
    assert Address.screen("provoz").parent is None


def test_instance_object_hangs_under_the_instance_itself():
    # D-17: instance je objekt jako kazdy jiny - ma adresu a vlastni ACL.
    # Diky tomu se INSTANCE udalosti vyhodnocuji touz funkci resolve()
    # a nevznika zvlastni cesta.
    assert Address.instance("log").parent == Address.instance_root()


def test_the_instance_itself_is_the_top():
    assert Address.instance_root().parent is None


def test_instance_root_renders_as_a_bare_prefix():
    assert str(Address.instance_root()) == "instance:"


def test_instance_root_round_trips_through_string():
    assert Address.parse("instance:") == Address.instance_root()


def test_address_is_a_value_usable_as_a_key():
    registry = {Address.screen("provoz"): "plocha"}
    assert registry[Address.screen("provoz")] == "plocha"


def test_two_addresses_with_same_parts_are_equal():
    assert Address.screen("provoz") == Address.screen("provoz")


def test_new_id_is_unique():
    assert len({new_id() for _ in range(1000)}) == 1000


def test_new_id_is_safe_inside_an_address():
    # Kdyby generator vyrobil ':' nebo '/', adresa by se rozpadla pri parsovani.
    generated = new_id()
    assert Address.parse(str(Address.screen(generated))) == Address.screen(generated)


def test_new_id_is_not_a_counter():
    # Procesni citac 1,2,3 vyrobi ve dvou procesech tutez adresu pro dve ruzne
    # plochy (par. 2). Neprurhledne id proto nesmi byt kratke cislo.
    assert not new_id().isdigit()


@pytest.mark.parametrize("bad", ["", "ma:dvojtecku", "ma/lomitko"])
def test_id_that_would_break_the_address_is_rejected(bad):
    with pytest.raises(ValueError):
        Address.screen(bad)


@pytest.mark.parametrize("bad", ["", "screen", "neco:jineho", "screen:a/neco:b"])
def test_parsing_a_malformed_address_fails_loudly(bad):
    with pytest.raises(ValueError):
        Address.parse(bad)


# -- registrace apky je objekt s adresou a vlastnim ACL (D-36) -------------


def test_app_registration_has_an_address():
    assert str(Address.app("example.hello")) == "app:example.hello"


def test_app_address_round_trips():
    assert Address.parse("app:example.hello") == Address.app("example.hello")


def test_app_address_is_top_level():
    # Registrace apky nepatri pod plochu - existuje driv, nez je jake okno.
    assert Address.app("example.hello").parent is None


def test_an_app_id_with_a_slash_is_refused():
    with pytest.raises(ValueError):
        Address.app("example/hello")
