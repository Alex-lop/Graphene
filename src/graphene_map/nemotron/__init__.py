"""Nemotron on Token Factory, an optional extra: `graphene-map[nemotron]`. The core reaches it only
through graphene_map/extra.py. Without contree-sdk installed, it does not load."""

from importlib.util import find_spec

if find_spec("contree_sdk") is None:
    raise ImportError("the Nemotron extra is not installed: graphene-map[nemotron]")
