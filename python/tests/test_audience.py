"""Publikum zpravy.

Nejdulezitejsi zmena oproti viewBase2 (architektura-navrh.md par. 3): zprava
je od narozeni dvojice (obsah, publikum) a publikum se vyhodnocuje AZ PRI
DORUCENI. Testy nize drzi obe poloviny toho rozhodnuti - zvlast tu druhou,
protoze prave ta je duvod, proc `Audience` nema tvar se zmrazenymi principaly.
"""
import dataclasses

import pytest

from viewbase.core import audience as audience_module
from viewbase.core.access import Acl, Verb
from viewbase.core.addressing import Address
from viewbase.core.audience import And, Audience, Message, Ref, Session
from viewbase.core.identity import PUBLIC, USERS, Caller

MZDY = Address.window("provoz", "mzdy")
LOG = Address.instance("log")


def resolver(table):
    """Falesny registr prav: (adresa, sloveso) -> Acl."""

    def resolve(address, verb):
        return table.get((address, verb), Acl.empty())

    return resolve


# -- Ref: kdo smi videt / zasahovat do objektu ------------------------------


def test_ref_delivers_to_someone_the_acl_allows():
    resolve = resolver({(MZDY, Verb.READ): Acl.of("group:ucetni")})
    caller = Caller.for_user("hana", ["ucetni"])
    assert Ref(MZDY, Verb.READ).allows(caller, resolve)


def test_ref_does_not_deliver_to_someone_outside_the_acl():
    resolve = resolver({(MZDY, Verb.READ): Acl.of("group:ucetni")})
    assert not Ref(MZDY, Verb.READ).allows(Caller.for_user("petr"), resolve)


def test_ref_asks_about_the_verb_it_was_given():
    resolve = resolver(
        {
            (MZDY, Verb.READ): Acl.of(PUBLIC),
            (MZDY, Verb.WRITE): Acl.of("user:hana"),
        }
    )
    anonymous = Caller.anonymous()
    assert Ref(MZDY, Verb.READ).allows(anonymous, resolve)
    assert not Ref(MZDY, Verb.WRITE).allows(anonymous, resolve)


def test_ref_asks_about_the_address_it_was_given():
    resolve = resolver({(LOG, Verb.READ): Acl.of("group:auditor")})
    caller = Caller.for_user("hana", ["auditor"])
    assert Ref(LOG, Verb.READ).allows(caller, resolve)
    assert not Ref(MZDY, Verb.READ).allows(caller, resolve)


# -- pozdni vazba: tohle je duvod celeho tvaru -----------------------------


def test_a_message_made_before_rights_were_taken_away_is_not_delivered_after():
    # Kdyby se mnozina principalu zmrazila pri vzniku zpravy, delta vyrobena
    # vterinu pred odebranim prav by se dorucila i po nem. Proto je pozdni
    # vazba POVINNA, ne volitelna (D-03).
    table = {(MZDY, Verb.READ): Acl.of("user:hana")}
    resolve = resolver(table)
    message = Message(payload={"text": "mzdy za brezen"}, audience=Ref(MZDY, Verb.READ))
    caller = Caller.for_user("hana")

    assert message.audience.allows(caller, resolve)

    table[(MZDY, Verb.READ)] = Acl.empty()  # spravce prava odebral

    assert not message.audience.allows(caller, resolve)


def test_narrowing_the_log_acl_applies_to_records_already_queued():
    # Tyz pripad u logu: uzeni ACL musi platit i na zaznamy, ktere uz cekaji
    # ve fronte - jinak auditni stopa odtece pres to, co je "uz vyrobene".
    table = {(LOG, Verb.READ): Acl.of(PUBLIC)}
    resolve = resolver(table)
    record = Message(payload={"line": "login user:hana"}, audience=Ref(LOG, Verb.READ))

    assert record.audience.allows(Caller.anonymous(), resolve)

    table[(LOG, Verb.READ)] = Acl.of("group:auditor")

    assert not record.audience.allows(Caller.anonymous(), resolve)


def test_widening_an_acl_also_applies_immediately():
    table = {(MZDY, Verb.READ): Acl.empty()}
    resolve = resolver(table)
    reference = Ref(MZDY, Verb.READ)
    caller = Caller.for_user("hana")

    assert not reference.allows(caller, resolve)

    table[(MZDY, Verb.READ)] = Acl.of(USERS)

    assert reference.allows(caller, resolve)


# -- Session: adresna odpoved ----------------------------------------------


def test_session_audience_reaches_that_one_session():
    caller = Caller.for_user("hana", session="s1")
    assert Session("s1").allows(caller, resolver({}))


def test_session_audience_does_not_reach_another_session():
    caller = Caller.for_user("hana", session="s2")
    assert not Session("s1").allows(caller, resolver({}))


def test_session_audience_does_not_reach_a_caller_without_a_session():
    # Programovy vstup zadnou relaci nema; adresna odpoved mu nepatri.
    assert not Session("s1").allows(Caller.anonymous(), resolver({}))


def test_session_audience_does_not_consult_the_acl_at_all():
    # Adresna odpoved je odpoved tomu, kdo se ptal - proto nesmi zaviset na
    # tom, jestli resolver o adrese vubec neco vi.
    def exploding_resolve(address, verb):  # pragma: no cover - nesmi se zavolat
        raise AssertionError("Session se nema ptat na prava objektu")

    caller = Caller.for_user("hana", session="s1")
    assert Session("s1").allows(caller, exploding_resolve)


# -- And: obojí zaroven ----------------------------------------------------


def test_and_needs_both_parts():
    resolve = resolver({(MZDY, Verb.READ): Acl.of("user:hana")})
    caller = Caller.for_user("hana", session="s1")
    assert And(Session("s1"), Ref(MZDY, Verb.READ)).allows(caller, resolve)


def test_and_denies_when_the_acl_half_fails():
    # "Odpoved mne, ale jen kdyz na to mam": spravna relace, chybejici pravo.
    resolve = resolver({(MZDY, Verb.READ): Acl.empty()})
    caller = Caller.for_user("hana", session="s1")
    assert not And(Session("s1"), Ref(MZDY, Verb.READ)).allows(caller, resolve)


def test_and_denies_when_the_session_half_fails():
    resolve = resolver({(MZDY, Verb.READ): Acl.of("user:hana")})
    caller = Caller.for_user("hana", session="s2")
    assert not And(Session("s1"), Ref(MZDY, Verb.READ)).allows(caller, resolve)


# -- zprava bez publika nesmi jit vyrobit ----------------------------------


def test_message_without_an_audience_cannot_be_built():
    # Princip 1: nic neopusti proces bez uvedeni publika.
    with pytest.raises(TypeError):
        Message(payload={"text": "ahoj"})  # type: ignore[call-arg]


def test_message_carries_its_audience():
    message = Message(payload={"text": "ahoj"}, audience=Session("s1"))
    assert message.audience == Session("s1")


def test_message_is_a_value():
    assert Message(payload={"a": 1}, audience=Session("s1")) == Message(
        payload={"a": 1}, audience=Session("s1")
    )


# -- invariant nad registrem tvaru, ne nad jednotlivosti -------------------
# Princip 5: "pro kazdy tvar publika plati, ze..." chyti i ten ctvrty, ktery
# nekdo dopise pristi rok.


def _audience_shapes():
    return [
        value
        for value in vars(audience_module).values()
        if isinstance(value, type)
        and issubclass(value, Audience)
        and value is not Audience
    ]


def test_the_only_audience_shapes_are_ref_session_and_and():
    assert {shape.__name__ for shape in _audience_shapes()} == {"Ref", "Session", "And"}


def test_no_audience_shape_can_carry_a_frozen_set_of_principals():
    # Kdyby ten tvar existoval, sel by pouzit omylem - a publikum by se
    # zmrazilo. Neexistence je zaruka, ne doporuceni.
    for shape in _audience_shapes():
        fields = {f.name for f in dataclasses.fields(shape)}
        assert "principals" not in fields, shape.__name__
        assert "acl" not in fields, shape.__name__


def test_every_audience_shape_decides_through_allows():
    for shape in _audience_shapes():
        assert callable(getattr(shape, "allows", None)), shape.__name__
