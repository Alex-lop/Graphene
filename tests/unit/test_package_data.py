from __future__ import annotations

import tomllib
from pathlib import Path

from graphene import package_data

ROOT = Path(__file__).parents[2]


def test_legacy_resources_resolve_in_checkout_and_installed_layout(
    monkeypatch, tmp_path: Path
) -> None:
    assert package_data.source_project_root() == ROOT
    assert package_data.legacy_project_root() == ROOT
    assert package_data.north_star_project_root() == ROOT

    installed_package = tmp_path / "site-packages" / "graphene"
    installed_package.mkdir(parents=True)
    packaged_legacy = installed_package / "_legacy"
    packaged_north_star = installed_package / "_north_star"
    monkeypatch.setattr(package_data, "_PACKAGE_ROOT", installed_package)
    monkeypatch.setattr(package_data, "_SOURCE_ROOT", tmp_path / "lib")
    monkeypatch.setattr(package_data, "_PACKAGED_LEGACY_ROOT", packaged_legacy)
    monkeypatch.setattr(
        package_data, "_PACKAGED_NORTH_STAR_ROOT", packaged_north_star
    )

    assert package_data.source_project_root() is None
    assert package_data.legacy_project_root() == packaged_legacy
    assert package_data.north_star_project_root() == packaged_north_star


def test_build_declares_the_minimal_legacy_bundle_and_installed_proof() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    included = project["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert included == {
        "demo/taskmaster": "graphene/_taskmaster",
        "contracts/golden_path.json": "graphene/_legacy/contracts/golden_path.json",
        "contracts/graph_mvp.json": "graphene/_legacy/contracts/graph_mvp.json",
        "demo/fixture": "graphene/_legacy/demo/fixture",
        "demo/north_star": "graphene/_north_star/demo/north_star",
        "scripts/materialize_north_star.py": (
            "graphene/_north_star/scripts/materialize_north_star.py"
        ),
    }
    assert "pydantic==2.13.4" in project["project"]["dependencies"]
    assert all(
        not dependency.lower().startswith("pytest")
        for dependency in project["project"]["dependencies"]
    )

    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "python scripts/verify_installed_artifacts.py --require-clean" in workflow
