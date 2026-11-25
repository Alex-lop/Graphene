# The walk, on real sessions (24 November 2026)

`editors/vscode/e2e/sessions.mjs` drives a real VS Code, and a real Cursor, in a throwaway profile with only the
extension installed, `graphene` on no PATH it can see, and a new git repository with no Graphene files. Every
session in these pictures is a real Claude Code session (`claude -p`, haiku) on that scratch repository.
Half size. `code-*`: VS Code, a 1280 px window, the page about 460 px wide beside the file. `cursor-*`: Cursor,
the page 680 px wide.

| Step | Picture |
| --- | --- |
| 1. A session starts: a page opens by itself, and the file being typed in keeps the keyboard | `code-01`, `cursor-01` |
| 2. While it works its card says so; a click opens its terminal view | `code-02`, `cursor-03` |
| 3. It finishes: two files, the test and its result | `code-03`, `cursor-04` |
| 4. A second session: a second page; Add to page…: one page, two bands | `code-04`, `code-06` |
| 5. The window reloads: the pages come back | `code-07` |
| 6. The first session, resumed from its card | `code-09` |
| Also: the tail of a session started outside the editor; the editor's own terminal revealed; a changed file's diff; a push flagged, with git's word on the commit | `code-08`, `code-10`, `code-11`, `code-13` |

Run it again: `npm run package` in `editors/vscode`, then in `e2e`: `node sessions.mjs --out DIR`, and
`node sessions.mjs --short --app cursor --width 1360 --height 860 --out DIR` (the first three steps). It starts
five small sessions on your Claude subscription and takes about two minutes.
