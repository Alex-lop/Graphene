# The Nemotron path on screen, as the storyboard has it (docs/demo/STORYBOARD.md): a paragraph to the
# Nemotron Ultra planner on the left, its tree appearing in `graphene watch` on the right, a prune that
# goes too far, R with Nemotron executors, the leaf that comes back with its fix, w, R, the history
# reading as the tree, and the bill. Real calls to Token Factory; the waits for them are cut.
#
#   vhs docs/proof/nemotron.tape        (writes docs/assets/nemotron.gif; spends real tokens)
#
# Needs vhs, tmux, graphene on PATH, and NEBIUS_API_KEY (and NEBIUS_PROJECT_ID for Sandboxes) in the
# environment vhs starts. The repository is made fresh at ~/graphene-nemotron (deleted first), and tmux
# runs a server of its own (-L graphene-nemotron), never yours. A draft against a stand-in is rendered
# from a copy of this tape with the waits cut, and says so where it is kept.

Output docs/assets/nemotron.gif
Set Shell "bash"
Set FontSize 13
Set Width 1500
Set Height 820
Set Padding 12
Set TypingSpeed 18ms
Set WindowBar Colorful

Hide
Type "unset CLAUDECODE CLAUDE_CODE_SESSION_ID CLAUDE_CODE_ENTRYPOINT AI_AGENT GRAPHENE_AS; export PS1='$ ' BASH_SILENCE_DEPRECATION_WARNING=1" Enter
# the prune, scripted: E on the goal opens the whole plan, and cli/main.py goes from every scope (a person
# would type it), so the leaf that needs it comes back with its fix
Type `export EDITOR="sed -i.bak -e 's#, cli/main.py##' -e 's#cli/main.py, ##'"` Enter
Type "D=$HOME/graphene-nemotron; rm -rf $D; python3 docs/test/make_task.py feeds $D > /dev/null && cd $D && graphene init --planner nemotron --executor nemotron > /dev/null && clear" Enter
Sleep 8s
Type `G=$(command -v graphene); tmux -L graphene-nemotron -f /dev/null new-session -s demo -x 180 -y 48 "bash --norc --noprofile" \; set -g status off \; split-window -h -l 52% -c "$PWD" "$G watch" \; select-pane -L` Enter
Sleep 4s
Show

Type `graphene ask "Look at this repo. I want the new Northwind XML feed to load the same way csv and json already do: same load command, same JSONL out. Prices in that feed are already in cents. The summary line at the end is not a product. A price of 0 means skip it, for every supplier. Don't touch vendored or legacy files that aren't ours this week."`
Sleep 1s
Enter
Sleep 4s
Hide
Sleep 90s
Show
Sleep 4s

# to the plan: read it, prune a scope too far, accept everything, run
Ctrl+B
Type "o"
Sleep 1s
Type "gg"
Sleep 3s
Type "E"
Sleep 3s
Type ":plan accept"
Sleep 1s
Enter
Sleep 3s
Type "R"
Sleep 10s
Hide
Sleep 180s
Show
Type "/came back"
Sleep 1s
Enter
Sleep 1s
Escape
Sleep 6s
# it came back wanting cli/main.py: take the offer, run again
Type "w"
Sleep 3s
Type "R"
Sleep 8s
Hide
Sleep 120s
Show
Sleep 4s
Type "gg"
Sleep 5s
Type "q"
Sleep 1s
Ctrl+B
Type "o"
Sleep 1s
Type "git log --graph --oneline | head -16; graphene plan record | tail -3" Enter
Sleep 8s
Hide
Type "tmux -L graphene-nemotron kill-server" Enter
Sleep 1s
