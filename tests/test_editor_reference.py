"""docs/HOW_IT_WORKS.md on the editor night: the facts cut to fit the cap (42cc11dd) went back once the cap
was raised, and each is still true of the code."""

from pathlib import Path

HOW = (Path(__file__).resolve().parents[1] / "docs/HOW_IT_WORKS.md").read_text(encoding="utf-8")


def test_the_facts_cut_for_the_cap_are_back_and_still_true():
    import typer.main

    from graphene_map.cli import build

    commands = typer.main.get_command(build()).commands
    assert "classic" in {p.name for p in commands["watch"].params}  # `graphene watch --classic` exists
    assert "record" in commands["plan"].commands  # `graphene plan record` exists
    said = " ".join(HOW.split())
    assert "The classic watch shows them on a running leaf's row." in said
    assert "ran from a script: the vendor's rule." in said
    assert "(`\"onFailure\": \"block\"`) and says so." in said
    assert "what it cost. It works for any executor." in said
