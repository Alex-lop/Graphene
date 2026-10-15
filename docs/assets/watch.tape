# The README's picture: `graphene demo`, the scripted replay, stepped with its own keys (space pauses,
# `.` is the next change) in an empty directory. No model, no key, no network, $0.
#
#   vhs docs/assets/watch.tape        (from the repository root; writes docs/assets/watch.gif, ~2 minutes)
#
# Needs vhs (with ttyd and ffmpeg) and uv. It films this checkout's build: its .venv goes first on PATH,
# so the words on screen are the tree's, not those of a graphene installed elsewhere.

Output docs/assets/watch.gif
Set Shell "bash"
Set FontSize 16
Set Width 1200
Set Height 700
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
Type "." Sleep 2.5s Type "." Sleep 2.5s Type "." Sleep 2.5s Type "." Sleep 2.5s
Type "." Sleep 2.5s Type "." Sleep 2.5s Type "." Sleep 2.5s Type "." Sleep 2.5s
Type "." Sleep 2.5s Type "." Sleep 2.5s Type "." Sleep 2.5s Type "." Sleep 2.5s
Type "." Sleep 2.5s Type "." Sleep 2.5s Type "." Sleep 2.5s Type "." Sleep 4s
# the leaf that came back: the last row, then one up, and its record
Type "G" Sleep 1s Type "k" Sleep 1.5s
Enter
Sleep 8s
Type "q"
Sleep 500ms
