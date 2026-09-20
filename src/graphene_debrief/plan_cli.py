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

    def next_lines(store, who: P.Caller) -> list[str]:
        """What the caller can do now, read from the plan as it stands at this moment."""
        everything = P.nodes(store)
        by_id = {n.id: n for n in everything}
        mine = P.ready(everything, who)
        if mine:
            first = mine[0]
            also = f" (also ready: {', '.join(n.id for n in mine[1:])})" if mine[1:] else ""
            return [
                f"next: {first.id}, {first.title}{also}. `graphene node start {first.id}` prints its "
                "contract as it stands now; it may have changed since you last saw it"
            ]
        left = [n for n in everything if n.state in (P.PROPOSED, P.OPEN, P.REVIEW)]
        if not left:
            return ["next: nothing; every node is done"]
        why = []
        for n in left:
            reasons = [f"{b.id} ({b.state})" for b in P.unmet(n, by_id)]
            if n.state == P.REVIEW:
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

    def describe(store, n: P.Node, by_id: dict[str, P.Node]) -> str:
        if n.state == P.RUNNING:
            return f"{n.executor} since {(n.started_at or '')[11:16]}Z"
        if n.state == P.REVIEW:
            return f"check passed; waits for a sign-off: `graphene node signoff {n.id}`"
        if n.state == P.PROPOSED:
            return f"proposed by {n.proposed_by}; `graphene plan accept {n.id}`"
        if n.state == P.OPEN:
            blockers = P.unmet(n, by_id)
            if blockers:
                return "waits on " + ", ".join(
                    f"{b.id} ({b.owner}'s)" if b.owner != P.AGENT else b.id for b in blockers
                )
            last = (store.node_log(n.id, ("started", "released", "reopened")) or [{"kind": ""}])[-1]
            if last["kind"] == "released":
                return f"ready · handed back: {last['detail'].get('why', '')}"
            if last["kind"] == "reopened":
                return f"ready · sent back: {last['detail'].get('note', '')}"
            return "ready"
        return ""

    def print_plan(store, who: P.Caller) -> None:
        everything = [n for n in P.order(P.nodes(store)) if n.state not in P.GONE]
        if not everything:
            out(
                "no plan yet. A person adds a node with `graphene node add 'title' --scope 'src/x/**' "
                "--check 'pytest tests/x'`; an agent proposes some with `graphene plan propose plan.json`"
            )
            return
        by_id = {n.id: n for n in everything}
        counts = {s: sum(1 for n in everything if n.state == s) for s in (P.RUNNING, P.DONE)}
        head = f"the plan: {len(everything)} nodes, {counts[P.DONE]} done, {counts[P.RUNNING]} running"
        if P.paused(store):
            head += " · PAUSED: nothing starts and nothing is enforced"
        elif counts[P.DONE] == len(everything):
            head += " · still in force: agents write nothing here until you add a node, archive or pause"
        out(head)
        wid = max(len(n.id) for n in everything)
        wt = min(44, max(len(n.title) for n in everything))
        wo = max(len(n.owner) for n in everything)
        for n in everything:
            state = "waiting" if n.state == P.OPEN and P.unmet(n, by_id) else n.state
            out(
                f"  {n.id.ljust(wid)}  {state.ljust(8)}  {n.title[:wt].ljust(wt)}  {n.owner.ljust(wo)}  "
                f"{', '.join(n.scope)}  ·  {describe(store, n, by_id)}"
            )
        try:
            loose = P.unowned(store, checkout()) if not counts[P.RUNNING] else []
        except P.Refused:
            loose = []  # not a checkout git can read: nothing to compare
        if loose:
            listed = ", ".join(loose[:8]) + (f" and {len(loose) - 8} more" if len(loose) > 8 else "")
            out(f"changed while no node owned it: {listed}  (yours? `graphene plan ack`; else put it back)")
        yours = [n for n in everything if n.state in (P.PROPOSED, P.REVIEW)]
        yours += [n for n in P.ready(everything) if n.owner != P.AGENT]
        if who.person and yours:
            ask = {P.PROPOSED: "accept", P.REVIEW: "sign off", P.OPEN: "yours to do"}
            out("waiting on a person: " + ", ".join(f"{n.id} ({ask[n.state]})" for n in yours))
        if not who.person:
            for line in next_lines(store, who):
                out(line)

    def log_line(e: dict, with_node: bool = False) -> str:
        detail = e["detail"]
        said = (
            detail.get("why")
            or detail.get("note")
            or detail.get("override")
            or detail.get("path")
            or ", ".join(detail.get("outside") or detail.get("paths") or detail.get("unowned") or [])
            or "; ".join(f"{k}: {a!r} -> {b!r}" for k, (a, b) in detail.get("changed", {}).items())
            or detail.get("command")
            or ""
        )
        who = e["actor"] or (f"claude:{e['session_id'][:8]}" if e["session_id"] else "")
        node = f"{e['node_id'].ljust(6)}  " if with_node else ""
        return f"  {e['timestamp'][:19]}Z  {node}{e['kind'].ljust(12)}  {who.ljust(16)}  {said}"

    # -- graphene plan ----------------------------------------------------------------------------

    plan_cli = typer.Typer(
        help="The shared plan: what will be done, by whom, inside which paths.", invoke_without_command=True
    )
    cli.add_typer(plan_cli, name="plan")

    @plan_cli.callback()
    def show_plan(
        ctx: typer.Context,
        as_json: bool = typer.Option(False, "--json", help="The plan as JSON, the shape `propose` reads."),
    ) -> None:
        """Print the plan and where the work stands."""
        if ctx.invoked_subcommand is not None:
            return
        who = P.caller()
        run(lambda s: out(P.to_json(P.nodes(s))) if as_json else print_plan(s, who))

    @plan_cli.command()
    def propose(
        file: str = typer.Argument(
            ..., help="A JSON file ('-' for stdin): {\"nodes\": [{title, scope, check, …}]}"
        ),
    ) -> None:
        """Add nodes from a file. From an agent they are proposals until a person accepts them."""
        try:
            raw = json.loads(sys.stdin.read() if file == "-" else Path(file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            fail(f"cannot read {file}: {exc}", 1)
        items = raw.get("nodes") if isinstance(raw, dict) else raw
        if not isinstance(items, list) or not items:
            fail('expected {"nodes": [ … ]} with at least one node', 1)
        who = P.caller()

        def go(store):
            added = P.propose(store, items, who)
            for n in added:
                out(f"{n.id}  {n.state}  {n.title}")
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
            for n in P.accept(store, ids or [], P.caller()):
                out(f"{n.id}  accepted  {n.title}")
            runs, waits = P.forecast(P.nodes(store))
            out("left alone, agents can reach: " + (", ".join(n.id for n in runs) or "nothing"))
            for n, why in waits:
                out(f"  {n.id} will wait: {'; '.join(why)}")

        run(go)

    @plan_cli.command("log")
    def log_() -> None:
        """Everything that happened on the plan, oldest first; `*` is what belonged to no node."""
        run(lambda s: [out(log_line(e, with_node=True)) for e in s.node_log()])

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
    ) -> None:
        """Run every node an agent can reach: one executor per node, and Graphene decides what is done."""
        from .run import DEFAULT_WITH, run_plan

        r = root()
        with open_store(r) as store:
            if not P.nodes(store, (P.OPEN, P.RUNNING)):
                fail("nothing to run: the plan has no open node (`graphene plan`)", 1)
            run_plan(
                store, checkout(), executor or DEFAULT_WITH, attempts, node or None, out, r / ".graphene/runs"
            )
            for line in next_lines(store, P.Caller("agent", False)):
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
    ) -> None:
        """Add a node. From a person it is in the plan at once; from an agent it is a proposal."""
        item = changes(title=title, scope=scope, check=check, goal=goal, needs=needs, owner=owner, id=node_id)
        item["signoff"] = signoff
        [n] = run(lambda s: P.propose(s, [item], P.caller()))
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
    ) -> None:
        """Change a node's contract (a person only). It binds the very next write, and the next start."""
        edits = changes(title=title, scope=scope, check=check, goal=goal, owner=owner)
        if needs:
            edits["needs"] = [i for i in needs if i != "none"]
        if signoff is not None:
            edits["signoff"] = signoff
        if not edits:
            fail(
                "nothing to change: pass --scope, --check, --goal, --needs, --owner, --title or --signoff", 1
            )
        n = run(lambda s: P.edit(s, node_id, edits, P.caller()))
        out(f"{n.id} is now revision {n.rev}")
        if n.state == P.RUNNING:
            out(
                f"{n.id} is running: {n.executor} was told revision {n.told_rev}. Writes are checked against "
                "the new scope from now on, and `done` against the new check"
            )

    @node_cli.command()
    def drop(node_id: str = typer.Argument(...)) -> None:
        """Take a node out of the plan."""
        run(lambda s: P.drop(s, node_id, P.caller()))
        out(f"{node_id} dropped")

    @node_cli.command()
    def start(node_id: str = typer.Argument(...)) -> None:
        """Take a node and print its contract as it stands now."""

        def go(store):
            n = P.start(store, node_id, P.caller(), checkout())
            out(P.contract(n))
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
                held = [
                    n
                    for n in P.nodes(store, (P.RUNNING,))
                    if (n.session_id == who.session_id if who.session_id else n.executor == who.name)
                ]
                if len(held) != 1:
                    raise P.Refused("which node? `graphene node done <id>`")
                target = held[0].id
            n = P.finish(store, target, who, override=override)
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
            for line in next_lines(store, who):
                out(line)

        run(go)

    @node_cli.command("signoff")
    def signoff_(node_id: str = typer.Argument(...)) -> None:
        """A person's say-so: the node is done."""
        run(lambda s: P.signoff(s, node_id, P.caller()))
        out(f"{node_id} is done (signed off)")

    @node_cli.command()
    def reopen(
        node_id: str = typer.Argument(...),
        note: str = typer.Option(..., "--note", help="What is wrong; whoever takes it next is told."),
    ) -> None:
        """Not good enough: send a finished node back, with what is wrong."""
        run(lambda s: P.reopen(s, node_id, P.caller(), note))
        out(f"{node_id} is open again")

    @node_cli.command()
    def show(node_id: str = typer.Argument(...)) -> None:
        """A node's contract, then its record: who held it, what changed, what was refused, and how
        much of it is verified."""
        from .node_record import node_record, render

        def go(store):
            n = P.get(store, node_id)
            out(P.contract(n))
            for line in render(node_record(store, root(), n)):
                out(line)
            out("  log:")
            for e in store.node_log(n.id):
                out("  " + log_line(e))

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
