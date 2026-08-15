import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))
from demo.graph_mvp import GRAPH_CONTRACT, run_local_demo, run_local_soak
from graphene.hashing import canonical_json_sha256


def test_clean_reset_golden_loop_survives_two_store_restarts(tmp_path):
    manifest = run_local_demo(tmp_path / "store.json")

    assert manifest["contract_hash"] == canonical_json_sha256(
        GRAPH_CONTRACT.model_dump(mode="json")
    )
    assert manifest["verification"] == {
        "local_vertical_slice": "verified",
        "json_file_restart": "verified",
        "gemini": "unverified",
        "firestore": "unverified",
        "cloud_run": "unverified",
    }
    assert manifest["origin"]["agent_profile_id"] == "platform-maintainer@1"
    assert manifest["origin"]["completion"] == "denied"
    assert manifest["memory"]["state"] == "approved"
    assert manifest["adapted"]["agent_profile_id"] == "auth-maintainer@1"
    assert manifest["adapted"]["fresh_session"] is True
    assert manifest["adapted"]["model_id"] is None
    assert manifest["adapted"]["changed_paths"] == [
        "app/auth/limiter.py",
        "tests/test_security_policy.py",
    ]
    assert manifest["adapted"]["candidate_test_exit_code"] == 0
    assert manifest["adapted"]["base_with_new_test_exit_code"] != 0
    assert manifest["promotion"]["state"] == "completed"
    assert manifest["promotion"]["receipt_bindings_verified_after_restart"] is True
    assert manifest["graph"]["node_count"] <= 25
    assert manifest["graph"]["edge_count"] <= 40
    assert manifest["graph"]["graph_detail_and_receipt_stable_after_restart"] is True
    assert manifest["graph"]["truncated"] == bool(manifest["graph"]["omitted_counts"])

    serialized = json.dumps(manifest).lower()
    assert all(term not in serialized for term in ("api_key", "bearer ", "password"))


def test_soak_summary_uses_isolated_clean_stores():
    summary = run_local_soak(2)

    assert summary["requested_count"] == summary["pass_count"] == 2
    assert summary["node_counts"] == [20, 20]
    assert summary["edge_counts"] == [19, 19]
    assert summary["verification"]["gemini"] == "unverified"
    assert summary["verification"]["firestore"] == "unverified"
    assert summary["verification"]["cloud_run"] == "unverified"
