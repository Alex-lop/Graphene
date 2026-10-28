# The harness: the extension in real VS Code and Cursor

Playwright's Electron driver launches the real app, the way VS Code's own smoke tests do. Every launch has
a `--user-data-dir` and `--extensions-dir` of its own under a short temp dir, never yours. It installs a
`.vsix`, writes the profile's settings (`graphene.path` is the clone's `.venv/bin/graphene`, the theme, no
welcome page, no release notes, no telemetry, workspace trust off), opens a fixture repository, and can run
`graphene auto` against the scripted stand-in so the store changes as it would live.

One thing a profile does not cover: Cursor keeps a folder's agent data (canvases, terminals, mcps) under
`~/.cursor/projects/<the folder's path with dashes>`, whatever `--user-data-dir` says, and a `HOME` of the
profile's own stops it on a "Keychain Not Found" dialog. So `close` in `lib.mjs` removes that entry when it
closes Cursor, and every script here closes through it.

## Set up

```
cd editors/vscode && npm ci && npm run package   # the .vsix the harness installs
cd e2e && npm ci
```

`uv sync` in the clone gives the harness its `graphene`. VS Code comes from `VSCODE_EXECUTABLE`, else the
Mac's `/Applications/Visual Studio Code.app`, else a build `@vscode/test-electron` downloads. Cursor is
`/Applications/Cursor.app` (`CURSOR_EXECUTABLE`). `VSIX` names a package other than the newest in
`editors/vscode`. Video needs Playwright's own ffmpeg; the first recording fetches it into `e2e/.pw`.

## The check

`npm test` installs the `.vsix` in a fresh profile, adds three tasks to a wordkit fixture, launches VS Code,
opens Graphene and the graph panel, and fails when either graph does not draw the three tasks. On Linux
run it under `xvfb-run`. `E2E_APP=cursor` runs it in Cursor; `E2E_SHOT=file.png` keeps a screenshot.

`npm run home` clicks Home through, against the stand-in: a folder with no plan is set up with one click (and
`review: every`), an ask is planned, Start runs the agents, Approve before the changes were opened asks first,
Open Changes shows the diff, Approve lands the task and Send back… returns another with a note. It fails when a
step does not show what it should, and keeps a screenshot of each step (`E2E_SHOTS=dir`, else in its scratch).

## Screenshots and video

```
node shots.mjs --app code --out shots --video ~/graphene-film/harness
node shots.mjs --app cursor --out shots --during
```

The side bar at 280, 320 and 400 px, the editor tab at 1280x800 and 1920x1080, each in Dark Modern, Light
Modern and High Contrast: `APP-WHAT-THEME.png`, with `APP-smallest-text.json` beside them (the smallest text
drawn in each shot, font size times the SVG's scale, in CSS px). The race runs to its end before the window
opens, so every shot shows the same finished store; `--during` starts it after the window opens, so the
video shows it live. The store's race is `graphene auto` against `dev/proof/standin.py`.

## The driver, for a reader with only a shell

```
node drive.mjs --app code --auto --shots /tmp/look &     # prints `port N`
printf 'shot first\n' | nc 127.0.0.1 N                   # /tmp/look/first.png
printf 'graph\nframes\n' | nc 127.0.0.1 N                # what the graph frames show; every frame's text
printf 'sidebar 320\nshot narrow\n' | nc 127.0.0.1 N
printf 'palette Graphene: Show Graph\nsize 1920x1080\ntheme light\nshot panel\n' | nc 127.0.0.1 N
printf 'click Run ready\nkey Escape\n' | nc 127.0.0.1 N
printf 'sh node set top --title "a new title"\n' | nc 127.0.0.1 N
printf 'quit\n' | nc 127.0.0.1 N
```

One command a line; the answer comes back on the same connection. `sh` reads its line as a shell does, so
a title with spaces goes in quotes. `--fixture DIR` opens your own
repository instead of a fresh wordkit; `--standin` starts the stand-in without the race; `auto` starts it.
The stand-in answers Add Step too (`sh ask --step --after top -- "a --version flag on the CLI"`): one leaf
named by the sentence's first words, owning files no task has, as a proposal.

## Measures

Each prints its number and how it was taken, so a before and an after come from the same script. Timing
numbers mean little on a loaded machine: the latency line prints the load average beside them.

```
node measure/first-graph.mjs --app code --vsix FILE      # seconds from install to the first graph, median of 3
node measure/latency.mjs --app code --vsix FILE          # ms from `graphene node set` to the title on screen, 20 runs: p50, p90, max, mean
node measure/idle-cpu.mjs --app code --vsix FILE         # 60 s idle: the extension host, the graphene processes
uv run python editors/vscode/e2e/measure/moves.py        # the cockpit's keys against the extension's commands
```

## From your own script

`lib.mjs` exports the pieces: `findApp`, `makeProfile`, `installVsix`, `makeFixture`, `startStandin`,
`startAuto`, `launch`, `openSidebar`, `openPanel`, `palette`, `setSidebarWidth`, `setSize`, `setTheme`,
`graphFrames` (the webview frames that hold a graph, found by their content: VS Code nests the page two
iframes deep), `waitForGraph`, `readGraph`, `smallestText`, `framesText`, `shot`.

A note on the environment: the harness strips the agent's marks (`CLAUDE*`, `CODEX*`, `AI_AGENT`) from
what it runs, sets `NEBIUS_API_KEY=fake-key` when a stand-in is in play, and `GRAPHENE_KEYCHAIN=off` always.
Without the fake key graphene would read the keychain for a real one.
