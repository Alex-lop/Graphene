# ruff: noqa: F811  (pytest fixtures imported from test_plan are named again as arguments)
"""A protected name is matched as the disk reaches it, whatever its unicode form. A Mac's disk takes
`café` spelled decomposed (NFD: e, then the accent) as the same directory as `café` composed (NFC), so a
scope or a write spelled NFD reached a directory the setting `protected: café/**` keeps out: `covers`
casefolded and never normalized, and the propose-time check compared strings."""

import unicodedata

import pytest
from test_plan import ALEX, BOT, repo, store  # noqa: F401  (fixtures)

from graphene_map import plan as P
from graphene_map import settings as S

NFC, NFD = unicodedata.normalize("NFC", "café"), unicodedata.normalize("NFD", "café")
assert NFC != NFD


@pytest.mark.parametrize("glob, path", [(NFC, NFD), (NFD, NFC), (NFC, NFC)])
def test_a_standing_glob_covers_the_path_in_either_form(glob, path):
    assert P.covers([f"{glob}/**"], f"{path}/key.txt")
    assert P.kept_out_by(f"{path}/key.txt", [("protected", f"{glob}/**")]) == f"protected: {glob}/**"
    node = P.from_dict({"id": "t", "title": "t", "scope": ["**"], "check": "true"}, "t")
    assert not P.binds(f"{path}/key.txt", node, [("protected", f"{glob}/**")])


@pytest.mark.parametrize("glob, scope", [(NFC, NFD), (NFD, NFC)])
def test_propose_refuses_a_scope_spelled_in_the_other_form(store, glob, scope):
    S.apply(store, f"protected: {glob}/**\n", ALEX)
    files = [f"{glob}/key.txt"]
    with pytest.raises(P.Refused, match="keeps out of every scope"):
        P.propose(store, [{"id": "t", "title": "t", "scope": [f"{scope}/**"], "check": "true"}], BOT,
                  files=files)  # fmt: skip
