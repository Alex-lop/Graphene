#!/usr/bin/env bash
# Runs a command as the person, in the scratch repositories only (decision 95's precedent): every agent
# mark the source names is dropped and GRAPHENE_AS=person:alex is set, so the log says "(no terminal)".
exec env -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_ENTRYPOINT -u CODEX_SESSION_ID \
  -u CODEX_SANDBOX -u AI_AGENT -u GEMINI_CLI -u CURSOR_AGENT -u GRAPHENE_NODE -u GRAPHENE_PLANNER \
  GRAPHENE_AS=person:alex "$@"
