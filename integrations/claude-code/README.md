# Claude Code door

Copy `graphene.md` to `.claude/commands/graphene.md` in any project that has
the `graphene` MCP server connected, and `/graphene <goal>` runs the loop.
`.claude/` is git-ignored in this repository, which is why the file lives here.

The server itself is offered automatically by the committed [`.mcp.json`](../../.mcp.json)
when Claude Code opens this clone (it asks you to approve the project server
once); its own prompt is `/mcp__graphene__goal <goal>`. For another clone:

```bash
claude mcp add --scope project graphene -- uv run --directory /path/to/Graphene --frozen graphene-mcp
```
