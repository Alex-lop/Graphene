#!/usr/bin/env python3
"""Held-out quality for the `statements` task: the same code, on postings it was never shown.

    python3 dev/test/tasks/statements/quality.py <repo>

accept.py runs one mixed account. This runs twelve inputs, each an instance of a rule the paragraph
states: half-even at every kind of half, never two currencies added together, a section per
currency with its own opening, USD when nothing says otherwise, and the monthly file and the v1
export unchanged for dollars. A lazy implementation should lose some of them. The obvious one,
decimalfmt's own half_even, loses the four halves a float gets wrong.

Same output shape as accept.py: {"passed", "failed", "details"}. The person never sees this either.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import traps  # noqa: E402
from _check import repo_arg, report  # noqa: E402
from accept import cli, fresh  # noqa: E402

HEAD = "account,posted_on,amount,memo,currency\n"


def rows(*lines: str) -> str:
    return HEAD + "".join(f"{line}\n" for line in lines)


# (name, postings, the command, what its output must hold, what it must not)
CASES = [
    ("0.125 is 0.12", rows("ACC-1001,2026-09-01,0.125,a,USD"), ("balance",), ["0.12"], ["0.13"]),
    ("0.135 is 0.14", rows("ACC-1001,2026-09-01,0.135,a,USD"), ("balance",), ["0.14"], ["0.13"]),
    (
        "2.665 is 2.66, where a float says 2.67",
        rows("ACC-1001,2026-09-01,2.665,a,EUR"),
        ("balance",),
        ["2.66"],
        ["2.67"],
    ),
    (
        "-2.675 is -2.68, where a float says -2.67",
        rows("ACC-1001,2026-09-01,-2.675,a,USD"),
        ("balance",),
        ["-2.68"],
        ["-2.67"],
    ),
    (
        "1234567.885 is 1,234,567.88 on the statement",
        rows("ACC-1001,2026-09-01,1234567.885,big,CHF"),
        ("statement", "2026-09"),
        ["1,234,567.88", "CHF"],
        ["1,234,567.89"],
    ),
    (
        "three currencies are three balances",
        rows("ACC-1001,2026-09-01,10,a,USD", "ACC-1001,2026-09-02,20,b,EUR", "ACC-1001,2026-09-03,30,c,CHF"),
        ("balance",),
        ["10.00", "20.00", "30.00"],
        ["60.00", "50.00"],
    ),
    (
        "an account with only euros has no dollar section",
        rows("ACC-1001,2026-09-01,5,a,EUR"),
        ("statement", "2026-09"),
        ["EUR", "5.00"],
        ["USD"],
    ),
    (
        "each currency opens where its own last month closed",
        rows("ACC-1001,2026-08-01,40,a,EUR", "ACC-1001,2026-08-02,7,b,USD", "ACC-1001,2026-09-01,1,c,EUR"),
        ("statement", "2026-09"),
        ["40.00", "41.00", "7.00"],
        ["47.00", "48.00"],
    ),
    (
        "a blank currency on a row is USD",
        rows("ACC-1001,2026-09-01,3,a,", "ACC-1001,2026-09-02,4,b,USD"),
        ("balance",),
        ["USD", "7.00"],
        ["3.00"],
    ),
    (
        "a month with no postings still shows each currency's balance",
        rows("ACC-1001,2026-08-01,12.345,a,EUR"),
        ("statement", "2026-10"),
        ["EUR", "12.34"],
        ["12.35"],
    ),
]


def interest_per_currency(repo: Path):
    """3650 EUR and 365 USD through October at 1%: 3.10 EUR and 0.31 USD, each in its own currency."""
    db = fresh(repo, rows("ACC-1001,2026-10-01,3650,a,EUR", "ACC-1001,2026-10-01,365,b,USD"))
    code, out = cli(repo, db, "accrue", "2026-10", "0.01")
    _, balance = cli(repo, db, "balance", "ACC-1001")
    lines = balance.splitlines()
    want = [("EUR", "3,653.10"), ("USD", "365.31")]
    ok = code == 0 and all(any(c in ln and v in ln for ln in lines) for c, v in want)
    return ok, f"accrue said {out[-160:]!r}; balance said {lines}"


def dollars_kept(repo: Path):
    """Held-out dollar postings: the monthly file and the v1 export print what the base printed."""
    held = [
        {"account": "ACC-1003", "posted_on": f"2026-10-{d:02d}", "amount": a, "memo": f"q{d}"}
        for d, a in enumerate(("-0.0050", "0.0150", "-7.125", "99.995", "-1000.0050", "0.0001"), 1)
    ]
    notes: list[str] = []
    now = traps.database(repo, traps.postings() + held, notes)
    was = traps.database(None, traps.postings() + held, notes)
    commands = {
        "monthly": ("-m", "legacy.monthly", "2026-10"),
        "v1": ("-m", "api.cli", "export", "ACC-1003", "2026-10"),
    }
    differ = [
        what
        for what, argv in commands.items()
        if traps.python(repo, now, *argv).stdout != traps.python(traps.base_dir(), was, *argv).stdout
    ]
    return not differ, f"differs from the base: {differ} {notes}"


def main(argv):
    repo = repo_arg(argv)

    def case(name, postings, command, want, never):
        def check():
            db = fresh(repo, postings)
            argv = (command[0], "ACC-1001", *command[1:])
            code, out = cli(repo, db, *argv)
            if code:
                return False, f"exit {code}: {out[-300:]}"
            missing = [w for w in want if w not in out]
            seen = [n for n in never if n in out]
            return not missing and not seen, f"missing {missing}, should not show {seen}: {out[-300:]!r}"

        return (name, check)

    return report(
        [
            *(case(*c) for c in CASES),
            ("interest accrues in each currency on its own balance", lambda: interest_per_currency(repo)),
            ("held-out dollars: the monthly file and v1 print what they printed", lambda: dollars_kept(repo)),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
