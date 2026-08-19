"""Audit jako komponenta, ne uroven.

Ctyri pravidla z par. 7, kazde ma svuj duvod z provozu viewBase2:

  * SANACE NA JEDNOM MISTE - ridici znaky (jinak cizi text prebarvi
    `docker logs`), zalomeni radku (podvrzeny zaznam), strop delky,
  * REDAKCE PODLE KLICU na ceste do logu, ne v kazdem volajicim (chyba 3.10:
    kod z autentikatoru se objevil v ladicim logu),
  * SLOUPCOVY FORMAT, at jde cist po pozicich i strojove,
  * AUDIT PROJDE VZDYCKY, bez ohledu na prah zavaznosti - bezpecnostni
    udalost se nesmi dat utisit nastavenim.

Uroven rika, JAK JE TO ZLE. Komponenta rika, ZE JDE O BEZPECNOSTNI STOPU.
Uspesne odemceni neni `warning` a odmitnuty kod neni `error`.
"""
import dataclasses
import pathlib

import pytest

# Ciste funkce a tvar zaznamu jsou v core (nezavisi na nicem), nadoba se
# stavem a prahem v runtime. Testy si to berou odtud, kde to opravdu je -
# jinak by re-export zakryl, kdyby se to zase slilo dohromady.
from viewbase.core.audit import (
    LEVELS,
    MAX_DETAIL,
    SECURITY,
    SESSION_PREFIX,
    Record,
    redact,
    sanitize,
)
from viewbase.runtime.audit import AuditLog


# ===========================================================================
# Sanace: jedno misto pro vsechny cesty
# ===========================================================================


def test_escape_sequences_cannot_repaint_someone_elses_terminal():
    # `docker logs` se cte v terminalu; text s \x1b[2J smaze obrazovku,
    # obarvi cizi radky nebo schova ty vlastni.
    assert "\x1b" not in sanitize("\x1b[2Jsmazano")


def test_a_control_character_is_shown_as_its_code():
    assert sanitize("\x07zvonek") == "\\x07zvonek"


def test_a_newline_cannot_forge_a_second_record():
    # Zalomeni v cizim textu by vyrobilo zaznam, ktery vypada jako od serveru.
    sanitised = sanitize("prihlaseni\n2026-01-01 INFO  spravce se prihlasil")
    assert "\n" not in sanitised
    assert "\\n" in sanitised


def test_a_windows_newline_is_caught_too():
    assert "\r" not in sanitize("a\r\nb")


def test_one_message_cannot_drown_the_rest():
    sanitised = sanitize("x" * (MAX_DETAIL + 500))
    assert len(sanitised) < MAX_DETAIL + 100


def test_a_truncated_message_says_how_much_is_missing():
    # Tise oriznuty text vypada jako uplny a to je horsi nez dlouhy.
    assert "+500" in sanitize("x" * (MAX_DETAIL + 500))


def test_ordinary_text_goes_through_unchanged():
    assert sanitize("uzivatel hana odemkl okno mzdy") == "uzivatel hana odemkl okno mzdy"


def test_something_that_is_not_text_is_still_sanitised():
    # Do logu tecou i cizi objekty; nesmi to spadnout ani projit syrove.
    assert sanitize({"a": "\x1b[2J"}).count("\\x1b") == 1


# ===========================================================================
# Redakce podle klicu: chyba 3.10
# ===========================================================================


def test_a_code_from_the_authenticator_never_reaches_the_log():
    assert "123456" not in str(redact({"code": "123456"}))


@pytest.mark.parametrize("key", ["code", "token", "secret", "sid", "password", "otp"])
def test_every_dangerous_key_is_redacted(key):
    assert "tajne" not in str(redact({key: "tajne"}))


def test_a_redacted_value_says_how_long_it_was():
    # Delka je uzitecna pri hledani chyb ("prisel prazdny kod") a nic
    # neprozradi.
    assert redact({"code": "123456"})["code"] == "<redacted:6>"


def test_redaction_reaches_into_nested_payloads():
    # Payload udalosti byva zanoreny; redakce jen na prvni urovni by byla
    # jen zdanim.
    payload = {"event": {"detail": {"token": "abcdef"}}}
    assert "abcdef" not in str(redact(payload))


def test_redaction_reaches_into_lists():
    assert "abcdef" not in str(redact({"items": [{"secret": "abcdef"}]}))


def test_the_key_is_matched_case_insensitively():
    assert "abcdef" not in str(redact({"Token": "abcdef"}))


def test_a_key_that_merely_contains_a_dangerous_word_is_redacted_too():
    # `access_token`, `user_secret` - cekat na presnou shodu by znamenalo
    # hlidat seznam, ktery nikdy nebude uplny.
    assert "abcdef" not in str(redact({"access_token": "abcdef"}))


def test_harmless_values_survive():
    assert redact({"window": "mzdy"})["window"] == "mzdy"


# ===========================================================================
# Prah: audit se utisit neda
# ===========================================================================


def test_a_record_below_the_threshold_is_dropped():
    log = AuditLog(threshold="warning")
    log.record("info", component="server", action="start")
    assert len(log) == 0


def test_a_record_at_the_threshold_passes():
    log = AuditLog(threshold="warning")
    log.record("warning", component="server", action="pomalu")
    assert len(log) == 1


@pytest.mark.parametrize("threshold", LEVELS)
def test_a_security_record_passes_at_every_threshold(threshold):
    # Tohle je to pravidlo: bezpecnostni udalost se nesmi dat schovat
    # nastavenim log_level.
    log = AuditLog(threshold=threshold)
    log.security("info", action="window_unlock", detail="hana odemkla mzdy")
    assert len(log) == 1


def test_a_security_record_keeps_its_own_severity():
    # Uroven rika, jak je to zle; komponenta rika, ze jde o bezpecnostni
    # stopu. Uspesne odemceni neni warning.
    log = AuditLog(threshold="error")
    log.security("info", action="window_unlock")
    assert log[0].level == "info"


def test_a_security_record_is_marked_by_its_component_not_by_its_level():
    log = AuditLog()
    log.security("info", action="window_unlock")
    assert log[0].component == SECURITY


def test_the_component_security_cannot_be_claimed_by_an_ordinary_record():
    # Kdyby si ji smel vzit kdokoli, prah by sel obejit z druhe strany.
    log = AuditLog(threshold="error")
    with pytest.raises(ValueError):
        log.record("info", component=SECURITY, action="podvrh")


def test_an_unknown_level_is_refused():
    log = AuditLog()
    with pytest.raises(ValueError):
        log.record("kriticke", component="server", action="neco")


# ===========================================================================
# Sloupce a to, co se do nich nesmi dostat
# ===========================================================================


def test_the_session_appears_only_as_a_prefix():
    # Cele session id je prihlasovaci udaj; jeho drzitel JE tou relaci.
    log = AuditLog()
    log.security("info", action="connect", session="s1abcdef0123456789")
    assert log[0].session == "s1abcdef"[:SESSION_PREFIX]
    assert "0123456789" not in str(log[0])


def test_a_missing_column_holds_its_place():
    # Sloupce se ctou po pozicich; chybejici hodnota drzi misto pomlckou.
    log = AuditLog()
    log.record("info", component="server", action="start")
    assert " - " in log.format(log[0])


def test_the_line_starts_with_time_and_level():
    log = AuditLog(clock=lambda: 0.0)
    log.record("warning", component="server", action="pomalu")
    line = log.format(log[0])
    assert line.split()[0].startswith("1970")
    assert "WARNING" in line


def test_the_line_can_be_read_by_position():
    log = AuditLog(clock=lambda: 0.0)
    log.security("info", action="connect", session="s1abcdef99", source="10.0.0.9")
    line = log.format(log[0])
    assert "s1abcdef" in line and "10.0.0.9" in line and "security" in line


# ===========================================================================
# Invariant nad zaznamem, ne nad jednotlivosti (princip 5)
# ===========================================================================


def test_every_text_column_of_a_record_is_sanitised():
    """Sanace ma byt na JEDNOM miste - a tenhle test to hlida nad CELYM
    zaznamem, takze pokryje i sloupec, ktery nekdo pridá pristi rok."""
    log = AuditLog()
    jed = "\x1b[2Jpodvrh\nfalesny radek"
    log.security(
        "info", action=jed, detail=jed, session=jed, source=jed, by=jed
    )
    record = log[0]
    for field in dataclasses.fields(Record):
        value = getattr(record, field.name)
        if isinstance(value, str):
            assert "\x1b" not in value, field.name
            assert "\n" not in value, field.name


def test_the_levels_are_exactly_four():
    # Audit neni pata uroven. Kdyby pribyla, ma o tom padnout rozhodnuti.
    assert LEVELS == ("debug", "info", "warning", "error")


def test_a_record_is_a_value():
    log = AuditLog(clock=lambda: 0.0)
    log.record("info", component="server", action="start")
    assert log[0] == log[0]


# ===========================================================================
# Tataz pravidla na skutecne instanci
# ===========================================================================


def instance_at(level):
    import viewbase as vb

    instance = vb.Instance(log_level=level)
    screen = instance.screen.open(id="provoz")
    return instance, screen.window.open("panel", id="mzdy")


def test_a_change_of_rights_survives_the_strictest_threshold():
    # "Kdo co komu otevrel" musi jit dohledat i na instanci, ktera bezi
    # s log_level='error'. Tohle je to pravidlo v praxi.
    instance, window = instance_at("error")
    window.access.read.set(["group:ucetni"])
    assert any(r.action == "read" for r in instance.audit)


def test_the_change_is_marked_as_a_security_record():
    instance, window = instance_at("info")
    window.access.read.set(["group:ucetni"])
    assert instance.audit[-1].component == SECURITY


def test_an_ordinary_record_obeys_the_threshold():
    # Prah ma na necem platit - jinak by to nebyl prah, ale ozdoba.
    import viewbase as vb

    instance = vb.Instance(log_level="error", knows_principal=lambda name: False)
    window = instance.screen.open(id="provoz").window.open("panel", id="mzdy")
    window.access.read.set(["group:neznama"])
    assert not any(r.action == "unknown_principal" for r in instance.audit)


def test_the_same_record_passes_at_a_lower_threshold():
    import viewbase as vb

    instance = vb.Instance(log_level="info", knows_principal=lambda name: False)
    window = instance.screen.open(id="provoz").window.open("panel", id="mzdy")
    window.access.read.set(["group:neznama"])
    assert any(r.action == "unknown_principal" for r in instance.audit)


def test_a_forged_line_cannot_enter_the_trail_through_a_principal_name():
    # Jmeno principala je vstup od cloveka a tece do stopy - takze i tudy
    # musi projit sanaci.
    instance, window = instance_at("info")
    window.access.read.set(["group:a\nfalesny radek"])
    assert all("\n" not in (r.detail or "") for r in instance.audit)


def test_every_record_from_the_instance_says_who_did_it():
    instance, window = instance_at("info")
    window.access.read.set(["group:ucetni"])
    assert all(r.by for r in instance.audit)


def test_the_pure_half_of_the_audit_needs_nothing_from_the_runtime():
    """Sanace a redakce se musi dat pouzit i tam, kde zadna instance neni -
    treba v nastroji spravce nebo v testu apky.

    Bezi to v SAMOSTATNEM PROCESU zamerne: v tomhle uz je runtime davno
    naimportovany, takze by import v nem nic nedokazal. (Prvni verze tohohle
    testu mazala moduly ze sys.modules a rozbila tim jine testy - mit test
    s globalnim vedlejsim ucinkem je horsi nez ten test nemit.)
    """
    import subprocess
    import sys

    script = (
        "import sys\n"
        "from viewbase.core.audit import sanitize, redact\n"
        "assert sanitize('\\x1b[2J') == '\\\\x1b[2J'\n"
        "assert redact({'token': 'abc'})['token'] == '<redacted:3>'\n"
        "leaked = [n for n in sys.modules if n.startswith('viewbase.runtime')]\n"
        "assert not leaked, leaked\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(pathlib.Path(__file__).resolve().parent.parent),
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr


def test_an_unavailable_content_stays_an_ordinary_record():
    # Spadly kontejner je provozni stav, ne bezpecnostni udalost - jinak by
    # se bezpecnostni stopa zaplnila restarty.
    import viewbase as vb

    class Spadla:
        def open_content(self, handle, spec, subject):
            raise ConnectionError("spadla")

        def snapshot(self, handle, subject):
            raise ConnectionError("spadla")

        def apply_event(self, handle, subject, event):
            return []

        def close_content(self, handle):
            pass

    instance = vb.Instance(log_level="error")
    instance.app.register("a", kind="graph", scope="app", backend=Spadla())
    instance.screen.open(id="infra").window.open("graph", id="net", app="a")

    assert not any(r.action == "content_unavailable" for r in instance.audit)
