"""dev/process/prove/x3_score.py, the harness that scores X3's readers against truth.json: the regex that
finds the leaf whose check passed before any work was rewritten with the words and had no check, so it
dropped the shared form (`a, b: their check (`true`) passes before any work`) and scored every reader who
named one of those leaves wrong."""

import importlib.util
import json
from pathlib import Path

PROVE = Path(__file__).resolve().parents[1] / "dev" / "process" / "prove"
spec = importlib.util.spec_from_file_location("x3_score", PROVE / "x3_score.py")
x3_score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(x3_score)
SHARED = ("a, b: their check (`true`) passes before any work: it would pass with nothing done; "
          "`graphene node set <id> --check '<a real one>'`, or e in `graphene watch`")  # fmt: skip


def test_q4s_truth_is_every_leaf_of_a_shared_check_and_any_of_them_is_a_right_answer(tmp_path):
    (tmp_path / "truth.json").write_text(json.dumps({"red_first": [SHARED]}))
    truth = x3_score.truth_of(tmp_path)
    assert truth["q4"] == {"a", "b"}
    right = {"q4_check_passed_at_base_leaf": "b", "q3_refused_commands_count": None}
    assert x3_score.score(right, truth)["q4"]
    assert not x3_score.score({**right, "q4_check_passed_at_base_leaf": "c"}, truth)["q4"]
    one = SHARED.replace("a, b: their", "one: its")
    (tmp_path / "truth.json").write_text(json.dumps({"red_first": [one]}))
    assert x3_score.truth_of(tmp_path)["q4"] == {"one"}
