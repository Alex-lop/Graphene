"""Explanations: one sentence per changed file, per prompt.

``NullExplainer`` is deterministic and needs nothing. ``ClaudeCodeExplainer`` shells out to
``claude -p`` once per prompt and is the only place Graphene talks to a model.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from typing import Protocol

from .model import FileChange

INSTRUCTION = """You are summarising what a coding agent changed, for the developer who asked for it.
Below is the developer's request and, for each file, the diff the agent produced while working on it
(with line counts; a diff may be truncated or omitted for size, so rely on the counts and effect too).
Return ONLY a JSON object: keys are the file paths exactly as given, values are one sentence each,
present tense, no preamble, saying what changed in that file in service of the request.
If a file's change does not serve the request, the value must be exactly: unrelated to the request
"""
REPLY_SCHEMA = '{"type":"object","additionalProperties":{"type":"string"}}'
MAX_DIFF_CHARS = 4000
MAX_TOTAL_CHARS = 80000


class ExplainError(Exception):
    pass


class Explainer(Protocol):
    name: str

    def explain_prompt(self, prompt_text: str, files: list[FileChange]) -> dict[str, str]: ...


def template(change: FileChange) -> str:
    """The factual sentence used when no model is involved."""
    name = change.path.rsplit("/", 1)[-1]
    counts = f"+{change.added}/−{change.removed}"
    if change.effect == "created":
        defined = f", defining {_join(change.symbols)}" if change.symbols else ""
        return f"Created {name} with {change.added} lines{defined}."
    if change.effect == "deleted":
        return f"Deleted {name} ({change.removed} lines)."
    if change.effect == "reverted":
        return f"Edited {name} and then restored it; no net change."
    if change.strategy == "none":
        return f"Changed {name} through a shell command (no diff available)."
    if change.symbols:
        n = len(change.symbols)
        noun = "definition" if n == 1 else "definitions"
        return f"Edited {n} {noun} in {name}: {_join(change.symbols)} ({counts})."
    total = change.added + change.removed
    return f"Changed {total} line{'s' if total != 1 else ''} in {name} ({counts})."


def _join(names: list[str]) -> str:
    return ", ".join(names[:-1]) + f" and {names[-1]}" if len(names) > 1 else names[0]


class NullExplainer:
    name = "none"

    def explain_prompt(self, prompt_text: str, files: list[FileChange]) -> dict[str, str]:
        return {f.path: template(f) for f in files}


class ClaudeCodeExplainer:
    """One ``claude -p`` call per prompt, covering all of its files."""

    name = "claude"

    def __init__(
        self, model: str | None = None, timeout: float = 120.0, runner=subprocess.run, command: str = "claude"
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.runner = runner
        self.command = command

    def argv(self) -> list[str]:
        args = [
            self.command,
            "-p",
            "--output-format",
            "json",
            "--tools",
            "",
            "--max-turns",
            "1",
            "--no-session-persistence",
            "--setting-sources",
            "",
            "--disable-slash-commands",
            "--strict-mcp-config",
            "--json-schema",
            REPLY_SCHEMA,
        ]
        if self.model:
            args += ["--model", self.model]
        return args

    def request(self, prompt_text: str, files: list[FileChange]) -> str:
        budget = MAX_TOTAL_CHARS
        entries = []
        for f in files:
            diff = "\n".join(line for h in f.hunks for line in h.lines)
            if len(diff) > MAX_DIFF_CHARS:
                diff = diff[:MAX_DIFF_CHARS] + "\n… (diff truncated)"
            if len(diff) > budget:
                diff = "(diff omitted for size)"
            budget -= len(diff)
            entries.append(
                {"path": f.path, "effect": f.effect, "added": f.added, "removed": f.removed, "diff": diff}
            )
        payload = {"request": prompt_text[:4000], "files": entries}
        return INSTRUCTION + "\n" + json.dumps(payload, ensure_ascii=False, indent=1)

    def explain_prompt(self, prompt_text: str, files: list[FileChange]) -> dict[str, str]:
        if not files:
            return {}
        try:
            proc = self.runner(
                self.argv(),
                input=self.request(prompt_text, files),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=tempfile.gettempdir(),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ExplainError(f"could not run {self.command}: {exc.__class__.__name__}") from exc
        if proc.returncode != 0:
            raise ExplainError(f"{self.command} exited {proc.returncode}: {proc.stderr.strip()[:200]}")
        return parse_reply(proc.stdout, [f.path for f in files])


def parse_reply(stdout: str, paths: list[str]) -> dict[str, str]:
    """Pull the per-path sentences out of ``claude -p --output-format json`` output."""
    try:
        envelope = json.loads(stdout)
    except ValueError as exc:
        raise ExplainError("reply was not JSON") from exc
    if not isinstance(envelope, dict) or envelope.get("is_error"):
        raise ExplainError("claude reported an error")
    structured = envelope.get("structured_output")
    if isinstance(structured, dict):
        mapping = structured
    else:
        text = envelope.get("result")
        if not isinstance(text, str):
            raise ExplainError("reply had no result text")
        mapping = _object_in(text)
    wanted = set(paths)
    return {k: v.strip() for k, v in mapping.items() if k in wanted and isinstance(v, str) and v.strip()}


_PAIR = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _object_in(text: str) -> dict:
    """The JSON object in a model reply; when it does not parse, salvage the "key": "value" pairs."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ExplainError("reply contained no JSON object")
    try:
        mapping = json.loads(text[start : end + 1])
    except ValueError:
        mapping = None
    if isinstance(mapping, dict):
        return mapping
    salvaged: dict[str, str] = {}
    for key, value in _PAIR.findall(text[start : end + 1]):
        try:
            salvaged[json.loads(f'"{key}"')] = json.loads(f'"{value}"')
        except ValueError:
            continue
    if not salvaged:
        raise ExplainError("reply JSON did not parse")
    return salvaged


def pick_explainer(choice: str | None) -> tuple[Explainer, str | None]:
    """``--explain`` resolution: explicit choice wins; otherwise claude if on PATH, with a notice."""
    if choice == "none":
        return NullExplainer(), None
    if choice == "claude":
        return ClaudeCodeExplainer(), None
    if choice is not None:
        raise ValueError(f"unknown explainer {choice!r}; use claude or none")
    if shutil.which("claude"):
        return ClaudeCodeExplainer(), "explanations by claude (pass --explain none to skip the model)"
    return NullExplainer(), None
