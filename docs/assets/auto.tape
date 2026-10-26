# The README's first picture: `graphene demo --auto`, the scripted replay of auto mode on the Nemotron path, played
# at four times its pace in an empty directory, then the plan as a graph. No model, no key, no network, $0.
# One goal; Ultra's three tasks; three Nano forks racing each; one fork stopped at a file outside its task; the
# rule keeping one a task; the whole suite red after all three land; Ultra's fix racing; the suite green.
#
#   vhs docs/assets/auto.tape        (from the repository root; about a minute)
#
# Needs vhs (with ttyd and ffmpeg) and uv. It films this checkout's build: its .venv goes first on PATH,
# so the words on screen are the tree's, not those of a graphene installed elsewhere.

Output docs/assets/auto.gif
Set Shell "bash"
Set FontSize 30
Set Width 2240
Set Height 1200
Set Padding 28
Set TypingSpeed 40ms

Hide
Type "export PS1='> ' BASH_SILENCE_DEPRECATION_WARNING=1; R=$(git rev-parse --show-toplevel) && (cd $R && uv sync -q) && export PATH=$R/.venv/bin:$PATH && cd $(mktemp -d) && clear" Enter
Wait
Show

Type "graphene demo --auto --speed 4"
Sleep 400ms
Enter
Wait+Screen@120s /ended: last frame/
Sleep 2500ms
# the plan as a graph, flowing into your goal
Type "g"
Sleep 4s
# off camera: the GIF loops from the graph, not from a shell prompt
Hide
Type "q"
Sleep 500ms
