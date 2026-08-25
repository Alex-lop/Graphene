#!/usr/bin/env python3
"""Drive `graphene demo --live` through its INTERACTIVE edit pause with a scripted operator.

`--plan-edit COMMAND` never touches the prompt path: it runs COMMAND on the export and
continues. A person on camera goes through `input()` instead: the demo prints
"It is exported to <path>." then blocks on "Edit it, then press Enter to compile the
revision: ". This driver takes exactly that path -- it watches the demo's output,
edits the exported file when the prompt appears (with the same transform a rehearsal
uses, so the plan the live planner actually returned is what gets edited), and then
presses Enter. Everything after that is the demo's own code.

    rehearse_interactive_edit.py TRANSCRIPT EDIT_COMMAND [demo args...]

Exit status is the demo's exit status. The transcript is the demo's byte stream with a
few `#driver` timing lines appended by this script, clearly marked.
"""

from __future__ import annotations

import os
import re
import select
import shlex
import subprocess
import sys
import time
from pathlib import Path

# The console folds the long absolute path across lines at 80 columns, so the
# path is everything between the two sentences with all whitespace removed.
EXPORT = re.compile(r"It is exported to\s*(.*?)\.\s*Edit it, then press Enter", re.S)
PROMPT = "press Enter to compile the revision: "


def main() -> int:
    transcript = Path(sys.argv[1])
    edit_command = sys.argv[2]
    demo = ["uv", "run", "--frozen", "graphene", "demo", "--live", *sys.argv[3:]]
    started = time.monotonic()
    marks: list[str] = [f"#driver argv {shlex.join(demo)}"]
    process = subprocess.Popen(
        demo,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )
    assert process.stdout is not None and process.stdin is not None
    fd = process.stdout.fileno()
    buffer = b""
    pressed = False
    with transcript.open("wb") as out:
        while True:
            ready, _, _ = select.select([fd], [], [], 0.25)
            if ready:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                out.write(chunk)
                out.flush()
                buffer += chunk
            text = buffer.decode("utf-8", "replace")
            if not pressed and PROMPT in text:
                match = EXPORT.search(text)
                if match is None:
                    marks.append(
                        "#driver prompt appeared but no export path was printed; aborting"
                    )
                    process.kill()
                    break
                export = Path(re.sub(r"\s+", "", match.group(1)))
                at_prompt = time.monotonic() - started
                marks.append(f"#driver prompt at {at_prompt:.1f}s; export {export}")
                edited = subprocess.run(
                    [*shlex.split(edit_command), str(export)],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                marks.append(
                    f"#driver edit exit={edited.returncode} stdout={edited.stdout.strip()!r} "
                    f"stderr={edited.stderr.strip()[:200]!r}"
                )
                process.stdin.write(b"\n")
                process.stdin.flush()
                pressed = True
                marks.append(
                    f"#driver Enter pressed at {time.monotonic() - started:.1f}s"
                )
            if process.poll() is not None and not ready:
                # drain anything left
                while True:
                    ready, _, _ = select.select([fd], [], [], 0.1)
                    if not ready:
                        break
                    chunk = os.read(fd, 65536)
                    if not chunk:
                        break
                    out.write(chunk)
                break
        code = process.wait()
        marks.append(
            f"#driver demo exit={code} total={time.monotonic() - started:.1f}s"
        )
        out.write(("\n" + "\n".join(marks) + "\n").encode())
    print("\n".join(marks))
    return code


if __name__ == "__main__":
    sys.exit(main())
