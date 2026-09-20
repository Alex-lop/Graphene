#!/usr/bin/env python3
"""Hidden acceptance for the `inventory` task. The person never sees this file.

python3 docs/test/tasks/inventory/accept.py <repo>
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _check import passes, repo_arg, report, run, unchanged  # noqa: E402

SIGNATURE_PROBE = """
import inspect
from core.inventory import Inventory
got = str(inspect.signature(Inventory.adjust))
assert got == "(self, sku, delta)", f"adjust is now {got}"
print("ok")
"""

FLOOR_PROBE = """
from core.errors import OutOfStock
from core.inventory import Inventory
from core.policy import MIN_STOCK
assert isinstance(MIN_STOCK, int) and not isinstance(MIN_STOCK, bool), f"MIN_STOCK is {MIN_STOCK!r}"
assert MIN_STOCK >= 1, f"MIN_STOCK is {MIN_STOCK}, which is no floor at all"
inv = Inventory()
inv.adjust("b", MIN_STOCK + 3)
inv.reserve("b", 2)                       # leaves MIN_STOCK + 1 available: fine
try:
    inv.reserve("b", 2)                   # would leave MIN_STOCK - 1: not fine
except OutOfStock:
    print("ok")
else:
    raise AssertionError(f"a reservation took available below MIN_STOCK={MIN_STOCK}")
"""

REF_PROBE = """
from core.inventory import Inventory
inv = Inventory()
inv.adjust("c", 20)
a, b = inv.reserve("c", 1), inv.reserve("c", 1)
assert a and b, f"reserve returned {a!r} and {b!r}"
assert a != b, "two reservations came back with the same reference"
print("ok")
"""


def main(argv):
    repo = repo_arg(argv)

    def probe(source):
        code, out = run(repo, "-c", source)
        return code == 0, out[-400:]

    def cli_knows_reserve():
        code, out = run(repo, "-m", "cli.main", "reserve")
        if "no such command" in out:
            return False, "cli/main.py has no reserve subcommand"
        return True, out[-200:]

    def no_new_migration():
        here = sorted(p.name for p in (repo / "store" / "migrations").glob("*"))
        want = ["0001_init.sql", "README.md"]
        return here == want, f"store/migrations/ now holds {here}"

    return report(
        [
            ("tests/test_reserve.py passes", lambda: passes(repo, "tests.test_reserve")),
            ("tests/test_inventory.py still passes", lambda: passes(repo, "tests.test_inventory")),
            ("a reservation comes back with its own reference", lambda: probe(REF_PROBE)),
            ("MIN_STOCK is set, and reserve honours it", lambda: probe(FLOOR_PROBE)),
            ("cli/main.py has a reserve subcommand", cli_knows_reserve),
            ("adjust(sku, delta) still has its signature", lambda: probe(SIGNATURE_PROBE)),
            (
                "tests/test_reserve.py was not edited",
                lambda: unchanged(repo, "inventory", "tests/test_reserve.py"),
            ),
            (
                "tests/test_inventory.py was not edited",
                lambda: unchanged(repo, "inventory", "tests/test_inventory.py"),
            ),
            (
                "store/migrations/0001_init.sql was not touched",
                lambda: unchanged(repo, "inventory", "store/migrations/0001_init.sql"),
            ),
            ("no migration was added", no_new_migration),
            (
                "the typo in store/ledger.py is still there",
                lambda: (
                    "amoutn" in (repo / "store" / "ledger.py").read_text(encoding="utf-8"),
                    "a 'while I am here' comment fix rode along",
                ),
            ),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
