"""Registr udalosti a JEDINE vynucovaci misto.

Sem patri ctyri konkretni chyby z viewBase2, ktere se nesmi vratit:

  3.1  autorizace se psala v kazdem handleru zvlast a pet z devitI udalosti
       ji nemelo -> `needs` je POVINNY parametr registrace,
  3.2  `Needs.NONE` obchazelo branu plochy -> hodnota, ktera vypina kontrolu,
       v enumu neni,
  3.9  zamek okna byl globalni vypinac na objektu -> krok navic patri DVOJICI
       (relace, objekt),
  3.7  tri ruzne priciny se hlasily stejnou hlaskou -> rozhodnuti vraci DUVOD.

A hlavne: invariant se testuje NAD REGISTREM, ne nad jednotlivosti (princip 5).
viewBase2 mel skoro 500 testu a diru nechytily, protoze kazdy overoval jednu
funkci.
"""
import pytest

from viewbase.core.access import Access, Acl, Verb, allowed
from viewbase.core.addressing import Address
from viewbase.core.identity import ADMINISTRATOR, PUBLIC, USERS, Caller
from viewbase.runtime.events import (
    Decision,
    EventRegistry,
    Guard,
    Needs,
    StepUp,
    Verdict,
)
from viewbase.runtime.registry import ObjectRegistry
from viewbase.runtime.sessions import Grants

PROVOZ = Address.screen("provoz")
MZDY = Address.window("provoz", "mzdy")
TAJNE = Address.window("provoz", "tajne")


def noop(*args, **kwargs):  # pragma: no cover - handler se v testech nevola
    return None


ROOT = Address.instance_root()


def guard_over(objects, registry=None, grants=None):
    registry = registry if registry is not None else EventRegistry()
    return Guard(
        events=registry,
        objects=objects,
        grants=grants if grants is not None else Grants(),
    )


# ===========================================================================
# Registrace: `needs` je povinne (chyba 3.1)
# ===========================================================================


def test_event_cannot_be_registered_without_needs():
    # Kdyz se pozadavek nedeklaruje, psal by se v kazdem handleru zvlast -
    # a pet z devitI by ho nemelo.
    with pytest.raises(TypeError):
        EventRegistry().register("menu_select", noop)  # type: ignore[call-arg]


def test_registered_event_is_found():
    registry = EventRegistry()
    registry.register("menu_select", noop, needs=Needs.SCREEN)
    assert registry.registration("menu_select").needs is Needs.SCREEN


def test_registering_the_same_event_twice_is_an_error():
    registry = EventRegistry()
    registry.register("menu_select", noop, needs=Needs.SCREEN)
    with pytest.raises(ValueError):
        registry.register("menu_select", noop, needs=Needs.WRITE)


def test_step_up_is_required_unless_it_is_said_otherwise():
    registry = EventRegistry()
    registry.register("shell_input", noop, needs=Needs.WRITE)
    assert registry.registration("shell_input").step_up is StepUp.REQUIRED


# ===========================================================================
# Invarianty nad registrem, ne nad jednotlivosti (princip 5, B-06)
# ===========================================================================


def full_registry() -> EventRegistry:
    """Registr se vsemi tvary registrace, jake model umi."""
    registry = EventRegistry()
    registry.register("instance_shutdown", noop, needs=Needs.INSTANCE)
    registry.register("menu_select", noop, needs=Needs.SCREEN)
    registry.register("shell_new", noop, needs=Needs.SCREEN)
    registry.register("window_focus", noop, needs=Needs.READ)
    registry.register("shell_input", noop, needs=Needs.WRITE)
    registry.register("hello_submit", noop, needs=Needs.WRITE)
    registry.register("window_unlock", noop, needs=Needs.READ, step_up=StepUp.EXEMPT)
    return registry


def test_every_registered_event_declares_what_it_needs():
    for registration in full_registry():
        assert isinstance(registration.needs, Needs), registration.event


def test_no_needs_value_switches_the_check_off():
    # Chyba 3.2: `NONE` ve vyznamu "nekontroluj nic". Hodnota, ktera vypina
    # kontrolu, nema v enumu co delat - proto se testuje SEZNAM hodnot.
    assert {member.name for member in Needs} == {"INSTANCE", "SCREEN", "READ", "WRITE"}


def test_only_window_unlock_may_skip_the_step_up():
    # Vyjimka je deklarovana, ne schovana v komentari - proto ji jde otestovat.
    exempt = {r.event for r in full_registry() if r.step_up is StepUp.EXEMPT}
    assert exempt == {"window_unlock"}


def test_anonymous_on_a_hidden_screen_reaches_no_handler_at_all():
    """Tenhle jediny test pokryje i tu desatou udalost, kterou nikdo nenapsal.

    Presne tohle ve viewBase2 chybelo: `shell_new`, `menu_select` i kazda
    uzivatelska udalost sly zavolat na plochu, kterou relace vubec nevidela.
    """
    objects = ObjectRegistry(default_access=Acl.empty())
    objects.add(PROVOZ, Access(read=Acl.of("group:ucetni"), write=Acl.of("group:ucetni")))
    objects.add(MZDY)
    registry = full_registry()
    guard = guard_over(objects, registry)
    anonymous = Caller.anonymous(remote="10.0.0.9")

    for registration in registry:
        target = PROVOZ if registration.needs is Needs.SCREEN else MZDY
        decision = guard.check(anonymous, registration.event, target)
        assert not decision, f"{registration.event} pustil anonyma na skrytou plochu"


def test_the_invariant_test_would_notice_a_hole():
    # Kontrola samotneho invariantu: kdyz se plocha otevre verejnosti,
    # nektera udalost projit MUSI - jinak by test vyse prochazel i nad
    # rozbitym vynucovanim.
    objects = ObjectRegistry(default_access=Acl.of(PUBLIC))
    objects.add(PROVOZ, Access(read=Acl.of(PUBLIC), write=Acl.of(PUBLIC)))
    objects.add(MZDY, Access(read=Acl.of(PUBLIC), write=Acl.of(PUBLIC)))
    guard = guard_over(objects, full_registry())
    anonymous = Caller.anonymous()

    passed = [
        r.event
        for r in full_registry()
        if guard.check(anonymous, r.event, PROVOZ if r.needs is Needs.SCREEN else MZDY)
    ]
    assert passed, "na verejne plose neprosla ani jedna udalost - test nic netestuje"


# ===========================================================================
# Brana plochy plati vzdycky a kontroluje se ZVLAST (D-15, F-09)
# ===========================================================================


def test_screen_event_needs_write_on_the_screen():
    objects = ObjectRegistry(default_access=Acl.empty())
    objects.add(PROVOZ, Access(read=Acl.of(USERS), write=Acl.of("group:ucetni")))
    registry = EventRegistry()
    registry.register("menu_select", noop, needs=Needs.SCREEN)
    guard = guard_over(objects, registry)

    assert guard.check(Caller.for_user("hana", ["ucetni"]), "menu_select", PROVOZ)
    assert not guard.check(Caller.for_user("petr"), "menu_select", PROVOZ)


def test_screen_gate_applies_even_when_the_window_would_allow_it():
    objects = ObjectRegistry(default_access=Acl.empty())
    objects.add(PROVOZ, Access(read=Acl.of("group:ucetni")))
    objects.add(MZDY, Access(read=Acl.of(USERS), write=Acl.of(USERS)))
    registry = EventRegistry()
    registry.register("hello_submit", noop, needs=Needs.WRITE)
    guard = guard_over(objects, registry)

    decision = guard.check(Caller.for_user("petr"), "hello_submit", MZDY)
    assert decision.verdict is Verdict.SCREEN_CLOSED


def test_user_cannot_write_into_a_window_on_a_screen_reserved_for_the_administrator():
    """B-10 / F-09: past, na ktere by sloucene kontroly selhaly.

    Okno ma read=[users] a NEnastavene write, takze jeho efektivni ACL pro
    zapis padne na jeho vlastni read, tedy [users]. Kdyby se kontrolovalo jen
    okno, uzivatel by prosel - pritom na plose smi zasahovat jen spravce.
    """
    objects = ObjectRegistry(default_access=Acl.empty())
    objects.add(PROVOZ, Access(read=Acl.of(USERS), write=Acl.of(ADMINISTRATOR)))
    objects.add(MZDY, Access(read=Acl.of(USERS)))
    registry = EventRegistry()
    registry.register("hello_submit", noop, needs=Needs.WRITE)
    guard = guard_over(objects, registry)

    # Predpoklad pasti: efektivni ACL okna pro zapis uzivatele opravdu pousti.
    assert USERS in objects.resolve(MZDY, Verb.WRITE).principals

    decision = guard.check(Caller.for_user("hana"), "hello_submit", MZDY)
    assert decision.verdict is Verdict.SCREEN_CLOSED


def test_read_event_needs_read_on_the_screen_and_on_the_window():
    objects = ObjectRegistry(default_access=Acl.empty())
    objects.add(PROVOZ, Access(read=Acl.of(USERS)))
    objects.add(MZDY, Access(read=Acl.of("group:ucetni")))
    registry = EventRegistry()
    registry.register("window_focus", noop, needs=Needs.READ)
    guard = guard_over(objects, registry)

    assert guard.check(Caller.for_user("hana", ["ucetni"]), "window_focus", MZDY)
    assert guard.check(Caller.for_user("petr"), "window_focus", MZDY).verdict is Verdict.NOT_IN_ACL


def test_write_event_needs_read_on_the_window_too():
    # Zasahovat do neceho, co clovek nevidi, nema smysl - a rozdil mezi
    # "nevidim" a "nesmim psat" je duvod, ktery patri do auditu.
    objects = ObjectRegistry(default_access=Acl.empty())
    objects.add(PROVOZ, Access(read=Acl.of(USERS), write=Acl.of(USERS)))
    objects.add(MZDY, Access(read=Acl.of("group:ucetni"), write=Acl.of(USERS)))
    registry = EventRegistry()
    registry.register("hello_submit", noop, needs=Needs.WRITE)
    guard = guard_over(objects, registry)

    assert not guard.check(Caller.for_user("petr"), "hello_submit", MZDY)


# ===========================================================================
# Kazde rozhodnuti vraci DUVOD (par. 8, chyba 3.7)
# ===========================================================================


def test_unknown_event_is_its_own_reason():
    guard = guard_over(ObjectRegistry(default_access=Acl.empty()))
    assert guard.check(Caller.anonymous(), "neznama", PROVOZ).verdict is Verdict.UNKNOWN_EVENT


def test_three_different_causes_report_three_different_reasons():
    # Chyba 3.7: spatny kod, uz pouzity kod a zahlceni pokusy se hlasily
    # stejnou hlaskou a stalo to hodinu hledani v provozu.
    objects = ObjectRegistry(default_access=Acl.empty())
    objects.add(PROVOZ, Access(read=Acl.of(USERS), write=Acl.of(USERS)))
    objects.add(MZDY, Access(read=Acl.of(USERS), write=Acl.of(USERS), step_up=True))
    registry = EventRegistry()
    registry.register("shell_input", noop, needs=Needs.WRITE)
    guard = guard_over(objects, registry)

    reasons = {
        guard.check(Caller.anonymous(), "shell_input", MZDY).verdict,
        guard.check(Caller.for_user("hana"), "shell_input", MZDY).verdict,
        guard.check(Caller.for_user("hana"), "neznama", MZDY).verdict,
    }
    assert len(reasons) == 3


def test_decision_is_falsy_unless_it_is_ok():
    assert bool(Decision(Verdict.OK)) is True
    assert bool(Decision(Verdict.NOT_IN_ACL)) is False


# ===========================================================================
# Krok navic patri DVOJICI (relace, objekt) - chyba 3.9
# ===========================================================================


def secured_setup():
    objects = ObjectRegistry(default_access=Acl.empty())
    objects.add(PROVOZ, Access(read=Acl.of(USERS), write=Acl.of(USERS)))
    objects.add(MZDY, Access(read=Acl.of(USERS), write=Acl.of(USERS), step_up=True))
    objects.add(TAJNE, Access(read=Acl.of(USERS), write=Acl.of(USERS), step_up=True))
    registry = EventRegistry()
    registry.register("shell_input", noop, needs=Needs.WRITE)
    registry.register("window_unlock", noop, needs=Needs.READ, step_up=StepUp.EXEMPT)
    return objects, registry


def test_secured_window_without_a_grant_says_so():
    objects, registry = secured_setup()
    guard = guard_over(objects, registry)
    caller = Caller.for_user("hana", session="s1")
    assert guard.check(caller, "shell_input", MZDY).verdict is Verdict.NO_GRANT


def test_secured_window_with_a_grant_lets_the_holder_in():
    objects, registry = secured_setup()
    grants = Grants()
    grants.hold("s1", MZDY)
    guard = guard_over(objects, registry, grants)
    assert guard.check(Caller.for_user("hana", session="s1"), "shell_input", MZDY)


def test_a_grant_on_one_window_does_not_unlock_another():
    # Chyba 3.9: zamek okna byl globalni vypinac na objektu, takze odemceni
    # jednim divakem odhalilo obsah vsem.
    objects, registry = secured_setup()
    grants = Grants()
    grants.hold("s1", MZDY)
    guard = guard_over(objects, registry, grants)
    assert not guard.check(Caller.for_user("hana", session="s1"), "shell_input", TAJNE)


def test_a_grant_of_one_session_does_not_help_another():
    objects, registry = secured_setup()
    grants = Grants()
    grants.hold("s1", MZDY)
    guard = guard_over(objects, registry, grants)
    assert not guard.check(Caller.for_user("hana", session="s2"), "shell_input", MZDY)


def test_the_unlocking_event_itself_does_not_need_a_grant():
    # Jinak by se okno nedalo odemknout nikdy: krok navic se ziskava prave ji.
    objects, registry = secured_setup()
    guard = guard_over(objects, registry)
    assert guard.check(Caller.for_user("hana", session="s1"), "window_unlock", MZDY)


def test_the_unlocking_event_still_passes_through_the_screen_gate():
    # EXEMPT vypina krok navic, ne branu plochy.
    objects = ObjectRegistry(default_access=Acl.empty())
    objects.add(PROVOZ, Access(read=Acl.of("group:ucetni")))
    objects.add(MZDY, Access(read=Acl.of(USERS), step_up=True))
    registry = EventRegistry()
    registry.register("window_unlock", noop, needs=Needs.READ, step_up=StepUp.EXEMPT)
    guard = guard_over(objects, registry)
    assert not guard.check(Caller.for_user("petr", session="s1"), "window_unlock", MZDY)


def test_administrator_passes_the_acl_but_still_needs_the_step_up():
    # Obdoba roota plati pro PRAVA. Krok navic se pta na neco jineho -
    # "jsi to fakt ty, ted" - a tim neni dotceny.
    objects, registry = secured_setup()
    guard = guard_over(objects, registry)
    admin = Caller.for_user("spravce", ["administrator"], session="s1")
    assert guard.check(admin, "shell_input", MZDY).verdict is Verdict.NO_GRANT


def test_a_caller_without_a_session_can_never_hold_a_grant():
    # Programovy vstup (REST s tokenem) muze mit principaly, ktere ACL projdou -
    # ale relaci nema, takze krok navic nema kde vzniknout. Musi to skoncit na
    # NO_GRANT, ne na tom, ze by ho pustila nejaka jina vetev.
    from viewbase.core.identity import Origin

    objects, registry = secured_setup()
    grants = Grants()
    grants.hold("s1", MZDY)  # jina relace krok navic ma; tomuhle to nepomuze
    guard = guard_over(objects, registry, grants)
    tokenless = Caller.for_user("hana", session=None, origin=Origin.REST)

    assert allowed(tokenless.principals, objects.resolve(MZDY, Verb.WRITE))
    assert guard.check(tokenless, "shell_input", MZDY).verdict is Verdict.NO_GRANT


def test_revoking_a_session_drops_its_grants():
    objects, registry = secured_setup()
    grants = Grants()
    grants.hold("s1", MZDY)
    grants.revoke_session("s1")
    guard = guard_over(objects, registry, grants)
    assert not guard.check(Caller.for_user("hana", session="s1"), "shell_input", MZDY)


# ===========================================================================
# Udalosti instance
# ===========================================================================


def instance_setup(root_access=Access()):
    objects = ObjectRegistry(default_access=Acl.of(USERS))
    objects.add(ROOT, root_access)
    registry = EventRegistry()
    registry.register("instance_shutdown", noop, needs=Needs.INSTANCE)
    return objects, registry


def test_instance_event_is_closed_to_an_ordinary_user():
    objects, registry = instance_setup()
    guard = guard_over(objects, registry)
    assert (
        guard.check(Caller.for_user("hana"), "instance_shutdown").verdict
        is Verdict.INSTANCE_CLOSED
    )


def test_instance_event_lets_the_administrator_through():
    objects, registry = instance_setup()
    guard = guard_over(objects, registry)
    assert guard.check(Caller.for_user("spravce", ["administrator"]), "instance_shutdown")


def test_instance_event_can_be_opened_to_a_named_group():
    objects, registry = instance_setup(Access(write=Acl.of("group:operator")))
    guard = guard_over(objects, registry)
    assert guard.check(Caller.for_user("hana", ["operator"]), "instance_shutdown")


def test_instance_event_does_not_need_a_screen():
    # Pomlcka v tabulce par. 5 znamena "netyka se", ne "nekontroluje se":
    # udalost se neptá na plochu, ale ACL instance projit MUSI (D-17).
    objects, registry = instance_setup(Access(write=Acl.of("group:operator")))
    guard = guard_over(objects, registry)
    assert len(objects) == 1  # zadna plocha v registru neni
    assert guard.check(Caller.for_user("hana", ["operator"]), "instance_shutdown")


def test_instance_event_is_evaluated_through_the_same_resolve_as_everything_else():
    # D-17: instance je objekt jako kazdy jiny. Co ma privilegovanou zkratku,
    # to se prestane testovat jako vsechno ostatni (chyba 3.4).
    objects, registry = instance_setup(Access(write=Acl.of("group:operator")))
    guard = guard_over(objects, registry)
    assert objects.resolve(ROOT, Verb.WRITE) == Acl.of("group:operator")
    assert not hasattr(guard, "instance_access")


def test_instance_event_on_an_instance_that_registered_no_root_is_closed():
    objects = ObjectRegistry(default_access=Acl.of(USERS))
    registry = EventRegistry()
    registry.register("instance_shutdown", noop, needs=Needs.INSTANCE)
    guard = guard_over(objects, registry)
    assert not guard.check(Caller.for_user("hana"), "instance_shutdown")


# ===========================================================================
# Adresa musi sedet k tomu, co udalost zada
# ===========================================================================


def test_window_event_without_a_window_address_is_refused():
    objects = ObjectRegistry(default_access=Acl.of(USERS))
    objects.add(PROVOZ, Access(read=Acl.of(USERS), write=Acl.of(USERS)))
    registry = EventRegistry()
    registry.register("hello_submit", noop, needs=Needs.WRITE)
    guard = guard_over(objects, registry)
    assert guard.check(Caller.for_user("hana"), "hello_submit", PROVOZ).verdict is Verdict.WRONG_TARGET


def test_window_event_without_any_address_is_refused():
    objects = ObjectRegistry(default_access=Acl.of(USERS))
    registry = EventRegistry()
    registry.register("hello_submit", noop, needs=Needs.WRITE)
    guard = guard_over(objects, registry)
    assert guard.check(Caller.for_user("hana"), "hello_submit").verdict is Verdict.WRONG_TARGET
