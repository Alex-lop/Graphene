"""The VS Code extension marks in the Explorer which running task writes a file, so it reads scope globs
itself (editors/vscode/src/owners.ts, a port of `plan._pattern` and `plan.in_scope`). Its test reads this
table of in_scope's answers; here in_scope gives them again, so a change to the CLI's rules fails here until
the table, and the port, follow."""

import json
from pathlib import Path

from graphene_map.plan import in_scope

TABLE = Path(__file__).parents[1] / "editors" / "vscode" / "test" / "fixtures" / "scope-cases.json"


def test_the_extensions_scope_table_is_what_in_scope_answers():
    cases = json.loads(TABLE.read_text())
    assert len(cases) > 200
    wrong = [c for c in cases if in_scope(c["path"], c["scope"]) != c["inside"]]
    assert not wrong, wrong[:5]
