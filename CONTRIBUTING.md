# Contributing

The most useful thing is a report of where the plan misread what you meant, or where a word stopped you. After
you have tried it, [the first-hour form](../../issues/new?template=first-hour.yml) takes two minutes.

## Run it from source

```
git clone https://github.com/Alex-lop/Graphene && cd Graphene
uv sync --all-extras
uv run graphene demo        # the scripted replay: no key, nothing runs
uv run pytest -q -n auto    # the whole suite: about six minutes on an 11-core laptop
uv run ruff check
```

Python 3.12 or newer, on macOS or Linux. The tests need no key and spend nothing.

To look at a screen with no terminal, do what the tests do: drive the app with `App.run_test(size=(80, 24))` and
`pilot.press` (`tests/test_cockpit_app.py`), then `app.save_screenshot()` writes what it shows as an SVG
(`dev/screens/meter_shot.py`). To record the demo Graphene ships again after a change to the run:
`RECORD_DEMO=src/graphene_map/demo.jsonl uv run pytest tests/test_demo_script.py`, and the one `graphene demo --auto`
plays: `RECORD_DEMO_AUTO=src/graphene_map/demo-auto.jsonl uv run pytest tests/test_demo_auto.py`. The README's GIF
of it is `vhs docs/assets/auto.tape`.

The VS Code extension builds and tests with Node 22 or newer, apart from the Python suite:

```
cd editors/vscode && npm ci && npm test   # types, unit tests, and a smoke test in a local VS Code if there is one
npm run package                           # graphene-0.8.0.vsix, for `code --install-extension`
```

## Where things are

`src/graphene_map/` is the product and `tests/` its tests; `editors/vscode/` is Graphene for VS Code, a client
of `graphene state --json` and the CLI. `docs/` is what you need to use it, starting with
`docs/HOW_IT_WORKS.md`. `dev/` is how it gets built ([`dev/README.md`](dev/README.md)); `dev/DIRECTION.md` is the
maintainer's own document, and a change that goes against a decision in it should say so, and why.

## A change

One concern a pull request, with the test that fails without it. A test that pins words moves with the words.
