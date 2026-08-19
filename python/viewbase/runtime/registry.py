"""Jeden registr objektu instance podle adresy.

Ve viewBase2 byly ctyri paralelni mapy podle typu okna a kazda otazka "mam
okno s timhle id?" se musela ptat ctyrikrat. Tady je registr jeden.

Dava odpoved na jedinou otazku, kterou potrebuje vynucovani i vysilaci
smycka: `resolve(address, verb) -> Acl`. Je to zaroven ta JEDINA funkce,
kterou smycka o pravech dostane (par. 3) - nic jineho o oknech nevi.

Zavisi jen na `core` (par. 11).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.access import Access, Acl, Verb, effective_acl
from ..core.addressing import Address


@dataclass
class ObjectRegistry:
    """Objekty instance podle adresy, vcetne jejich politiky.

    Registr je majetek instance, ne modulu - dve instance v jednom procesu
    maji dva registry a nemaji si co predat (chyba 3.14).
    """

    default_access: Acl
    _objects: dict[Address, Access] = field(default_factory=dict)

    # -- evidence --------------------------------------------------------

    def add(self, address: Address, access: Access | None = None) -> None:
        """Zapis objekt. Adresa uz obsazena je chyba, ne prepis.

        Dve okna s touz adresou znamenaji, ze jedno z nich nepujde adresovat.
        """
        if address in self._objects:
            raise ValueError(f"adresa uz je obsazena: {address}")
        self._objects[address] = access if access is not None else Access()

    def replace_access(self, address: Address, access: Access) -> None:
        """Vymen politiku objektu za novou hodnotu.

        Zmenu vede instance, ne objekt - jen ona k ni umi pripojit kdo/kdy/co
        (par. 4b). Registr je tady uloziste, ne rozhodovaci misto.
        """
        if address not in self._objects:
            raise KeyError(address)
        self._objects[address] = access

    def remove(self, address: Address) -> None:
        self._objects.pop(address, None)

    def access_of(self, address: Address) -> Access:
        """Politika zapsana PRIMO na objektu, bez dedicnosti."""
        return self._objects[address]

    def __contains__(self, address: Address) -> bool:
        return address in self._objects

    def __len__(self) -> int:
        return len(self._objects)

    # -- to jedine, co potrebuje vynucovani a vysilani -------------------

    def resolve(self, address: Address, verb: Verb) -> Acl:
        """Efektivni ACL pro adresu a sloveso.

        Projde dedicnost objekt -> rodic -> ... -> vychozi hodnota instance.

        NEZNAMA ADRESA JE ZAVRENO, ne vychozi hodnota. Zprava muze dorazit
        k doruceni pote, co okno zaniklo; "neznam" nesmi znamenat "vychozi"
        (chyba 3.5) a uz vubec ne "kdokoli". Totez plati, kdyz zanikne rodic:
        osirely objekt nema od koho dedit a je zavreny.

        DVA RUZNE VYCHOZI STAVY, a je to rozdil mezi "co se ukazuje" a "co je
        instance zac":

          * retez plochy a registrace apky konci `default_access` instance
            (typicky `group:users`). Plochy, okna i spoustec jsou k tomu, aby
            se videly; utajit se daji ACL,
          * retez instance konci ZAVRENO. Auditni stopa a sprava instance, na
            kterych nikdo ACL nenastavil, nesmi byt otevrene vsem prihlasenym
            (par. 7).

        Kdyby oboji koncilo `default_access`, staci zapomenout na ACL logu a je
        z nej verejny audit. Kdyby oboji koncilo zavreno, neuvidi cerstve
        nasazena instance nic a spravce zacina tim, ze odemyka po jednom.
        """
        chain: list[Access] = []
        current: Address | None = address
        while current is not None:
            if current not in self._objects:
                return Acl.empty()
            chain.append(self._objects[current])
            current = current.parent
        default = (
            self.default_access
            if address.segments[0][0] in ("screen", "app")
            else Acl.empty()
        )
        return effective_acl(verb, chain, default=default)

    def step_up_at(self, address: Address) -> bool:
        """Chce tenhle objekt krok navic?

        NEDEDI SE. Krok navic se pta "jsi to fakt ty, ted" u konkretniho
        objektu; dedit ho by znamenalo, ze odemceni jednoho okna odemkne
        celou plochu (blizke chybe 3.9).

        Neznama adresa chce krok navic - stejne jako u `resolve` je bezpecna
        odpoved ta prisnejsi.
        """
        access = self._objects.get(address)
        return True if access is None else access.step_up
