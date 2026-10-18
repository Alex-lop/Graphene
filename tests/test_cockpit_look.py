"""The cockpit's small shared parts: segments that carry actions, fitting text to a width, agent names."""

from graphene_map.cockpit.lines import Line, Seg, ago, fit, pad, seg_at
from graphene_map.cockpit.look import NAMES, color_of, name_for, short


def test_a_click_finds_the_segment_under_it_and_its_action():
    line = Line([Seg("ab", "", ""), Seg("cd", "bold", "take"), Seg("ef")])
    assert seg_at(line, 0).text == "ab" and seg_at(line, 2).action == "take" and seg_at(line, 5).text == "ef"
    assert seg_at(line, 6) is None
    assert line.plain() == "abcdef" and line.width() == 6


def test_text_is_fitted_with_an_ellipsis_and_lines_are_padded_to_the_width():
    assert fit("short", 10) == "short" and fit("a longer sentence", 8) == "a longe…"
    assert sum(len(s.text) for s in pad([Seg("abc")], 10)) == 10
    assert sum(len(s.text) for s in pad([Seg("abcdef")], 3)) == 6  # never cut, only padded


def test_seconds_read_as_seconds_then_minutes():
    assert ago(12.6) == "12s" and ago(89) == "89s" and ago(150) == "2m"


def test_an_agent_keeps_its_name_and_two_running_agents_never_share_one():
    assert name_for("session-1", set()) == name_for("session-1", set())
    first = name_for("session-1", set())
    second = name_for("session-1", {first})
    assert second != first and second in NAMES
    assert color_of(first).startswith("#") and color_of("nobody") == "white"


def test_a_sentence_title_gets_a_short_name():
    assert short("The account's note says what it corrected, and only that") == "account's note says what it"
    assert short("Docs: a long explanation after the colon") == "Docs"
    assert short("") == ""


def test_a_short_name_ends_where_a_phrase_ends():
    assert short("Add an XML reader and a test for it") == "Add an XML reader"
    assert short("Reject price 0 in validation") == "Reject price 0 in validation"
    assert short("Wire the reader - then check it") == "Wire the reader"
    assert short("users returns ids: each user has its id") == "users returns ids"
    assert short("The whole of it") == "whole of it"


def test_a_name_does_not_end_on_a_possessive_that_wants_its_noun():
    assert short("The reference names the three views' files again, as a test pins them") == (
        "reference names the three views' files"
    )
    assert short("Fix Alex's bug in the parser and the lexer") == "Fix Alex's bug"
