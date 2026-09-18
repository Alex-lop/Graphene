"""The HTML record: the data survives the round trip, nothing can escape into markup, node runs the script."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from graphene_debrief.cli import build
from graphene_debrief.debrief import Debrief, FileLine, PromptBlock, build_debrief, to_json
from graphene_debrief.export_html import TEMPLATE, render
from graphene_debrief.store import Store

sys.path.insert(0, str(Path(__file__).parent))
from test_debrief import NOW, seed_golden  # noqa: E402

TEMPLATE_PATH = Path(__file__).parents[1] / "src" / "graphene_debrief" / TEMPLATE
DATA = re.compile(r'<script type="application/json" id="graphene-data">(.*?)</script>', re.S)
SCRIPT = re.compile(r"<script>\n(.*?)\n</script>", re.S)
runner = CliRunner()


@pytest.fixture
def golden(tmp_path):
    with Store.open(tmp_path) as store:
        seed_golden(store)
        yield build_debrief(store, ["sess-golden-1"], tmp_path, now=NOW)


def embedded(page: str) -> dict:
    match = DATA.search(page)
    assert match, "no embedded data script in the page"
    return json.loads(match.group(1))


def test_the_page_carries_the_whole_debrief_and_shows_every_prompt_and_file(golden):
    page = render(golden)
    data = embedded(page)
    assert set(data) == {"debrief", "nodes"}
    assert data["debrief"] == json.loads(to_json(golden))
    assert "__GRAPHENE_" not in page
    for block in golden.prompts:
        assert json.dumps(block.text[:40])[1:-1] in page  # JSON-escaped, so newlines are \n
        for line in block.files:
            assert line.path in page
    types = {n["type"] for n in data["nodes"]}
    assert types == {"session", "prompt", "file", "dir"}  # distinct node types, as the roadmap needs
    assert [n["path"] for n in data["nodes"] if n["type"] == "dir"] == ["app", "tests"]
    assert any(n["hunks"] for block in data["debrief"]["prompts"] for n in block["files"])


def test_prompt_flags_drive_the_filters(golden):
    nodes = {n["id"]: n for n in embedded(render(golden))["nodes"]}
    # prompt 1's pytest failed then passed on a rerun; prompt 3 reverted README.md
    assert nodes["prompt:sess-golden-1:1"]["abandoned"] is True
    assert nodes["prompt:sess-golden-1:3"]["abandoned"] is True
    assert nodes["prompt:sess-golden-1:2"]["abandoned"] is False  # nothing of p2's survived to a revert
    assert nodes["file:README.md"]["abandoned"] is True
    assert not any(n.get("unrequested") for n in nodes.values())  # nothing unrequested in the golden


def test_an_unrequested_file_marks_its_prompt():
    debrief = Debrief(generated_at="2026-03-01T12:00:00.000Z")
    block = PromptBlock("s1", "p1", 1, "2026-03-01T09:00:00.000Z", "fix the test")
    block.files.append(FileLine("app/x.py", "modified", 2, 1, True, "payload", "changed x", "none"))
    debrief.prompts.append(block)
    debrief.unrequested.append({"path": "app/x.py", "session_id": "s1", "prompt_ordinal": 1})
    nodes = {n["id"]: n for n in embedded(render(debrief))["nodes"]}
    assert nodes["prompt:s1:1"]["unrequested"] is True
    assert nodes["file:app/x.py"]["unrequested"] is True
    assert nodes["dir:app"]["files"] == 1


def test_markup_cannot_be_injected_through_a_prompt():
    nasty = "</script><img src=x onerror=alert(1)>\n<!-- comment -->"
    debrief = Debrief(generated_at="2026-03-01T12:00:00.000Z")
    debrief.prompts.append(PromptBlock("s1", "p1", 1, "2026-03-01T09:00:00.000Z", nasty))
    page = render(debrief)
    payload = DATA.search(page).group(1)
    assert "</script>" not in payload and "<\\/script>" in payload
    assert "<!--" not in payload and "\\u003c!--" in payload
    assert json.loads(payload)["debrief"]["prompts"][0]["text"] == nasty  # still the real text
    assert "onerror=alert(1)>" in payload  # inert: the page only ever writes it with textContent
    assert "<img src=x onerror" not in page.replace(payload, "")


def test_the_template_itself_reaches_nothing_outside_the_file():
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "__GRAPHENE_DATA__" in text and "__GRAPHENE_TITLE__" in text
    for pattern in ("http://", "https://", "//cdn", "fetch(", "XMLHttpRequest", "innerHTML", "<img"):
        assert pattern not in text, pattern
    assert len(text.splitlines()) < 900


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_node_parses_the_page_script(tmp_path, golden):
    script = SCRIPT.search(render(golden))
    assert script, "no behaviour script in the page"
    out = tmp_path / "record.js"
    out.write_text(script.group(1), encoding="utf-8")
    checked = subprocess.run([shutil.which("node"), "--check", str(out)], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr


def test_the_cli_writes_the_record(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
    import make_transcript_fixture as fixture

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setattr(fixture, "CWD", str(tmp_path))
    transcripts = tmp_path / "transcripts"
    for path, text in fixture.render().items():
        target = transcripts / path.relative_to(fixture.OUT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    loaded = runner.invoke(
        build(), ["ingest", "--backfill", "--transcript", str(transcripts / f"{fixture.SID}.jsonl")]
    )
    assert loaded.exit_code == 0, loaded.output

    out = tmp_path / "out" / "record.html"
    result = runner.invoke(build(), ["debrief", "--html", str(out), "--explain", "none"])
    assert result.exit_code == 0, result.output + result.stderr
    assert "wrote" in result.output + result.stderr
    page = out.read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>")
    assert "app/hello.py" in page and "__GRAPHENE_" not in page
    assert embedded(page)["debrief"]["prompt_count"] == 3
    assert "# Graphene" not in result.output  # --html alone does not also print the card
