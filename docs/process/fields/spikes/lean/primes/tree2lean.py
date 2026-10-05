"""tree.txt -> the Lean side of the tree: the statements Challenge.lean defines, and the type each
Gate asserts (write-gates.sh's table). It reads the plan's text with Graphene's own parser, so it runs
with the worktree's source:

    uv run --project <the fields worktree> python tree2lean.py tree.txt

The convention it relies on, which Graphene's grammar does not know: a leaf's prose carries a line
`Lean: S_x := <statement>` (or `Lean: S_x, ...` for a statement defined above it), its scope is
`Proofs/<File>.lean`, and its `needs:` are its hypotheses, in order.
"""

import re
import sys
from pathlib import Path

from graphene_map import plan_text as T

LEAN = re.compile(r"Lean: (S_\w+)(?: := (.*))?")


def convert(text: str) -> tuple[dict[str, str], list[str]]:
    _, lines = T.parse(text)
    defs: dict[str, str] = {}
    stmt: dict[str, str] = {}
    for line in lines:
        for said in line.goal:
            found = LEAN.match(said)
            if found:
                if found[2]:
                    defs[found[1]] = found[2]
                stmt.setdefault(line.id, found[1])
    rows = []
    for line in lines:
        if not line.scope:
            continue
        file = re.fullmatch(r"Proofs/(\w+)\.lean", line.scope[0])[1]
        rows.append(f"{file}|{line.id}|{' → '.join([*(stmt[n] for n in line.needs), stmt[line.id]])}")
    return defs, rows


if __name__ == "__main__":
    defs, rows = convert(Path(sys.argv[1]).read_text())
    print("\n".join(f"def {name} : Prop := {body}" for name, body in defs.items()))
    print()
    print("\n".join(rows))
