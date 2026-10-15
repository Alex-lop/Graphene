"""The replay's run summaries say today's words: a run's closing line reads "agents <1m · 2 of 2 at once ·
you: 6 moves, 1m" (run.clocks), and the recording kept the words it was shot with, "width" and "acts"."""

import json

from typer.testing import CliRunner

from graphene_map import demo
from graphene_map.cli import build


def said(summary: str) -> None:
    assert " at once · you: " in summary and " move" in summary and "agents <1m," in summary, summary
    assert "width" not in summary and " act" not in summary and " min" not in summary, summary


def test_the_recordings_run_summaries_say_todays_words():
    lines = [json.loads(line) for line in demo.SHIPPED.read_text().splitlines() if line.strip()]
    runs = [json.loads(e["detail"])["summary"] for line in lines for e in line.get("node_log", [])
            if e["kind"] == "run"]  # fmt: skip
    assert len(runs) == 2, runs
    for summary in runs:
        said(summary)


def test_demo_once_closes_on_todays_words(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "200")
    out = CliRunner().invoke(build(), ["demo", "--once"])
    assert out.exit_code == 0, out.output
    (row,) = [r for r in out.stdout.splitlines() if " run: " in r]
    said(row)
