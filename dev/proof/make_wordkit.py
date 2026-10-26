#!/usr/bin/env python3
"""wordkit, a small word-counting library with a CLI and tests, for `dev/proof/auto.sh` and the recording
`graphene demo --auto` replays: three wishes that can run at once, one file and one test file each, and an
old test (a hyphenated word counts as two) that one of them breaks while its own check passes.

    dev/proof/make_wordkit.py <dir>

unittest only, so a check needs nothing installed.
"""

import pathlib
import subprocess
import sys
import textwrap

d = pathlib.Path(sys.argv[1])
d.mkdir(parents=True)
files = {
    ".gitignore": "__pycache__/\n*.pyc\n.graphene/\n.claude/\n",
    "README.md": "# wordkit\n\nCount words in text files.\n\n```\npython3 -m wordkit.cli notes.txt\n```\n\n"
    "Run the tests with `python3 -m unittest`.\n",
    "wordkit/__init__.py": '"""wordkit: count words in text."""\n',
    "wordkit/clean.py": textwrap.dedent('''\
        """Text clean-up before counting."""
        import re

        _WORD = re.compile(r"[a-z0-9']+")


        def normalize(text: str) -> str:
            """Lower-case the text and keep only words, separated by single spaces."""
            return " ".join(_WORD.findall(text.lower()))
        '''),
    "wordkit/count.py": textwrap.dedent('''\
        """Counting words."""
        from collections import Counter

        from wordkit.clean import normalize


        def words(text: str) -> list[str]:
            return normalize(text).split()


        def word_count(text: str) -> int:
            return len(words(text))


        def top_words(text: str, n: int) -> list[tuple[str, int]]:
            """The n most common words, most common first; ties in the order they first appear."""
            return Counter(words(text)).most_common(n)
        '''),
    "wordkit/cli.py": textwrap.dedent('''\
        """python3 -m wordkit.cli FILE: print how many words FILE has."""
        import argparse
        import sys

        from wordkit.count import word_count


        def main(argv: list[str] | None = None) -> int:
            parser = argparse.ArgumentParser(prog="wordkit")
            parser.add_argument("file")
            args = parser.parse_args(argv)
            with open(args.file, encoding="utf-8") as f:
                text = f.read()
            print(f"{word_count(text)} words")
            return 0


        if __name__ == "__main__":
            sys.exit(main())
        '''),
    "tests/__init__.py": "",
    "tests/test_clean.py": textwrap.dedent('''\
        import unittest

        from wordkit.clean import normalize


        class TestNormalize(unittest.TestCase):
            def test_lower_and_punctuation(self):
                self.assertEqual(normalize("Hello, World!  It's me."), "hello world it's me")


        if __name__ == "__main__":
            unittest.main()
        '''),
    "tests/test_count.py": textwrap.dedent('''\
        import unittest

        from wordkit.count import top_words, word_count


        class TestCount(unittest.TestCase):
            def test_word_count(self):
                self.assertEqual(word_count("one two, three"), 3)

            def test_a_hyphen_splits_a_word(self):
                self.assertEqual(word_count("a well-known word"), 4)

            def test_top_words(self):
                self.assertEqual(top_words("a b a c a b", 2), [("a", 3), ("b", 2)])


        if __name__ == "__main__":
            unittest.main()
        '''),
    "tests/test_cli.py": textwrap.dedent('''\
        import contextlib
        import io
        import pathlib
        import tempfile
        import unittest

        from wordkit.cli import main


        class TestCli(unittest.TestCase):
            def test_counts_a_file(self):
                with tempfile.TemporaryDirectory() as tmp:
                    path = pathlib.Path(tmp) / "notes.txt"
                    path.write_text("one two three", encoding="utf-8")
                    out = io.StringIO()
                    with contextlib.redirect_stdout(out):
                        self.assertEqual(main([str(path)]), 0)
                    self.assertEqual(out.getvalue().strip(), "3 words")


        if __name__ == "__main__":
            unittest.main()
        '''),
}
for rel, body in files.items():
    p = d / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
for a in (["init", "-q", "-b", "main"], ["config", "user.email", "demo@example.com"],
          ["config", "user.name", "Demo"], ["add", "-A"],
          ["commit", "-qm", "wordkit: count words, the top words, and a CLI"]):
    subprocess.run(["git", "-C", str(d), *a], check=True)
