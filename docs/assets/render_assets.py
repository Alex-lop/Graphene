"""Render the README's terminal images from the synthetic transcript fixture.

A dev script, not part of the package: it builds a throwaway git repo, loads the fixture session
into a store there, and records the card and both `why` views into SVGs. Re-runnable; the output
depends only on the fixture, so re-running it rewrites the same three files.

    uv run python docs/assets/render_assets.py
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tests" / "fixtures"))

import make_transcript_fixture as fixture  # noqa: E402
from rich.console import Console  # noqa: E402

from graphene_debrief.debrief import (  # noqa: E402
    build_debrief,
    print_card,
    print_why,
    select_sessions,
    stamp,
)
from graphene_debrief.sources.claude_code import backfill  # noqa: E402
from graphene_debrief.store import Store  # noqa: E402
from graphene_debrief.why import why_line, why_path  # noqa: E402

WIDTH = 80


def fixture_repo(directory: Path) -> Path:
    """A git repo holding the fixture session's transcript and the file `why` is asked about."""
    root = directory / "project"
    (root / "app").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "app" / "hello.py").write_text(fixture.HELLO_V2)
    fixture.CWD = str(root)  # the fixture renders with this repo as the session's cwd
    transcripts = directory / "transcripts"
    for path, text in fixture.render().items():
        target = transcripts / path.relative_to(fixture.OUT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return root


def record(out: Path, title: str, draw) -> str:
    console = Console(width=WIDTH, record=True, force_terminal=True, file=io.StringIO())
    draw(console)
    out.write_text(console.export_svg(title=title, clear=False))
    return console.export_text()


def main(out_dir: Path) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        root = fixture_repo(directory)
        with Store.open(root) as store:
            backfill(store, root, transcripts=sorted((directory / "transcripts").glob("*.jsonl")))
            debrief = build_debrief(store, select_sessions(store), root)
            entries = why_path(store, root, "app/hello.py")
            answer = why_line(store, root, "app/hello.py", 2)
        out_dir.mkdir(parents=True, exist_ok=True)
        where = (
            f"committed in {answer.commit[:7]} ({stamp(answer.committed_at)})"
            if answer.commit
            else "not committed"
        )
        texts = {
            "card.svg": record(out_dir / "card.svg", "graphene", lambda c: print_card(c, debrief)),
            "why-path.svg": record(
                out_dir / "why-path.svg",
                "graphene why app/hello.py",
                lambda c: print_why(
                    c, "app/hello.py", "", f"{len(entries)} prompt(s), newest first", entries
                ),
            ),
            "why-line.svg": record(
                out_dir / "why-line.svg",
                "graphene why app/hello.py:2",
                lambda c: print_why(
                    c,
                    "app/hello.py:2",
                    answer.content or "",
                    f"{where} · {answer.reason}",
                    answer.matches,
                ),
            ),
        }
        for name in texts:
            written = (out_dir / name).read_text()
            assert tmp not in written and str(root) not in written, f"{name} leaked the temp repo path"
    for name, text in texts.items():
        print(f"--- {name}")
        print(text)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent, help="where to write the SVGs")
    raise SystemExit(main(parser.parse_args().out))
