"""Model pristupu: ACL jako mnozina povolenych, dve slovesa, dedicnost.

Prebrano z viewBase2 (nejzdravejsi kus projektu), zmeneno jen to, co rika
architektura-navrh.md par. 4: Acl je NEMENNA HODNOTA a krok navic bydli
v `access`, ne vedle nej."""
import pytest

from viewbase.core.access import Access, Acl, Verb, allowed, effective_acl
from viewbase.core.identity import ADMINISTRATOR, PUBLIC, USERS, user_principals


# -- allowed: cela autorizace je jedna funkce nad mnozinami -----------------


def test_principal_in_the_acl_is_allowed():
    assert allowed({"user:hana"}, Acl.of("user:hana"))


def test_principal_outside_the_acl_is_not():
    assert not allowed({"user:petr"}, Acl.of("user:hana"))


def test_group_membership_is_enough():
    assert allowed(user_principals("hana", ["ucetni"]), Acl.of("group:ucetni"))


def test_empty_acl_lets_nobody_in():
    # Zadne "deny" model nema, takze prazdna mnozina je zavreno - a to je
    # zaroven bezpecny vychozi stav.
    assert not allowed(user_principals("hana"), Acl.empty())


def test_administrator_passes_even_through_an_empty_acl():
    # Obdoba roota, vedome: instance musi mit nekoho, kdo spatne nastavene
    # ACL opravi zevnitr.
    assert allowed({ADMINISTRATOR}, Acl.empty())


def test_anonymous_reaches_only_what_is_public():
    assert allowed(user_principals(None), Acl.of(PUBLIC))
    assert not allowed(user_principals(None), Acl.of(USERS))


# -- Acl je hodnota, ne objekt se stavem -----------------------------------


def test_adding_a_principal_returns_a_new_acl():
    original = Acl.of("user:hana")
    assert original.with_added("user:petr") == Acl.of("user:hana", "user:petr")


def test_adding_a_principal_leaves_the_original_untouched():
    # Par. 4b: zmena vede pres instanci, ktera k ni pripoji kdo/kdy/proc.
    # Kdyby sla Acl menit na miste, auditni stopa by o zmene nevedela.
    original = Acl.of("user:hana")
    original.with_added("user:petr")
    assert original == Acl.of("user:hana")


def test_removing_a_principal_returns_a_new_acl():
    assert Acl.of("user:hana", PUBLIC).without(PUBLIC) == Acl.of("user:hana")


def test_removing_a_principal_that_is_not_there_is_not_an_error():
    assert Acl.of("user:hana").without(PUBLIC) == Acl.of("user:hana")


def test_acl_normalises_bare_names_to_groups():
    assert Acl.of("ucetni") == Acl.of("group:ucetni")


def test_acl_is_hashable_so_it_can_be_a_value_in_a_snapshot():
    assert {Acl.of("user:hana"): 1}[Acl.of("user:hana")] == 1


def test_acl_cannot_be_mutated_through_its_members():
    acl = Acl.of("user:hana")
    with pytest.raises((AttributeError, TypeError)):
        acl.principals.add("user:petr")  # type: ignore[attr-defined]


# -- dve slovesa ------------------------------------------------------------


def test_write_falls_back_to_read_when_it_is_not_set():
    # Nenastavene `write` = totez co `read`; jinak by kazde okno potrebovalo
    # obe ACL a vetsina by je mela stejne.
    access = Access(read=Acl.of("user:hana"))
    assert access.for_verb(Verb.WRITE) == Acl.of("user:hana")


def test_write_set_separately_is_independent_of_read():
    # Verejne log okno, ktere smi vyprazdnit jen spravce.
    access = Access(read=Acl.of(PUBLIC), write=Acl.of("user:hana"))
    assert access.for_verb(Verb.READ) == Acl.of(PUBLIC)
    assert access.for_verb(Verb.WRITE) == Acl.of("user:hana")


def test_unset_read_means_inherit_not_open():
    assert Access().for_verb(Verb.READ) is None


# -- dedicnost objekt -> plocha -> vychozi hodnota instance -----------------


def test_object_with_its_own_acl_does_not_inherit():
    chain = [Access(read=Acl.of("user:hana")), Access(read=Acl.of(PUBLIC))]
    assert effective_acl(Verb.READ, chain, default=Acl.of(USERS)) == Acl.of("user:hana")


def test_object_without_acl_takes_the_one_from_its_screen():
    chain = [Access(), Access(read=Acl.of("group:ucetni"))]
    assert effective_acl(Verb.READ, chain, default=Acl.of(USERS)) == Acl.of("group:ucetni")


def test_object_and_screen_without_acl_fall_to_the_instance_default():
    chain = [Access(), Access()]
    assert effective_acl(Verb.READ, chain, default=Acl.of(USERS)) == Acl.of(USERS)


def test_inheritance_is_per_verb():
    # Okno zdedi `read` od plochy, ale `write` ma vlastni. Efektivni read je
    # po D-70 SJEDNOCENI, takze hana je v nem taky - smi menit, tedy smi videt.
    chain = [Access(write=Acl.of("user:hana")), Access(read=Acl.of(PUBLIC))]
    assert effective_acl(Verb.READ, chain, default=Acl.empty()) == Acl.of(
        PUBLIC, "user:hana"
    )
    assert effective_acl(Verb.WRITE, chain, default=Acl.empty()) == Acl.of("user:hana")


def test_empty_chain_falls_to_the_default():
    assert effective_acl(Verb.READ, [], default=Acl.of(USERS)) == Acl.of(USERS)


def test_an_explicitly_empty_acl_is_not_the_same_as_unset():
    # "Nikdo" je rozhodnuti a nesmi se prepsat dedicnosti na "kdokoli".
    chain = [Access(read=Acl.empty()), Access(read=Acl.of(PUBLIC))]
    assert effective_acl(Verb.READ, chain, default=Acl.of(USERS)) == Acl.empty()


# -- krok navic je ortogonalni ---------------------------------------------


def test_step_up_is_off_by_default():
    assert Access().step_up is False


def test_step_up_lives_in_access_not_beside_it():
    # Par. 4a: viewBase2 mel `private=True` jako boolean na okne, zatimco
    # pristup byl objekt. Oboji je politika a patri na jedno misto.
    assert Access(read=Acl.of(PUBLIC), step_up=True).step_up is True


def test_step_up_does_not_change_who_is_in_the_acl():
    # Krok navic se pta "jsi to fakt ty, ted" - neni to dalsi ACL.
    access = Access(read=Acl.of("user:hana"), step_up=True)
    assert access.for_verb(Verb.READ) == Acl.of("user:hana")


def test_access_is_a_value():
    assert Access(read=Acl.of(PUBLIC), step_up=True) == Access(
        read=Acl.of(PUBLIC), step_up=True
    )


# ===========================================================================
# Sipka ukazuje jednim smerem: manage => write => read (D-70)
#
# Kdo ma manage, ma i write; kdo ma write, ma i read. OPACNE NE - write
# nikoho nepovysuje na manage. Obe implikace zaviraji tutez chybu o patro
# jinde: kdo smi menit ACL, si write udeli jednim krokem (odepirat ho je
# divadlo), a editovat neco, na co se neda divat, nedava smysl.
# ===========================================================================


def test_write_implies_read():
    # Efektivni read je sjednoceni: kdo smi menit, smi i videt.
    access = Access(read=Acl.of("group:ctenari"), write=Acl.of("group:pisari"))
    assert effective_acl(Verb.READ, [access], default=Acl.empty()) == Acl.of(
        "group:ctenari", "group:pisari"
    )


def test_read_does_not_imply_write():
    # Sipka jednim smerem. Kdyby platila i opacne, byla by slovesa jedno.
    access = Access(read=Acl.of("group:ctenari"), write=Acl.of("group:pisari"))
    assert effective_acl(Verb.WRITE, [access], default=Acl.empty()) == Acl.of(
        "group:pisari"
    )


def test_someone_who_may_only_write_may_also_read():
    access = Access(read=Acl.empty(), write=Acl.of("user:hana"))
    assert allowed({"user:hana"}, effective_acl(Verb.READ, [access], default=Acl.empty()))


def test_write_is_always_a_subset_of_effective_read():
    """Invariant, ne priklad: pro KAZDOU dvojici ACL musi platit
    write podmnozina read_effective."""
    kombinace = [
        (Acl.empty(), Acl.empty()),
        (Acl.of("a"), Acl.empty()),
        (Acl.empty(), Acl.of("b")),
        (Acl.of("a"), Acl.of("b")),
        (Acl.of("a", "b"), Acl.of("b")),
        (Acl.of("a"), Acl.of("a", "b")),
    ]
    for read, write in kombinace:
        access = Access(read=read, write=write)
        eff_read = effective_acl(Verb.READ, [access], default=Acl.empty())
        eff_write = effective_acl(Verb.WRITE, [access], default=Acl.empty())
        assert eff_write.principals <= eff_read.principals, (read, write)


def test_the_implication_survives_inheritance():
    # Okno dedi read od plochy a ma vlastni write - i tak plati sipka.
    chain = [Access(write=Acl.of("user:hana")), Access(read=Acl.of(USERS))]
    eff_read = effective_acl(Verb.READ, chain, default=Acl.empty())
    assert "user:hana" in eff_read
    assert USERS in eff_read
