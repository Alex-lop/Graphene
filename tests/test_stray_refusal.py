# ruff: noqa: F811  (pytest fixtures imported from test_plan are named again as arguments)
"""A stray file holds a leaf up: the agent is told to put it back if it made it, and on 14 October the
gate refused that, since no leaf was held (a zero-byte uv lock a reader's `uv run` left). The refusal
then says what is left: the person removes it, or `graphene plan ack` makes it theirs."""

import pytest
from test_plan import ALEX, BOT, api_node, repo, store  # noqa: F401  (fixtures)

from graphene_map import plan
from graphene_map.plan import Refused


@pytest.mark.parametrize("strays", [["uv-a.lock"], ["uv-a.lock", "uv-b.lock"]])
def test_an_agent_told_to_put_a_stray_back_is_told_what_to_do_when_that_is_refused(store, repo, strays):
    plan.propose(store, [api_node(id="b")], ALEX)
    plan.mark_boundary(store, repo)
    for name in strays:
        (repo / name).write_text("")
    it = "it" if len(strays) == 1 else "them"
    for _ in range(2):  # the lecture and the short one both say it
        with pytest.raises(Refused) as no:
            plan.start(store, "b", BOT, repo)
        last = str(no.value).splitlines()[-1]
        assert last.startswith(f"  if you made {it}, put {it} back; ")
        assert last.endswith(f"; if putting {it} back is refused because no leaf is held, ask the person to "
                             f"remove {it}, or `graphene plan ack` makes {it} theirs")  # fmt: skip
