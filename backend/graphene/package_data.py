from __future__ import annotations

from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent
_SOURCE_ROOT = _PACKAGE_ROOT.parents[1]
_PACKAGED_LEGACY_ROOT = _PACKAGE_ROOT / "_legacy"
_PACKAGED_NORTH_STAR_ROOT = _PACKAGE_ROOT / "_north_star"


def source_project_root() -> Path | None:
    """Return the checkout root only when this module is imported from it."""

    source_package = _SOURCE_ROOT / "backend" / "graphene"
    try:
        if source_package.samefile(_PACKAGE_ROOT):
            return _SOURCE_ROOT
    except OSError:
        pass
    return None


def legacy_project_root() -> Path:
    """Resolve the small legacy resource bundle in a checkout or installation."""

    return source_project_root() or _PACKAGED_LEGACY_ROOT


def north_star_project_root() -> Path:
    """Resolve the North Star materializer bundle in a checkout or installation."""

    return source_project_root() or _PACKAGED_NORTH_STAR_ROOT
