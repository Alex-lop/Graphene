# Scene 08 of dev/demo/STORYBOARD.md: the leaf that came back: its reason and its fix, w, R.
# dev/demo/build.sh films it: it sets the take's stage (tmux -L graphene-film) and writes $FILM/attach, and
# sets Output, Width and Height here. The tape attaches, presses its keys in real time, and leaves.
# Ctrl+B M marks the time where the footage starts and ends: build.sh plays the clip at that length,
# since VHS captures fewer frames a second than it plays when the machine is busy.
# wait: $ tail -n 1 "$(ls -t .graphene/runs/run-*.txt | head -n 1)" | grep -q "^run: " up to 40 min; cut: the executors at work
# only if: /came back/
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
Ctrl+B
Type "M"
Show
Escape
Type "/came back"
Enter
Sleep 6s
Type "w"
Sleep 3s
Type "R"
Sleep 5s
Hide
Ctrl+B
Type "M"
Sleep 0.5s
