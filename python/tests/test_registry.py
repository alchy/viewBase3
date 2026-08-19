"""Jeden registr objektu podle adresy.

Ve viewBase2 byly ctyri paralelni mapy podle typu okna a kazda otazka "mam
okno s timhle id?" se musela ptat ctyrikrat. Tady je registr jeden a dava
odpoved na jedinou otazku, kterou vynucovani i vysilani potrebuji:
"jake ACL plati pro tuhle adresu a tohle sloveso?"
"""
import pytest

from viewbase.core.access import Access, Acl, Verb
from viewbase.core.addressing import Address
from viewbase.core.identity import USERS
from viewbase.runtime.registry import ObjectRegistry

PROVOZ = Address.screen("provoz")
MZDY = Address.window("provoz", "mzdy")
LOG = Address.instance("log")


def registry(default=Acl.of(USERS)):
    return ObjectRegistry(default_access=default)


# -- ulozeni a cteni --------------------------------------------------------


def test_registered_object_can_be_found():
    reg = registry()
    reg.add(PROVOZ, Access(see=Acl.of("group:ucetni")))
    assert reg.access_of(PROVOZ) == Access(see=Acl.of("group:ucetni"))


def test_object_registers_without_explicit_access():
    reg = registry()
    reg.add(PROVOZ)
    assert reg.access_of(PROVOZ) == Access()


def test_registering_the_same_address_twice_is_an_error():
    # Dve okna s touz adresou znamenaji, ze jedno z nich nepujde adresovat -
    # a to je tise ztraceny objekt, ne prepis.
    reg = registry()
    reg.add(PROVOZ)
    with pytest.raises(ValueError):
        reg.add(PROVOZ)


def test_asking_about_an_unknown_object_is_an_error():
    with pytest.raises(KeyError):
        registry().access_of(PROVOZ)


def test_removed_object_is_gone():
    reg = registry()
    reg.add(PROVOZ)
    reg.remove(PROVOZ)
    assert PROVOZ not in reg


# -- resolve: dedicnost objekt -> plocha -> vychozi hodnota instance --------


def test_window_with_its_own_acl_does_not_inherit():
    reg = registry()
    reg.add(PROVOZ, Access(see=Acl.of(USERS)))
    reg.add(MZDY, Access(see=Acl.of("group:ucetni")))
    assert reg.resolve(MZDY, Verb.SEE) == Acl.of("group:ucetni")


def test_window_without_acl_inherits_from_its_screen():
    reg = registry()
    reg.add(PROVOZ, Access(see=Acl.of("group:ucetni")))
    reg.add(MZDY)
    assert reg.resolve(MZDY, Verb.SEE) == Acl.of("group:ucetni")


def test_window_and_screen_without_acl_fall_to_the_instance_default():
    reg = registry(default=Acl.of(USERS))
    reg.add(PROVOZ)
    reg.add(MZDY)
    assert reg.resolve(MZDY, Verb.SEE) == Acl.of(USERS)


def test_unset_write_falls_back_to_see_on_the_same_object():
    reg = registry()
    reg.add(PROVOZ)
    reg.add(MZDY, Access(see=Acl.of(USERS)))
    assert reg.resolve(MZDY, Verb.WRITE) == Acl.of(USERS)


def test_instance_object_does_not_inherit_from_any_screen():
    # Auditni stopa je instance-wide; kdyby dedila od plochy, na ktere zrovna
    # lezi okno, publikuje ji prvni verejna plocha (chyba 3.4).
    reg = registry(default=Acl.empty())
    reg.add(PROVOZ, Access(see=Acl.of("group:public")))
    reg.add(LOG, Access(see=Acl.of("group:auditor")))
    assert reg.resolve(LOG, Verb.SEE) == Acl.of("group:auditor")


def test_instance_object_without_acl_takes_the_instance_default_not_a_screen():
    reg = registry(default=Acl.empty())
    reg.add(PROVOZ, Access(see=Acl.of("group:public")))
    reg.add(LOG)
    assert reg.resolve(LOG, Verb.SEE) == Acl.empty()


# -- bezpecne chovani u zmizeleho objektu ----------------------------------


def test_resolving_an_unknown_address_is_closed_not_open():
    # Zprava muze dorazit k doruceni pote, co okno zaniklo. "Neznam" nesmi
    # znamenat "vychozi", natoz "kdokoli" (chyba 3.5).
    assert registry(default=Acl.of(USERS)).resolve(MZDY, Verb.SEE) == Acl.empty()


def test_window_whose_screen_disappeared_is_closed():
    reg = registry(default=Acl.of(USERS))
    reg.add(PROVOZ)
    reg.add(MZDY)
    reg.remove(PROVOZ)
    assert reg.resolve(MZDY, Verb.SEE) == Acl.empty()


# -- krok navic je vlastnost objektu, dotaz na nej je vlastni otazka -------


def test_step_up_is_read_from_the_object_itself():
    reg = registry()
    reg.add(PROVOZ)
    reg.add(MZDY, Access(step_up=True))
    assert reg.step_up_at(MZDY) is True


def test_step_up_is_not_inherited_from_the_screen():
    # Krok navic se pta "jsi to fakt ty, ted" u KONKRETNIHO objektu. Dedit ho
    # by znamenalo, ze odemceni jednoho okna odemkne celou plochu.
    reg = registry()
    reg.add(PROVOZ, Access(step_up=True))
    reg.add(MZDY)
    assert reg.step_up_at(MZDY) is False


def test_step_up_at_an_unknown_address_is_required_not_waived():
    assert registry().step_up_at(MZDY) is True
