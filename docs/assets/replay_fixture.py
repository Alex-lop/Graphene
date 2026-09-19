"""Serve the synthetic run (tests/fixtures/make_run_fixture.py) the way `graphene ui` serves a repo.

A dev script, outside the package: it loads the fixture's ground truth into a scratch store and
starts the map's own server on it, so the page can be looked at, tested in a browser and recorded
without any real transcript. Run from the repo root:

    uv run python docs/assets/replay_fixture.py            # serves until Ctrl-C, prints the address
    uv run python docs/assets/replay_fixture.py --both     # both sessions on one axis
    uv run python docs/assets/replay_fixture.py --export FILE
"""

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests" / "fixtures"))

import make_run_fixture as run  # noqa: E402

from graphene_debrief.server import export_html, make_server  # noqa: E402
from graphene_debrief.store import Store  # noqa: E402


def main(argv: list[str]) -> None:
    scratch = Path(tempfile.mkdtemp(prefix="graphene-fixture-"))
    (scratch / ".git").mkdir()
    sessions = [run.S1, run.S2] if "--both" in argv else [run.S1]
    with Store.open(scratch) as store:
        run.load(store)
        if "--export" in argv:
            target = Path(argv[argv.index("--export") + 1])
            target.write_text(export_html(store, sessions), encoding="utf-8")
            print(f"wrote {target}")
            return
    server = make_server(scratch, sessions)
    print(f"http://127.0.0.1:{server.server_address[1]}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main(sys.argv[1:])
