# Scene 02 of dev/demo/STORYBOARD.md: the ask, one paragraph.
# dev/demo/build.sh films it: it sets the take's stage (tmux -L graphene-film) and writes $FILM/attach, and
# sets Output, Width and Height here. The tape attaches, presses its keys in real time, and leaves.
# Ctrl+B M marks the time where the footage starts and ends: build.sh plays the clip at that length,
# since VHS captures fewer frames a second than it plays when the machine is busy.

Output scene.mp4
Set Shell "bash"
Set FontSize 24
Set Width 1876
Set Height 1080
Set Padding 20
Set Framerate 20
Set TypingSpeed 35ms
Set CursorBlink false

Hide
Type 'source "$FILM/attach"'
Enter
Sleep 1.5s
# pasted, as a person pastes a paragraph: typing it takes VHS half a minute on a busy machine
Type@1ms `graphene ask "Look at this repo. I want the new Northwind XML feed to load the same way csv and json already do: same load command, same JSONL out. Prices in that feed are already in cents. The summary line at the end is not a product. A price of 0 means skip it, for every supplier. Don't touch vendored or legacy files that aren't ours this week."`
Sleep 0.5s
Ctrl+B
Type "M"
Show
Sleep 7s
Enter
Sleep 6s
Hide
Ctrl+B
Type "M"
Sleep 0.5s
