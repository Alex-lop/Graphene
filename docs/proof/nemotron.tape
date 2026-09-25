# The Nemotron path's terminal parts, recorded: docs/proof/nemotron.sh on feeds, from nothing to the bill.
#
#   vhs docs/proof/nemotron.tape        (writes docs/assets/nemotron.gif; spends real tokens)
#
# Needs vhs, graphene on PATH, and NEBIUS_API_KEY (and NEBIUS_PROJECT_ID for Sandboxes) in the environment
# vhs starts. The repository is made fresh at ~/graphene-nemotron (deleted first). OUT and DIR override
# where the gif and the repository go (a draft against a stand-in is rendered elsewhere, and says so).

Output docs/assets/nemotron.gif
Set Shell "bash"
Set FontSize 13
Set Width 1400
Set Height 820
Set Padding 12
Set TypingSpeed 15ms
Set WindowBar Colorful

Hide
Type "unset CLAUDECODE CLAUDE_CODE_SESSION_ID CLAUDE_CODE_ENTRYPOINT AI_AGENT GRAPHENE_AS; export PS1='$ ' BASH_SILENCE_DEPRECATION_WARNING=1" Enter
Type "D=${DIR:-$HOME/graphene-nemotron}; rm -rf $D; clear" Enter
Show

Type "docs/proof/nemotron.sh $D"
Sleep 500ms
Enter
Sleep 90s
Sleep 5s
