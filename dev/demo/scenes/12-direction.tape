# Scene 12 of dev/demo/STORYBOARD.md: Graphene's own direction: the goals above tonight's plans, every session attached.
# dev/demo/build.sh films it: it sets the take's stage (tmux -L graphene-film) and writes $FILM/attach, and
# sets Output, Width and Height here. The tape attaches, presses its keys in real time, and leaves.
# Ctrl+B M marks the time where the footage starts and ends: build.sh plays the clip at that length,
# since VHS captures fewer frames a second than it plays when the machine is busy.
# only if: $ graphene direction
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
Type 'cd "$FILM_SELF" && clear'
Enter
Sleep 0.5s
Ctrl+B
Type "M"
Show
Type "graphene direction"
Enter
Sleep 13s
Hide
Ctrl+B
Type "M"
Sleep 0.5s
