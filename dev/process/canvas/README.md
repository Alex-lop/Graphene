# The canvas run's evidence

The target is [dev/ui/canvas.html](../../ui/canvas.html). The shots here are the VS Code graph before the
run and at its end (dev/SCOPE.md: the look, then the stages in the header from leaf `pipeline`), taken by
[shoot.mjs](shoot.mjs): real VS Code, Graphene: Watch the Demo, 1920x1050, the side bar closed, at the first
frame in which three tasks are working with their nine attempts fanned out. The demo replays a scripted
stand-in: no model ran.

| | Dark Modern | Light Modern |
|---|---|---|
| Before | ![before, dark](before-demo-1920x1050-dark.png) | ![before, light](before-demo-1920x1050-light.png) |
| After | ![after, dark](after-demo-1920x1050-dark.png) | ![after, light](after-demo-1920x1050-light.png) |

To take them again:

```sh
cd editors/vscode && npm ci && npm run package && cd e2e && npm ci && cd ../../..
node dev/process/canvas/shoot.mjs after
node dev/process/canvas/shoot.mjs readme    # the README's picture, editors/vscode/media/graph.png
```

`readme` takes the demo later, when one task has landed and two are working, in a 1440x1050 window with the
first working task selected, so its pane is open on Scope, and the status bar hidden.

High contrast, the narrow drawing and the other states (a suggested plan, a task that came back, a selected
task) are easiest to look at in the preview page, which needs no editor: `npm --prefix editors/vscode run build`,
then open `editors/vscode/media/preview.html?fixture=race&theme=hc` in a browser (its first lines list the
fixtures and switches).
