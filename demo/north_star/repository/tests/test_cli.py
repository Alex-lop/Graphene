import io
import json
from pathlib import Path

import pytest

from ledger_service.cli import REPORT_FORMATS, build_parser, main


def movement(
    movement_id: str, sku: str, kind: str, quantity: int, hour: int, note: str = ""
) -> dict[str, object]:
    return {
        "movement_id": movement_id,
        "sku": sku,
        "kind": kind,
        "quantity": quantity,
        "recorded_at": f"2024-05-01T{hour:02d}:00:00+00:00",
        "note": note,
    }


SAMPLE = {
    "items": [
        {"sku": "BOLT-M8", "name": "M8 bolt", "reorder_level": 70},
        {"sku": "NUT-M8", "name": "M8 nut"},
        {"sku": "WASHER", "name": "Washer", "unit": "box"},
    ],
    "movements": [
        movement("m3", "BOLT-M8", "issue", 30, 12, "shipped"),
        movement("m1", "BOLT-M8", "receipt", 100, 9),
        movement("m2", "NUT-M8", "receipt", 40, 10, "ask ops@example.com"),
        movement("m4", "BOLT-M8", "adjustment", -5, 13, "damaged"),
    ],
}


def write_ledger(tmp_path: Path, document: object = SAMPLE) -> str:
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return str(path)


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), out, err)
    return code, out.getvalue(), err.getvalue()


def test_balances(tmp_path: Path) -> None:
    code, out, err = run("--ledger", write_ledger(tmp_path), "balances")
    assert (code, err) == (0, "")
    assert out == "BOLT-M8\t65\teach\nNUT-M8\t40\teach\nWASHER\t0\tbox\n"


def test_audit_is_time_ordered_and_redacted(tmp_path: Path) -> None:
    code, out, _ = run("--ledger", write_ledger(tmp_path), "audit")
    lines = out.splitlines()
    assert code == 0 and len(lines) == 4
    assert lines[0] == "1\t2024-05-01T09:00:00+00:00\tBOLT-M8\treceipt\t+100\t100\t"
    assert lines[1].endswith("\tNUT-M8\treceipt\t+40\t40\task [REDACTED]")
    assert lines[3].endswith("\tadjustment\t-5\t65\tdamaged")
    assert "ops@example.com" not in out


def test_audit_sku_filter(tmp_path: Path) -> None:
    path = write_ledger(tmp_path)
    code, out, _ = run("--ledger", path, "audit", "--sku", "NUT-M8")
    assert code == 0 and out.count("\n") == 1
    assert run("--ledger", path, "audit", "--sku", "NOPE") == (
        1,
        "",
        "error: unknown sku: NOPE\n",
    )


def test_empty_ledger(tmp_path: Path) -> None:
    path = write_ledger(tmp_path, {"items": [], "movements": []})
    assert run("--ledger", path, "balances")[1] == "(no items)\n"
    assert run("--ledger", path, "audit")[1] == "(no movements)\n"


def test_unreadable_or_invalid_documents(tmp_path: Path) -> None:
    code, _, err = run("--ledger", str(tmp_path / "missing.json"), "balances")
    assert code == 1 and err.startswith("error: cannot read ")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    code, _, err = run("--ledger", str(broken), "balances")
    assert code == 1 and "is not valid JSON" in err
    code, _, err = run("--ledger", write_ledger(tmp_path, {"items": 1}), "balances")
    assert code == 1 and err.startswith("error: ledger document needs")


def test_report_formats_are_parsed_and_bounded(tmp_path: Path) -> None:
    parser = build_parser()
    for fmt in REPORT_FORMATS:
        args = parser.parse_args(["--ledger", "x.json", "report", "--format", fmt])
        assert (args.command, args.format) == ("report", fmt)
    with pytest.raises(SystemExit) as info:
        main(["--ledger", write_ledger(tmp_path), "report", "--format", "yaml"])
    assert info.value.code == 2
