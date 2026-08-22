"""Observation and authority do not mix.

A static import scan proves that the mission orchestration package never
imports the shadow package and vice versa, and that the two SQLite schemas
share no table names. Relative imports are resolved against each module's
package so a lazy `from ..shadow import x` inside a function is caught too.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from graphene.orchestration.store import _SCHEMA as MISSION_SCHEMA
from graphene.shadow.store import _SCHEMA as SHADOW_SCHEMA
from graphene.shadow.store import SHADOW_DB_FILENAME

ROOT = Path(__file__).parents[3]
PACKAGE_ROOT = ROOT / "backend"
ORCHESTRATION = PACKAGE_ROOT / "graphene" / "orchestration"
SHADOW = PACKAGE_ROOT / "graphene" / "shadow"
MISSION_DB_FILENAME = "missions.sqlite3"
_TABLE = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+)")


def _imported_modules(path: Path) -> set[str]:
    """Absolute dotted names of every import statement in one source file."""

    package = path.relative_to(PACKAGE_ROOT).with_suffix("").parts[:-1]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                assert node.level - 1 <= len(package), f"{path} imports above the root"
                base = package[: len(package) - (node.level - 1)]
                head = ".".join((*base, node.module) if node.module else base)
            else:
                head = node.module or ""
            found.add(head)
            found.update(f"{head}.{alias.name}" for alias in node.names)
    return found


def _sources(tree_root: Path) -> dict[Path, str]:
    files = sorted(tree_root.rglob("*.py"))
    assert files, f"no python sources under {tree_root}"
    return {path: path.read_text(encoding="utf-8") for path in files}


def _offenders(tree_root: Path, forbidden: str) -> dict[str, list[str]]:
    offenders: dict[str, list[str]] = {}
    for path in _sources(tree_root):
        hits = sorted(
            module
            for module in _imported_modules(path)
            if module == forbidden or module.startswith(forbidden + ".")
        )
        if hits:
            offenders[path.relative_to(ROOT).as_posix()] = hits
    return offenders


def _table_names(schema: str) -> set[str]:
    names = set(_TABLE.findall(schema))
    assert names, "schema text declares no tables"
    return names


def test_import_resolver_handles_relative_imports() -> None:
    shadow_store = _imported_modules(SHADOW / "store.py")
    assert "graphene.hashing" in shadow_store
    assert "graphene.hashing.canonical_json_bytes" in shadow_store
    assert "graphene.shadow.events" in shadow_store
    assert "graphene.shadow.events.ShadowEvent" in shadow_store
    assert "graphene.hashing" in _imported_modules(ORCHESTRATION / "store.py")


def test_orchestration_never_imports_shadow() -> None:
    assert _offenders(ORCHESTRATION, "graphene.shadow") == {}


def test_shadow_never_imports_orchestration() -> None:
    assert _offenders(SHADOW, "graphene.orchestration") == {}


def test_orchestration_sources_never_mention_shadow() -> None:
    mentions = [
        path.relative_to(ROOT).as_posix()
        for path, text in _sources(ORCHESTRATION).items()
        if "shadow" in text.lower()
    ]
    assert mentions == []


def test_shadow_sources_never_name_orchestration_modules() -> None:
    mentions = [
        path.relative_to(ROOT).as_posix()
        for path, text in _sources(SHADOW).items()
        if "graphene.orchestration" in text or ".orchestration" in text
    ]
    assert mentions == []


def test_mission_schema_does_not_mention_shadow() -> None:
    assert "shadow" not in MISSION_SCHEMA.lower()


def test_shadow_schema_does_not_declare_mission_tables() -> None:
    assert "mission" not in SHADOW_SCHEMA.lower()
    assert _table_names(MISSION_SCHEMA).isdisjoint(_table_names(SHADOW_SCHEMA))
    assert _table_names(SHADOW_SCHEMA) == {
        "shadow_schema_migrations",
        "shadow_sessions",
        "shadow_events",
    }


def test_stores_use_different_files() -> None:
    assert SHADOW_DB_FILENAME == "shadow.sqlite3"
    assert SHADOW_DB_FILENAME != MISSION_DB_FILENAME
    mission_cli = (PACKAGE_ROOT / "graphene" / "cli" / "mission.py").read_text()
    assert f'"{MISSION_DB_FILENAME}"' in mission_cli
