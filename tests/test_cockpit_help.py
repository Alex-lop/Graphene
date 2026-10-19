"""`?`: every key with one verb, the words the screens use, on one screen of 80 by 24."""

from graphene_map.cockpit.help import help_text


def test_the_help_says_task_and_names_each_key_by_the_one_verb_the_screens_use():
    said = help_text(76).plain  # the words' room in the help's box at 80 columns
    keys = {line[10:16].strip(): line[16:] for line in said.splitlines() if line[10:16].strip()}
    assert [keys[k].split(":")[0].split(";")[0] for k in "wi"] == ["widen", "details"]
    assert keys["x"].startswith("hand back a running task; reopen")
    assert "accept every proposal" in keys["d A"] and "the cockpit, the graph, the map" in keys["c g m"]
    assert said.count("leaf") == 1 and "call a task a leaf" in said  # said once, for the commands
    assert all(len(line) <= 76 for line in said.splitlines()) and len(said.splitlines()) <= 22
