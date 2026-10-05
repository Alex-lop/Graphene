"""The Nemotron extra (graphene_map.nemotron) is reached from the core only through extra.py. Without the
extra installed, the CLI starts, no Token Factory code loads, and its commands are not registered."""

import json
import re
import subprocess
import sys
from pathlib import Path

import graphene_map

SRC = Path(graphene_map.__file__).parent
IMPORT = re.compile(r"^\s*(?:from\s+(?:graphene_map)?\.*nemotron\b|import\s+graphene_map\.nemotron\b|"
                    r"from\s+(?:graphene_map|\.)\s+import\s+[^#\n]*\bnemotron\b)", re.M)  # fmt: skip
EXTRA = ["key", "plan cover", "plan note", "plan precheck", "board lookup"]


def strays(src: Path) -> list[str]:
    """The core's files that import the extra, the shim aside."""
    core = [p.relative_to(src) for p in src.rglob("*.py")]
    core = [p for p in core if p.parts[0] != "nemotron" and p != Path("extra.py")]
    return sorted(str(p) for p in core if IMPORT.search((src / p).read_text(encoding="utf-8")))


def test_the_core_imports_the_extra_only_through_the_shim():
    assert (SRC / "extra.py").exists() and (SRC / "nemotron" / "__init__.py").exists()
    assert strays(SRC) == []


def test_a_stray_import_of_the_extra_is_caught(tmp_path):
    for n, line in enumerate(("from .nemotron import keys", "from . import nemotron",
                              "    from graphene_map.nemotron.executor import template",
                              "import graphene_map.nemotron.sandbox")):  # fmt: skip
        (tmp_path / f"m{n}.py").write_text(f"x = 1\n{line}\n")
    (tmp_path / "extra.py").write_text("from . import nemotron\n")  # the shim may
    assert strays(tmp_path) == ["m0.py", "m1.py", "m2.py", "m3.py"]


PROBE = """
import json, sys
{block}
from typer.main import get_command
from graphene_map.cli import build
cli = get_command(build())
names = lambda group: sorted(group.commands)
print(json.dumps({{"root": names(cli), "plan": names(cli.commands["plan"]),
                  "board": names(cli.commands["board"]),
                  "loaded": sorted(m for m in sys.modules if m.startswith("graphene_map.nemotron"))}}))
"""


def commands(installed: bool) -> dict:
    block = "" if installed else "sys.modules['contree_sdk'] = None  # the extra's dependency, absent"
    done = subprocess.run([sys.executable, "-c", PROBE.format(block=block)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    said = json.loads(done.stdout)
    shown = {*said["root"], *(f"plan {c}" for c in said["plan"]), *(f"board {c}" for c in said["board"])}
    return {"registered": [c for c in EXTRA if c in shown], "loaded": said["loaded"]}


def test_without_the_extra_the_cli_starts_and_registers_none_of_its_commands():
    assert commands(installed=False) == {"registered": [], "loaded": []}


def test_with_the_extra_its_commands_register():
    with_it = commands(installed=True)
    assert with_it["registered"] == EXTRA and "graphene_map.nemotron.tokenfactory" not in with_it["loaded"]
