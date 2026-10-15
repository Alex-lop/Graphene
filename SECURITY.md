# Security

Graphene runs on your machine. With Claude Code or Codex it sends nothing anywhere itself
([Privacy](docs/HOW_IT_WORKS.md#privacy)). `graphene init` adds hooks to one project; they record that project's
Claude Code sessions (prompts, tool calls and what they returned, the files it edits) on your machine only, and
`graphene init --remove` takes them out.

## What it holds, and where that ends

A hook refuses a Claude Code write outside the files a leaf may change, before the write; git checks again when a
leaf is declared done. The limits are written down, each next to the control it weakens, in
[Where each mechanism ends](docs/HOW_IT_WORKS.md#where-each-mechanism-ends). The ones to know first: a hook that
crashes or times out lets the call through; a script or an MCP server that writes a file itself is not seen by the
hooks (git catches it at done); and "only a person" rests on the environment's variables.

## Reporting a problem

Please do not put a way around the controls in a public issue. Use this repository's **Security** tab and
"Report a vulnerability", which is private. If it is not there, open an issue that says only that you have a
security report and how to reach you, and I will reach out.

A case where Graphene lets something through that its own page says it holds is exactly the report that is
wanted. A new limit is at least a documentation fix.
