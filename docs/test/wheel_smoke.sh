#!/usr/bin/env bash
# The built wheel in clean containers, as a judge would install it: for each Python, its dependencies
# are fetched into a wheelhouse (the only step with a network), then the wheel is installed from it and
# run with --network none and no key: `graphene demo --once`, and docs/proof/nemotron.sh end to end
# against the scripted stand-in (tests/test_demo_script.py, with the wheel's `graphene` on PATH).
#
#   docs/test/wheel_smoke.sh [3.12 3.13 3.14]      (from the repository's root; needs Docker)
set -euo pipefail
cd "$(dirname "$0")/../.."
rm -rf dist && uv build -q
WHEEL=$(basename dist/graphene_map-*.whl)
for py in "${@:-3.12 3.13 3.14}"; do
  for v in $py; do
    house=$(mktemp -d)
    docker run --rm -e PIP_ROOT_USER_ACTION=ignore -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
      -v "$PWD/dist:/dist:ro" -v "$house:/wh" "python:$v" \
      pip wheel -q -w /wh "/dist/$WHEEL" pytest >/dev/null
    docker run --rm --network none -v "$house:/wh:ro" -v "$PWD/tests:/src/tests:ro" \
      -v "$PWD/docs/proof:/src/docs/proof:ro" -e HOME=/tmp/home -e PIP_ROOT_USER_ACTION=ignore \
      -e PIP_DISABLE_PIP_VERSION_CHECK=1 "python:$v" bash -c "
        set -e
        pip install -q --no-index --find-links /wh graphene-map pytest
        mkdir -p /tmp/home && cd /tmp
        git config --global user.email judge@example.com && git config --global user.name judge
        echo \"python $v: \$(graphene --version)\"
        graphene demo --once | head -1
        cp -r /src /tmp/src && cd /tmp/src
        python -m pytest -q -p no:cacheprovider tests/test_demo_script.py 2>&1 | tail -1
      "
    rm -rf "$house"
  done
done
