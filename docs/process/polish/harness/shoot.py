"""shoot.py <phase> <graphene> <snapshot|-> <name> [step ...]: the watch screen at 80x24 and 120x36.

Restores the snapshot into ~/graphene-polish (unless '-'), opens a fresh window in each isolated mux
running `<graphene> watch` there, sends each step (keys; '~N' sleeps N seconds), and saves the screen
as .txt, .ans and .svg under shots/<phase>/, then closes the window. Steps are Python string
literals, so '\\r' and '\\x1b' work."""
import ast, io, os, re, shutil, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = Path.home() / "graphene-polish"
SIZES = ("80x24", "120x36")
phase, graphene, snap, name, *steps = sys.argv[1:]

def mux(size, *args):
    return subprocess.run([str(HERE / "mux.sh"), size, *args], capture_output=True, text=True)

if snap != "-":
    shutil.rmtree(REPO, ignore_errors=True)
    subprocess.run(["cp", "-a", snap, str(REPO)], check=True)
panes = {}
for size in SIZES:
    made = mux(size, "spawn", "--new-window", "--cwd", str(REPO), "--", str(HERE / "person.sh"), "/bin/zsh", "-fc", f"{graphene} watch; sleep 600")
    panes[size] = made.stdout.strip()
time.sleep(3.5)
for step in steps:
    if step.startswith("~"):
        time.sleep(float(step[1:]))
        continue
    step = ast.literal_eval(f"'{step}'")
    for size in SIZES:
        mux(size, "send-text", "--pane-id", panes[size], "--no-paste", step)
    time.sleep(0.7)
time.sleep(1.2)
out = Path(os.environ.get("SHOTS", HERE / "shots")) / phase
out.mkdir(parents=True, exist_ok=True)
from rich.console import Console
from rich.text import Text
for size in SIZES:
    cols = int(size.split("x")[0])
    ans = mux(size, "get-text", "--pane-id", panes[size], "--escapes").stdout
    txt = mux(size, "get-text", "--pane-id", panes[size]).stdout
    mux(size, "kill-pane", "--pane-id", panes[size])
    (out / f"{name}-{size}.ans").write_text(ans)
    (out / f"{name}-{size}.txt").write_text(txt)
    norm = re.sub(r"\x1b\[([0-9;:]*)m", lambda m: "\x1b[" + re.sub(r"(3|4)8:2::(\d+):(\d+):(\d+)", r"\g<1>8;2;\2;\3;\4", m.group(1)) + "m", ans.replace("\x1b(B", ""))
    con = Console(record=True, width=cols, file=io.StringIO(), force_terminal=True, color_system="truecolor")
    for line in norm.rstrip("\n").split("\n"):
        con.print(Text.from_ansi(line), no_wrap=True, crop=True, overflow="crop")
    con.save_svg(str(out / f"{name}-{size}.svg"), title=f"graphene watch · {size} · {phase}")
    print(f"---- {name} {size}"); print(txt.rstrip())
time.sleep(0.5)
