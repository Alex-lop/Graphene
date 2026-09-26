# The screen harness

How the screens of `graphene watch` in the diary were taken: at 80x24 and 120x36, as a person sees
them, saved as text and as an SVG with its colours. It needs WezTerm and a Python with rich.

`start.sh 80x24` and `start.sh 120x36` start two isolated WezTerm mux servers (their sockets and
config under `$SOCKS`, default `/tmp/graphene-mux`; a mux of your own is never touched). `shoot.py
<phase> <graphene> <snapshot|-> <name> [keys ...]` restores a saved repository into
`~/graphene-polish` (unless `-`), opens a fresh window in both muxes running that `graphene watch`
as a person (`person.sh`: no agent's marks, which `wezterm cli spawn` would otherwise pass on),
sends the keys, and saves the screen under `$SHOTS/<phase>/` (default `./shots` beside it).
`mux.sh <size> <wezterm cli command…>` runs one command against a mux.

`shots.sh <phase> <graphene>` is the polish run's list of screens (`SNAP` names the directory of
saved repositories: a copy of `~/graphene-polish` taken at each moment of a real run, made again by
`docs/proof/try.sh` and a run; they are not committed, each is a git repository with worktrees).
`items.sh <graphene> <dir>` is the CLI's side: each message item in a fresh repository of its own.

Used by the polish run (`docs/process/polish/`, before at `2c86399`, after its branch) and by
folding (`docs/process/nemotron/folding/`, whose `plan30.py` makes the thirty-leaf plan it shot).
