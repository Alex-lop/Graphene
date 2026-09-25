# Fixed trees

Every configuration of the benchmark (`docs/test/bench.py`) runs the same tree for a task:
`docs/test/trees/<task>.plan`, the plan's text as `graphene plan --text` prints it. The bench loads it
as the person, all of it accepted, so what changes from one configuration to the next is the executor
and nothing else. Each run's rows carry the tree's hash (`tree`), so a reader can check that.

A tree is made once per task, before any configuration runs, and it needs the live planner:

1. **The Nemotron planner proposes it** from a paragraph a stand-in person wrote from the task's card.
2. **The stand-in prunes it** against the card. The stand-in is the card's only reader, as in
   `standin.py`: whoever starts it (and whoever tunes the executor) never opens `intent.md`,
   `accept.py`, `quality.py` or `intent_globs.txt`, never sees the paragraph, and gets back no word
   of the card.
3. **Every leaf's check must fail at the base commit.** A check that already passes is not a check:
   the stand-in fixes it or prunes its leaf, and the number it fixed goes in the commit message. The
   bench flags and counts any that are left (`checks_passing_at_base`) on every run.
4. **The pruned text is committed** as `docs/test/trees/<task>.plan`, and not touched once a
   configuration has run on it.

## The commands

Once, in a terminal (the key is read from the environment and never written down):

```sh
G=~/Desktop/AllThingsAgenticHackathon          # this checkout, at the commit under test
(cd $G && uv sync) && export PATH="$G/.venv/bin:$PATH"
export NEBIUS_API_KEY=…
mkdir -p ~/graphene-trees
bash $G/docs/test/newrun.sh ~/graphene-trees feeds standin tree 1   # repo, graphene init, env.sh
# the planner's calls go to the night's ledger, under its cap, as every bench run's do
printf 'export GRAPHENE_LEDGER=%s GRAPHENE_SPEND_CAP_USD=%s\n' \
  "$G/docs/test/ledger-2026-09-25.jsonl" "${GRAPHENE_SPEND_CAP_USD:-30}" \
  >> ~/graphene-trees/feeds-standin-tree-1/env.sh
```

Without that line Token Factory's client writes no ledger and holds no cap: the Ultra calls
that make the tree would be spent where the bench's 80% and 100% stops cannot see them.

Then start the stand-in, a sub-agent, with this brief (put the task's name in place of `feeds`):

> You are the person who wants the change on the card in
> `~/Desktop/AllThingsAgenticHackathon/docs/test/tasks/feeds/intent.md`. Read it: it is yours. Never
> paste it into anything, and never repeat it in what you write back. Read nothing else under
> `docs/test/`. Every shell you open starts with `source ~/graphene-trees/feeds-standin-tree-1/env.sh`.
>
> 1. From the card alone, before you open any file of the repo, write the paragraph you would type
>    to a colleague, with every constraint you still remember, into `../paragraph.txt`.
> 2. `as_me graphene ask "$(cat ../paragraph.txt)" --with nemotron` (Nemotron Ultra proposes the tree).
> 3. Prune it against the card: `as_me graphene plan --text > "$TMPDIR/before.txt"`, copy it to
>    `"$TMPDIR/after.txt"`, delete the leaves you do not want and fix any scope or check that is
>    wrong by the card, then `as_me env EDITOR="cp $TMPDIR/after.txt" graphene plan edit` and
>    `as_me graphene plan accept`.
> 4. `as_me graphene plan --text > ~/Desktop/AllThingsAgenticHackathon/docs/test/trees/feeds.plan`
> 5. `cd ~/Desktop/AllThingsAgenticHackathon && uv run python docs/test/bench.py feeds --config tree
>    --executor nemotron --checks-only` builds a fresh repo, loads the tree and runs every check at the
>    base commit, spending nothing. It exits 0 only when every check fails there. Fix or drop each
>    leaf it names (steps 3 and 4 again) until it does.
> 6. Write back only: how many leaves the planner proposed, how many you dropped, how many you
>    changed, and how many checks you fixed in step 5.

Commit the tree with those four numbers in the message:

```sh
git -C $G add docs/test/trees/feeds.plan
git -C $G commit -m "the fixed tree for feeds: <kept> of <proposed> leaves, <changed> changed, <fixed> checks that passed at base fixed"
```

## Running a configuration on it

One run at a time (two at once would share the machine, and their wall times would mean nothing).
Model ids come from the live list, never typed:

```sh
cd $G
NANO=$(uv run python -c 'from graphene_map import tokenfactory as tf; print(tf.roles()["nano"])')
SUPER=$(uv run python -c 'from graphene_map import tokenfactory as tf; print(tf.roles()["super"])')
for n in 1 2 3; do
  uv run python docs/test/bench.py feeds --config nano --executor "nemotron --model $NANO" \
    --parallel 4 --run $n || break
done
uv run python docs/test/results.py      # docs/test/results-2026-09-25.md, from the rows
```

`--executor` is what `graphene run --with` takes: `"nemotron --model $NANO --model $SUPER"` is Nano
first and Super on the next attempt. A run's repo, its run log and each round's output are in
`~/graphene-bench/<date>/<task>-<config>-<run>/`; its rows are appended to
`docs/test/runs-2026-09-25.jsonl`, and every Token Factory call to `docs/test/ledger-2026-09-25.jsonl`.
At 80% of `GRAPHENE_SPEND_CAP_USD` (30 if unset) the bench starts no new run, and at 100% it stops
between rounds; both exit 3, which ends the loop above. So does stopping the bench (Ctrl-C, or a
plain `kill` of its process, not `-9`): it stops its round, ends every executor that round started, and counts the
run as far as it got, marked stopped.
