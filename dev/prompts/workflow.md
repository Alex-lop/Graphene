# Prompt

Copy this. Fill the two blanks. Send it as the whole ask. The ambition and the limits are already
in the files it names, so the message stays short.

```
Read dev/SCOPE.md and dev/PRODUCT_NEXT.md before anything else. Do slice 1 only.

Slice 1 is one project type, one requested behavior, and a review that connects that request to a
check Graphene runs or to an artifact a person can open. Show an expectation the check does not
cover as uncovered. A check that was already green stays labeled as already green.

Project type: <the one current users already bring>
Behavior: <one modest change, for example adding CSV export of the visible rows>

Files you may edit:
- <path>
- <path>

If the slice needs a file that is not in that list, stop and name it. Do not explore the
repository for more work. Do not add a command, a provider, a graph control, or a general
workflow builder.

Done when a person can say what changed and what is still uncertain without reading your
transcript. Run the tests for the files you touched, and uv run ruff check.
```

Slice 2 and slice 3 use the same message with the slice number changed, and with their own file
list. [SCOPE.md](../SCOPE.md) says what each slice is. One slice a pull request.
