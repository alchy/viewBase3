"""Jedno povinne autentizacni API pro oba kanaly apky (D-47, D-48).

Autor apky nevymysli autentizaci - to je misto, kde se to obvykle pokazi.
Volajici predlozi token, apka ho overi introspekci a dostane, kdo to je.

Tri veci, ktere se tim ziskaji:

  * klic k apce prestane byt mocny jako vsechna jeji data,
  * davkova uloha bezi JAKO NEKDO - tyz subjekt v okne i v cronu, takze se
    to v auditu spoji,
  * pravdu drzi tabulka, ne podpis: odvolani je smazani radku a je okamzite.

INTROSPEKCE, NE PODPIS. Podepsany token by prinesl klic k rotaci, generace
kvuli odvolavani a hodiny k synchronizaci - a nic by neresil, protoze
autentizuje tyz proces, ktery token vydal (tataz uvaha jako u session id
ve viewBase2).
"""
import pytest

import viewbase as vb
from viewbase.core.identity import Caller
from conftest import register_app


class FakeApp:
    def open_content(self, handle, spec, subject):
        return {"handle": handle, "state": {}, "cursor": 1}

    def snapshot(self, handle, subject):
        return {"state": {}, "cursor": 1}

    def apply_event(self, handle, subject, event):
        return []

    def close_content(self, handle):
        pass


class Clock:
    """Rucicka, kterou v testu posuneme - abychom nemuseli cekat."""

    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def with_app(groups_of_interest=(), clock=None):
    instance = vb.Instance(clock=clock) if clock else vb.Instance()
    register_app(instance, "example.hello", kind="panel", scope="app", backend=FakeApp(),
        groups_of_interest=groups_of_interest,
    )
    return instance


HANA = Caller.for_user("hana", ["ucetni", "mzdy"], session="s1")


# ===========================================================================
# Token rika KDO, pozadavek rika CO
# ===========================================================================


def test_a_token_can_be_introspected_back_to_its_subject():
    instance = with_app()
    token = instance.auth.issue(HANA, audience="app:example.hello")
    assert instance.auth.introspect(token, audience="app:example.hello")["subject_id"] == "user:hana"


def test_the_token_is_opaque():
    # Neni to podepsany blob s obsahem - pravdu drzi tabulka.
    instance = with_app()
    token = instance.auth.issue(HANA, audience="app:example.hello")
    assert "hana" not in token
    assert "example.hello" not in token


def test_the_token_does_not_carry_a_handle():
    # "Token rika kdo, pozadavek rika co." Kdyby v nem rukojet byla, splynulo
    # by identifikovani s opravnovanim - a to je presne to, cemu se vyhybame.
    instance = with_app()
    result = instance.auth.introspect(
        instance.auth.issue(HANA, audience="app:example.hello"),
        audience="app:example.hello",
    )
    assert "handle" not in result


def test_introspection_says_when_the_token_expires():
    instance = with_app()
    result = instance.auth.introspect(
        instance.auth.issue(HANA, audience="app:example.hello"),
        audience="app:example.hello",
    )
    assert result["expires_at"] > 0


def test_an_anonymous_caller_gets_an_anonymous_token():
    instance = with_app()
    token = instance.auth.issue(Caller.anonymous(), audience="app:example.hello")
    assert instance.auth.introspect(token, audience="app:example.hello")["subject_id"] == "anonymous"


# ===========================================================================
# audience je POVINNA a apka ji overuje (D-47)
# ===========================================================================


def test_issuing_without_an_audience_is_impossible():
    instance = with_app()
    with pytest.raises(TypeError):
        instance.auth.issue(HANA)


def test_introspecting_without_an_audience_is_impossible():
    instance = with_app()
    token = instance.auth.issue(HANA, audience="app:example.hello")
    with pytest.raises(TypeError):
        instance.auth.introspect(token)


def test_a_token_for_one_app_does_not_pass_at_another():
    # Tohle je duvod, proc je audience povinna: bez ni je token pro apku X
    # klicem k apce Y, jakmile ho X ziska.
    instance = with_app()
    register_app(instance, "jina", kind="panel", scope="app", backend=FakeApp())
    token = instance.auth.issue(HANA, audience="app:example.hello")
    assert instance.auth.introspect(token, audience="app:jina") is None


def test_a_token_used_at_the_wrong_audience_is_audited():
    # Je to pokus o pouziti tokenu jinde, nez byl vydan - to patri do auditu
    # vzdycky, bez ohledu na prah logu.
    instance = with_app()
    register_app(instance, "jina", kind="panel", scope="app", backend=FakeApp())
    token = instance.auth.issue(HANA, audience="app:example.hello")
    instance.auth.introspect(token, audience="app:jina")
    assert any(r.action == "token_wrong_audience" for r in instance.audit)


def test_an_audience_that_is_not_a_registered_app_is_refused():
    instance = with_app()
    with pytest.raises(ValueError, match="audience"):
        instance.auth.issue(HANA, audience="app:neexistuje")


# ===========================================================================
# Odvolani je okamzite, protoze pravdu drzi tabulka
# ===========================================================================


def test_an_unknown_token_introspects_to_nothing():
    instance = with_app()
    assert instance.auth.introspect("vymysleny", audience="app:example.hello") is None


def test_a_revoked_token_stops_working_at_once():
    instance = with_app()
    token = instance.auth.issue(HANA, audience="app:example.hello")
    instance.auth.revoke(token)
    assert instance.auth.introspect(token, audience="app:example.hello") is None


def test_an_expired_token_introspects_to_nothing():
    clock = Clock()
    instance = with_app(clock=clock)
    token = instance.auth.issue(HANA, audience="app:example.hello", ttl=60)

    clock.now += 61

    assert instance.auth.introspect(token, audience="app:example.hello") is None


def test_a_token_still_inside_its_lifetime_works():
    clock = Clock()
    instance = with_app(clock=clock)
    token = instance.auth.issue(HANA, audience="app:example.hello", ttl=60)

    clock.now += 59

    assert instance.auth.introspect(token, audience="app:example.hello") is not None


def test_revoking_a_subject_drops_all_its_tokens():
    # Smazany uzivatel nesmi dal chodit do apek (chyba 3.5).
    instance = with_app()
    prvni = instance.auth.issue(HANA, audience="app:example.hello")
    druhy = instance.auth.issue(HANA, audience="app:example.hello")
    instance.auth.revoke_subject("user:hana")
    assert instance.auth.introspect(prvni, audience="app:example.hello") is None
    assert instance.auth.introspect(druhy, audience="app:example.hello") is None


# ===========================================================================
# Skupiny: jen ty, o ktere si apka rekla (D-48)
# ===========================================================================


def test_an_app_that_asked_for_nothing_learns_no_groups():
    # Jinak se kazda apka dozvi celou pozici cloveka v organizaci.
    instance = with_app(groups_of_interest=())
    result = instance.auth.introspect(
        instance.auth.issue(HANA, audience="app:example.hello"),
        audience="app:example.hello",
    )
    assert result["groups"] == []


def test_an_app_learns_only_the_groups_it_declared():
    instance = with_app(groups_of_interest=("group:ucetni",))
    result = instance.auth.introspect(
        instance.auth.issue(HANA, audience="app:example.hello"),
        audience="app:example.hello",
    )
    assert result["groups"] == ["group:ucetni"]


def test_a_group_the_person_is_not_in_is_not_reported():
    instance = with_app(groups_of_interest=("group:ucetni", "group:sklad"))
    result = instance.auth.introspect(
        instance.auth.issue(HANA, audience="app:example.hello"),
        audience="app:example.hello",
    )
    assert result["groups"] == ["group:ucetni"]


def test_the_declared_groups_are_normalised_like_any_principal():
    instance = with_app(groups_of_interest=("ucetni",))
    result = instance.auth.introspect(
        instance.auth.issue(HANA, audience="app:example.hello"),
        audience="app:example.hello",
    )
    assert result["groups"] == ["group:ucetni"]


def test_an_app_never_learns_the_session_id():
    # Session id je prihlasovaci udaj a do apky nepatri za zadnych okolnosti.
    instance = with_app(groups_of_interest=("group:ucetni",))
    result = instance.auth.introspect(
        instance.auth.issue(HANA, audience="app:example.hello"),
        audience="app:example.hello",
    )
    assert set(result) == {"subject_id", "groups", "expires_at"}
    assert "s1" not in str(result)
