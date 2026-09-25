# How the before and after were taken

`start.sh 80x24` and `start.sh 120x36` start two isolated WezTerm mux servers. `shots.sh <phase>
<graphene>` restores each saved repository (a copy of `~/graphene-polish` taken at that moment of
the real run: proposed, signed, running, came back, review, done, and an empty one) and runs
`shoot.py`, which opens a fresh window in both muxes running that `graphene watch` as a person
(`person.sh`: no agent's marks, which `wezterm cli spawn` would otherwise pass on), sends the keys,
and saves the screen as text and as an SVG with its colours. The before ran `graphene` from a
worktree at `2c86399`; the after, this branch. The saved repositories are not committed (each is a
git repository with worktrees); `docs/proof/try.sh` and a run make them again. `items.sh <graphene>
<dir>` is the CLI's side: each message item in a fresh repository of its own.
