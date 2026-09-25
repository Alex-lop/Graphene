"""plan30.py <dir> [goal|arrive|late]: a thirty-leaf plan, mid-run, in a fresh git repository at <dir>.
`goal` stops once the goal is set; `arrive` does the rest into the repository `goal` made, for a
screen already open on it; `late` goes on to finish the report, which leaves a tree of 21 rows.

Six sub-goals: two finished (6 and 5 leaves), one with a leaf that came back, a running one, a
proposal and one waiting; one with a review, a running leaf and two ready; one ready, waiting and
the person's own; and a proposed sub-goal of three. 30 leaves drawn: 14 done, 2 running, 1 came back,
3 waiting, 4 proposed, 1 review, 4 ready, 1 yours.

The screens beside this file were taken from it with the polish run's harness
(docs/process/polish/harness), as a copy whose shoot.py had REPO = /tmp/graphene-fold/feeds, muxes
started with SOCKS=/tmp/graphene-fold/mux: `python plan30.py /tmp/graphene-fold/feeds`, a copy of it
kept as the snapshot, then `shoot.py <before|after> <graphene> <snapshot> <name> <keys>` for each
name: f01-opens (no key), f02-zM, f03-zR-zx, f04-folded-row (/reader), f05-came-back (/came back),
f06-zo (/validate, zo). The before ran af03827's src (git archive), the after this branch.
f07-late was taken the same way from `late`; f08-arrives opened the screen on `goal` and ran
`arrive` into it five seconds later, the screen taken fifteen seconds after that."""

import os
import subprocess
import sys
import time
from pathlib import Path

from graphene_map import plan
from graphene_map.store import Store

root = Path(sys.argv[1])
mode = sys.argv[2] if len(sys.argv) > 2 else ""
os.environ["USER"] = "alex"


def git(*args):
    subprocess.run(
        ["git", "-c", "user.email=alex@example.com", "-c", "user.name=Alex", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


alex = plan.Caller("alex", True)
RUN = plan.Caller("run:nemotron", False, "7e1f00aa-run-session")
SESSION = plan.Caller("claude:aaaa1111", False, "aaaa1111-session")
if mode != "arrive":
    root.mkdir(parents=True)
    git("init", "-q", "-b", "main")
    (root / "README.md").write_text("feeds\n")
    (root / ".gitignore").write_text(".graphene/\n")
    git("add", "-A")
    git("commit", "-qm", "start")
    with Store.open(root) as store:
        plan.set_goal(store, "csv feeds import cleanly, and every bad row is named with its line", alex)
if mode == "goal":
    sys.exit(0)


def leaf(i, title, parent, **more):
    return {"id": i, "title": title, "parent": parent, "scope": [f"feeds/{i}.py"], "check": "true", **more}


with Store.open(root) as store:
    plan.propose(store, [
        {"id": "reader", "title": "read every feed as rows"},
        leaf("csv-open", "open a feed whatever its encoding", "reader"),
        leaf("csv-sniff", "sniff the delimiter from the first lines", "reader"),
        leaf("csv-header", "map the header to our field names", "reader"),
        leaf("csv-quotes", "quoted fields with newlines in them", "reader"),
        leaf("csv-bom", "a byte order mark is not part of the first field", "reader"),
        leaf("csv-stream", "stream a large feed without reading it whole", "reader"),
        {"id": "dialects", "title": "the dialects our suppliers send"},
        leaf("tsv", "tab separated feeds", "dialects"),
        leaf("semicolon", "semicolons and decimal commas", "dialects"),
        leaf("excel", "what Excel writes when it saves as csv", "dialects"),
        leaf("fixed", "fixed width feeds from the old system", "dialects"),
        leaf("gzip", "gzipped feeds", "dialects"),
        {"id": "validate", "title": "every row checked before it is imported"},
        leaf("v-types", "numbers, dates and prices parse", "validate"),
        leaf("v-required", "required fields are there", "validate"),
        leaf("v-price", "a zero or negative price is a bad row", "validate"),
        leaf("v-dupes", "duplicate skus in one feed", "validate"),
        leaf("v-rules", "rules a supplier can switch off", "validate", needs=["v-dupes"]),
        {"id": "report", "title": "the bad rows report"},
        leaf("r-lines", "each bad row keeps its line number", "report"),
        leaf("r-format", "the report as a table a person reads", "report", signoff=True),
        leaf("r-json", "the report as json for the dashboard", "report"),
        leaf("r-email", "mail the report to the supplier", "report"),
        leaf("r-limit", "cap the report at a thousand rows", "report"),
        {"id": "cli", "title": "one command imports a feed"},
        leaf("cli-import", "feeds import <file>", "cli"),
        leaf("cli-dry", "a dry run that imports nothing", "cli"),
        leaf("cli-exit", "the exit code says whether any row was bad", "cli", needs=["cli-import"]),
        leaf("cli-progress", "a progress line for a large feed", "cli", needs=["cli-import"]),
        {"id": "cli-review", "title": "try it on last month's real feeds", "parent": "cli", "owner": "alex"},
    ], alex)  # fmt: skip

    def done(i):
        plan.start(store, i, RUN, root)
        (root / "feeds").mkdir(exist_ok=True)
        (root / "feeds" / f"{i}.py").write_text(f"# {i}\n")
        plan.finish(store, i, RUN, checkout=root)
        git("add", "-A")
        git("commit", "-qm", i)

    for i in (
        "csv-open",
        "csv-sniff",
        "csv-header",
        "csv-quotes",
        "csv-bom",
        "csv-stream",
        "tsv",
        "semicolon",
        "excel",
        "fixed",
        "gzip",
        "v-types",
        "v-required",
        "r-lines",
    ):
        done(i)
    done("r-format")  # signed off by a person: it waits in review
    plan.start(store, "v-dupes", SESSION, root)
    store.log_node(
        "v-dupes", plan._now(), "denied", None, SESSION.session_id, None, {"path": "feeds/skus.py"}
    )
    plan.release(
        store,
        "v-dupes",
        SESSION,
        "a duplicate sku is decided by the sku table, which is feeds/skus.py, outside my scope",
        wants=["feeds/skus.py"],
    )
    for i in ("v-price", "r-json"):
        plan.start(store, i, RUN, root)
        log = root / ".graphene" / "runs" / f"{i}-1.txt"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("reading the feed module\n")
        store.log_node(
            i, plan._now(), "attempt", RUN.label, RUN.session_id, None, {"attempt": 1, "log": str(log)}
        )
    plan.propose(store, [
        {"id": "v-empty", "title": "an empty row is skipped, not a bad row", "parent": "validate",
         "scope": ["feeds/v-empty.py"], "check": "true"},
        {"id": "docs", "title": "the importer documented"},
        leaf("d-usage", "usage in the README", "docs"),
        leaf("d-dialects", "which dialects we read, with an example of each", "docs"),
        leaf("d-report", "how to read the bad rows report", "docs"),
    ], SESSION)  # fmt: skip
    if mode == "late":
        plan.signoff(store, "r-format", alex, checkout=root)
        (root / "feeds" / "r-json.py").write_text("# r-json\n")
        plan.finish(store, "r-json", RUN, checkout=root)
        git("add", "-A")
        git("commit", "-qm", "r-json")
        done("r-email")
        done("r-limit")
    time.sleep(0.1)

with Store.open(root) as store:
    nodes = plan.nodes(store)
    back = {n.id for n in nodes if plan.came_back(store, n)}
    under = plan.kids(nodes, drawn=True)
    words = [plan.reads(n, nodes, back) for n in nodes if not under.get(n.id)]
    print(len(words), {w: words.count(w) for w in sorted(set(words))})
