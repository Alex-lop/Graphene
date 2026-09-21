"""`graphene plan` and `graphene node`: the plan in a terminal, for a person and for an agent alike.

Plain text, never wrapped or cut: an agent reads these lines as its contract, and a person greps them.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import typer

from . import plan as P


def register(cli: typer.Typer, root, open_store, fail):
    out = typer.echo

    def checkout() -> Path:
        """The working tree the caller stands in: a worktree is its own checkout, with one shared plan."""
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        return Path(top.stdout.strip()) if top.returncode == 0 and top.stdout.strip() else root()

    def run(operation):
        """One plan operation against the repo's store; a refusal is one plain message and exit 1."""
        with open_store(root()) as store:
            try:
                return operation(store)
            except P.Refused as no:
                fail(str(no), 1)

    def next_lines(store, who: P.Caller, but: str | None = None) -> list[str]:
        """What the caller can do now, read from the plan as it stands at this moment. ``but`` is a
        node the caller has just handed back: it is not sent straight back to it."""
        everything = P.nodes(store)
        by_id = {n.id: n for n in everything}
        held = [n for n in everything if n.state == P.RUNNING and holds(n, who)]
        if held:
            n = held[0]
            return [
                f"next: you hold {n.id} ({n.title}). Finish it with `graphene node done {n.id}`, or hand "
                f"it back with `graphene node release {n.id} --why '…'`"
            ]
        mine = [n for n in P.ready(everything, who) if n.id != but]
        if mine:
            first = mine[0]
            also = f" (also ready: {', '.join(n.id for n in mine[1:])})" if mine[1:] else ""
            return [
                f"next: {first.id}, {first.title}{also}. `graphene node start {first.id}` prints its "
                "contract as it stands now; it may have changed since you last saw it"
            ]
        left = [n for n in everything if n.state in (P.PROPOSED, P.OPEN, P.RUNNING, P.REVIEW)]
        if not left:
            return ["next: nothing; every node is done"]
        why = []
        for n in left:
            reasons = [f"{b.id} ({b.state})" for b in P.unmet(n, by_id)]
            if n.id == but:
                why.append(f"{n.id} is back with the person, who reads why you handed it back")
            elif n.state == P.RUNNING:
                why.append(f"{n.id} is held by {n.executor}")
            elif n.state == P.REVIEW:
                why.append(f"{n.id} waits for a sign-off")
            elif n.state == P.PROPOSED:
                why.append(f"{n.id} is a proposal not yet accepted")
            elif not P.may_take(n, who):
                why.append(f"{n.id} is {n.owner}'s")
            elif reasons:
                why.append(f"{n.id} waits on {', '.join(reasons)}")
        tail = (
            ""
            if who.person
            else " You can stop: the rest waits for a person, and `graphene plan` shows them that"
        )
        return [f"next: nothing is ready for you: {'; '.join(why)}.{tail}"]

    def brief(text: str, node_id: str) -> str:
        """A reason as one table cell: the whole of it is in `node show`."""
        text = " ".join(text.split())
        return text if len(text) <= 100 else f"{text[:97]}… (`graphene node show {node_id}` has all of it)"

    def cut(text: str, wide: int) -> str:
        return text if len(text) <= wide else text[: wide - 1] + "…"

    def scope_cell(n: P.Node, wide: int = 36) -> str:
        """The scope as one table cell: as many globs as fit, then how many more (`node show` has all)."""
        shown: list[str] = []
        for glob in n.scope:
            if shown and len(", ".join([*shown, glob])) > wide - 9:
                return f"{', '.join(shown)}, +{len(n.scope) - len(shown)} more"
            shown.append(glob)
        return ", ".join(shown)

    def holds(n: P.Node, who: P.Caller) -> bool:
        return n.session_id == who.session_id if who.session_id else n.executor == who.name

    def describe(store, n: P.Node, by_id: dict[str, P.Node]) -> str:
        if n.state == P.RUNNING:
            return f"{n.executor} since {(n.started_at or '')[11:16]}Z"
        if n.state == P.REVIEW:
            return f"check passed; waits for a sign-off: `graphene node signoff {n.id}`"
        if n.state == P.PROPOSED:
            needs = f"would wait on {', '.join(n.needs)}; " if n.needs else ""
            return f"proposed by {n.proposed_by}; {needs}`graphene plan accept {n.id}`"
        if n.state == P.OPEN:
            blockers = P.unmet(n, by_id)
            if blockers:
                return "waits on " + ", ".join(
                    f"{b.id} ({b.owner}'s)" if b.owner != P.AGENT else b.id for b in blockers
                )
            last = (store.node_log(n.id, ("started", "released", "reopened")) or [{"kind": ""}])[-1]
            if last["kind"] == "released":
                return f"ready · handed back: {brief(last['detail'].get('why', ''), n.id)}"
            if last["kind"] == "reopened":
                return f"ready · sent back: {brief(last['detail'].get('note', ''), n.id)}"
            return "ready"
        return ""

    FOLD = 12  # lines of tree the plain print shows before finished leaves fold into their sub-goal

    def plan_lines(store, who: P.Caller, everything: bool = False) -> list[str]:
        """The plan as a tree, for a person and an agent alike: what waits on the person first, then
        the goal, then the tree folded to what is still moving. ``everything`` unfolds it."""
        alive = [n for n in P.order(P.nodes(store)) if n.state not in P.GONE]
        if not alive:
            return [
                "no plan yet. `graphene plan goal 'why any of this is being done'` names the root; "
                "`graphene node add 'title' --scope 'src/x/**' --check 'pytest tests/x' [--parent n1] "
                "[--needs n1] [--goal …]` adds a node: from a person it is in the plan at once, from an "
                "agent it is a proposal a person accepts. `graphene plan propose FILE` adds a whole "
                "subtree from JSON"
            ]
        by_id = {n.id: n for n in alive}
        under = P.kids(alive)
        leaves = [n for n in P.leaves(alive) if not n.aside]
        asides = [n for n in alive if n.aside]
        count = {s: sum(1 for n in leaves if n.state == s) for s in (P.RUNNING, P.DONE)}
        lines = [f"the plan: {P.goal(store)}"] if P.goal(store) else []
        head = (
            f"{'' if lines else 'the plan: '}{len(leaves)} lea{'f' if len(leaves) == 1 else 'ves'}, "
            f"{count[P.DONE]} done, {count[P.RUNNING]} running"
        )
        if asides:
            head += f" · {len(asides)} made from a prompt"
        if P.paused(store):
            head += " · PAUSED: nothing starts and nothing is enforced"
        elif leaves and count[P.DONE] == len(leaves):
            head += " · finished; `graphene plan archive` puts it away"
        lines.append(head)
        yours = [n for n in alive if n.state == P.REVIEW]
        yours += [  # a proposed subtree is asked about once, at its top
            n
            for n in alive
            if n.state == P.PROPOSED and (n.parent not in by_id or by_id[n.parent].state != P.PROPOSED)
        ]
        yours += [n for n in P.ready(alive) if n.owner != P.AGENT]
        stuck = [
            n
            for n in alive
            if n.state == P.OPEN and under.get(n.id) and all(c.state == P.DONE for c in under[n.id])
        ]
        if who.person and (yours or stuck):
            ask = {P.PROPOSED: "accept", P.REVIEW: "sign off", P.OPEN: "yours to do"}
            seen: list[str] = []
            told = [
                f"{n.id} ({ask[n.state]}"
                + (f", with the {len(P.below(n.id, alive))} under it" if under.get(n.id) else "")
                + ")"
                for n in yours
                if n.id not in seen and not seen.append(n.id)
            ]
            told += [f"{n.id} (its leaves are done and its own check fails)" for n in stuck]
            lines.append("waiting on a person: " + ", ".join(told))
        wid = max(len(n.id) + 2 * len(P.above(n, by_id)) for n in alive)
        wt = min(44, max(len(n.title) for n in alive))
        wo = max(len(n.owner) for n in alive)
        ws = max(len(scope_cell(n)) for n in alive)
        shown = [n for n in alive if not n.aside or n.state != P.DONE]
        fold = not everything and len(shown) > FOLD

        def row(n: P.Node, depth: int) -> str:
            mine = under.get(n.id, [])
            if mine:
                done = sum(1 for c in P.below(n.id, alive) if not under.get(c.id) and c.state == P.DONE)
                of = sum(1 for c in P.below(n.id, alive) if not under.get(c.id))
                state, what = (
                    ("done" if n.state == P.DONE else n.state if n.state != P.OPEN else "sub-goal"),
                    (f"{done}/{of} done" + (f"; then `{n.check}`" if n.check and n.state != P.DONE else "")),
                )
            else:
                state = "waiting" if n.state == P.OPEN and P.unmet(n, by_id) else n.state
                what = describe(store, n, by_id)
            ident = ("  " * depth + n.id).ljust(wid)
            cells = f"  {ident}  {state.ljust(8)}  {cut(n.title, wt).ljust(wt)}  {n.owner.ljust(wo)}  "
            return f"{cells}{scope_cell(n).ljust(ws)}  ·  {what}".rstrip()

        def walk(parent: str | None, depth: int) -> None:
            folded: list[P.Node] = []
            for n in under.get(parent, []):
                if n.aside and n.state == P.DONE and not everything:
                    continue
                if fold and n.state == P.DONE:
                    folded.append(n)
                    continue
                lines.append(row(n, depth))
                walk(n.id, depth + 1)
            if folded:
                inside = sum(len(P.below(n.id, alive)) for n in folded)
                lines.append(
                    f"  {'  ' * depth}✓ {len(folded)} done here"
                    + (f" (with {inside} under them)" if inside else "")
                    + f": {cut(', '.join(n.id for n in folded), 60)}   (`graphene plan --all` unfolds)"
                )

        walk(None, 0)
        done_asides = [n for n in asides if n.state == P.DONE]
        if done_asides and not everything:
            lines.append(
                f"  ✓ {len(done_asides)} done from a prompt, each with its record "
                f"(`graphene plan --all`; latest: {done_asides[-1].id}, {cut(done_asides[-1].title, 40)})"
            )
        try:
            loose = P.unowned(store, checkout()) if not P.nodes(store, (P.RUNNING,)) else []
        except P.Refused:
            loose = []  # not a checkout git can read: nothing to compare
        if loose:
            listed = ", ".join(loose[:8]) + (f" and {len(loose) - 8} more" if len(loose) > 8 else "")
            lines.append(
                f"changed while no node owned it: {listed}  (yours? `graphene plan ack`; else put it back)"
            )
        if not who.person:
            lines += next_lines(store, who)
        return lines

    def print_plan(store, who: P.Caller, everything: bool = False) -> None:
        for line in plan_lines(store, who, everything):
            out(line)

    def log_line(e: dict, with_node: int = 0, who_wide: int = 16) -> str:
        detail = e["detail"]
        changed = detail.get("changed")  # an edit's field changes (a dict), or an ending's paths (a list)
        fields = changed.items() if isinstance(changed, dict) else ()
        said = (
            detail.get("why")
            or detail.get("note")
            or detail.get("override")
            or (f"by their prompt in the session: {detail.get('prompt', '')!r}" if detail.get("by") else "")
            or detail.get("path")
            or ", ".join(detail.get("outside") or detail.get("paths") or detail.get("unowned") or [])
            or "; ".join(f"{k}: {a!r} -> {b!r}" for k, (a, b) in fields)
            or (f"changed: {', '.join(changed)}" if isinstance(changed, list) and changed else "")
            or detail.get("command")
            or ""
        )
        who = e["actor"] or (f"claude:{e['session_id'][:8]}" if e["session_id"] else "")
        node = f"{e['node_id'].ljust(with_node)}  " if with_node else ""
        return (
            f"  {e['timestamp'][:19]}Z  {node}{e['kind'].ljust(12)}  {who.ljust(who_wide)}  {said}".rstrip()
        )

    # -- graphene plan ----------------------------------------------------------------------------

    plan_cli = typer.Typer(
        help="The shared plan: what will be done, by whom, inside which paths.", invoke_without_command=True
    )
    cli.add_typer(plan_cli, name="plan")

    @plan_cli.callback()
    def show_plan(
        ctx: typer.Context,
        as_json: bool = typer.Option(False, "--json", help="The plan as JSON, the shape `propose` reads."),
        everything: bool = typer.Option(False, "--all", help="Unfold the tree: finished work included."),
    ) -> None:
        """Print the plan as a tree: what waits on you, then what is moving. Finished work is folded."""
        if ctx.invoked_subcommand is not None:
            return
        who = P.caller()
        run(lambda s: out(P.to_json(P.nodes(s))) if as_json else print_plan(s, who, everything))

    @plan_cli.command("goal")
    def goal_(text: str = typer.Argument(None, help="Why any of this is being done, in your words.")) -> None:
        """Say (or read) the root of the tree. Every executor is told it, above its own node."""
        if text is None:
            out(run(P.goal) or "no goal yet: `graphene plan goal 'why any of this is being done'`")
            return
        run(lambda s: P.set_goal(s, text, P.caller()))
        out(f"the plan: {text.strip()}")

    @cli.command()
    def watch(
        everything: bool = typer.Option(False, "--all", help="Unfold the tree: finished work included."),
        every: float = typer.Option(1.0, "--every", help="Seconds between looks at the plan."),
        once: bool = typer.Option(False, "--once", help="Draw one frame and leave (for a script)."),
    ) -> None:
        """The plan, live: leaves light up as they start and finish, and what waits on you is first.
        The same lines `graphene plan` prints, redrawn as the plan changes. Ctrl-C leaves."""
        import time

        from rich.console import Console
        from rich.live import Live
        from rich.text import Text

        who = P.caller()
        colours = {
            "running": "bold yellow",
            "done": "green",
            "ready": "bold",
            "waiting on a person": "bold magenta",
        }  # noqa: E501

        def frame() -> Text:
            with open_store(root()) as store:
                lines = plan_lines(store, who, everything)
                recent = store.node_log()[-6:]
            text = Text("\n".join(lines))
            for word, style in colours.items():
                text.highlight_regex(rf"(?m)^  \s*\S+\s+{word}\b|^{word}:", style)
            text.highlight_regex(r"(?m)^\s+✓.*$", "dim")
            if recent:
                text.append("\n\njust now\n", "dim")
                text.append("\n".join(log_line(e, with_node=8) for e in recent), "dim")
            return text

        console = Console()
        if once:
            console.print(frame())
            return
        try:
            with Live(frame(), console=console, screen=True, auto_refresh=False) as live:
                while True:
                    time.sleep(every)
                    live.update(frame(), refresh=True)
        except KeyboardInterrupt:
            pass

    @plan_cli.command()
    def propose(
        file: str = typer.Argument(
            ..., help="A JSON file ('-' for stdin): {\"nodes\": [{title, scope, check, …}]}"
        ),
    ) -> None:
        """Add several nodes at once from JSON: a file, or '-' for stdin. From an agent they are
        proposals until a person accepts them. One node at a time needs no JSON: `graphene node add`.

        {"nodes": [{"id": "api", "title": "one line", "goal": "what it should achieve",
        "scope": ["src/api/**", "!src/api/gen/**"], "check": "pytest tests/api", "needs": ["schema"],
        "owner": "agent", "signoff": false, "parent": "n3", "children": [ … ]}]}
        (id, goal, needs, owner, signoff, parent and children are optional. A node with children is a
        sub-goal and needs only a title; "parent" puts a node under one already in the plan, which
        is how a leaf too big to do is split)"""
        try:
            raw = json.loads(sys.stdin.read() if file == "-" else Path(file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            fail(f"cannot read {file}: {exc}", 1)
        items = raw.get("nodes") if isinstance(raw, dict) else raw
        if not isinstance(items, list) or not items:
            fail('expected {"nodes": [ … ]} with at least one node', 1)
        who = P.caller()

        def go(store):
            added = P.propose(store, items, who, files=P.tracked(checkout()))
            by_id = {n.id: n for n in P.nodes(store)}
            for n in added:
                out(f"{'  ' * len(P.above(n, by_id))}{n.id}  {n.state}  {n.title}")
            if not who.person:
                out(
                    f"{len(added)} proposed. Nobody can start them until a person runs `graphene plan "
                    "accept`; tell them the plan is ready to look at, and stop"
                )

        run(go)

    @plan_cli.command()
    def accept(ids: list[str] = typer.Argument(None, help="Node ids; none means every proposal.")) -> None:
        """Accept proposals into the plan, and say what an unattended run will and will not reach."""

        def go(store):
            by_id = {n.id: n for n in P.nodes(store)}
            for n in P.accept(store, ids or [], P.caller()):
                out(f"{'  ' * len(P.above(n, by_id))}{n.id}  accepted  {n.title}")
            runs, waits = P.forecast(P.nodes(store))
            out("left alone, agents can reach: " + (", ".join(n.id for n in runs) or "nothing"))
            for n, why in waits:
                out(f"  {n.id} will wait: {'; '.join(why)}")

        run(go)

    @plan_cli.command("log")
    def log_() -> None:
        """Everything that happened on the plan, oldest first; `*` is what belonged to no node."""

        def go(store):
            entries = store.node_log()
            wide = max((len(e["node_id"]) for e in entries), default=1)
            who_wide = max((len(e["actor"] or "") for e in entries), default=16)
            for e in entries:
                out(log_line(e, with_node=wide, who_wide=max(who_wide, 16)))

        run(go)

    @plan_cli.command()
    def archive() -> None:
        """Put finished nodes away. With nothing else left, the plan is no longer in force."""
        gone = run(lambda s: P.archive(s, P.caller()))
        out(f"archived {', '.join(n.id for n in gone)}" if gone else "nothing finished to archive")

    @plan_cli.command()
    def ack() -> None:
        """Accept, as they are, the changes made while no node owned them (they are yours, or fine)."""
        paths = run(lambda s: P.acknowledge(s, checkout(), P.caller()))
        out(f"acknowledged: {', '.join(paths)}" if paths else "nothing had changed between nodes")

    @plan_cli.command()
    def pause() -> None:
        """Suspend the plan: nothing starts, and no write is refused, until `graphene plan resume`."""
        run(lambda s: P.set_paused(s, True, P.caller()))
        out("paused: nothing starts and nothing is enforced until `graphene plan resume`")

    @plan_cli.command()
    def prompts(
        how: str = typer.Argument(
            None, help="'leaf' (default): a prompt you type is a leaf. 'strict': it is not."
        ),
    ) -> None:
        """What a request typed into a session means while the plan is in force. 'leaf': the first
        write of the turn makes a leaf from your prompt, held by that session, and its record says
        what it touched. 'strict': a session that holds no node writes nothing, as in 0.3."""
        if how not in (None, "leaf", "strict"):
            fail("say 'leaf' or 'strict'", 1)

        def go(store):
            if how is not None:
                P._person_only(P.caller(), "changing what a typed prompt means")
                store.set_meta("asides", "off" if how == "strict" else "on")
            return "strict" if store.meta("asides") == "off" else "leaf"

        now = run(go)
        out(
            "strict: a session that holds no node writes nothing; it proposes, and you accept"
            if now == "strict"
            else "leaf: what you type into a session becomes a leaf when the agent first writes for it"
        )

    @plan_cli.command()
    def resume() -> None:
        """Put the plan back in force."""
        run(lambda s: P.set_paused(s, False, P.caller()))
        out("the plan is in force")

    @cli.command("run")
    def run_(
        executor: str = typer.Option(
            None,
            "--with",
            help="The executor: a command that takes a prompt as its last argument. Default: "
            "'claude -p --permission-mode acceptEdits'; e.g. 'codex exec --sandbox workspace-write'.",
        ),
        attempts: int = typer.Option(3, "--attempts", help="How often a refused executor is sent back."),
        node: list[str] = typer.Option(None, "--node", help="Only this node; repeat it."),
        parallel: int = typer.Option(
            1,
            "--parallel",
            help="Leaves at once, each in its own worktree and branch, merged here when clean. "
            "1 (default) works in this checkout and commits nothing.",
        ),
    ) -> None:
        """Run every leaf an agent can reach: one executor per leaf, and Graphene decides what is done."""
        from .run import DEFAULT_WITH, run_parallel, run_plan

        r = root()
        with open_store(r) as store:
            if not P.nodes(store, (P.OPEN, P.RUNNING)):
                fail("nothing to run: the plan has no open node (`graphene plan`)", 1)
            logs = r / ".graphene" / "runs"
            try:
                if parallel > 1:
                    run_parallel(
                        lambda: open_store(r), r, checkout(), parallel, executor or DEFAULT_WITH,
                        attempts, node or None, out, logs,
                    )  # fmt: skip
                else:
                    run_plan(store, checkout(), executor or DEFAULT_WITH, attempts, node or None, out, logs)
            except P.Refused as no:
                fail(str(no), 1)
            for line in next_lines(store, P.caller()):
                out(line)

    # -- graphene node ----------------------------------------------------------------------------

    node_cli = typer.Typer(help="One node of the plan: shape it, take it, finish it, read its record.")
    cli.add_typer(node_cli, name="node")

    def changes(**given) -> dict:
        found = {k: v for k, v in given.items() if v not in (None, [], ())}
        if "needs" in found:
            found["needs"] = [i for i in found["needs"] if i != "none"]
        return found

    @node_cli.command()
    def add(
        title: str = typer.Argument(..., help="One line: what this node is."),
        scope: list[str] = typer.Option(
            None, "--scope", help="A glob it may touch; repeat it. '!glob' excludes."
        ),
        check: str = typer.Option(None, "--check", help="The command that must pass for it to be done."),
        goal: str = typer.Option(None, "--goal", help="What the work should achieve, in a sentence or two."),
        needs: list[str] = typer.Option(None, "--needs", help="A node it waits on; repeat it."),
        owner: str = typer.Option(None, "--owner", help="'agent' (default), 'me', or a person's name."),
        signoff: bool = typer.Option(False, "--signoff", help="A person must also sign it off."),
        node_id: str = typer.Option(None, "--id", help="An id of your choosing; else n1, n2, …"),
        parent: str = typer.Option(
            None, "--parent", help="The node this one helps achieve. Under a leaf, it splits the leaf."
        ),
    ) -> None:
        """Add a node. From a person it is in the plan at once; from an agent it is a proposal.
        With children to come it needs only a title: `graphene node add 'the API' --id api`, then
        `graphene node add … --parent api`."""
        item = changes(
            title=title,
            scope=scope,
            check=check,
            goal=goal,
            needs=needs,
            owner=owner,
            id=node_id,
            parent=parent,
        )
        item["signoff"] = signoff
        [n] = run(lambda s: P.propose(s, [item], P.caller(), files=P.tracked(checkout())))
        out(f"{n.id}  {n.state}  {n.title}")

    @node_cli.command("set")
    def set_(
        node_id: str = typer.Argument(...),
        title: str = typer.Option(None, "--title"),
        scope: list[str] = typer.Option(None, "--scope", help="Replaces the scope; repeat it."),
        check: str = typer.Option(None, "--check"),
        goal: str = typer.Option(None, "--goal"),
        needs: list[str] = typer.Option(None, "--needs", help="Replaces what it waits on; 'none' clears it."),
        owner: str = typer.Option(None, "--owner", help="'agent', 'me', or a person's name."),
        signoff: bool = typer.Option(None, "--signoff/--no-signoff"),
        parent: str = typer.Option(None, "--parent", help="Move it under another node; 'none' is the top."),
    ) -> None:
        """Change a node's contract (a person only). It binds the very next write, and the next start."""
        edits = changes(title=title, scope=scope, check=check, goal=goal, owner=owner, parent=parent)
        if needs:
            edits["needs"] = [i for i in needs if i != "none"]
        if signoff is not None:
            edits["signoff"] = signoff
        if not edits:
            fail(
                "nothing to change: pass --scope, --check, --goal, --needs, --owner, --title or --signoff", 1
            )

        def go(store):
            before = P.get(store, node_id).rev
            node = P.edit(store, node_id, edits, P.caller(), files=P.tracked(checkout()))
            last = store.node_log(node_id, ("edited",))[-1] if node.rev != before else None
            return node, last

        n, last = run(go)
        if last is None:
            out(f"{n.id} is unchanged (revision {n.rev})")
            return
        out(f"{n.id} is now revision {n.rev}:")
        for name, (before, after) in last["detail"]["changed"].items():
            out(f"  {name}: {before!r} -> {after!r}")
        if n.state == P.RUNNING:
            out(
                f"{n.id} is running: {n.executor} was told revision {n.told_rev}. Writes are checked against "
                "the new scope from now on, and `done` against the new check"
            )

    @node_cli.command()
    def drop(node_id: str = typer.Argument(...)) -> None:
        """Take a node out of the plan, with everything under it. Dropping a sub-goal's children
        makes it a leaf again: that is how a split is undone."""
        run(lambda s: P.drop(s, node_id, P.caller()))
        out(f"{node_id} dropped")

    @node_cli.command()
    def start(node_id: str = typer.Argument(...)) -> None:
        """Take a node and print its contract as it stands now."""

        def go(store):
            n = P.start(store, node_id, P.caller(), checkout())
            out(P.contract(n, P.trail(store, n)))
            for note in P.notes(store, n.id):
                out(f"  sent back with: {note}")

        run(go)

    @node_cli.command()
    def done(
        node_id: str = typer.Argument(None, help="The node; may be left out when you hold exactly one."),
        override: str = typer.Option(None, "--override", help="A person's reason for overruling the gate."),
    ) -> None:
        """Finish a node: Graphene runs its check and asks git what changed. Then says what is next."""
        who = P.caller()

        def go(store):
            target = node_id
            if target is None:
                held = [n for n in P.nodes(store, (P.RUNNING,)) if holds(n, who)]
                if len(held) != 1:
                    raise P.Refused("which node? `graphene node done <id>`")
                target = held[0].id
            n = P.finish(store, target, who, override=override, checkout=checkout())
            how = (
                "overruled by a person" if override is not None else "check passed, nothing outside its scope"
            )
            out(f"{n.id} is {'done' if n.state == P.DONE else 'finished and waits for a sign-off'} ({how})")
            for line in next_lines(store, who):
                out(line)

        run(go)

    @node_cli.command()
    def release(
        node_id: str = typer.Argument(...),
        why: str = typer.Option(..., "--why", help="What is in the way. The person reads this."),
    ) -> None:
        """Hand a running node back, saying why. The way out when it cannot be finished as written."""
        who = P.caller()

        def go(store):
            P.release(store, node_id, who, why)
            out(f"{node_id} handed back: {why}")
            for line in next_lines(store, who, but=node_id):
                out(line)

        run(go)

    @node_cli.command("signoff")
    def signoff_(node_id: str = typer.Argument(...)) -> None:
        """A person's say-so: the node is done."""
        run(lambda s: P.signoff(s, node_id, P.caller(), checkout=checkout()))
        out(f"{node_id} is done (signed off)")

    @node_cli.command()
    def reopen(
        node_id: str = typer.Argument(...),
        note: str = typer.Option(..., "--note", help="What is wrong; whoever takes it next is told."),
    ) -> None:
        """Not good enough: send a finished node back, with what is wrong."""
        run(lambda s: P.reopen(s, node_id, P.caller(), note))
        out(
            f"{node_id} is open again. Whoever takes it next is shown your note; the contract itself is "
            "unchanged, so if the note changes what is wanted, say it there too: "
            f"`graphene node set {node_id} --goal …`"
        )

    @node_cli.command()
    def show(node_id: str = typer.Argument(...)) -> None:
        """A node's contract, then its record: who held it, what changed, what was refused, and how
        much of it is verified."""
        from .node_record import node_record, render

        def go(store):
            n = P.get(store, node_id)
            out(P.contract(n, P.trail(store, n)))
            for line in render(node_record(store, root(), n)):
                out(line)
            entries = len(store.node_log(n.id))
            out(f"  every entry, check runs included: `graphene plan log` ({entries} for {n.id})")

        run(go)

    def plan_or_nothing() -> bool:
        """Plain `graphene`: where the work stands, when the repo has a plan. False when it has none."""
        r = root()
        if not (r / ".graphene" / "graphene.db").exists():
            return False
        with open_store(r) as store:
            if not [n for n in P.nodes(store) if n.state not in P.GONE]:
                return False
            print_plan(store, P.caller())
        return True

    return plan_or_nothing
