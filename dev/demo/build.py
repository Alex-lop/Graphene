"""The rough cut, filmed scene by scene in real time and assembled with the narration as subtitles.

    dev/demo/build.sh                   film a take of the demo run, then assemble dev/demo/rough.mp4
    dev/demo/build.sh --rehearsal       the same take against the stand-ins: dev/demo/rehearsal.mp4
    dev/demo/build.sh --take DIR        assemble a take already filmed (after the storyboard changed)
    dev/demo/build.sh --size 80x24      film at 80x24 instead of 120x36, to see what fits

A take is the demo run of dev/proof/nemotron.sh (rung 7: feeds, `graphene init --planner nemotron
--executor nemotron`, the ask, the board, the prune, R, the leaf that comes back, w, R, the history and
the bill), played by the person's keys in `graphene watch` inside a tmux session of its own
(-L graphene-film). Each scene is a VHS tape under dev/demo/scenes/ that attaches to that session,
presses its keys in real time and leaves. What happens between two scenes is a real wait: the tape's
`# wait:` line names the text the screen must show before it is filmed, and the seconds waited are
cut from the video and said on the screen's top line as the next scene starts.

The take runs against whatever `graphene` is on PATH and whatever the environment gives it: with the
key, Token Factory and Nemotron; with --rehearsal, the scripted stand-in (dev/demo/standin.py, on
tests/fake_tokenfactory.py) and Docker for the sandbox when Docker is up, and the top line of every frame
says "REHEARSAL: scripted stand-in, not live".

rough.mp4 is written only from a take whose run was live, and the run says so itself: `graphene demo
--record` records the plan's store over the whole take, and `graphene demo <it> --once` says "as it
ran, live" only when every model call the run logged went to Token Factory. No flag changes that.
Takes, clips and videos are kept under dev/demo/takes/ and git-ignored: the script is committed,
never the video.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCENES = HERE / "scenes"
TAKES = HERE / "takes"
STORYBOARD = HERE / "STORYBOARD.md"
SOCKET = "graphene-film"  # tmux's own server: never the person's
LIVE = (
    "as it ran, live"  # what `graphene demo --once` says of a run whose every model call was Token Factory's
)
BANNER = "REHEARSAL: scripted stand-in, not live"
# pixels for VHS at FontSize 24 and Padding 20 (measured: 1876 x 1080 is 120 x 36 cells); the video is
# padded to 1920 x 1080 in the terminal's own colour
SIZES = {"120x36": (1876, 1080), "80x24": (1264, 732)}
BACKGROUND = "0x171717"  # VHS's default theme
MARKS = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT", "CODEX_SESSION_ID",
         "CODEX_SANDBOX", "AI_AGENT", "GRAPHENE_AS", "GRAPHENE_NODE", "GRAPHENE_PLANNER", "GEMINI_CLI",
         "CURSOR_AGENT")  # fmt: skip
# before a scene: wait until the screen shows the text, or until the command succeeds in the take's repository
WAIT = re.compile(
    r"^# wait: (?:/(?P<text>.+)/|\$ (?P<command>.+)) up to (?P<minutes>\d+) min; cut: (?P<what>.+)$",
    re.MULTILINE,
)
# a scene filmed only when the screen shows the text, or only when the command runs (from Graphene's checkout)
ONLY = re.compile(r"^# only if: (?:/(?P<text>.+)/|\$ (?P<command>.+))$", re.MULTILINE)
WORDS_A_SECOND = 2.5  # narration read aloud at 150 words a minute


def say(line: str) -> None:
    print(f"build: {line}", flush=True)


# -- the storyboard ------------------------------------------------------------------------------------------


def storyboard(path: Path = STORYBOARD) -> list[dict]:
    """The scenes table: each row's number, name, planned seconds, kind, what is on screen and narration."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 6 or not re.fullmatch(r"\d{2}", cells[0]):
            continue
        seconds = re.fullmatch(r"(\d+) s", cells[2])
        if not seconds:
            raise SystemExit(f"STORYBOARD.md: scene {cells[0]}'s length is not like '12 s': {cells[2]!r}")
        rows.append({"n": cells[0], "name": cells[1], "seconds": int(seconds.group(1)), "kind": cells[3],
                     "screen": cells[4], "narration": cells[5].strip('"“” ')})  # fmt: skip
    return rows


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?:])\s+(?=[A-Z0-9])", text.strip()) if s]


def srt(scenes: list[dict]) -> str:
    """The narration as subtitles: each filmed scene's sentences over its own footage, sharing its seconds
    by their length."""
    cues, at = [], 0.0
    for s in scenes:
        parts = sentences(s["narration"])
        total = sum(len(p) for p in parts) or 1
        start = at
        for p in parts:
            end = start + s["filmed"] * len(p) / total
            cues.append((start, end, p))
            start = end
        at += s["filmed"]

    def stamp(t: float) -> str:
        ms = round(t * 1000)
        return f"{ms // 3_600_000:02}:{ms // 60_000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"

    return "".join(f"{k}\n{stamp(a)} --> {stamp(b)}\n{text}\n\n" for k, (a, b, text) in enumerate(cues, 1))


# -- the stage: the repository, the recorder, the stand-in and the tmux session ------------------------------


def tmux(*args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", "-L", SOCKET, *args], capture_output=True, text=True, **kw)


def screen() -> str:
    return tmux("capture-pane", "-p", "-t", "film").stdout


def marked(env: dict) -> str | None:
    return next((m for m in MARKS if env.get(m)), None)


class Stage:
    def __init__(self, take: Path, rehearsal: bool, size: str):
        self.take, self.rehearsal, self.size = take, rehearsal, size
        self.dir = Path(os.environ.get("FILM_DIR") or Path.home() / "graphene-film")
        self.repo = self.dir / "feeds"
        self.fake = self.recorder = None

    def env(self) -> dict:
        env = dict(os.environ)
        editor = "vim -u NONE -N"  # the prune is typed in a plain vim, on camera
        env |= {
            "VISUAL": editor,
            "EDITOR": editor,
            "COLORTERM": "truecolor",
            "PS1": "$ ",
            "BASH_SILENCE_DEPRECATION_WARNING": "1",
            "FILM_SELF": str(ROOT),
        }  # fmt: skip  (Graphene's checkout)
        if not self.rehearsal:
            # live, the spend is reserved in the practice ladder's ledger under rung 7's cap, unless the shell
            # already names a ledger and a cap (the night's)
            ledger = Path(env.get("GRAPHENE_LEDGER") or ROOT / ".graphene" / "practice" / "ledger.jsonl")
            ledger.parent.mkdir(parents=True, exist_ok=True)
            env["GRAPHENE_LEDGER"] = str(ledger)
            env.setdefault("GRAPHENE_SPEND_CAP_USD", f"{spent(ledger) + 3.0:.4f}")
            return env
        # the stand-ins, as the practice ladder's dry run sets them: no key, no project, no agent's marks
        env = {k: v for k, v in env.items() if k not in MARKS and not k.startswith(("NEBIUS_", "CONTREE_"))}
        env = {k: v for k, v in env.items() if not k.startswith("GRAPHENE_") or k == "GRAPHENE_KEYCHAIN"}
        env |= self.fake.env() | {"CONTREE_HOME": str(self.take / "no-contree"), "GRAPHENE_KEYCHAIN": "off"}
        if docker_runs():
            env["GRAPHENE_SANDBOX"] = "docker"
        return env

    def __enter__(self) -> Stage:
        if not self.rehearsal and marked(os.environ):
            mark = marked(os.environ)
            raise SystemExit(
                f"build: an agent's mark ({mark}) is set in this shell: a live take spends "
                "your key, so it is yours to run, in a terminal of your own"
            )
        if self.repo.exists():
            if not (self.dir / ".graphene-film").exists():
                raise SystemExit(f"build: {self.repo} exists and is not a take's: name another FILM_DIR")
            shutil.rmtree(self.repo)
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / ".graphene-film").write_text("made by dev/demo/build.py; each take replaces feeds/\n")
        if self.rehearsal:
            sys.path[:0] = [str(ROOT / "tests"), str(HERE)]
            from fake_tokenfactory import Fake
            from standin import reply

            self.fake = Fake([reply] * 100_000).__enter__()
        env = self.env()
        if tmux("has-session").returncode == 0:
            raise SystemExit(f"build: a take's tmux is still running: tmux -L {SOCKET} kill-server")
        run([sys.executable, ROOT / "dev" / "test" / "make_task.py", "feeds", self.repo], env)
        # the recorder starts before init, as nemotron.sh starts it: it waits for the store
        self.recorder = subprocess.Popen(["graphene", "demo", "--record", str(self.take / "run.jsonl")],
                                         cwd=self.repo, env=env, stdout=subprocess.DEVNULL,
                                         stderr=open(self.take / "recorder.log", "w"))  # fmt: skip
        # EXECUTOR, as nemotron.sh reads it: 'nemotron --placement local' while Sandboxes refuse the project
        docker = env.get("GRAPHENE_SANDBOX") == "docker"
        executor = os.environ.get("EXECUTOR") or ("nemotron --placement sandbox" if docker else "nemotron")
        run(["graphene", "init", "--planner", "nemotron", "--executor", executor], env, cwd=self.repo)
        cols, rows = self.size.split("x")
        # bash started by tmux itself, not through the login shell: a shell's startup files (~/.zshenv) would
        # put their own key over the stage's
        tmux("-f", "/dev/null", "new-session", "-d", "-s", "film", "-x", cols, "-y", str(int(rows) - 1),
             "-c", str(self.repo), "/bin/bash", "--norc", "--noprofile", env=env)  # fmt: skip
        for option in (["escape-time", "0"], ["status", "on"], ["status-position", "top"],
                       ["status-interval", "1"], ["default-terminal", "xterm-256color"],
                       ["window-size", "latest"], ["status-right-length", "120"],
                       ["status-left-length", "60"], ["status-right", ""], ["window-status-format", ""],
                       ["window-status-current-format", ""]):  # fmt: skip
            tmux("set", "-g", *option)
        tmux("set", "-as", "terminal-features", ",xterm-256color:RGB")
        # Ctrl+B M, pressed by each tape as its footage starts and ends: the clock the clip is played to
        stamp = f"python3 -c 'import time; print(time.time())' >> '{self.take / 'marks'}'"
        tmux("bind-key", "M", "run-shell", stamp)
        if self.rehearsal:
            tmux("set", "-g", "status-style", "bg=red,fg=white,bold")
            tmux("set", "-g", "status-left", f" {BANNER} ")
        else:
            tmux("set", "-g", "status-style", "bg=#171717,fg=#a0a0a0")
            tmux("set", "-g", "status-left", "")
        tmux("send-keys", "-t", "film", "clear", "Enter")
        return self

    def __exit__(self, *exc) -> None:
        tmux("kill-server")
        if self.recorder is not None:
            self.recorder.send_signal(signal.SIGTERM)
            try:
                self.recorder.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.recorder.kill()
        if self.fake is not None:
            self.fake.__exit__(None, None, None)


def run(args: list, env: dict, cwd: Path | None = None) -> None:
    done = subprocess.run([str(a) for a in args], env=env, cwd=cwd, capture_output=True, text=True)
    if done.returncode:
        raise SystemExit(
            f"build: `{' '.join(map(str, args))}` failed: {(done.stdout + done.stderr).strip()[-400:]}"
        )


def docker_runs() -> bool:
    return (
        shutil.which("docker") is not None
        and subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    )


def spent(ledger: Path) -> float:
    total = 0.0
    for line in ledger.read_text(encoding="utf-8").splitlines() if ledger.exists() else []:
        try:
            total += float(json.loads(line).get("dollars") or 0)
        except (ValueError, AttributeError):
            continue
    return total


# -- filming -------------------------------------------------------------------------------------------------


def wait_for(wait: re.Match, repo: Path, env: dict) -> float:
    """Seconds until the stage's screen shows the wait's text, or its command succeeds in the take's
    repository; a take that never gets there stops, saying what the screen showed."""
    began, minutes = time.monotonic(), int(wait["minutes"])
    found = re.compile(wait["text"], re.MULTILINE) if wait["text"] else None
    while not (found.search(screen()) if found else ran(wait["command"], repo, env)):
        if time.monotonic() - began > minutes * 60:
            raise SystemExit(f"build: waited {minutes} min for {wait['text'] or wait['command']}; the screen "
                             f"shows:\n{screen()}")  # fmt: skip
        time.sleep(0.5)
    return time.monotonic() - began


def ran(command: str, cwd: Path, env: dict) -> bool:
    return subprocess.run(command, shell=True, cwd=cwd, env=env, capture_output=True).returncode == 0


def label(seconds: float, what: str) -> str:
    m, s = divmod(round(seconds), 60)
    return f" cut {m}:{s:02} of {what} "


def label_the_cut(seconds: float, what: str) -> threading.Thread:
    """The top line says what was cut, from the moment the scene's terminal attaches, for six seconds."""
    tmux("set", "-g", "status-right", label(seconds, what))
    tmux("set", "-g", "status-right-style", "bg=yellow,fg=black,bold")

    def clear() -> None:
        while not tmux("list-clients").stdout.strip():
            time.sleep(0.1)
        time.sleep(6)
        tmux("set", "-g", "status-right", "")

    thread = threading.Thread(target=clear, daemon=True)
    thread.start()
    return thread


def film(tape: Path, out: Path, size: str, env: dict) -> None:
    width, height = SIZES[size]
    text = tape.read_text(encoding="utf-8")
    text = re.sub(r"^Output .*$", f'Output "{out}"', text, flags=re.MULTILINE)
    text = re.sub(r"^Set Width .*$", f"Set Width {width}", text, flags=re.MULTILINE)
    text = re.sub(r"^Set Height .*$", f"Set Height {height}", text, flags=re.MULTILINE)
    copy = out.with_suffix(".tape")
    copy.write_text(text, encoding="utf-8")
    done = subprocess.run(["vhs", str(copy)], env=env, capture_output=True, text=True)
    if done.returncode or not out.exists():
        raise SystemExit(f"build: vhs {tape.name} failed: {(done.stdout + done.stderr).strip()[-600:]}")


def unmet(only: re.Match | None, env: dict) -> str:
    """Why a scene's `# only if:` is not met, or "" when it is (or it has none)."""
    if only is None:
        return ""
    if only["text"]:
        return "" if re.search(only["text"], screen()) else f"the screen did not show /{only['text']}/"
    return "" if ran(only["command"], ROOT, env) else f"`{only['command']}` did not run here"


def stamps(take: Path) -> list[float]:
    time.sleep(0.3)  # the last mark's run-shell, done
    marks = take / "marks"
    return [float(x) for x in marks.read_text().split()] if marks.exists() else []


def real_time(raw: Path, clip: Path, marks: list[float]) -> None:
    """The clip at the length it took: VHS plays every frame it caught at its frame rate, and catches fewer
    than that when the machine is busy, which would play the footage faster than it happened."""
    took = marks[-1] - marks[0] if len(marks) >= 2 else 0
    stretch = took / seconds_of(raw) if took > 0 else 1.0
    done = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-vf",
                           f"setpts=PTS*{stretch:.5f}", "-r", "30", "-c:v", "libx264", "-crf", "16",
                           "-pix_fmt", "yuv420p", str(clip)], capture_output=True, text=True)  # fmt: skip
    if done.returncode:
        raise SystemExit(f"build: ffmpeg could not retime {raw.name}: {done.stderr.strip()[-400:]}")


def seconds_of(clip: Path) -> float:
    said = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                           str(clip)], capture_output=True, text=True)  # fmt: skip
    return float(said.stdout.strip() or 0)


def shoot(take: Path, rehearsal: bool, size: str) -> None:
    board = {s["n"]: s for s in storyboard()}
    tapes = sorted(SCENES.glob("[0-9][0-9]-*.tape"))
    missing = [t.name for t in tapes if t.name[:2] not in board] + [n for n in board if not
               any(t.name.startswith(n + "-") for t in tapes)]  # fmt: skip
    if missing:
        raise SystemExit(f"build: the storyboard and the tapes disagree: {', '.join(missing)}")
    shot = []
    with Stage(take, rehearsal, size) as stage:
        began = time.strftime("%Y-%m-%d %H:%M:%S")
        stated = {"rehearsal": rehearsal, "size": size, "repo": str(stage.repo), "began": began}
        (take / "stage.json").write_text(json.dumps(stated))
        env = {**stage.env(), "FILM": str(take)}
        (take / "attach").write_text(f"exec tmux -L {SOCKET} attach -t film\n")
        for tape in tapes:
            text, n = tape.read_text(encoding="utf-8"), tape.name[:2]
            waited, what = 0.0, ""
            for w in WAIT.finditer(text):
                waited += wait_for(w, stage.repo, env)
                what = w["what"]
            no = unmet(ONLY.search(text), env)
            if no:
                say(f"scene {n} not filmed: {no}")
                shot.append({"n": n, "skipped": no, "cut": waited})
                continue
            if waited >= 2:
                label_the_cut(waited, what)
            clip, raw = take / f"{tape.stem}.mp4", take / f"{tape.stem}.raw.mp4"
            began, marks = time.monotonic(), stamps(take)
            film(tape, raw, size, env)
            real_time(raw, clip, stamps(take)[len(marks) :])
            tmux("set", "-g", "status-right", "")
            took = round(time.monotonic() - began, 1)
            shot.append({"n": n, "clip": clip.name, "cut": round(waited, 1),
                         "filmed": round(seconds_of(clip), 2), "captured": round(seconds_of(raw), 2),
                         "took": took})  # fmt: skip
            say(
                f"scene {n} filmed: {shot[-1]['filmed']} s"
                + (f", after {waited:.0f} s cut" if waited >= 2 else "")
            )
        (take / "screen-at-the-end.txt").write_text(screen())
    (take / "scenes.json").write_text(json.dumps(shot, indent=1))


# -- the cut -------------------------------------------------------------------------------------------------


def shown(take: Path) -> str:
    """What made the take's run, as the run's own recording says it (`graphene demo --once`, its top line)."""
    rec = take / "run.jsonl"
    if not rec.exists():
        return "no recording of the run"
    said = subprocess.run(["graphene", "demo", str(rec), "--once"], capture_output=True, text=True,
                          env={k: v for k, v in os.environ.items()
                               if not k.startswith("NEBIUS_")})  # fmt: skip
    top = next((ln.strip() for ln in said.stdout.splitlines() if "replay" in ln), "")
    return top or f"`graphene demo --once` said nothing readable (exit {said.returncode})"


def assemble(take: Path, rehearsal: bool) -> Path:
    stage = json.loads((take / "stage.json").read_text())
    if rehearsal and not stage["rehearsal"]:
        raise SystemExit(
            f"build: {take.name} was filmed live, without the rehearsal's top line: film one with --rehearsal"
        )
    top = shown(take)
    if not rehearsal and LIVE not in top:
        raise SystemExit(
            f"build: rough.mp4 not written: the take's run was not live; its recording says: {top}\n"
            f"       `dev/demo/build.sh --take {take} --rehearsal` makes a rehearsal of a rehearsal take"
        )
    board = {s["n"]: s for s in storyboard()}
    shot = [s | board[s["n"]] for s in json.loads((take / "scenes.json").read_text()) if "clip" in s]
    subtitles = take / "narration.srt"
    subtitles.write_text(srt(shot), encoding="utf-8")
    listing = take / "clips.txt"
    listing.write_text("".join(f"file '{take / s['clip']}'\n" for s in shot))
    size = "" if stage["size"] == "120x36" else f"-{stage['size']}"
    out = HERE / f"{'rehearsal' if rehearsal else 'rough'}{size}.mp4"
    frame = f"scale=-2:1080,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color={BACKGROUND},format=yuv420p"
    done = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                           "-i", str(listing), "-i", str(subtitles), "-map", "0:v", "-map", "1:s",
                           "-vf", frame, "-c:v", "libx264",
                           "-crf", "18", "-r", "30", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng",
                           "-disposition:s:0", "default", str(out)],
                          capture_output=True, text=True)  # fmt: skip
    if done.returncode:
        raise SystemExit(f"build: ffmpeg failed: {done.stderr.strip()[-600:]}")
    shutil.copy(subtitles, out.with_suffix(".srt"))
    report(take, shot, top, out)
    return out


def report(take: Path, shot: list[dict], top: str, out: Path) -> None:
    rows = json.loads((take / "scenes.json").read_text())
    say(f"the run: {top}")
    total = 0.0
    for r in rows:
        planned = next(s for s in storyboard() if s["n"] == r["n"])
        if "clip" not in r:
            say(f"  {r['n']} {planned['name']:<24} not filmed ({r['skipped']})")
            continue
        words = len(planned["narration"].split())
        fast = " · narration too long to say in it" if words > r["filmed"] * WORDS_A_SECOND else ""
        cut = f" · {r['cut']:.0f} s cut before it" if r["cut"] >= 2 else ""
        filmed = f"{r['filmed']:6.1f} s (planned {planned['seconds']} s)"
        say(f"  {r['n']} {planned['name']:<24} {filmed}{cut}{fast}")
        total += r["filmed"]
    say(f"  total {total:.1f} s" + (" · OVER three minutes" if total > 180 else " · under three minutes"))
    say(f"wrote {out.relative_to(ROOT)} and {out.with_suffix('.srt').relative_to(ROOT)}; play: open {out}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="dev/demo/build.sh", description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--rehearsal", action="store_true", help="the stand-ins; writes rehearsal.mp4, never rough.mp4"
    )
    ap.add_argument("--take", type=Path, help="a take already filmed: assemble it only")
    ap.add_argument("--size", choices=sorted(SIZES), default="120x36")
    a = ap.parse_args(argv)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))  # the stage is taken down as on Ctrl-C
    for tool in ("vhs", "ffmpeg", "ffprobe", "tmux", "graphene"):
        if shutil.which(tool) is None:
            raise SystemExit(f"build: {tool} is not on PATH")
    take = a.take
    if take is None:
        take = TAKES / (time.strftime("%Y%m%d-%H%M%S") + ("-rehearsal" if a.rehearsal else "") +
                        ("" if a.size == "120x36" else f"-{a.size}"))  # fmt: skip
        take.mkdir(parents=True)
        say(f"filming into {take.relative_to(ROOT)}" + (" (rehearsal: the stand-ins)" if a.rehearsal else ""))
        shoot(take, a.rehearsal, a.size)
    assemble(take.resolve(), a.rehearsal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
