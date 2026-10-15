# Contributing

The most useful thing is a report of where the plan misread what you meant, or where a word stopped you. After
you have tried it, [the first-hour form](../../issues/new?template=first-hour.yml) takes two minutes.

## Run it from source

```
git clone https://github.com/Alex-lop/Graphene && cd Graphene
uv sync --all-extras
uv run graphene demo      # the scripted replay: no key, nothing runs
uv run pytest -q          # about 18 minutes in one process; add -n auto where pytest-xdist is installed
uv run ruff check
```

Python 3.12 or newer. The tests need no key and spend nothing.

## Where things are

`src/graphene_map/` is the product and `tests/` its tests. `docs/` is what you need to use it, starting with
`docs/HOW_IT_WORKS.md`. `dev/` is how it gets built ([`dev/README.md`](dev/README.md)); `dev/DIRECTION.md` is the
maintainer's own document, and a change that goes against a decision in it should say so, and why.

## A change

One concern a pull request, with the test that fails without it. A test that pins words moves with the words.
