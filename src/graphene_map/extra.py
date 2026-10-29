"""The core's one way to the Nemotron extra (graphene_map.nemotron). tests/test_nemotron_boundary.py fails
on any other import of it in the core. Without the extra installed, `load` is None."""

import importlib

INSTALL = "uv tool install --python 3.12 'graphene-map[nemotron]'"  # the extra, and `graphene key` with it
MISSING = f"Nemotron is an optional extra, and it is not installed here: {INSTALL}"


def load(name: str):
    """The extra's module ``name``, or None when the extra is not installed."""
    try:
        importlib.import_module("graphene_map.nemotron")
    except ImportError:
        return None
    return importlib.import_module(f"graphene_map.nemotron.{name}")


def need(name: str):
    """The extra's module ``name``, or a refusal that says how to install it."""
    if (module := load(name)) is None:
        from .plan import Refused

        raise Refused(MISSING)
    return module
