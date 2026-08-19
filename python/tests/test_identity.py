"""Principalove: proti cemu se vyhodnocuje ACL.

Model prebrany z viewBase2 beze zmeny (co-prevzit-z-viewbase2.md par. 1) -
meni se jen jazyk identifikatoru a to, ze modul nezna nic jineho."""
import pytest

from viewbase.core.identity import (
    ADMINISTRATOR,
    PUBLIC,
    USERS,
    principal,
    user_principals,
)


def test_bare_name_becomes_a_group():
    # `acl.add("ucetni")` se pise rucne; tise selhat kvuli chybejicimu prefixu
    # by znamenalo tise otevrene okno.
    assert principal("ucetni") == "group:ucetni"


def test_explicit_user_prefix_is_kept():
    assert principal("user:hana") == "user:hana"


def test_explicit_group_prefix_is_kept():
    assert principal("group:ucetni") == "group:ucetni"


def test_surrounding_whitespace_is_ignored():
    assert principal("  ucetni  ") == "group:ucetni"


@pytest.mark.parametrize("bad", ["", "   ", "user:", "group:", "user:a:b"])
def test_unusable_principal_is_rejected(bad):
    with pytest.raises(ValueError):
        principal(bad)


def test_anonymous_session_sees_only_what_is_public():
    assert user_principals(None) == {PUBLIC}


def test_signed_in_person_gets_their_own_user_principal():
    assert "user:hana" in user_principals("hana")


def test_signed_in_person_gets_a_group_named_after_them():
    # Vlastni skupina umoznuje adresovat cloveka i tam, kde se ceka skupina.
    assert "group:hana" in user_principals("hana")


def test_signed_in_person_is_always_in_users():
    # Bez toho by vychozi hodnota instance `group:users` neznamenala
    # "kdokoli prihlaseny", ale "kdo to ma nahodou vypsane v zaznamu".
    assert USERS in user_principals("hana")


def test_signed_in_person_is_still_public():
    assert PUBLIC in user_principals("hana")


def test_groups_from_the_directory_are_normalised():
    assert "group:ucetni" in user_principals("hana", ["ucetni"])


def test_nobody_becomes_administrator_by_signing_in():
    # Sprava se dostane jen z evidence, nikdy jako vedlejsi ucinek prihlaseni.
    assert ADMINISTRATOR not in user_principals("hana", ["ucetni"])


def test_administrator_comes_only_from_the_directory():
    assert ADMINISTRATOR in user_principals("hana", ["administrator"])


def test_principals_of_two_people_do_not_overlap_beyond_the_shared_groups():
    hana = user_principals("hana")
    petr = user_principals("petr")
    assert hana & petr == {PUBLIC, USERS}


# -- Caller: jeden typ volajiciho pro relaci i programovy vstup -------------
# Chyba 3.3 z viewBase2: REST nemel identitu zadnou, takze `curl` bez niceho
# spustil autorsky handler. Dve vetve ve vynucovacim kodu jsou ta chyba.


def test_anonymous_caller_has_only_public():
    from viewbase.core.identity import Caller

    assert Caller.anonymous().principals == {PUBLIC}


def test_anonymous_caller_has_no_session():
    from viewbase.core.identity import Caller

    assert Caller.anonymous().session is None


def test_caller_for_a_signed_in_person_carries_their_principals():
    from viewbase.core.identity import Caller

    caller = Caller.for_user("hana", groups=["ucetni"], session="s1")
    assert "user:hana" in caller.principals
    assert "group:ucetni" in caller.principals


def test_programmatic_input_without_a_token_is_public_not_privileged():
    from viewbase.core.identity import Caller, Origin

    caller = Caller.anonymous(origin=Origin.REST)
    assert caller.principals == {PUBLIC}
    assert caller.origin is Origin.REST


def test_library_code_is_its_own_origin():
    # D-10: uzivatelsky kod knihovny NEPROCHAZI autorizaci, ale publikum
    # uvest musi. Aby to slo vynutit, musi jit poznat.
    from viewbase.core.identity import Caller, Origin

    assert Caller.internal().origin is Origin.INTERNAL


def test_caller_is_a_value():
    from viewbase.core.identity import Caller

    assert Caller.anonymous() == Caller.anonymous()


def test_caller_principals_cannot_be_extended_after_the_fact():
    # Principaly dosazuje vzdycky server; kdyby sly pripsat, poslal by si je
    # klient sam a byl by z toho spravce (par. 5).
    from viewbase.core.identity import Caller

    with pytest.raises((AttributeError, TypeError)):
        Caller.anonymous().principals.add(ADMINISTRATOR)  # type: ignore[attr-defined]
