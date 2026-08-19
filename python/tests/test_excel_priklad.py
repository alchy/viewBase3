"""Uplny priklad z dodatku: jeden excel, dve oddeleni.

architektura-navrh.md, sekce "Uplny priklad" - napsany doslova, vcetne
prefixu promennych (D-64). Je to VSECHNO, co se dnes da deklarovat; delsi
priklad nez tenhle neexistuje.

Tri radky te tabulky jsou cely model prav:

  1. taz nabidka, taz plocha, dva ruzni lide -> rozhodl OBSAH,
  2. tyz dokument, dve plochy, jine chovani -> o interakci rozhoduje OKNO,
     o datech OBSAH, a musi pustit oboji,
  3. omyl, ktery nic neprozradi -> polozit dokument na verejnou plochu ho
     NEZVEREJNI.
"""
import pytest

import viewbase as vb
from viewbase.core.identity import Caller
from viewbase.runtime.events import Needs, Verdict


class ExcelApp:
    """Fiktivni tabulkovy procesor."""

    manifest = {"app_id": "excel", "kind": "panel", "scope": "explicit"}

    def open_content(self, handle, spec, subject):
        return {"handle": handle, "state": {"cells": {}}, "cursor": 1}

    def snapshot(self, handle, subject):
        return {"state": {"cells": {}}, "cursor": 1}

    def apply_event(self, handle, subject, event):
        return []

    def close_content(self, handle):
        pass


# Lide: hana je v group:uctarna, petr v group:risk, novak (financni reditel)
# v group:risk a jmenovite v obou dokumentech.
HANA = Caller.for_user("hana", ["uctarna"], session="s-hana")
PETR = Caller.for_user("petr", ["risk"], session="s-petr")
NOVAK = Caller.for_user("novak", ["risk"], session="s-novak")
ANONYM = Caller.anonymous()


def firma():
    """Prostredi z dodatku, radek po radku."""
    # -- 1. instance --------------------------------------------------------
    inst = vb.Instance(default_access=["group:zamestnanci"])

    # -- 2. apka: jen deklarace, zadna prava --------------------------------
    app_excel = inst.app.register(ExcelApp())

    # -- 3. plochy: jedna na oddeleni, jedna verejna ------------------------
    scr_uctarna = inst.screen.open(title="Uctarna", id="uctarna",
                                   read=["group:uctarna"], write=["group:uctarna"])

    scr_risk = inst.screen.open(title="Risk", id="risk",
                                read=["group:risk"], write=["group:risk"])

    scr_zasedacka = inst.screen.open(title="Zasedacka", id="zasedacka",
                                     read=["group:public"], write=[])  # [] = nikdo

    # -- 4. dokumenty: obsah, ktery prezije zavreni okna --------------------
    cnt_mzdy = app_excel.content.open(title="Mzdy.xls",
                                      read=["group:uctarna", "user:novak"],
                                      write=["group:uctarna"])

    cnt_rizika = app_excel.content.open(title="Rizika.xls",
                                        read=["group:risk", "user:novak"],
                                        write=["group:risk"])

    # -- 5. nabidky: co jde kde otevrit -------------------------------------
    # Apka i titulek se berou z obsahu (D-66, D-67) - nic se neopakuje.
    scr_uctarna.app.register(cnt_mzdy, require_authentication=True)  # + krok navic
    scr_uctarna.app.register(app_excel, title="Novy sesit")          # bez obsahu

    scr_risk.app.register(cnt_rizika)
    scr_risk.app.register(cnt_mzdy)

    scr_zasedacka.app.register(cnt_rizika)

    return locals()


def nabidky(scr, kdo):
    return sorted(o.title for o in scr.app.visible_to(kdo))


def plochy(inst, kdo):
    from viewbase.core.access import Verb, allowed

    return sorted(
        scr.title
        for scr in inst.screen.all()
        if allowed(kdo.principals, inst.objects.resolve(scr.address, Verb.READ))
    )


def zapise(scr, kdo, title):
    """Otevre si to a smi do toho psat?"""
    for offer in scr.app.visible_to(kdo):
        if offer.title == title:
            return "write" in offer.open(kdo).capabilities_for(kdo)
    return False


# ===========================================================================
# Tabulka z dodatku, radek po radku
# ===========================================================================


def test_hana_sees_her_department_and_the_boardroom():
    f = firma()
    assert plochy(f["inst"], HANA) == ["Uctarna", "Zasedacka"]


def test_hana_is_offered_her_two_documents():
    f = firma()
    assert nabidky(f["scr_uctarna"], HANA) == ["Mzdy.xls", "Novy sesit"]


def test_hana_is_offered_nothing_in_the_boardroom():
    # Zasedacku vidi, ale Rizika.xls jsou pro risk - obsah ji nepusti.
    f = firma()
    assert nabidky(f["scr_zasedacka"], HANA) == []


def test_hana_writes_into_the_payroll():
    f = firma()
    assert zapise(f["scr_uctarna"], HANA, "Mzdy.xls")


def test_petr_sees_risk_and_the_boardroom():
    f = firma()
    assert plochy(f["inst"], PETR) == ["Risk", "Zasedacka"]


def test_petr_is_offered_the_risk_document_on_both_screens():
    f = firma()
    assert nabidky(f["scr_risk"], PETR) == ["Rizika.xls"]
    assert nabidky(f["scr_zasedacka"], PETR) == ["Rizika.xls"]


def test_petr_writes_on_the_risk_screen_but_not_in_the_boardroom():
    # RADEK 2 TABULKY: tyz dokument, dve plochy, jine chovani. O interakci
    # rozhoduje OKNO (zasedacka ma write=[]), o datech OBSAH - a musi pustit
    # oboji.
    f = firma()
    assert zapise(f["scr_risk"], PETR, "Rizika.xls")
    assert not zapise(f["scr_zasedacka"], PETR, "Rizika.xls")


def test_novak_is_offered_both_documents_on_the_risk_screen():
    # RADEK 1 TABULKY: taz nabidka, taz plocha, dva ruzni lide. Mzdy.xls na
    # plose Risk vidi novak a nevidi petr - oba plochu vidi stejne. Rozhodl
    # OBSAH, ne plocha.
    f = firma()
    assert nabidky(f["scr_risk"], NOVAK) == ["Mzdy.xls", "Rizika.xls"]
    assert nabidky(f["scr_risk"], PETR) == ["Rizika.xls"]


def test_novak_writes_only_into_the_risk_document():
    # Mzdy.xls vidi (je v nich jmenovite), ale zapisuje do nich jen uctarna.
    f = firma()
    assert zapise(f["scr_risk"], NOVAK, "Rizika.xls")
    assert not zapise(f["scr_risk"], NOVAK, "Mzdy.xls")


def test_an_anonymous_visitor_sees_only_the_boardroom():
    f = firma()
    assert plochy(f["inst"], ANONYM) == ["Zasedacka"]


def test_an_anonymous_visitor_is_offered_nothing():
    # RADEK 3 TABULKY: plocha ho pusti, obsah ne.
    f = firma()
    assert nabidky(f["scr_zasedacka"], ANONYM) == []


# ===========================================================================
# Omyl, ktery nic neprozradi
# ===========================================================================


def test_putting_a_document_on_a_public_screen_does_not_publish_it():
    """Tohle je ta chyba, kvuli ktere druha uroven vznikla - a tady se uz
    napsat neda."""
    f = firma()
    f["scr_zasedacka"].app.register(f["cnt_mzdy"])

    assert nabidky(f["scr_zasedacka"], ANONYM) == []
    assert nabidky(f["scr_zasedacka"], HANA) == ["Mzdy.xls"]


def test_the_lock_on_the_offer_still_wants_a_code():
    # `require_authentication=True` u nabidky Mzdy.xls: schopnosti to nemeni
    # (krok navic je druha, nezavisla osa), ale udalost bez kodu neprojde.
    f = firma()
    inst = f["inst"]
    inst.events.register("zapis_bunky", lambda *a: None, needs=Needs.WRITE)

    okno = [o for o in f["scr_uctarna"].app.visible_to(HANA)
            if o.title == "Mzdy.xls"][0].open(HANA)

    assert "write" in okno.capabilities_for(HANA)
    assert inst.guard.check(HANA, "zapis_bunky", okno.address).verdict is Verdict.NO_GRANT

    inst.grants.hold(HANA.session, okno.address)
    assert inst.guard.check(HANA, "zapis_bunky", okno.address)


def test_the_offer_without_content_makes_a_new_document_on_click():
    # "Novy sesit" je nabidka bez obsahu: dokument vznikne az kliknutim.
    f = firma()
    nabidka = [o for o in f["scr_uctarna"].app.visible_to(HANA)
               if o.title == "Novy sesit"][0]
    prvni = nabidka.open(HANA)
    druhy = nabidka.open(HANA)
    assert prvni.app.handle != druhy.app.handle


def test_nothing_is_open_before_anyone_clicks():
    f = firma()
    for scr in f["inst"].screen.all():
        assert scr.window.all() == (), scr.title
