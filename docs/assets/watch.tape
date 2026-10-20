# The README's pictures: `graphene demo`, the scripted replay of the Nemotron path in the cockpit, stepped with
# its own keys (space pauses, `.` is the next change) in an empty directory. No model, no key, no network, $0.
# The GIF and the four stills (map.png, cockpit.png, forks.png, graph.png) are filmed in one take. A still is
# taken on the next frame, so a pause after it keeps the next key out of it. The replay has 37 changes
# (`graphene demo` counts them on its top line); the numbers below are the change each `.` shows.
#
#   vhs docs/assets/watch.tape        (from the repository root; about two and a half minutes)
#
# Needs vhs (with ttyd and ffmpeg) and uv. It films this checkout's build: its .venv goes first on PATH,
# so the words on screen are the tree's, not those of a graphene installed elsewhere.

Output docs/assets/watch.gif
Set Shell "bash"
Set FontSize 32
Set Width 2240
Set Height 1200
Set Padding 28
Set TypingSpeed 40ms

Hide
Type "export PS1='> ' BASH_SILENCE_DEPRECATION_WARNING=1; R=$(git rev-parse --show-toplevel) && (cd $R && uv sync -q) && export PATH=$R/.venv/bin:$PATH && cd $(mktemp -d) && clear" Enter
Wait
Show

Type "graphene demo"
Sleep 400ms
Enter
Wait+Screen /space pause/
# paused at 2 of 37, on the plan: four tasks proposed, and what the planner asks before anything is written
Space
Sleep 4s
# the map: which folders each task may write, before anything runs
Type "m"
Sleep 2500ms
Screenshot docs/assets/map.png
Sleep 600ms
Type "c"
Sleep 800ms
# your answers (3 to 5), what they change (6), the accept (7), then three agents at once (8 to 10)
Type "." Sleep 1500ms Type "." Sleep 1500ms Type "." Sleep 2s
Type "." Sleep 1200ms
Type "." Sleep 1500ms
Type "." Sleep 300ms
Type "." Sleep 800ms Type "." Sleep 2500ms
# agent 1 is stopped at a file outside its task (11), then hands it back with its reason (13)
Type "." Sleep 2500ms
Type "." Sleep 800ms
Type "." Sleep 3s
Screenshot docs/assets/cockpit.png
Sleep 600ms
Type "i"
Sleep 3s
Escape
Sleep 600ms
# agents 2 and 3 land (14 to 18); w widens agent 1's task to the file it asked for (19), f forks it three
# ways (20), and it tries again, still agent 1, as forks 1a, 1b and 1c at once (23 and 24)
Type "." Sleep 500ms Type "." Sleep 500ms Type "." Sleep 500ms Type "." Sleep 500ms
Type "." Sleep 1500ms
Type "." Sleep 2500ms
Type "." Sleep 2500ms
Type "." Sleep 300ms
Type "." Sleep 800ms
Type "." Sleep 2500ms
Type "." Sleep 3s
# the fork race: the task's row is open on its three forks, each with its pace and its last move
Screenshot docs/assets/forks.png
Sleep 600ms
# fork 1a gives up (25); 1b passes (26 and 27, its 4 lines counted at 28) while 1c still works (28 and 29);
# 1c passes with 6 lines, and the rule keeps b, the smaller (30 and 31)
Type "." Sleep 2500ms
Type "." Sleep 800ms Type "." Sleep 2s
Type "." Sleep 800ms Type "." Sleep 300ms
Type "." Sleep 800ms Type "." Sleep 3s
# the task is proven and lands as one merge (32 and 33); the task that waited on two starts as agent 4 (34),
# and everything is proven (37: the end)
Type "." Sleep 800ms Type "." Sleep 1500ms
Type "." Sleep 1500ms Type "." Sleep 500ms Type "." Sleep 300ms Type "." Sleep 3500ms
# the plan as a graph, from your goal down
Type "g"
Sleep 3500ms
Screenshot docs/assets/graph.png
Sleep 600ms
# off camera: the GIF loops from the graph, not from a shell prompt
Hide
Type "q"
Sleep 500ms
