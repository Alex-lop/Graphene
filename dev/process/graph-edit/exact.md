# Exact: what the three settings cover, and what they do not

Home's Exact switch (off by default) is built over settings that exist: on, it sets `board: on`, `review: every`
and `auto: off`, and keeps what review and auto were to put them back. Asked of the engine on 11 November 2026
with `probes/exact.sh`: a plan with a question and a risk, each with a default, accepted whole as Start does.

| Exact should mean | Covered by | What the probe showed |
|---|---|---|
| each finished task waits for you | `review: every` | yes (Set Up already turns it on) |
| nothing is accepted for you | `auto: off` | yes (the default) |
| every open item is shown | `board: on` | in the cockpit and `graphene plan`, yes; Home already shows every open item whatever the setting (`state --json` lists the question and the risk under `board: auto` too) |
| Start waits for your answers | nothing | no: `graphene plan accept` said `accepted top; took the defaults of q-n, r-hyphen` under `board: on` as under `auto` |
| the plan leaves blanks for you | nothing | no setting tells the planner to leave a task's files or check open |

Built, in the extension only: while Exact is on and anything is open, Home's Start is off and says how many
questions wait; a default's own button confirms it. That holds Home's button, not the plan: `graphene plan
accept`, `graphene run` and the cockpit's `A` still take the defaults.

Not built (it is the engine's):

- accepting refused while the board asks (a third value for `board:`, or a flag on `plan accept`), so Exact holds
  from every door;
- a planner told to leave blanks: a suggested task with no files or no check, which today `plan propose` refuses
  (`a leaf needs a scope`). The graph's draft boxes are the nearest thing, and they are the page's own.
