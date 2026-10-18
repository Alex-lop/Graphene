# The README's picture: `graphene demo`, the scripted replay in the cockpit, stepped with its own
# keys (space pauses, `.` is the next change) in an empty directory. No model, no key, no network, $0.
#
#   vhs docs/assets/watch.tape        (from the repository root; writes docs/assets/watch.gif, ~2 minutes)
#
# Needs vhs (with ttyd and ffmpeg) and uv. It films this checkout's build: its .venv goes first on PATH,
# so the words on screen are the tree's, not those of a graphene installed elsewhere.

Output docs/assets/watch.gif
Set Shell "bash"
Set FontSize 16
Set Width 1000
Set Height 480
Set TypingSpeed 40ms

Hide
Type "export PS1='> ' BASH_SILENCE_DEPRECATION_WARNING=1; R=$(git rev-parse --show-toplevel) && (cd $R && uv sync -q) && export PATH=$R/.venv/bin:$PATH && cd $(mktemp -d) && clear" Enter
Wait
Show

Type "graphene demo"
Sleep 500ms
Enter
Wait+Screen /space pause/
Sleep 2s
Space
Sleep 1s
# one `.` a change; the first is on screen when it opens, and a `.` past the last does nothing
Type "." Sleep 2s Type "." Sleep 2s Type "." Sleep 2s Type "." Sleep 2s
Type "." Sleep 2s Type "." Sleep 2s Type "." Sleep 2s Type "." Sleep 2s
Type "." Sleep 2s Type "." Sleep 2s Type "." Sleep 2s Type "." Sleep 2s
Type "." Sleep 2s Type "." Sleep 2s Type "." Sleep 2s Type "." Sleep 3s
# the plan as boxes and arrows, the folders each task may write, and back to the rows
Type "g" Sleep 3s Type "m" Sleep 3s Type "c" Sleep 1s
# the leaf that came back: everything about it, then its record
Enter
Sleep 3s
Type "r"
Sleep 4s
Escape
Sleep 500ms
Type "q"
Sleep 500ms
