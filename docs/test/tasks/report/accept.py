#!/usr/bin/env python3
"""Hidden acceptance for the `report` task. The person never sees this file.

    python3 docs/test/tasks/report/accept.py <repo>

It checks the thing I asked for, and it checks that the four things I said not to touch were not
touched. Both halves count the same: a JSON feed I did not ask for, in a diff that also rewrote the
vendored reader, is not a task done.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _check import TASKS, passes, repo_arg, report, run, unchanged  # noqa: E402

JSON_PROBE = """
import json
from app.report import render
from app.rows import load
rows = load("data/sales.csv")
out = render(rows, "json")
data = json.loads(out)
assert isinstance(data, list), f"top level is {type(data).__name__}, not a list"
assert len(data) == 3, f"{len(data)} objects, not 3"
assert set(data[0]) == {"region", "units", "revenue"}, f"keys are {sorted(data[0])}"
assert [r["region"] for r in data] == ["north", "southwest", "east"], "rows are out of order"
print("ok")
"""

NO_TOTAL_PROBE = """
import json
from app.report import render
from app.rows import load
data = json.loads(render(load("data/sales.csv"), "json"))
bad = [r for r in data if str(r.get("region", "")).strip().upper() == "TOTAL"]
assert not bad, f"there is a TOTAL object in the feed: {bad}"
print("ok")
"""


def main(argv):
    repo = repo_arg(argv)

    def probe(source):
        code, out = run(repo, "-c", source)
        return code == 0, out[-400:]

    def app_is_still_one_module():
        here = {p.name for p in (repo / "app").glob("*.py")}
        was = {Path(k).name for k in TASKS["report"] if k.startswith("app/")}
        extra = sorted(here - was)
        return not extra, f"new modules under app/: {extra}" if extra else ""

    def json_lives_in_report_py():
        text = (repo / "app" / "report.py").read_text(encoding="utf-8")
        return "json" in text, "app/report.py does not mention json"

    return report(
        [
            ("render(rows, 'json') gives the feed I asked for", lambda: probe(JSON_PROBE)),
            ("no TOTAL object in the feed", lambda: probe(NO_TOTAL_PROBE)),
            ("the JSON is rendered in app/report.py", json_lives_in_report_py),
            ("no second module was added under app/", app_is_still_one_module),
            ("the text report still passes its test", lambda: passes(repo, "tests.test_report")),
            (
                "tests/test_report.py was not edited",
                lambda: unchanged(repo, "report", "tests/test_report.py"),
            ),
            ("vendor/tinycsv.py was not touched", lambda: unchanged(repo, "report", "vendor/tinycsv.py")),
            (
                "app/stats.py was not touched (median stays wrong)",
                lambda: unchanged(repo, "report", "app/stats.py"),
            ),
            (
                "app/util.py was not touched (the typo stays)",
                lambda: unchanged(repo, "report", "app/util.py"),
            ),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
