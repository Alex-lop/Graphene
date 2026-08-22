"""Command line: ``python -m ledger_service --ledger FILE <command>``.

Commands: ``balances``, ``audit [--sku SKU]`` (notes redacted), and
``report --format json|markdown`` (renderers not implemented yet).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import IO

from .ledger import DocumentError, Ledger, LedgerError
from .redact import DEFAULT_POLICY, RedactionPolicy, redact_text

REPORT_FORMATS = ("json", "markdown")
EXIT_OK = 0
EXIT_FAILURE = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ledger_service",
        description="Inspect a stock ledger document.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--ledger",
        required=True,
        type=Path,
        metavar="FILE",
        help="JSON document with 'items' and 'movements' lists",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("balances", help="print on-hand quantity per item")
    audit = commands.add_parser("audit", help="print the ordered audit trail")
    audit.add_argument("--sku", help="restrict the trail to one item")
    report = commands.add_parser("report", help="render a status report")
    report.add_argument("--format", choices=REPORT_FORMATS, required=True)
    return parser


def load_ledger(path: Path) -> Ledger:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise DocumentError(f"cannot read {path}: {error.strerror}") from error
    except ValueError as error:
        raise DocumentError(f"{path} is not valid JSON: {error}") from error
    return Ledger.from_document(document)


def render_balances(ledger: Ledger) -> str:
    lines = [
        f"{sku}\t{quantity}\t{ledger.item(sku).unit}"
        for sku, quantity in ledger.balances().items()
    ]
    return "".join(f"{line}\n" for line in lines) or "(no items)\n"


def render_audit(ledger: Ledger, sku: str | None, policy: RedactionPolicy) -> str:
    lines = []
    for entry in ledger.audit_trail(sku):
        movement = entry.movement
        lines.append(
            "\t".join(
                (
                    str(entry.sequence),
                    movement.recorded_at,
                    movement.sku,
                    movement.kind.value,
                    f"{movement.delta:+d}",
                    str(entry.balance_after),
                    redact_text(movement.note, policy),
                )
            )
        )
    return "".join(f"{line}\n" for line in lines) or "(no movements)\n"


def render_report(ledger: Ledger, fmt: str, policy: RedactionPolicy) -> str:
    """Render a status report in ``fmt`` (one of ``REPORT_FORMATS``)."""
    raise NotImplementedError("report renderers are added by the mission")


def main(
    argv: list[str] | None = None,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
) -> int:
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    args = build_parser().parse_args(argv)
    try:
        ledger = load_ledger(args.ledger)
        if args.command == "balances":
            text = render_balances(ledger)
        elif args.command == "audit":
            text = render_audit(ledger, args.sku, DEFAULT_POLICY)
        else:
            text = render_report(ledger, args.format, DEFAULT_POLICY)
    except LedgerError as error:
        print(f"error: {error}", file=err)
        return EXIT_FAILURE
    out.write(text)
    return EXIT_OK
