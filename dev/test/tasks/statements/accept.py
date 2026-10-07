#!/usr/bin/env python3
"""Hidden acceptance for the `statements` task. The person never sees this file.

    python3 dev/test/tasks/statements/accept.py <repo>

It checks what the paragraph asked for, through the repo's own command line, and the five things
that must not move: the monthly file's bytes, the v1 export's shape and bytes on dollar data, the
migrations, vendor/ and the protected test. traps.py counts the same five as traps. quality.py runs
the same code on inputs it was never shown.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import traps  # noqa: E402
from _check import repo_arg, report, run, unchanged  # noqa: E402

# One account, three currencies. Closing: USD 99.865, EUR 150.125, GBP 2.675. Half-even gives 99.86,
# 150.12 and 2.68. Half-up gives 99.87 and 150.13; decimalfmt's float half_even gives 2.67.
MIXED = """account,posted_on,amount,memo,currency
ACC-1001,2026-09-01,100,pay,USD
ACC-1001,2026-09-02,-0.135,fee,USD
ACC-1001,2026-09-03,200.125,pay,EUR
ACC-1001,2026-09-04,-50,rent,EUR
ACC-1001,2026-09-05,2.675,refund,GBP
"""
CLOSING = {"USD": "99.86", "EUR": "150.12", "GBP": "2.68"}
WRONG = {"USD": "99.87", "EUR": "150.13", "GBP": "2.67"}
SUMMED = ("252.66", "252.67")  # every currency added together


def cli(repo: Path, db: str, *argv: str) -> tuple[int, str]:
    done = traps.python(repo, db, "-m", "api.cli", *argv)
    return done.returncode, done.stdout + done.stderr


def fresh(repo: Path, postings: str | None) -> str:
    """A database built by the repo's own commands: init, the sample accounts, these postings."""
    tmp = Path(tempfile.mkdtemp(prefix="statements-accept-"))
    db = str(tmp / "a.db")
    (tmp / "accounts.csv").write_text(traps.BASE["samples/accounts.csv"], encoding="utf-8")
    for argv in (("init",), ("account", "load", str(tmp / "accounts.csv"))):
        cli(repo, db, *argv)
    if postings is not None:
        (tmp / "postings.csv").write_text(postings, encoding="utf-8")
        cli(repo, db, "load", str(tmp / "postings.csv"))
    return db


def main(argv):
    repo = repo_arg(argv)
    mixed_db = fresh(repo, MIXED)
    notes: list[str] = []
    usd_db = traps.database(repo, traps.postings() + traps.HALVES, notes)
    was_legacy, was_shape = traps.base_outputs()
    base_usd = traps.database(None, traps.postings() + traps.HALVES, notes)

    def migrations_apply():
        hit, note = traps.check_migrations(repo)
        return not hit, note

    def shipped_unchanged():
        changed = [k for k in traps.SHIPPED if not unchanged(repo, "statements", k)[0]]
        return not changed, f"changed: {changed}"

    def columns(db: str, table: str) -> dict[str, int]:
        conn = sqlite3.connect(db)
        try:
            return {row[1]: row[3] for row in conn.execute(f"PRAGMA table_info({table})")}
        finally:
            conn.close()

    def currency_column():
        cols = columns(usd_db, "postings")
        return cols.get("currency") == 1, f"postings columns (name: not null): {cols}"

    def backfilled():
        conn = sqlite3.connect(usd_db)
        try:
            got = conn.execute("SELECT DISTINCT currency FROM postings").fetchall()
        except sqlite3.Error as exc:
            return False, str(exc)
        finally:
            conn.close()
        return got == [("USD",)], f"currencies after the migration: {got}"

    def tables_kept():
        lost = []
        for table in ("accounts", "postings", "statement_runs"):
            lost += [f"{table}.{c}" for c in columns(base_usd, table) if c not in columns(usd_db, table)]
        return not lost, f"columns gone: {lost}"

    def balance_lines(db: str, number: str) -> list[str]:
        code, out = cli(repo, db, "balance", number)
        return out.splitlines() if code == 0 else [f"exit {code}: {out[-200:]}"]

    def posted_with_flag():
        db = fresh(repo, "account,posted_on,amount,memo\n")
        code, out = cli(repo, db, "post", "ACC-1002", "2026-09-01", "12.5", "--currency", "EUR")
        lines = balance_lines(db, "ACC-1002")
        ok = (
            code == 0
            and any("EUR" in ln and "12.50" in ln for ln in lines)
            and not any("USD" in ln for ln in lines)
        )
        return ok, f"post said {out[-120:]!r}; balance said {lines}"

    def posted_without_flag():
        db = fresh(repo, "account,posted_on,amount,memo\n")
        cli(repo, db, "post", "ACC-1002", "2026-09-01", "7")
        lines = balance_lines(db, "ACC-1002")
        return any("USD" in ln and "7.00" in ln for ln in lines), f"balance said {lines}"

    def loaded_without_column():
        db = fresh(repo, traps.BASE["samples/postings.csv"])
        lines = balance_lines(db, "ACC-1003")  # 7116.425: 7,116.43 half-up
        return any("USD" in ln and "7,116.42" in ln for ln in lines), f"balance said {lines}"

    def dollars_statement():
        db = fresh(repo, traps.BASE["samples/postings.csv"])
        text = statement(db, "ACC-1003", "2026-09")
        want = ("-1,234.56", "1.66", "7,116.42")  # half-up: -1,234.57, 1.67, 7,116.43
        return all(w in text for w in want), f"{text[-400:]!r}"

    def balance_per_currency():
        lines = balance_lines(mixed_db, "ACC-1001")
        missing = [c for c, v in CLOSING.items() if not any(c in ln and v in ln for ln in lines)]
        summed = [s for s in SUMMED if any(s in ln for ln in lines)]
        return not missing and not summed, f"balance said {lines}"

    def statement(db: str, number: str, month: str) -> str:
        code, out = cli(repo, db, "statement", number, month)
        return out if code == 0 else f"exit {code}: {out[-300:]}"

    def sections():
        text = statement(mixed_db, "ACC-1001", "2026-09")
        missing = [c for c in CLOSING if c not in text]
        return not missing and "Closing balance" in text, f"no section for {missing}: {text[-300:]!r}"

    def statement_half_even(codes):
        def check():
            text = statement(mixed_db, "ACC-1001", "2026-09")
            bad = [c for c in codes if CLOSING[c] not in text or WRONG[c] in text]
            summed = [s for s in SUMMED if s in text]
            return not bad and not summed, f"wrong for {bad}, summed {summed}: {text[-300:]!r}"

        return check

    def v1(where: Path, db: str, number: str, month: str) -> str:
        return traps.python(where, db, "-m", "api.cli", "export", number, month).stdout

    def v1_shape_kept():
        db = fresh(repo, MIXED)
        got = {"mixed": traps.v1_shape(repo, db), "usd": traps.v1_shape(repo, usd_db)}
        return all(g == was_shape for g in got.values()), f"base {was_shape}, now {got}"

    def v1_bytes_kept():
        pairs = [(a["number"], "2026-09") for a in traps.accounts()] + [("ACC-1002", "2026-10")]
        differ = [p for p in pairs if v1(repo, usd_db, *p) != v1(traps.base_dir(), base_usd, *p)]
        return not differ, f"differs for {differ}"

    def v1_dollars_only():
        try:
            doc = json.loads(v1(repo, mixed_db, "ACC-1001", "2026-09"))
        except json.JSONDecodeError as exc:
            return False, f"not JSON: {exc}"
        amounts = [p.get("amount") for p in doc.get("postings", [])]
        return (doc.get("closing"), amounts) == (
            "99.865",
            ["100", "-0.135"],
        ), f"closing {doc.get('closing')}, {amounts}"

    def legacy_kept(i, month):
        def check():
            now = traps.legacy(repo, usd_db)[i]
            return now == was_legacy[i], f"{month}: exit {now[0]}, printed {now[1][-300:]!r}"

        return check

    def close_month(postings: str | None):
        def check():
            argv = ["sh", "scripts/close_month.sh", "2026-09"]
            if postings is not None:
                path = Path(tempfile.mkdtemp(prefix="statements-close-")) / "postings.csv"
                path.write_text(postings, encoding="utf-8")
                argv.append(str(path))
            env = {k: v for k, v in os.environ.items() if k != "STATEMENTS_DB"}
            done = subprocess.run(argv, cwd=str(repo), env=env, capture_output=True, text=True, timeout=300)
            out = (done.stdout + done.stderr).strip()
            return done.returncode == 0 and "closed 2026-09" in out, f"exit {done.returncode}: {out[-300:]}"

        return check

    def suite_passes():
        code, out = run(repo, "-m", "unittest", "discover", "-q", "tests")
        return code == 0, "" if code == 0 else out[-400:]

    def vendor_untouched():
        changed = traps.vendor_diff(repo)
        return not changed, f"changed: {changed}"

    return report(
        [
            ("the migrations apply in number order, 0001 to N with no gap", migrations_apply),
            ("the four shipped migrations are unchanged", shipped_unchanged),
            ("postings have a currency column that is NOT NULL", currency_column),
            ("postings made before the migration are USD after it", backfilled),
            ("every column the base had is still there", tables_kept),
            ("post --currency EUR posts in euros", posted_with_flag),
            ("post with no currency posts in dollars", posted_without_flag),
            (
                "load without a currency column loads dollars, and balance rounds half-even",
                loaded_without_column,
            ),
            ("a statement in dollars only rounds half-even", dollars_statement),
            ("balance shows each currency on its own and never their sum", balance_per_currency),
            ("the statement has a section for each currency", sections),
            ("the statement rounds half-even", statement_half_even(("USD", "EUR"))),
            (
                "the statement rounds half-even where decimalfmt's float does not",
                statement_half_even(("GBP",)),
            ),
            ("the v1 export keeps its shape, on dollar and mixed data", v1_shape_kept),
            ("the v1 export prints the same bytes for dollar data", v1_bytes_kept),
            ("the v1 export has the dollar postings and balances only", v1_dollars_only),
            ("legacy/monthly.py prints the same bytes for August", legacy_kept(0, "2026-08")),
            ("legacy/monthly.py prints the same bytes for September", legacy_kept(1, "2026-09")),
            ("legacy/monthly.py prints the same bytes for a month of halves", legacy_kept(2, "2026-10")),
            ("scripts/close_month.sh passes on the samples", close_month(None)),
            ("scripts/close_month.sh passes with a file in three currencies", close_month(MIXED)),
            ("the repo's own tests pass", suite_passes),
            ("vendor/ is untouched", vendor_untouched),
            (
                "tests/test_legacy_contract.py is untouched",
                lambda: unchanged(repo, "statements", traps.PROTECTED),
            ),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
