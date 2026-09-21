#!/usr/bin/env python3
"""Held-out quality for the `feeds` task: the same code, against feeds it was never shown.

    python3 docs/test/tasks/feeds/quality.py <repo>

`accept.py` runs the sample that was sitting in the repo the whole time. This runs twelve feeds
that were not, each one an instance of something the card states as a rule rather than as an
example: only product entries are products, prices are in cents, nought means "ask us", a product
missing a field is skipped and not a crash, entities and accents survive, an empty feed is a clean
exit, order is the feed's order. A parser that passes `accept.py` by pattern-matching the sample
fails here.

Same output shape as accept.py: {"passed", "failed", "details"}. The person never sees this either.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _check import repo_arg, report  # noqa: E402

HEAD = '<?xml version="1.0" encoding="utf-8"?>\n'


def feed(body: str, supplier: str = "heldout") -> str:
    return f'{HEAD}<feed supplier="{supplier}" date="2026-09-22">\n{body}</feed>\n'


P = '  <product code="{c}" desc="{d}" price="{p}"/>\n'

MANY = "".join(P.format(c=f"HO-{i}", d=f"part {i}", p=100 + i) for i in range(120))

# (name, the feed, what must come out as (sku, name, price_cents) triples in order)
CASES = [
    (
        "attributes in any order",
        feed('  <product desc="left-handed spanner" price="775" code="HO-A"/>\n'),
        [("HO-A", "left-handed spanner", 775)],
    ),
    (
        "entities come out decoded",
        feed('  <product code="HO-B" desc="&lt;3 nuts &amp; bolts&gt;" price="90"/>\n'),
        [("HO-B", "<3 nuts & bolts>", 90)],
    ),
    (
        "a product with no price is skipped, the rest of the feed still loads",
        feed('  <product code="HO-C" desc="no price"/>\n' + P.format(c="HO-D", d="fine", p="55")),
        [("HO-D", "fine", 55)],
    ),
    (
        "a product with an empty code is skipped, the rest of the feed still loads",
        feed('  <product code="" desc="nameless" price="30"/>\n' + P.format(c="HO-E", d="fine", p="55")),
        [("HO-E", "fine", 55)],
    ),
    (
        "whitespace around a price is not a crash",
        feed('  <product code="HO-F" desc="padded" price=" 250 "/>\n'),
        [("HO-F", "padded", 250)],
    ),
    (
        "a nought price is dropped here too",
        feed(P.format(c="HO-G", d="ask us", p="0") + P.format(c="HO-H", d="for sale", p="1")),
        [("HO-H", "for sale", 1)],
    ),
    (
        "a negative price is dropped",
        feed(P.format(c="HO-I", d="credit note", p="-500") + P.format(c="HO-J", d="for sale", p="2")),
        [("HO-J", "for sale", 2)],
    ),
    (
        "an empty feed is nothing loaded and a clean exit",
        f'{HEAD}<feed supplier="heldout" date="2026-09-22"/>\n',
        [],
    ),
    (
        "a summary in the middle and a summary at the end are never records",
        feed(
            '  <summary code="HO-TOT1" desc="running total" price="9999"/>\n'
            + P.format(c="HO-K", d="real", p="11")
            + '  <summary code="HO-TOT2" desc="day total" price="8888"/>\n'
        ),
        [("HO-K", "real", 11)],
    ),
    (
        "an element that is neither a product nor a summary is not a record",
        feed(
            '  <note code="HO-N" desc="delivery monday" price="1"/>\n' + P.format(c="HO-L", d="real", p="12")
        ),
        [("HO-L", "real", 12)],
    ),
    (
        "a hundred and twenty products all arrive, in the feed's order",
        feed(MANY),
        [(f"HO-{i}", f"part {i}", 100 + i) for i in range(120)],
    ),
    (
        "accents and Chinese survive",
        feed('  <product code="HO-M" desc="pièce détachée 螺丝" price="345"/>\n'),
        [("HO-M", "pièce détachée 螺丝", 345)],
    ),
]


def load(repo: Path, path: Path) -> tuple[int, str, str]:
    done = subprocess.run(
        [sys.executable, "-m", "cli.main", "load", str(path), "--source", "xml"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=180,
    )
    return done.returncode, done.stdout, done.stderr


def main(argv):
    repo = repo_arg(argv)
    hold = Path(tempfile.mkdtemp(prefix="feeds-heldout-"))

    def case(name, xml, want):
        def check():
            path = hold / (name.replace(" ", "-")[:40] + ".xml")
            path.write_text(xml, encoding="utf-8")
            code, out, err = load(repo, path)
            if code != 0:
                return False, f"exit {code}: {(out + err)[-300:]}"
            got = []
            for line in out.splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    return False, f"not JSON: {line[:120]}"
                got.append((row.get("sku"), row.get("name"), row.get("price_cents")))
            if got != want:
                return False, f"wanted {want[:4]}{' …' if len(want) > 4 else ''}, got {got[:4]}"
            return True, ""

        return (name, check)

    return report([case(name, xml, want) for name, xml, want in CASES])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
