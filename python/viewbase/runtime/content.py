"""Obsah ma vlastni identitu; okno je jen pohled na nej.

Puvodne instance obsahu splyvala s oknem - obsah vznikal otevrenim okna
a umiral jeho zavrenim. Tri bezne situace to porusuji (D-26):

  * naplnit obsah davkovou ulohou DRIV, nez ho nekdo otevre (okno jeste neni),
  * dve okna, ktera maji ukazovat TYZ obsah,
  * jeden clovek ve dvou tabech, ktery chce TYZ obsah.

    OBSAH  (u apky)      rukojet "vb1_9f2c..."   <- stav; zije vlastnim zivotem
       ^        ^
       | pohled | pohled
    OKNO A    OKNO B     (u workbenche)          <- kde se to ukazuje; ACL

RUKOJET RAZI INSTANCE, ne apka. Kdyby ji razila apka, kazdy jeji restart by
zneplatnil vsechny ulozene rukojeti a davkovy ukol by prestal fungovat bez
varovani (D-29). Odvozuje se HMACem z tajemstvi instance, takze je zaroven
neuhodnutelna a stabilni - a kdyz se tajemstvi ulozi, prezije i restart
instance.

RUKOJET IDENTIFIKUJE, NEOPRAVNUJE. Rika, KTERE instanci obsahu volate; jestli
smite, rika poverení k API apky. Kdyby stacila sama, unik jednoho retezce
z logu znamena, ze kdokoli pise do ciziho okna.
"""
from __future__ import annotations

import hmac
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from typing import Any, Protocol

from ..core.addressing import Address
from ..core.identity import ADMINISTRATOR, Caller

#: Jak se rukojet odvodi, kdyz ji nikdo nezada. Nahrazuje drivejsi
#: `content: shared | per-session | instance` a zobecnuje ho (D-27).
SCOPES = ("window", "session", "user", "instance", "app", "explicit")

#: `session` a `user` NEJSOU totez: shell chce dva terminaly ve dvou tabech,
#: osobni graf chce jedno okno do tehoz. Splynuti je chyba.
_VIEWER_SCOPES = ("session", "user")

#: Vychozi casove limity (D-32). Pomala apka smi zdrzet sebe, ne vysilaci smycku.
DEFAULT_TIMEOUTS = {"open_content": 2.0, "snapshot": 2.0, "apply_event": 5.0}


class ContentRefused(Exception):
    """Apka pripojeni k obsahu ODMITLA.

    Je to NORMALNI ODPOVED, ne chyba: neznama rukojet, cizi obsah, vycerpany
    limit. Divak dostane ram s hlaskou. Odlisuje se od vypadku zamerne -
    "neznam tuhle rukojet" a "spadl mi kontejner" jsou dve ruzne veci a
    divakovi se maji rict jinak (par. 8: kazde rozhodnuti vraci duvod).
    """


class ContentState(Enum):
    """Stav obsahu z pohledu INSTANCE - apka o nem z definice nemuze rict nic."""

    OK = "ok"
    UNAVAILABLE = "unavailable"  # spadla, restartuje se, nebo neodpovida vcas
    REFUSED = "refused"  # apka pripojeni odmitla; je to odpoved, ne porucha


class AppBackend(Protocol):
    """Co musi umet apka. Zadne `screen` ani `window` (D-28).

    Mapu okno -> rukojet drzi instance; apka resi jen svuj obsah. Hranice je
    tim ostrejsi, ne volnejsi - a apka se stava pouzitelnou i tam, kde zadna
    okna nejsou.
    """

    def open_content(self, handle: str, spec: dict) -> dict: ...
    def snapshot(self, handle: str, subject: dict) -> dict: ...
    def apply_event(self, handle: str, subject: dict, event: dict) -> list: ...
    def close_content(self, handle: str) -> None: ...


@dataclass
class Content:
    """Jedna bezici instance obsahu u apky."""

    handle: str
    app_id: str
    state: ContentState = ContentState.OK
    views: set[Address] = field(default_factory=set)
    #: Kdo obsah zalozil. Destruktivni akce smi jen on nebo spravce (D-41):
    #: jeden obsah muze byt ve dvou oknech s ruznymi ACL, takze pravo psat
    #: v jednom okne nesmi znamenat pravo znicit obsah videny v druhem.
    created_by: str | None = None
    #: Vychozi hodnoty voleb rendereru, ktere apka poslala v `open_content`.
    #: Smi je NASTAVIT, ne odebirat: co pro dana data nedava smysl, schova si
    #: renderer sam (D-46).
    view_defaults: dict = field(default_factory=dict)


def subject_of(caller: Caller, capabilities: list[str] | None = None) -> dict:
    """Co apka dostane misto identity.

    NIKDY session id ani skupiny: session id je prihlasovaci udaj a skupiny by
    z apky udelaly druhe misto, kde se rozhoduje o pravech (review, vyhrady
    2 a 4). Schopnosti jsou UZ ROZHODNUTE - apka je nepocita, jen se jimi ridi.
    """
    subject_id = "anonymous"
    for principal in caller.principals:
        if principal.startswith("user:"):
            subject_id = principal
            break
    return {
        "subject_id": subject_id,
        "correlation": caller.correlation,
        "capabilities": list(capabilities or []),
    }


class ContentRegistry:
    """Rukojeti, jejich stav a to, ktera okna se na ne divaji.

    Je to majetek instance: mapa okno -> rukojet nikdy neopusti workbench.
    """

    def __init__(
        self,
        secret: bytes,
        timeouts: dict[str, float] | None = None,
        audit: Callable[..., None] | None = None,
    ) -> None:
        self._secret = secret
        self._timeouts = {**DEFAULT_TIMEOUTS, **(timeouts or {})}
        self._audit = audit or (lambda *a, **k: None)
        self._contents: dict[str, Content] = {}
        self._backends: dict[str, AppBackend] = {}
        self._pending_view: dict = {}
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="viewbase-app")

    # -- razeni rukojeti --------------------------------------------------

    def mint(self, key: str) -> str:
        """Neuhodnutelna a stabilni rukojet pro dany klic.

        HMAC z tajemstvi instance: tataz plocha a okno daji touz rukojet, dve
        ruzne instance daji ruzne, a uhodnout ji nejde.
        """
        digest = hmac.new(self._secret, key.encode("utf-8"), sha256).hexdigest()
        return f"vb1_{digest[:32]}"

    def handle_for(self, app_id: str, scope: str, address: Address | None) -> str | None:
        """Odvod rukojet ze `scope`, nebo vrat None, kdyz to jeste nejde.

        U `session` a `user` se odvozuje az od diváka - pri otevirani okna
        jeste zadny neni.
        """
        if scope in _VIEWER_SCOPES:
            return None
        if scope == "app":
            return self.mint(f"app:{app_id}")
        if scope == "instance":
            return self.mint(f"instance:{app_id}")
        if scope == "window":
            return self.mint(f"window:{app_id}:{address}")
        raise ValueError(f"scope {scope!r} rukojet neodvozuje")

    # -- evidence ---------------------------------------------------------

    def bind_backend(self, app_id: str, backend: AppBackend | None) -> None:
        if backend is not None:
            self._backends[app_id] = backend

    def state(self, handle: str) -> ContentState | None:
        content = self._contents.get(handle)
        return None if content is None else content.state

    def views(self, handle: str) -> tuple[Address, ...]:
        content = self._contents.get(handle)
        return () if content is None else tuple(sorted(content.views, key=str))

    def view_defaults(self, handle: str | None) -> dict:
        content = self._contents.get(handle) if handle else None
        return {} if content is None else dict(content.view_defaults)

    def created_by(self, handle: str) -> str | None:
        content = self._contents.get(handle)
        return None if content is None else content.created_by

    def may_destroy(self, handle: str, caller: Caller) -> bool:
        """Smi tenhle volajici obsah znicit? (D-41)"""
        if ADMINISTRATOR in caller.principals:
            return True
        return self.created_by(handle) == subject_of(caller)["subject_id"]

    def attach(
        self,
        handle: str | None,
        app_id: str,
        address: Address | None,
        spec: dict,
        caller: Caller | None = None,
    ) -> tuple[str | None, ContentState]:
        """Napoj pohled na obsah; kdyz jeste nezije, otevri ho u apky.

        Druhy pohled uz obsah neotevira znovu - je to tyz obsah.

        `handle=None` znamena "zaloz novy a rekni mi jakou rukojet jsi razila"
        (D-39: razit ji smi obe strany). Neznama rukojet se ODMITNE, nikdy
        tise nezaklada: po preklepu by divak dostal prazdny obsah a myslel si,
        ze prisel o data (D-38).
        """
        caller = caller or Caller.internal()
        content = handle is not None and self._contents.get(handle)
        if content:
            if address is not None:
                content.views.add(address)
            return handle, content.state

        self._pending_view = {}
        minted, state = self._open_at_app(handle, app_id, spec, caller)
        if minted is None:
            return handle, state

        content = self._contents.get(minted)
        if content is None:
            content = Content(
                minted, app_id, state,
                created_by=subject_of(caller)["subject_id"],
                view_defaults=self._pending_view,
            )
            self._contents[minted] = content
        content.state = state
        if address is not None:
            content.views.add(address)
        return minted, state

    def detach(self, handle: str, address: Address) -> None:
        """Zavreni okna je ODPOJENI POHLEDU, ne smrt obsahu (D-26).

        Obsah zanika podle `scope` nebo vyslovne pres `close_content`.
        """
        content = self._contents.get(handle)
        if content is not None:
            content.views.discard(address)

    def close(self, handle: str) -> None:
        content = self._contents.pop(handle, None)
        if content is None:
            return
        backend = self._backends.get(content.app_id)
        if backend is not None:
            self._call(content, "close_content", backend.close_content, handle)

    # -- volani apky ------------------------------------------------------

    def snapshot_for(self, handle: str, caller: Caller, capabilities=None) -> dict | None:
        """Snapshot pro konkretniho diváka, nebo None, kdyz apka neodpovida.

        Vypadek je STAV OKNA, ne chyba: divak vidi ram, ostatni okna bezi dal.
        """
        content = self._contents.get(handle)
        if content is None:
            return None
        backend = self._backends.get(content.app_id)
        if backend is None:
            return None
        return self._call(
            content, "snapshot", backend.snapshot, handle, subject_of(caller, capabilities)
        )

    def list_content(self, app_id: str, caller: Caller) -> list:
        """Z ceho si divak muze vybrat (D-37).

        Filtruje APKA - vlastnictvi obsahu jsou jeji data; my rozhodujeme
        o oknech. Spadla apka da prazdny seznam, ne vyjimku: spoustec se kvuli
        jedne mrtve apce nesmi rozbit.
        """
        backend = self._backends.get(app_id)
        if backend is None or not hasattr(backend, "list_content"):
            return []
        placeholder = Content("-", app_id)
        result = self._call(
            placeholder, "snapshot", backend.list_content, subject_of(caller)
        )
        return result or []

    def _open_at_app(
        self, handle: str | None, app_id: str, spec: dict, caller: Caller
    ) -> tuple[str | None, ContentState]:
        """Otevri nebo pripoj obsah u apky. Vrat rukojet a stav."""
        backend = self._backends.get(app_id)
        if backend is None:
            # Lokalni obsah: dodava ho kod, ktery okno otevrel.
            return handle, ContentState.OK

        placeholder = Content(handle or "-", app_id)
        answer = self._call(
            placeholder, "open_content", backend.open_content, handle, spec,
            subject_of(caller),
        )
        if placeholder.state is not ContentState.OK:
            return handle, placeholder.state
        if isinstance(answer, dict) and answer.get("handle"):
            handle = answer["handle"]
        if isinstance(answer, dict) and isinstance(answer.get("view"), dict):
            self._pending_view = dict(answer["view"])
        return handle, ContentState.OK

    def _call(self, content: Content, what: str, fn: Callable, *args) -> Any:
        """Zavolej apku s casovym limitem a preloz selhani na STAV.

        Volani bezi v thread poolu, takze pomala apka nezastavi instanci -
        vlakno si dobehne samo, ale my na nej necekame dele nez limit.
        """
        try:
            result = self._pool.submit(fn, *args).result(self._timeouts.get(what, 2.0))
        except FutureTimeout:
            self._mark_unavailable(content, what, "neodpovedela vcas")
            return None
        except ContentRefused as refusal:
            # Odmitnuti je odpoved, ne porucha - a divakovi se rika jinak.
            content.state = ContentState.REFUSED
            self._audit(
                "content", "content_refused",
                detail=f"{content.app_id} {what}: {refusal}",
            )
            return None
        except Exception as problem:  # apka je cizi kod; nesmi shodit instanci
            self._mark_unavailable(content, what, f"{type(problem).__name__}: {problem}")
            return None
        content.state = ContentState.OK
        return result

    def _mark_unavailable(self, content: Content, what: str, why: str) -> None:
        content.state = ContentState.UNAVAILABLE
        self._audit(
            "content", "content_unavailable",
            detail=f"{content.app_id} {what}: {why}",
        )
