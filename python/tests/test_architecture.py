"""Invariant nad rozvrzenim, ne nad jednotlivosti.

Par. 11: "core/ nezavisi na nicem" ma byt TVRDE PRAVIDLO, ne nahoda. Ve
viewBase2 to `access.py` splnoval, ale nic to nehlidalo - a nahodne dodrzene
pravidlo se drive nebo pozdeji porusi. Tenhle test projde strojove vsechny
moduly, takze pokryje i ten desaty, ktery nikdo nenapsal.
"""
import ast
import pathlib

import pytest

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "viewbase"

#: Smer zavislosti. Vrstva smi importovat ze sebe a z vrstev napravo.
LAYERS = {
    "core": (),
    "runtime": ("core",),
    "transport": ("core", "runtime"),
    "providers": ("core",),
    "types": ("core", "runtime"),
}

#: Co `core/` nesmi videt ani zvenci - jinak by se autorizace neotestovala
#: bez serveru.
FORBIDDEN_IN_CORE = {"fastapi", "uvicorn", "starlette", "httpx", "socket", "asyncio"}


def _modules(layer: str) -> list[pathlib.Path]:
    directory = PACKAGE / layer
    if not directory.exists():
        return []
    return sorted(p for p in directory.rglob("*.py"))


def _imports(path: pathlib.Path) -> list[str]:
    """Vsechna importovana jmena v modulu, absolutne i relativne."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    package = path.relative_to(PACKAGE).parent.parts

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relativni import: dopocitej absolutni jmeno
                base = package[: len(package) - node.level + 1]
                found.append(".".join(("viewbase", *base, node.module or "")).rstrip("."))
            elif node.module:
                found.append(node.module)
    return found


ALL_MODULES = [(layer, path) for layer in LAYERS for path in _modules(layer)]


def test_there_is_something_to_check():
    # Kdyby se balicek prejmenoval, testy nize by tise prochazely nad prazdnem.
    assert ALL_MODULES, f"v {PACKAGE} nejsou zadne moduly vrstev"


@pytest.mark.parametrize(
    "layer,path", ALL_MODULES, ids=lambda v: v.stem if hasattr(v, "stem") else v
)
def test_layer_imports_only_downwards(layer, path):
    allowed_layers = {layer, *LAYERS[layer]}
    for name in _imports(path):
        if not name.startswith("viewbase"):
            continue
        parts = name.split(".")
        if len(parts) < 2:
            continue
        imported_layer = parts[1]
        if imported_layer not in LAYERS:
            continue
        assert imported_layer in allowed_layers, (
            f"{path.relative_to(PACKAGE)} importuje z vrstvy {imported_layer!r}; "
            f"{layer!r} smi jen {sorted(allowed_layers)}"
        )


@pytest.mark.parametrize("path", _modules("core"), ids=lambda p: p.stem)
def test_core_does_not_reach_for_the_server(path):
    for name in _imports(path):
        root = name.split(".")[0]
        assert root not in FORBIDDEN_IN_CORE, (
            f"{path.relative_to(PACKAGE)} importuje {name!r}; core/ se musi dat "
            "otestovat bez serveru"
        )


def test_core_is_importable_on_its_own():
    # Nejtvrdsi podoba tehoz pravidla: kazdy blok musi jit pouzit sam,
    # s falesnymi sousedy a bez serveru (par. 12.1).
    import importlib

    for path in _modules("core"):
        if path.stem == "__init__":
            continue
        importlib.import_module(f"viewbase.core.{path.stem}")
