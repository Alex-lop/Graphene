# The README's pictures: `graphene demo`, the scripted replay of the Nemotron path in the cockpit, stepped with
# its own keys (space pauses, `.` is the next change) in an empty directory. No model, no key, no network, $0.
# The GIF and the three stills (cockpit.png, map.png, graph.png) are filmed in one take.
#
#   vhs docs/assets/watch.tape        (from the repository root; about two minutes)
#
# Needs vhs (with ttyd and ffmpeg) and uv. It films this checkout's build: its .venv goes first on PATH,
# so the words on screen are the tree's, not those of a graphene installed elsewhere.

Output docs/assets/watch.gif
Set Shell "bash"
Set FontSize 16
Set Width 1120
Set Height 600
Set Padding 14
Set TypingSpeed 40ms

Hide
Type "export PS1='> ' BASH_SILENCE_DEPRECATION_WARNING=1; R=$(git rev-parse --show-toplevel) && (cd $R && uv sync -q) && export PATH=$R/.venv/bin:$PATH && cd $(mktemp -d) && clear" Enter
Wait
Show

Type "graphene demo"
Sleep 400ms
Enter
Wait+Screen /space pause/
# paused on the plan: four tasks proposed, and what the planner asks before anything is written
Space
Sleep 3500ms
# the map: which folders each task may write, before anything runs
Type "m"
Sleep 2500ms
Screenshot docs/assets/map.png
Type "c"
Sleep 600ms
# your answers, the accept, then three agents at once
Type "." Sleep 700ms Type "." Sleep 700ms Type "." Sleep 700ms
Type "." Sleep 1s
Type "." Sleep 300ms Type "." Sleep 300ms
Type "." Sleep 3s
# agent 1 is stopped at a file outside its task, then hands it back with its reason
Type "." Sleep 2s
Type "." Sleep 2500ms
Screenshot docs/assets/cockpit.png
Type "i"
Sleep 2500ms
Escape
Sleep 500ms
# the others land; w widens agent 1's task to the file it asked for, and it tries again, still agent 1
Type "." Sleep 400ms Type "." Sleep 400ms Type "." Sleep 400ms Type "." Sleep 400ms Type "." Sleep 1500ms
Type "." Sleep 1500ms
Type "." Sleep 300ms
Type "." Sleep 2s
Type "." Sleep 400ms Type "." Sleep 400ms Type "." Sleep 1500ms
# the task that waited on two starts as agent 4; everything is proven
Type "." Sleep 400ms Type "." Sleep 1500ms
Type "." Sleep 400ms Type "." Sleep 400ms Type "." Sleep 400ms Type "." Sleep 2s
# the plan as a graph, from your goal down
Type "g"
Sleep 3s
Screenshot docs/assets/graph.png
Type "q"
Sleep 500ms
