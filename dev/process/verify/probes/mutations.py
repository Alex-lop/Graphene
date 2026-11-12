"""Run PR #60's added/extended tests against isolated, deliberately broken source copies."""

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def override(text, name, statement):
    tree = ast.parse(text)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    first = node.body[0]
    at = (
        first.end_lineno
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
        else node.lineno
    )
    lines = text.splitlines(keepends=True)
    lines.insert(at, "    " + statement + "\n")
    return "".join(lines)


def main():
    with tempfile.TemporaryDirectory(prefix="gv-mutations-") as temp:
        base = Path(temp)
        subprocess.run(
            [
                "git",
                "archive",
                "2a2c6fbb",
                "src",
                "tests",
                "editors/vscode/src",
                "editors/vscode/test",
                "editors/vscode/package.json",
            ],
            cwd=ROOT,
            stdout=(base / "source.tar").open("wb"),
            check=True,
        )
        subprocess.run(["tar", "-xf", str(base / "source.tar"), "-C", str(base)], check=True)
        (base / "editors/vscode/node_modules").symlink_to(ROOT / "editors/vscode/node_modules")
        if "--strengthened" in sys.argv:
            shutil.copyfile(ROOT / "tests/test_every_agent.py", base / "tests/test_every_agent.py")
        env = {
            **os.environ,
            "PYTHONPATH": str(base / "src"),
            "ZDOTDIR": "/private/tmp/graphene-verify-empty-zdot",
            "NEBIUS_API_KEY": "fake-key",
            "GRAPHENE_KEYCHAIN": "off",
            "GRAPHENE_TOKENFACTORY_URL": "http://127.0.0.1:9",
        }
        for name in ("CODEX_SESSION_ID", "CODEX_SANDBOX", "CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "AI_AGENT"):
            env.pop(name, None)
        cases = []
        py = "src/graphene_map/"

        def python(test, file, fn, body):
            cases.append(
                (
                    test,
                    py + file,
                    lambda s: override(s, fn, body),
                    [sys.executable, "-m", "pytest", "-q", "tests/test_every_agent.py::" + test],
                )
            )

        for name in (
            "rows_1_to_3_a_write_outside_the_files_is_refused_and_logged_inside_is_let_through",
            "row_2_and_3_a_subagent_or_workflow_agent_cannot_write_outside_through_the_shell_either",
            "row_3_a_workflow_agent_in_its_own_worktree_is_judged_by_the_path_inside_it",
            "row_3_a_call_from_a_session_that_holds_nothing_is_refused_not_let_through",
        ):
            python("test_" + name, "gate.py", "decide", "return None")
        for name in (
            "row_5_another_cli_agent_is_not_stopped_at_the_write_but_the_finish_hands_the_task_back",
            "row_4_codex_runs_the_same_path_with_its_own_command_line",
            "row_6_an_editors_own_agent_with_no_hook_is_not_stopped_and_only_a_held_task_notices",
        ):
            python("test_" + name, "plan.py", "outside_scope", "return []")
        python(
            "test_row_5_a_stand_in_that_writes_only_inside_is_done",
            "plan.py",
            "finish",
            'raise Refused("mutant rejects every finish")',
        )
        python(
            "test_row_6_with_no_task_held_an_editors_agent_is_never_seen_at_all",
            "hooks.py",
            "hook_main",
            'raise RuntimeError("mutant breaks hook intake")',
        )

        def node(label, testfile, pattern, file, before, after):
            def mutate(s):
                assert before in s, (label, before)
                return s.replace(before, after, 1)

            cases.append(
                (
                    label,
                    "editors/vscode/src/" + file,
                    mutate,
                    [
                        "node",
                        "--experimental-strip-types",
                        "--test",
                        "--test-name-pattern=" + pattern,
                        "editors/vscode/test/" + testfile + ".test.ts",
                    ],
                )
            )

        node(
            "commands: new form fields",
            "commands",
            "every mutation",
            "commands.ts",
            'argv.push("--forks", String(value))',
            'argv.push("--wrong", String(value))',
        )
        node(
            "draft keys and blanks",
            "draft",
            "key is never",
            "graph/draft.ts",
            'Boolean(id?.startsWith(" d"))',
            "false",
        )
        node(
            "draft completion",
            "draft",
            "joins the plan when",
            "graph/draft.ts",
            "if (!d.title.trim())",
            "if (false)",
        )
        node(
            "draw validates its parent",
            "graph-check",
            "drawn task passes whole",
            "graph/check.ts",
            "if (parent !== null && !goals.some((g) => g.id === parent)) return undefined;",
            "",
        )
        node(
            "form validates values", "graph-check", "field of the form", "graph/check.ts", "v <= 8", "v <= 9"
        )
        node(
            "planner requires sentence",
            "graph-check",
            "planner fills",
            "graph/check.ts",
            "!r.sentence.trim()",
            "false",
        )
        node(
            "empty Add task is rejected",
            "graph-check",
            "host takes ready",
            "graph/check.ts",
            "if (!text(r.sentence)",
            'if (id === "" && act === "add-under" && !r.sentence) return { type: "act", act, id }; '
            "if (!text(r.sentence)",
        )
        # The replay test must fail on each newly added mutating act, not just one of its older acts.
        for act in ("set", "draw", "add-after", "add-under"):
            node(
                "replay refuses " + act,
                "graph-check",
                "replay.s host runs nothing",
                "graph/check.ts",
                "session.state?.replay && CHANGES.includes(act)",
                f'session.state?.replay && CHANGES.includes(act) && act !== "{act}"',
            )
        node(
            "host answers form and draw",
            "graph-host",
            "field set on the page",
            "graph.ts",
            "if (this.views.has(page))",
            "if (false)",
        )
        node(
            "host answers only requesting page",
            "graph-host",
            "answer goes to the page",
            "graph.ts",
            'void page.postMessage({ type: "said", ...to, ok: r.ok, '
            'line: r.ok ? "" : r.line, made: made ?? undefined });',
            'for (const w of this.views) void w.postMessage({ type: "said", ...to, ok: r.ok, '
            'line: r.ok ? "" : r.line, made: made ?? undefined });',
        )
        node(
            "planned fan",
            "graph-words",
            "fan is drawn before",
            "graph/words.ts",
            "t.planned ?? limit ?? 1",
            "1",
        )
        node(
            "edit semantics", "graph-words", "every state says", "graph/words.ts", "Working now:", "Stopped:"
        )
        node(
            "form replaces Edit button",
            "graph-words",
            "task offers the acts",
            "graph/words.ts",
            "const out: Button[] = [];",
            'const out: Button[] = [{ label: "Edit", act: "set", title: "mutant" }];',
        )
        node(
            "contracts read from plan",
            "state",
            "attempts, approval and owner",
            "state.ts",
            "planned: forks !== null",
            "planned: false && forks !== null",
        )
        node(
            "Exact disables Start",
            "home",
            "Exact: Start waits",
            "home/cards.ts",
            "exact && s.questions.length > 0",
            "false",
        )
        results = []
        for label, file, mutate, command in cases:
            path = base / file
            original = path.read_text()
            control = subprocess.run(command, cwd=base, env=env, capture_output=True, text=True, timeout=90)
            assert control.returncode == 0, (label, control.stdout[-1500:], control.stderr[-500:])
            try:
                path.write_text(mutate(original))
                broken = subprocess.run(
                    command, cwd=base, env=env, capture_output=True, text=True, timeout=90
                )
                verdict = "caught" if broken.returncode else "SURVIVED"
                results.append({"test": label, "mutation": file, "result": verdict})
                print(json.dumps(results[-1]), flush=True)
            finally:
                path.write_text(original)
        print("controls:", len(results), "caught:", sum(r["result"] == "caught" for r in results), flush=True)


if __name__ == "__main__":
    main()
