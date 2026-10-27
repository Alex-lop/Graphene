# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""A `#` in a task's check is read as bash reads it. The envelope's reader lexed a check with shlex, whose
default comment character is `#`, so `pytest x#;touch MARK;false` read as `pytest x` and passed both the
one-command rule and the `checks:` allowlist, while bash ran the `touch` after the `;`."""

import pytest
from test_auto_envelope import ALEX, proposed
from test_plan_cli import person, repo  # noqa: F401  (fixtures)

from graphene_map import auto as AUTO
from graphene_map import plan as P
from graphene_map import settings as S
from graphene_map.store import Store


@pytest.mark.parametrize("check, allowed, fits", [
    ("pytest x#;touch MARK;false", [], False),
    ("pytest x#;touch MARK;false", ["pytest"], False),
    ("pytest tests/ -q # the fast ones", ["pytest"], True),  # a comment that is one: bash drops it too
    ("pytest '#tag' -q", ["pytest"], True),
    ("pytest tests/ -q", ["pytest"], True),
])  # fmt: skip
def test_a_hash_glued_to_a_word_hides_no_second_command(check, allowed, fits):
    assert AUTO.runs_as_check(check, allowed) == fits


def test_the_envelope_makes_such_a_check_wait_for_the_person(repo):
    files = P.tracked(repo)
    with Store.open(repo) as store:
        S.apply(store, "auto: on\nchecks: pytest\n", ALEX)
        leaf = "? task 1  [t1]\n    scope: f1.py\n    check: pytest x#;touch MARK;false\n"
        why = AUTO.fits(store, proposed(store, leaf, files), files)
        assert why and why[0].startswith("t1's check is not one your envelope runs"), why
