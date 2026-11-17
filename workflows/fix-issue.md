workflow: fix-issue
# Fix one issue: a test that fails for it, the fix, the whole suite, then a draft pull request.
#   graphene workflow fix-issue -i issue=48 -i file=tests/test_export.py \
#     -i "test=uv run pytest tests/test_export.py -q"
# The first step writes the test and nothing else: it is done when the file is there and the test fails.
# Run it on the branch the pull request is for: the last step pushes the branch your checkout is on,
# and waits for your `graphene node done` before it does. A command runs in a clean copy of the
# repository, on no branch, so that step goes back to the checkout first (GRAPHENE_CHECKOUT names it).
input: issue
input: file
input: test
input: src = src/**
input: suite = uv run pytest -q
goal: fix issue {{issue}}

- a test that fails for issue {{issue}}  [test-{{issue}}]
    scope: {{file}}
    check: test -e {{file}} && ! {{test}}
- the fix for issue {{issue}}  [fix-{{issue}}]
    scope: {{src}}
    check: {{test}}
    needs: test-{{issue}}
- the whole suite  [suite-{{issue}}]
    run: {{suite}}
    needs: fix-{{issue}}
- open a draft pull request  [pr-{{issue}}]
    run: cd "$GRAPHENE_CHECKOUT" && git push -u origin HEAD && gh pr create --draft --fill
    needs: suite-{{issue}}
