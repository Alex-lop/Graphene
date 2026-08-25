#!/bin/bash
# Fail if a document still points at a session report's old root path, or if any
# relative markdown link in the tree does not resolve.
#
#   scripts/check_doc_references.sh
#
# The five session reports that used to sit at the repository root now live under
# docs/reports/ with dated names. A rename is only finished when nothing still
# names the old path, and greps that "confirm" a rename are the classic check
# that cannot fail -- so this one prints every hit it finds and exits non-zero on
# the first, rather than reporting a clean tree either way.
#
# Two deliberate scoping decisions, both of which weaken the check and are stated
# here rather than buried:
#
#   * evidence/ is excluded. It is append-only: those files recorded what was
#     true at the time they were written, and a path that was correct on
#     2026-08-23 is not a stale reference, it is history. Rewriting them to
#     match today's layout would be falsifying the record.
#   * Untracked files are excluded, because git grep only sees tracked ones.
#     HANDOFF.md and the root directives are untracked by design.
#
# Fixed-string matching (git grep -F) on purpose. A regex that anchors or spans
# is how a doc grep misses a stale path inside a long line -- the pattern matches
# part of the line, the reviewer reads a clean exit, and the reference survives.
set -uo pipefail
cd "$(dirname "$0")/.."

# The root paths that no longer exist. A hit on any of these is a broken
# reference even when it appears as bare prose rather than a markdown link.
OLD_ROOT_PATHS=(
  "NIGHT_REPORT.md"
  "CONVERGENCE_REPORT.md"
  "CONTRACT_REPORT.md"
  "NEXT_STEPS.md"
)

fail=0

echo "== references to session reports at their old root paths"
for old in "${OLD_ROOT_PATHS[@]}"; do
  # ':!evidence' is a pathspec exclusion; the hits are printed, never counted.
  if hits=$(git grep -n -F "$old" -- . ':!evidence' ':!scripts/check_doc_references.sh') && [ -n "$hits" ]; then
    printf 'FAIL %s is still referenced:\n%s\n' "$old" "$hits"
    fail=1
  else
    printf 'PASS %s unreferenced outside evidence/\n' "$old"
  fi
done

echo
echo "== every relative markdown link resolves"
# Reuses the tree-wide link check that already exists rather than reimplementing
# markdown link parsing here; it walks every *.md in the tree, not just the ones
# this rename touched, and it already handles percent-encoding and anchors.
if uv run --frozen pytest -q -p no:cacheprovider \
     tests/unit/test_documentation_truth.py::test_every_relative_markdown_link_resolves \
     >/tmp/graphene-doc-links.$$ 2>&1; then
  echo "PASS all relative markdown links resolve"
else
  echo "FAIL a relative markdown link does not resolve:"
  cat /tmp/graphene-doc-links.$$
  fail=1
fi
rm -f /tmp/graphene-doc-links.$$

echo
if [ "$fail" = 0 ]; then
  echo "DOC REFERENCES: ALL PASS"
else
  cat <<'EOF'
DOC REFERENCES: FAIL

Session reports live under docs/reports/ with dated names. If a hit above is a
NEW report rather than a stale reference, give it a dated name in that directory
(docs/reports/YYYY-MM-DD-night-report.md) instead of reusing the old root name.
EOF
fi
exit "$fail"
