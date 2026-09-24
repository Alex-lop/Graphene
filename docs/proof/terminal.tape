# The two-pane scene, recorded: a paragraph to a real Claude Code session on the left, the tree
# appearing in `graphene watch` on the right, a prune that goes too far, R, the leaf that comes back
# with its fix, the fix taken, R again. Real agents; the waits for them are cut from the recording.
#
#   vhs docs/proof/terminal.tape        (writes docs/assets/watch.gif; ~3 minutes, some cents)
#
# Needs vhs, tmux, claude, and graphene on PATH. The repository is made fresh under $TMPDIR/graphene-demo,
# and tmux runs a server of its own (-L graphene-demo), never yours.

Output docs/assets/watch.gif
Set Shell "bash"
Set FontSize 13
Set Width 1500
Set Height 820
Set Padding 12
Set TypingSpeed 18ms
Set WindowBar Colorful

Hide
Type "unset CLAUDECODE CLAUDE_CODE_SESSION_ID CLAUDE_CODE_ENTRYPOINT AI_AGENT GRAPHENE_AS; export PS1='$ ' BASH_SILENCE_DEPRECATION_WARNING=1" Enter
# this checkout's graphene, with its dependencies, first on PATH (the hooks find it there too)
Type "export PATH=$PWD/.venv/bin:$PATH" Enter
# the prune, scripted: e on the last leaf takes cli/main.py out of its scope (a person would type it)
Type `export EDITOR="sed -i.bak -e 's#, cli/main.py##' -e 's#cli/main.py, ##'"` Enter
Type "D=${TMPDIR:-/tmp}/graphene-demo; rm -rf $D; bash docs/proof/try.sh $D/feeds > /dev/null && cd $D/feeds && clear" Enter
Sleep 4s
Type `G=$(command -v graphene); tmux -L graphene-demo -f /dev/null new-session -s demo -x 180 -y 48 "bash --norc --noprofile" \; set -g status off \; split-window -h -l 48% -c "$PWD" "$G watch" \; select-pane -L` Enter
Sleep 4s
Show

Type `claude -p "Look at this repo. I want the new Northwind XML feed to load the same way csv and json already do: same load command, same JSONL out. Prices in that feed are already in cents. The summary line at the end is not a product. A price of 0 means skip it, for every supplier. Don't touch vendored or legacy files that aren't ours this week." --allowedTools "Bash(graphene *)" Read Grep Glob`
Sleep 1s
Enter
Sleep 3s
Hide
Sleep 75s
Show
Sleep 5s

# to the plan: prune a scope too far (cli/main.py goes), accept everything, run
Ctrl+B
Type "o"
Sleep 1s
Type "G"
Sleep 3s
Type "e"
Sleep 3s
Type ":plan accept"
Sleep 1s
Enter
Sleep 3s
Type "R"
Sleep 8s
Hide
Sleep 150s
Show
Type "G"
Sleep 6s
# it came back wanting cli/main.py: take the offer, run again
Type "w"
Sleep 3s
Type "R"
Sleep 6s
Hide
Sleep 120s
Show
Sleep 4s
Type "gg"
Sleep 4s
Type "q"
Sleep 1s
Ctrl+B
Type "o"
Sleep 1s
Type "git log --graph --oneline | head -20" Enter
Sleep 6s
Hide
Type "tmux -L graphene-demo kill-server" Enter
Sleep 1s
