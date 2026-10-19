"""The cockpit's small shared parts: segments that carry actions, fitting text to a width, agent numbers."""

import colorsys

from graphene_map.cockpit.lines import Line, Seg, ago, fit, pad, seg_at
from graphene_map.cockpit.look import PALETTE, color_of, short, who


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


def test_an_agent_goes_by_a_number_and_its_colour_comes_from_it():
    assert who("2") == "agent 2" and who("") == ""
    assert color_of("1") == PALETTE[0] and color_of("2") == PALETTE[1]
    assert color_of(str(len(PALETTE) + 1)) == PALETTE[0]  # the colours go round
    assert color_of("") == color_of("fox") == color_of("0") == "white"


def test_an_agents_colour_is_never_the_colour_of_a_state_and_reads_on_the_dark_screen():
    """Colour means state: proven green, running amber, quiet orange, need-you purple, came-back and stopped
    red, proposal cyan. An agent's colour is another hue, or one too muted to pass for a state."""
    states = ["#8ab17d", "#90be6d", "#43aa8b", "#e9c46a", "#f9c74f", "#e9a23b", "#c77dff", "#ef476f",
              "#e76f51", "#f3722c", "#4cc9f0"]  # fmt: skip

    def rgb(c):
        return [int(c[i : i + 2], 16) / 255 for i in (1, 3, 5)]

    def lum(c):  # WCAG's relative luminance
        return sum(w * (v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
                   for w, v in zip((0.2126, 0.7152, 0.0722), rgb(c), strict=True))  # fmt: skip

    def hue(c):
        h, _l, s = colorsys.rgb_to_hls(*rgb(c))
        return h * 360, s

    assert 8 <= len(set(PALETTE)) == len(PALETTE) <= 12 and not set(PALETTE) & set(states)
    for c in PALETTE:
        h, s = hue(c)
        apart = min(min(abs(h - hue(x)[0]), 360 - abs(h - hue(x)[0])) for x in states)
        assert s < 0.3 or apart >= 15, (c, apart)
        for ground in ("#0e1014", "#1a2030"):  # the screen, and the selected row
            assert (lum(c) + 0.05) / (lum(ground) + 0.05) >= 4.5, (c, ground)


def test_a_sentence_title_gets_a_short_name():
    assert short("The account's note says what it corrected, and only that") == "account's note says what it"
    assert short("Docs: a long explanation after the colon") == "Docs"
    assert short("") == ""


def test_a_row_takes_the_whole_title_and_only_its_article_and_what_follows_a_colon_are_left_out():
    title = "Store when each invoice was sent to the customer"
    assert short(title, 0) == title and short("The template: Jinja, as the shop has it", 0) == "template"
    assert short(title) == "Store when each invoice was"  # five words, the default: a sub-goal's name


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
