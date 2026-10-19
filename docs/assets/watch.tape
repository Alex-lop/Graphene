# The README's pictures: `graphene demo`, the scripted replay of the Nemotron path in the cockpit, stepped with
# its own keys (space pauses, `.` is the next change) in an empty directory. No model, no key, no network, $0.
# The GIF and the three stills (cockpit.png, map.png, graph.png) are filmed in one take. A still is
# taken on the next frame, so a pause after it keeps the next key out of it.
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
# paused at 2 of 29, on the plan: four tasks proposed, and what the planner asks before anything is written
Space
Sleep 4s
# the map: which folders each task may write, before anything runs
Type "m"
Sleep 2500ms
Screenshot docs/assets/map.png
Sleep 600ms
Type "c"
Sleep 800ms
# your answers (3 to 5), what they change (6), the accept (7), then three agents at once (9 and 10)
Type "." Sleep 1500ms Type "." Sleep 1500ms Type "." Sleep 2s
Type "." Sleep 1200ms
Type "." Sleep 1500ms
Type "." Sleep 300ms
Type "." Sleep 800ms Type "." Sleep 2500ms
# agent 1 is stopped at a file outside its task (12), then hands it back with its reason (13)
Type "." Sleep 800ms
Type "." Sleep 2500ms
Type "." Sleep 3s
Screenshot docs/assets/cockpit.png
Sleep 600ms
Type "i"
Sleep 3s
Escape
Sleep 600ms
# agents 2 and 3 land (14 to 18); w widens agent 1's task to the file it asked for (20), and it tries again,
# still agent 1, until it lands (25)
Type "." Sleep 500ms Type "." Sleep 500ms Type "." Sleep 500ms Type "." Sleep 500ms Type "." Sleep 1500ms
Type "." Sleep 300ms
Type "." Sleep 2500ms
Type "." Sleep 300ms
Type "." Sleep 800ms Type "." Sleep 800ms Type "." Sleep 800ms
Type "." Sleep 2s
# the task that waited on two starts as agent 4, and everything is proven (29: the end)
Type "." Sleep 800ms Type "." Sleep 800ms Type "." Sleep 300ms Type "." Sleep 3500ms
# the plan as a graph, from your goal down
Type "g"
Sleep 3500ms
Screenshot docs/assets/graph.png
Sleep 600ms
# off camera: the GIF loops from the graph, not from a shell prompt
Hide
Type "q"
Sleep 500ms
