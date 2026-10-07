"""shoot.py <phase> <graphene> <snapshot|-> <name> [step ...]: the watch screen at 80x24 and 120x36.

Restores the snapshot into ~/graphene-polish (unless '-'), opens a fresh window in each isolated mux
(start.sh) running `<graphene> watch` there as a person (person.sh), sends each step (keys; '~N'
sleeps N seconds), and saves the screen as .txt, .ans and .svg under $SHOTS/<phase>/ (default
./shots), then closes the window. Steps are Python string literals, so '\\r' and '\\x1b' work."""

import ast
import io
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.text import Text

HERE = Path(__file__).resolve().parent
REPO = Path.home() / "graphene-polish"
SIZES = ("80x24", "120x36")
TRUECOLOR = re.compile(r"(3|4)8:2::(\d+):(\d+):(\d+)")  # wezterm's colon form, which rich does not read


def mux(size: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(HERE / "mux.sh"), size, *args], capture_output=True, text=True)


def svg(ans: str, cols: int, path: Path, title: str) -> None:
    def sgr(m: re.Match) -> str:
        return "\x1b[" + TRUECOLOR.sub(r"\g<1>8;2;\2;\3;\4", m.group(1)) + "m"

    plain = re.sub(r"\x1b\[([0-9;:]*)m", sgr, ans.replace("\x1b(B", ""))
    con = Console(record=True, width=cols, file=io.StringIO(), force_terminal=True, color_system="truecolor")
    for line in plain.rstrip("\n").split("\n"):
        con.print(Text.from_ansi(line), no_wrap=True, crop=True, overflow="crop")
    con.save_svg(str(path), title=title)


def main(phase: str, graphene: str, snap: str, name: str, *steps: str) -> None:
    if snap != "-":
        shutil.rmtree(REPO, ignore_errors=True)
        subprocess.run(["cp", "-a", snap, str(REPO)], check=True)
    watch = f"{graphene} watch; sleep 600"
    panes = {
        size: mux(size, "spawn", "--new-window", "--cwd", str(REPO), "--", str(HERE / "person.sh"),
                  "/bin/zsh", "-fc", watch).stdout.strip()  # fmt: skip
        for size in SIZES
    }
    time.sleep(3.5)
    for step in steps:
        if step.startswith("~"):
            time.sleep(float(step[1:]))
            continue
        keys = ast.literal_eval(f"'{step}'")
        for size in SIZES:
            mux(size, "send-text", "--pane-id", panes[size], "--no-paste", keys)
        time.sleep(0.7)
    time.sleep(1.2)
    out = Path(os.environ.get("SHOTS", HERE / "shots")) / phase
    out.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        ans = mux(size, "get-text", "--pane-id", panes[size], "--escapes").stdout
        txt = mux(size, "get-text", "--pane-id", panes[size]).stdout
        mux(size, "kill-pane", "--pane-id", panes[size])
        (out / f"{name}-{size}.ans").write_text(ans)
        (out / f"{name}-{size}.txt").write_text(txt)
        svg(ans, int(size.split("x")[0]), out / f"{name}-{size}.svg", f"graphene watch · {size} · {phase}")
        print(f"---- {name} {size}")
        print(txt.rstrip())
    time.sleep(0.5)


if __name__ == "__main__":
    main(*sys.argv[1:])
