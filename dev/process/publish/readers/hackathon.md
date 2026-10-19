# hackathon: the event's facts, what the submission still needs, and what the README owes a judge

## 1. The event (official, fetched 18 Oct 2026)

The official pages answer to curl with a browser user agent. WebFetch got a 403 from them. The text was saved at `<scratch>/agents/hackathon-dl/*.txt`.
- Overview: https://nebiusglobalaihackathon.devpost.com/
- Official Rules: https://nebiusglobalaihackathon.devpost.com/rules
- FAQs: https://nebiusglobalaihackathon.devpost.com/details/faqs
- Updates: https://nebiusglobalaihackathon.devpost.com/updates (especially /updates/46204-here-s-how-judging-works and /updates/46205-how-to-build-a-winning-project)

**Dates (Rules §1)**
- Submission Period: 26 Aug 2026, 9:00 PT, to **Fri 30 Oct 2026, 10:00 PT**. That is 12 days from today. Devpost does not allow edits to a submission after the deadline (§5).
- Judging Period: 1 Dec 2026, 9:00 PT, to **15 Dec 2026, 12:00 PT**. Winners are announced on or around 11 Jan 2027.
- "Will It Ship", a live judges' session that reviews audience projects against the criteria: **Tue 20 Oct, 9:00 PT**. You opt in when you register (/updates/47053).

**Hard requirements (Rules §4)**
- The project must run on Token Factory or AI Cloud **and** use at least one NVIDIA open source model. The rules define "runs on" as: "the project makes a runtime call to the Token Factory inference API, or is deployed/run using Nebius AI Cloud compute". The FAQ adds that calling an NVIDIA model through HuggingFace or OpenRouter does not count, and that the rest of the app does not need to be on Nebius.
- Track text for Coding and Agentic Engineering, today: "Build coding agents and developer tools: agents that write, run, and test code in Token Factory."
  - A third-party summary dated 3 Oct quoted it as "...in Token Factory Sandboxes" (https://lucaberton.com/blog/aaif-builders-brews-amsterdam-nebius-nvidia-hackathon-2026/).
  - The official page no longer says Sandboxes. So Sandboxes are not a stated requirement now.
- What the submission must contain (Rules §4, "Submission Requirements"):
  1. A URL to a working demo, hosted application, or test build.
  2. A text description of the features.
  3. A public repository URL on GitHub, GitLab or Bitbucket. It must contain all the source and instructions, and an open source license file "detectable and visible at the top of the repository page (in the About section)".
  4. **A README with setup instructions, which must "highlight how you've used NVIDIA Nemotron ... and where Token Factory accelerated your workflow and any other Nebius Tools or Services used."**
  5. **A video under 3 minutes, public on YouTube, with footage of the project functioning.** The overview page adds that it should show "how you used Nebius Token Factory and NVIDIA Nemotron". "Judges are not required to watch beyond three minutes."
  6. The track.
  7. **Feedback** on Token Factory, AI Cloud and the NVIDIA models. This is required, and it is also judged for the Most Valuable Feedback prize: $100 plus swag, 10 winners.
  8. **If the project existed before 26 Aug, a written explanation of what was significantly updated during the Submission Period.**
- Testing: the project must stay "available free of charge and without any restriction ... until the Judging Period ends" (15 Dec). The rules also say: "Judges are not required to test the Project and may choose to judge based solely on the text description, images, and video."
- The project must "function as depicted in the video and/or expressed in the text description".

**Judging (Rules §6 and /updates/46204)**
- **Stage One is pass/fail**: "the Project reasonably fits the theme and reasonably applies the required APIs/SDKs ... not a superficial rebrand of an unrelated idea."
- **Stage Two scores each project 1 to 5 on four equally weighted criteria.** Ties are broken in this order:
  1. Technological Implementation: "how effectively does it use Nebius Token Factory or AI Cloud model(s), and NVIDIA Nemotron".
  2. Design: "a complete, coherent product experience not just a technical proof of concept".
  3. Potential Impact: "a credible, specific case for solving a real problem for a real audience ... based on what's demonstrated".
  4. Quality of the Idea: "a creative, non-obvious use of Token Factory ... and Nemotron ... genuine understanding of the problem space".
- The organisers' tip for this track: "a code-completion wrapper is a start; an agent that plans, writes, tests, and iterates on a real repo with minimal human input is where it gets interesting."
- Other organiser tips (/updates/46205):
  - Name Token Factory and the NVIDIA model in the description and in Built With, and "call them out clearly, with audio, in your demo video".
  - "Treat your video like a pitch, not a tutorial."
  - Hide API keys.

**Prizes:** Grand $20k, 2nd $10k, 3rd $6k. Each track winner gets an NVIDIA Jetson Orin Nano. Best Use of Tavily $3k. City awards need in-person attendance (FAQ). A project can win one overall award, **or** one track award plus one bonus award. 24,738 participants were registered on 18 Oct. 22 judges are named, from NVIDIA, Nebius and Tavily.

**docs/HACKATHON.md checked against the official pages:** the track name, Devpost, and "judges may test until 15 December" (HACKATHON.md:239) are all correct. The deadline, 30 Oct 10:00 PT, is not written anywhere in HACKATHON.md. That is low severity, but it is the one date that matters.

## 2. The repository name points to another event: Google's "All Things Agentic Hackathon"

- Pages: https://allthingsagentichackathon.devpost.com/ and /rules (fetched the same way). Google announcement: https://discuss.google.dev/t/the-all-things-agentic-hackathon-is-officially-live/389123
- Sponsor and tools: Google LLC. You build "an autonomous AI Agent leveraging Gemini 3.5 Flash" with ADK and Google Cloud.
- Tracks: **Taskmaster**, Collaborative Partner, Fortified Enterprise Fleet.
- Dates: submissions ran 3 Aug to **31 Aug 2026, 17:00 PT**. Judging ran 1 Sep to 1 Oct. Its rules give winners on or around 8 Oct. The overview page says "This hackathon has ended. Winners announced soon" and shows "Oct 21, 2026".
- How it connects to this repo:
  - The first commit is 9b38b601, dated 2026-08-10.
  - HACKATHON.md:357 says that before 26 Aug the repo was "*Graphene Taskmaster*, with its model path on Gemini through Vertex AI", reset to an empty package on 17 Sep (c8a8f6c).
  - "Taskmaster" is one of Google's track names. So the local folder name `AllThingsAgenticHackathon` and the pre-August code were most likely an attempt at Google's event.
- Whether Alex actually submitted to Google's event: **not checked**. His Devpost portfolio is not visible to me.
- Consequences:
  - Google's event is closed, and Graphene has no Gemini path any more. The name is a leftover. Only the local folder carries it; the GitHub repository is `Alex-lop/Graphene`.
  - For Nebius, the repo predates 26 Aug, so requirement 8 (the written explanation of what changed) applies. HACKATHON.md:350-375 already covers it.
- A similarly named but unrelated event: Apify's "All things agent hackathon" (https://luma.com/6eqa8nbh).

## 3. The repo checked against each requirement

| # | Requirement | State on origin/main 921834de | Severity |
|---|---|---|---|
| R1 | A runtime call to Token Factory with a Nemotron model | **In the code.** `graphene init --planner/--executor nemotron` (checked with `uv run graphene init --help`). `tests/nemotron`: **286 passed, 9 skipped in 91 s** in my clone, all against the scripted stand-in. Live: practice only, on 29 Sep and 2 Oct (HACKATHON.md:9-12). | OK in code; live proof is thin |
| R2 | Fits the track ("agents that write, run, and test code in Token Factory") | Only the Nemotron path fits: Ultra plans, Nano/Super execute, Graphene runs the check. Since mid-October the product puts **Claude Code first** (README:22, 63, 74). | **High.** See R4. |
| R3 | Working demo URL / test build | The candidates are PyPI `graphene-map` and `uvx --from graphene-map graphene demo`. **PyPI's latest is 0.5.0** (pypi.org JSON shows releases 0.2.0 and 0.5.0). Per memory it is 184 commits behind main and has no cockpit. A judge on PyPI gets a different product from the README and the video. | **High.** Needs Alex's 0.5.1 tag and push. |
| R4 | README highlights Nemotron and Token Factory | **The README says nothing about it.** `grep -i "nemotron\|token factory\|nebius\|hackathon" README.md` gives 0 lines. Alex's uncommitted README (context/alex-uncommitted-README.md) also has none. A Stage One reader sees "Claude Code or Codex" and could rule it a "superficial rebrand of an unrelated idea". | **Critical.** This is the pass/fail gate. |
| R5 | Video under 3 min, public on YouTube, project footage, Token Factory and Nemotron named | Alex's video (https://www.youtube.com/watch?v=S3mucmwD-kQ, 2:42, 17 Oct) is an essay with **no product footage** and no Token Factory or Nemotron. It does not meet the rule. `dev/demo/STORYBOARD.md` and `dev/launch/video.md` are both stale (see §4). | **Critical.** Alex has to record it. |
| R6 | Public repo with a visible license | Met. The GitHub API says `visibility: public`, `license: Apache-2.0`. The About section has description and topics, but **no topic names nemotron or nvidia** (topics: agent-orchestration, agentic-ai, agentic-workflow, ai-agents, claude-code, cli, developer-tools, git). Its description ("Trying to make the collaboration w/ Claude better...") also names only Claude. | Medium. Only Alex can change it (web UI). |
| R7 | Feedback section | Written: HACKATHON.md:378-436 (ids cased three ways, ConTree `cat`, Nano token use, and more). It is the best-prepared part. | OK. Refresh the dates. |
| R8 | What changed since 26 Aug | Written: HACKATHON.md:350-375. **Its numbers are frozen at 0334168**: "421 commits after". `git log --since=2026-08-26` now counts 971, and 181 before. The prose stops at 2 Oct, with nothing on the cockpit, Tell, sign-off or `demo --cheat`. | Medium |
| R9 | Testing until 15 Dec | HACKATHON.md:452-489 is stale (see §4). The judges' key path is `NEBIUS_API_KEY` or `graphene key set`. `graphene key` works, but **it is not listed in `graphene --help`**: the top level shows init, ask, watch, run, plan, node, board, demo, config. | Medium / low |
| R10 | Built With | HACKATHON.md:343-346. It has no claude-code entry, which is fine. | OK |

## 4. What is stale

**docs/HACKATHON.md** (489 lines; last touched a7968825, 17 Oct, but mostly as of 29 Sep to 2 Oct):
- **The product it describes is the September tree screen.**
  - The board, with "board" appearing 42 times: lines 46-60, the board's keys `y/1-9/d/p/Enter/a` in watch.
  - `graphene watch --classic` as the place you read the plan (:69).
  - `D` in watch for the direction (:125).
  - "Then you press `R`... in a Token Factory Sandbox" (:132). The STORYBOARD says Sandboxes refused Alex's project with ForbiddenError, so leaves run in local worktrees.
  - "Tab for the graph and the map" (:480). The cockpit uses `g` and `m`.
  - Testing instructions built on `graphene board` and Tab (:456-489).
- **None of the cockpit appears**: the row per task, what waits on you first, `t` tell, `w`, `x`, `i`, `g`, `m`.
- "What we learned" still holds the placeholder "**The chart goes here**" (:288). Its live Nemotron panel says "have not run" (:326).
- Its own banner says "**No registered number here comes from a live run**" (:7). That is honest, and a judge reads it as "not demonstrated".
- It never states the deadline. The inspiration paragraph (:23-27) is close to Alex's README "Why I built this" and could adopt his wording.
- Links to the `process` branch resolve (HTTP 200 for field.md, ideas.md, winning/screens).

**dev/demo/STORYBOARD.md** (a 13-scene, 165 s live Nemotron take):
- The format is right for the rules: live, Nemotron on Token Factory, narration naming both.
- **Scenes 03-09 film the old screen**: the tree with `?` rows (03), board rows (04), `Tab` outline/tree/graph (05), `gg`, `E` vim prune (06), `/running` and the node pane (07), `/came back` + `w` (08), `gg` all green (09).
- The section "What changes with tonight's work" is about the board, the views and the direction of late September.
- Scene 12 (`graphene direction`) and scene 11 (`graphene plan record`) need checking against current commands: **not checked**.
- It needs a rewrite on the cockpit: what waits for you on top, Enter, `t` tell heard at the next write, `w` widen on a hand-back, `g` flow, `m` territory, `R`.

**dev/launch/** (written 15 Oct for the 0.5.1 launch on Show HN; Claude-Code-first):
- `video.md`: 75 s, built from `demo --cheat` and `demo`. Nemotron and Token Factory are never named. That suits HN but **does not meet the hackathon video rule**. It could be the first 40 s of a hackathon cut.
- `claims.md`: good, and it still binds. It ends with "That Nemotron is broadly tested live" as a may-not-say (:33), and the hackathon text must respect it.
- `show-hn.md` and `pitches.md`: no Nemotron. That is right for HN. There is no hackathon pitch.
- `release-notes.md`: 0.5.1, not yet released (PyPI = 0.5.0). Keys like `c` in watch need checking against the cockpit: not checked.

## 5. How the README should serve a judge

A judge has many entries and may judge "solely on the text description, images, and video". The first screen of the README has to clear Stage One and answer Technological Implementation, which is also the first tie-breaker. In order of what they look for:

1. **Within the first screen, the NVIDIA and Nebius path in one line.** For example: "Planner: NVIDIA Nemotron 3 Ultra; executors: Nemotron Nano, then Super on retry, through Nebius Token Factory; Claude Code and Codex work too."
   - This is the Stage One gate (R4), and the rules use the word "highlight".
   - It can sit below Alex's "Why I built this", but it must sit above the fold or in a clearly titled section ("Built for the Nebius x NVIDIA hackathon", or "Nemotron on Token Factory").
2. **Proof that it works: the cockpit gif/screenshot driven by a Nemotron run.**
   - The shipped replay is labelled "a scripted stand-in, no model ran". Its planner and executor are `nvidia/Nemotron-3-*-fake` (src/graphene_map/demo.jsonl, first lines).
   - A **live** recording is better: STORYBOARD.md:92-96 already describes swapping in a live `run.jsonl`.
3. **The try-it path for a judge with a Token Factory key**, 3 to 4 commands:
   - install the version with the `[nemotron]` extra,
   - `graphene key set` or `NEBIUS_API_KEY`,
   - `graphene init --planner nemotron --executor nemotron`,
   - `ask`, `watch`, `R`.
   The no-key `uvx ... graphene demo` stays as the zero-cost first step. That path also has to work from the released wheel (R3).
4. **The problem and the audience in Alex's words** (Potential Impact): the README's "Why I built this" and the video's thesis, that the human's direction is the bottleneck, not tokens. Then **what is non-obvious** (Quality of the Idea):
   - the agent proposes a plan of leaves, each with files and a check,
   - writes outside a leaf are refused before they happen,
   - "done" is the check Graphene runs itself,
   - a cheap model (Nano) is safe to spend in bulk because the scope and the check hold it, which is the Token Factory angle that HACKATHON.md:23-27 already argues.
5. **Honesty that does not read as "unproven"**: keep claims.md's limits. Put them in a details block, not in the opening lines.
6. A link to the Devpost text (docs/HACKATHON.md), the feedback section, and the license, which is already in the footer.

## 6. What the submission still needs, by owner

**Only Alex can do these:**
- Record the ≤3 min YouTube video with audio naming Token Factory and Nemotron, filmed on the cockpit. A live take spends his key, and `build.sh` refuses an agent's shell (STORYBOARD.md:70).
- Tag and push 0.5.1 to PyPI.
- Add nemotron/nvidia topics and a description that names them in the GitHub About section.
- Fill in the Devpost form before **30 Oct, 10:00 PT**.
- Optionally opt in to the "Will It Ship" review on **20 Oct**.
- Get at least one live Nemotron run on the cockpit for the video and README numbers.

**A night agent can do these on the branch:**
- A README section that highlights Nemotron and Token Factory (R4, critical).
- A STORYBOARD rewritten for the cockpit keys.
- HACKATHON.md brought to the cockpit and Claude-Code-first reality: commit counts (971 after and 181 before, `git log --since/--before=2026-08-26`), what changed since 2 Oct, testing instructions with `g`/`m`/`t`, and the deadline stated.
- `graphene key` listed in `--help`.
- A hackathon pitch line next to dev/launch/pitches.md.

## Commands run
- `curl -sL -A <Safari UA>` on the Devpost overview, rules, resources, updates, /details/faqs and five update posts → HTTP 200. `/faqs` returned 404; the real path is /details/faqs.
- The same for allthingsagentichackathon.devpost.com and /rules → 200.
- `curl api.github.com/repos/Alex-lop/Graphene` → public, Apache-2.0, topics as listed in R6.
- `curl pypi.org/pypi/graphene-map/json` → 0.5.0.
- `uv run pytest tests/nemotron -q -n auto` in <scratch>/agents/hackathon → 286 passed, 9 skipped.
- `uv run graphene --help`, `graphene init --help`, `graphene key --help`.
- `git log --reverse`, `--since` and `--before` counts.
