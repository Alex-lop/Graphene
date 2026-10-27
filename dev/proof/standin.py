#!/usr/bin/env python3
"""The scripted stand-in for Token Factory, as a server of its own: tests/fake_tokenfactory.py on 127.0.0.1,
answering with auto mode's script from tests/test_demo_auto.py (Ultra plans wordkit's three wishes, three Nano
forks race each task, the goal's check goes red, Ultra plans the fix). It costs nothing and no model runs.

    uv run python dev/proof/standin.py

Its first line is the URL. It serves until it is killed. Then, in a repository dev/proof/make_wordkit.py made:

    export GRAPHENE_TOKENFACTORY_URL=<url> NEBIUS_API_KEY=fake-key GRAPHENE_KEYCHAIN=off
    graphene init --planner nemotron --executor nemotron
    graphene auto "<wordkit's goal, as dev/proof/auto.sh says it>" --budget 2 --forks 3 --rounds 2 \\
        --parallel 4 --check "python3 -m unittest"

runs the whole race for $0 and changes the store as a live run would. The key must be the stand-in's own
(`fake-key`): with none in the environment, graphene would read the keychain and send a real key here.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

from fake_tokenfactory import Fake  # noqa: E402
from test_demo_auto import reply  # noqa: E402

ENV = {"NEBIUS_API_KEY": "fake-key", "GRAPHENE_KEYCHAIN": "off"}


def main() -> None:
    # `reply` answers from the request alone, so the script never runs out: one callable a request, plenty
    with Fake([reply] * 100_000) as fake:
        print(fake.url, flush=True)
        env = {"GRAPHENE_TOKENFACTORY_URL": fake.url, **ENV}
        print(" ".join(f"{k}={v}" for k, v in env.items()), flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
