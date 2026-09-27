# The field: Coding and Agentic Engineering, 2026-09-25

*Private note for `docs/process/field.md` (item 11 of `WINNING_DIRECTIVE.md`). Everything about other entries comes from their public READMEs. None of it was run here, so "live" means "the README says it ran live".*

## Searches run (repeatable, read-only)
- **Devpost:** WebFetch plus a plain `curl` GET (for verbatim text) of `nebiusglobalaihackathon.devpost.com/` `rules`, `project-gallery` and `resources`, and WebFetch of `devpost.com/software/indie-app-ops-agent-nemotron-edition`.
- **Gallery:** not public. The page says "The hackathon managers haven't published this gallery yet, but hang tight!" It shows Participants (11988).
- **`gh search repos "<q>" --sort updated --limit 30`**, with q = nebius hackathon · nebiusglobalaihackathon · nebius nvidia hackathon · token factory nemotron · nebius token factory · contree · contree sandbox · token factory sandbox · nemotron coding agent · nemotron agent sandbox · nebius coding agent · nebius nemotron · nemotron 3 ultra · nemotron swe agent · nebius sandbox agent · Token Factory Sandboxes · nemotron sandboxes · coding agent nebius · agentic engineering nemotron · Coding and Agentic Engineering · nemotron nano coding · nemotron super coding agent · contree agent · sandbox branches nemotron · nemotron patch test agent · nebius x nvidia · Global AI Hackathon nemotron · nemotron tree plan agent · nemotron parallel agents.
- **`gh search code "<q>" --limit 60`**, with q = contree_sdk · ContreeSync · from contree · contree-sdk · nebiusglobalaihackathon · Token Factory Sandboxes · tokenfactory.nebius.com · Coding and Agentic Engineering.
- **WebSearch:** `devpost "Nebius" "Token Factory Sandboxes" coding agent Nemotron` · `"nebiusglobalaihackathon" Coding and Agentic Engineering` · `ConTree sandbox fork checkpoint coding agent Nemotron hackathon github` · `devpost.com/software Nemotron "Token Factory" sandbox coding agent` · `github Nemotron Token Factory coding agent human approves plan tree parallel sandboxes scope containment` · `"Nebius x NVIDIA" hackathon coding agent sandbox escape containment test Nemotron github`.
- **For each candidate:** `gh api repos/<owner>/<repo>/readme -H "Accept: application/vnd.github.raw"`.

## The rules, verbatim (rules page)
- **Submission Period:** "Wednesday, August 26, 2026 (9:00 am Pacific Time) – Friday, October 30, 2026 (10:00 am Pacific Time)". The header reads "Deadline: Oct 30, 2026 @ 10:00am PDT".
- **Judging Period:** "Tuesday, December 1, 2026 (9:00 am Pacific Time) – Tuesday, December 15, 2026 (12:00 pm Pacific Time)".
- **Track:** "Build coding agents and developer tools: agents that write, run, and test code in Token Factory Sandboxes."
- **Runtime:** "Runs on Nebius Token Factory or Nebius AI Cloud" means the project makes a runtime call to the Token Factory inference API, or is deployed/run using Nebius AI Cloud compute (Serverless Jobs, Serverless Endpoints, or DevPods).
- **Stage One:** "The first stage will determine via pass/fail whether the ideas meet a baseline level of viability, in that the Project reasonably fits the theme and reasonably applies the required APIs/SDKs featured in the Hackathon. A Project reasonably fits the theme if it is a genuine attempt at the track's stated goal, not a superficial rebrand of an unrelated idea."
- **Stage Two**, "equally weighted":
  - "Technological Implementation: How well is the project built, and how effectively does it use Nebius Token Factory or AI Cloud model(s), and NVIDIA Nemotron or other NVIDIA open source models as part of the solution?"
  - "Design: Does the project deliver a complete, coherent product experience not just a technical proof of concept?"
  - "Potential Impact: Does the project make a credible, specific case for solving a real problem for a real audience and does the solution actually address it based on what's demonstrated?"
  - "Quality of the Idea: Is this a creative, non-obvious use of Nebius Token Factory or AI Cloud model(s), and NVIDIA Nemotron or other NVIDIA open source models and does the team show genuine understanding of the problem space?"
- **Ties** are broken by the first criterion listed, then the next.
- **README:** "Include a README with setup instructions and clear guidance for running your project." "Make sure to highlight how you’ve used NVIDIA Nemotron or other NVIDIA open source models and where Token Factory accelerated your workflow and any other Nebius Tools or Services used."
- **Video:** "should be less than three (3) minutes. Judges are not required to watch beyond three minutes"; "should include footage that shows the Project functioning on the device for which it was built"; "must be uploaded to and made publicly visible on YouTube". The overview page adds: "with audio covering how you used Nebius Token Factory and NVIDIA Nemotron or other NVIDIA open source models."
- **Functionality:** "must function as depicted in the video and/or expressed in the text description."
- **Testing:** "available free of charge and without any restriction ... until the Judging Period ends. Judges are not required to test the Project and may choose to judge based solely on the text description, images, and video provided in the Submission."

## Entries found, closest first (all name this hackathon and the Coding track unless noted)
- **Arborist**, github.com/ZNLong2203/Nebius-Nvidia. Repairs a repo by "searching a tree of sandbox states": Super writes the hypotheses, Nano writes one patch per fork, Ultra steps in on stalls and ties. The tree is live and clickable.
  Live on Sandboxes and Nemotron, with a recorded public demo. SWE-bench Lite, 23 issues: branching 14/23 against linear 15/23, at $1.94 against $5.84. Test files are protected. No human pruning, and no write-scope containment.
- **Coppice**, github.com/morpheus-csmith/coppice. Forks one verified checkpoint into up to 16 candidate patches, runs the real suite in each, "cut back the failures". Uses tree language too.
  Live on Nemotron Super and Sandboxes. 10 SWE-bench Lite instances: 11% at 1 try, 60% at 16, $0.29 for the sweep. The width curve replicates on Docker and on Sandboxes. Nano/Super/Ultra were measured (only Super applies patches). Sandboxes vs Docker: 4.6 s against 66 s per branch. No containment claim.
- **ARCHON**, github.com/CodeWithEugene/Archon. Sandbox-verified repair and OpenAI/Anthropic-to-Nemotron migration, one Sandbox fork per candidate patch, a Tavily-grounded prompt, and a hosted cockpit (replay).
  Live since 12 Sep: 6/6 SWE-bench Verified `psf/requests` instances in Sandboxes for $0.67. It reports an honest migration failure. No containment claim.
- **PortVerdict**, github.com/dorakingx/portverdict. A migration agent that forks three strategies "from one immutable Sandbox checkpoint", tries to falsify each, and picks one or abstains.
  Its public demo is an "immutable recording" of live Nemotron, Tavily and Sandbox runs. The recorded suite: 9 builds passed, 6 candidates failed. Has provenance and security gates.
- **Chesterton**, github.com/ManuelGamal/Chesterton. A counterfactual reviewer: deletes each line of an AI patch in a Sandbox fork (24 at a time) and reports which deletions the tests never notice.
  Replay plus one live Super call. Its benchmark is **"pre-registered and reported as registered, including its null result."**
- **SwarmForge**, github.com/sampreeth0x/Swarmforge. A Super planner breaks a request into a **DAG of subtasks**. Nano workers each run in their own sandbox and may fork to race two approaches. A verifier, a judge and a merge arena follow.
  The demo is mock mode. A ConTree backend exists, but the README reports no live results. No human edits the plan.
- **SandForge**, github.com/AntrikshH90/sandforge. Plan (Nano), patch (Super), test. On red it backtracks to a clean checkpoint and escalates the strategy, up to 4 tries. It has a "branch tree of every attempt" dashboard and opens a real PR.
  Has a ConTree provider, but the README does not say it ran live (it was built in local/mock mode "before cloud keys were attached"). No evaluation numbers.
- **RepoMedic**, github.com/Almario1/repomedic. CI repair: reproduces the failure in a Sandbox, then "tournaments" candidate patches, each in a branch forked from one seeded state. Nano triages and Ultra patches. The offline demo covers 5 scenarios, and the model is mocked. It reports no live run.
- **sandcoder**, github.com/Sppdd/900. Best-of-N: N agents fork from one post-setup snapshot and the tests pick the winner. The README states no live results or numbers.
- **trialist**, github.com/mskutlu/trialist. Issue to green: a Lightning → Super → Ultra escalation ladder, ConTree rollback by branching "when available", test files read-only. Has a mock mode and reports no live results.
- **PQC Factory**, github.com/shankarsai000/pqc-factory. Ticket in: Ultra plans 2–3 approaches, each runs in a forked Sandbox branch with implementer, verifier, security and performance stages, and the best score wins. Local mode is the default. No live numbers.
- **Principal (AMTDRS)**, github.com/BugHunterX2101/AMTDRS. A wide-refactor swarm with a gate pipeline. **Gate 1 is "scope": the patch may only touch the files its blast radius allows** (a local check). Races attempts in Sandbox forks, and a human approves the PR. Its live demo runs without credentials, and it reports no live Sandbox results.
- **RuleBranch**, github.com/jessecalvin08/rulebranch. Turns plain-language permissions into tests of whether a coding agent stays inside its authority (.env, deletes, exfiltration).
  Live Nemotron, and "real runs recorded, including a measured block of an attempted secret read under enforcement" in Sandboxes. This is **containment at the policy/tool level, on the service.**
- **Shadow Engineer**, github.com/creatoropener/shadow-patch. A GitHub Action writes a hidden regression test first, runs 3 repair candidates in separate Sandbox branches (one after another), and replays the winner from a clean image. Recorded live run: 3 candidates, 2 passed.
- **Heisenbug**, github.com/matricphase-dot/heisenbug. Classifies flaky tests by forking replicas from byte-identical state at several fork points. Nano, Super and Ultra were verified live, and the hosted demo is a replay.
- **Others in this track, briefly:**
  - AgentSquad (piechockidaniel/agentsquad-nebius-maintenance): Contree MCP with fixed commands only, live Super.
  - BranchSmith (lifeinbeats9-prog/branchsmith): N candidates, falls back to the Best Apps track without ConTree.
  - PatchScout (zhaofeipeter/patchscout): demo mode is the default.
  - a11y-fix-agent (ryanilano): Super, then an Ultra retry.
  - Glitch Garden Cloud (Laolex).
  - AgentForge (MOHITPRADHAN35): Docker, not Sandboxes.
  - RoboCo (rennf93/roboco): a 176-star existing product that added the Token Factory provider and a `run_sandbox_tests` verb.
  - AgentDyno (muraliikrishnant): a harness dynamometer.
  - InfraSentinel (mojealterego).
  - Nemotron Axiom (fokrulanthro16-eng).
  - Plans only: FlakeProof (TahaKotwal12), Basebreak (zyganali-glitch), DEVOPSS-ENGINEER (marsshark13), sdlc-code (ChinGuang). **sdlc-code has a human "Design Gate" before coding; its agents are not built.**
- **Other tracks, but close in idea:**
  - Scopewatch (dkritarth): a pre-execution scope gateway, not on Sandboxes.
  - AetherGuard (davidakanno56-bit): a tool-call scope proxy.
  - Blast Radius (jenish1345, Best Apps): runs actions in a fork and compares the diff to the stated intent.
  - TracePilot (QIU-Guanzong, Best Apps): a human gate, mock only.
- **Not entries:** fruteroclub starter, opencolin workshop and skills, kreuzhofer Sandboxes demos and `tofa` CLI, nebius/contree-*.

## Where Graphene differs, and how far that holds
1. **The person prunes the tree the agent proposes, before anything is spent.** No entry found lets a person edit or prune the agent's plan and then run it. SwarmForge's DAG is never shown to a person. sdlc-code's Design Gate is unbuilt. Principal and Shadow Engineer put the human at the PR, at the end. This is the one difference the field supports, stated as "we found none", never "nobody".
2. **Containment on the service.** Graphene's escape test (redirect, `sed -i`, `open(w)`, `mv`, `rm`, git, symlink, `chmod`, all against a `setpriv` scope user) is so far **proven only against a Docker stand-in, not on ConTree.** RuleBranch has already recorded a live Sandbox block, at the policy level. Principal checks scope on the patch. trialist and Arborist protect test files. No entry found runs a filesystem-scope escape suite on Sandboxes, but until Graphene runs it live, neither has Graphene.
3. **Forks as the tree.** Forking N candidates from one checkpoint and letting the check pick is the field's **most common pattern**: Arborist, Coppice, ARCHON, PortVerdict, Chesterton, RepoMedic, sandcoder, PQC Factory, SwarmForge and Shadow Engineer all do it. Escalating through the tiers is common too (trialist, SandForge, Arborist, Principal, a11y). What stays Graphene's own is only the mapping: each leaf of the person's pruned plan gets its sandbox from one per-commit checkpoint, with forks inside the leaf.
4. **Pre-registered evidence, not yet run.** Chesterton pre-registered and published a null result. Coppice replicated its curve on two backends. Arborist compared branching against linear on SWE-bench Lite. ARCHON reports SWE-bench Verified results. Graphene has no live number yet. Its distinct axis is **tree against paragraph, same model, with the person's attention measured**, which no entry found measures. It counts only once it has run.

## Claims the submission must not make
- "The only / first tool that forks sandboxes from one checkpoint", "runs N forks and lets the check pick", "maps a tree onto a tree of sandboxes" or "searches a tree of sandbox states". Arborist, Coppice, SandForge and others falsify each of these. The directive's line "Nobody else maps a person's pruned tree onto a tree of sandboxes" should go out only as "we found no other entry where a person prunes the plan".
- "The only one with Nano→Super escalation", "with per-call pricing" or "with honest or pre-registered evaluation" (trialist, Coppice, Chesterton).
- "Most agent tools trust the model" as a contrast with this field. Most entries here gate on tests, and several gate on scope or policy (Principal, RuleBranch, AgentSquad).
- "Most entries are chat wrappers or proofs of concept." The Coding field has hosted cockpits, benchmarks and live recordings (ARCHON, PortVerdict, Arborist, Coppice). Do not disparage the field.
- "Containment proven in Token Factory Sandboxes" or "we can show the log", until the escape test has run on ConTree. Docker footage must never be shown or described as Sandboxes.
- **Any live claim that has not happened:** Nemotron plans or executes on Token Factory, a leaf ran in a Sandbox, landed share, cost per landed leaf, fork timings, the tree-vs-paragraph result. As of today there is no key in this session and no live run. The video and README may say only what was executed and recorded.
- "Today the only ways to steer agents are a paragraph and a diff" should be softened to "for most agents". sdlc-code's Design Gate and Principal's reviewer are other steering points in this field.