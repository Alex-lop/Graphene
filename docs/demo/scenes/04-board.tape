# Scene 04 of docs/demo/STORYBOARD.md: the board: one key answers the item under the cursor.
# docs/demo/build.sh films it: it sets the take's stage (tmux -L graphene-film) and writes $FILM/attach, and
# sets Output, Width and Height here. The tape attaches, presses its keys in real time, and leaves.
# Ctrl+B M marks the time where the footage starts and ends: build.sh plays the clip at that length,
# since VHS captures fewer frames a second than it plays when the machine is busy.
# only if: /\b(asks|risk|assumes|leaves out)\b/
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
# y takes the item's default, and the cursor goes to the next open item. The planner puts up at most three
# (decision 99); a y past the last lands on the settled fold, where it does nothing
# (tests/test_board_rows.py::test_each_key_answers_the_item_under_the_cursor_and_says_its_command).
Sleep 5s
Type "y"
Sleep 3s
Type "y"
Sleep 3s
Type "y"
Sleep 5s
Hide
Ctrl+B
Type "M"
Sleep 0.5s
