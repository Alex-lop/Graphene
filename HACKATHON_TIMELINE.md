# All Things Agentic Hackathon — Timeline and Requirements

> **Historical schedule snapshot — not current product truth.** Recheck the official rules and current deadlines before acting. Product authority is indexed in [`docs/HISTORY.md`](docs/HISTORY.md).

Source snapshot: August 10, 2026 (Pacific Time). The [Official Rules](https://allthingsagentichackathon.devpost.com/rules) are binding; recheck them before submitting.

## At a glance

- Official submission deadline: **August 31, 2026 at 5:00 PM PT**.
- Recommended internal deadline: **August 31 at 12:00 PM PT**.
- Request the **$150 Google Cloud credit** immediately. The form closes **August 28 at 12:00 PM PT** or earlier if supplies run out, and review can take 72 business hours.
- Get a thin, deployed, end-to-end demo working by **August 14**.
- Freeze scope by **August 25** and code by **August 28**.
- Optimize for the published rubric: **utility 40%, architecture 30%, demo/readiness 30%**.
- Build one convincing workflow. Extra integrations and bonus models are lower priority than a reliable demo.

## Official dates

| Date | Official event or deadline |
|---|---|
| Aug 3, 9:00 AM PT | Contest and submission period began |
| Aug 11, 8:30–10:00 AM or 9:00–10:30 PM PT | Webinar: multi-agent orchestration patterns |
| Aug 13, 9:00–10:30 AM or 9:00–10:30 PM PT | Webinar: long-running, resumable ADK workflows |
| Aug 20, 9:00–10:30 AM or 9:00–10:30 PM PT | Webinar: self-evolving agents |
| Aug 27, 9:00–10:30 AM or 9:00–10:30 PM PT | Webinar: agent memory and state |
| Aug 28, 12:00 PM PT | Cloud-credit request deadline, subject to supply |
| **Aug 31, 5:00 PM PT** | **Submission deadline** |
| Sep 1, 9:00 AM PT–Oct 1, 11:45 PM PT | Judging period |
| On or around Oct 8 | Winners announced; monitor email daily |

### Published date conflicts

The Devpost Schedule page gives different opening, judging-end, and winner-announcement times than the Official Rules. The August 31 deadline agrees. Use the **Official Rules** for planning and describe the announcement as “on or around October 8.”

The judging section also contains stale track names—“Continuous Action Engine,” “Evolving Knowledge Engine,” and “Multi-Agent Nexus”—while the current tracks are Taskmaster, Collaborative Partner, and Fortified Enterprise Fleet. Ask the organizer how those old track-specific judging notes map to the current tracks. Until clarified, rely on the current track definitions and the top-level 40/30/30 rubric.

## Requirements for every idea

### Eligibility and team

- Entrants must have reached the age of majority where they live by August 3, 2026 and have internet access.
- The rules exclude specified jurisdictions and contest-affiliated employees, family members, and household members. Check the eligibility section rather than relying on this summary.
- Individuals, teams, and organizations may enter. The rules do not state a team-size maximum.
- Add every teammate to the Devpost project and designate one representative.
- Multiple entries are allowed only when they are unique and substantially different. A project may win at most one prize.

### Project

- Create the project during the submission period. Standard frameworks, libraries, starter templates, and AI coding assistants are allowed; disclose other pre-existing code or work.
- Pick **exactly one** current track:
  - The Taskmaster
  - The Collaborative Partner
  - The Fortified Enterprise Fleet
- The project must work consistently as shown and described.
- Third-party code, APIs, data, trademarks, and other materials must be licensed or authorized for use.
- Do not expose credentials, personal data, private prompts, or proprietary source material in the app, repository, graph, logs, or video.

### Mandatory technology

Every project must use all three:

1. **Gemini 3.5 or newer**, through the Gemini API or Vertex AI.
2. At least one Google agent framework: **ADK, GenAI SDK, Antigravity SDK, or Genkit**.
3. At least one Google Cloud infrastructure service, such as **Cloud Run, Firestore, Cloud SQL, GKE, or Pub/Sub**.

### Submission checklist

- [ ] Select one track.
- [ ] Provide a hosted project URL if available; hosting is strongly encouraged.
- [ ] Describe features, functionality, technologies, data sources, findings, and learnings.
- [ ] Link a public or private GitHub, GitLab, or Bitbucket repository.
- [ ] If private, grant access to `testing@devpost.com` and `cloudhackathons@google.com`.
- [ ] Put step-by-step local setup or deployment instructions in `README.md`.
- [ ] Include a clear architecture diagram.
- [ ] Upload a publicly visible YouTube or Vimeo demo in English or with English subtitles.
- [ ] Keep the demo at or below four minutes; only the first four minutes may be evaluated.
- [ ] Show the problem, value proposition, and the real application working.
- [ ] Show visible proof that the backend runs on Google Cloud: for example, a `.run` URL, Cloud Run dashboard, Google Cloud Console, or Vertex AI logs.
- [ ] Verify every URL and credential from a logged-out browser.
- [ ] Remove secrets and test data before making anything public.
- [ ] Submit before the internal noon deadline and save proof of submission.

If a hosted URL is submitted, keep it stable and accessible through judging. Use scale-to-zero, instance caps, endpoint protection, and budget alerts to control cost.

### After the deadline

- Do not edit the submitted video, repository, app, or other submission artifacts. Continue work in a fork or separate branch that judges do not receive.
- Keep testing access valid through the judging period.
- Monitor email daily. The rules allow only two days to answer a potential-winner notification.

## How judging works

Stage one is pass/fail: every required artifact must be present, the project must address a challenge, and the required technology must be used.

| Criterion | Weight | What must be obvious |
|---|---:|---|
| Innovation and Operational Utility | 40% | A specific real-world friction is removed through autonomous action, not just chat or content generation. |
| Architectural Discipline and Tech Stack | 30% | State, memory, credentials, failures, retries, and component boundaries are deliberate and credible. |
| Demo and Production Readiness | 30% | The live execution, Google Cloud deployment, architecture, and reproducible setup are undeniable. |

Optional bonus points come only after the main judging stages:

- Public build article, podcast, or video: **+0.2**.
- Qualifying social post; use `#AllThingsAgenticHackathon` on X or LinkedIn: **+0.2**.
- An additional Google model such as Gemma, Veo, or Lyria: **+0.2 each, up to +0.6**.

The listed cash prizes total $180,000. The Grand Prize is $50,000; each current track prize is $20,000. Bonus work should wait until the core project can plausibly score five out of five.

## Build plan from August 10

| Date | Work | Exit condition |
|---|---|---|
| **Aug 10** | Register, add teammates, designate the representative, request credits, open a Devpost draft, and select the intended track. | Accounts and eligibility are handled; credit request is submitted. |
| **Aug 10–11** | Lock one user, one painful workflow, one measurable outcome, and one golden demo. | The idea can be explained without saying “platform,” “ecosystem,” or “for everyone.” |
| **Aug 11** | Watch the multi-agent webinar only if the task genuinely needs multiple agents. | Architecture choice is written down; needless agents are cut. |
| **Aug 12–14** | Build and deploy the thinnest end-to-end slice with the mandatory stack. | One real goal completes on Google Cloud and produces visible evidence. |
| **Aug 15–18** | Complete the differentiating loop. For the lineage idea: observable events create the graph, an output traces back to sources/actions, and feedback changes later work. | The product changes what the agent does; it is not a passive dashboard. |
| **Aug 19–21** | Add persistence, one safe failure/retry path, credential scoping, content redaction, and a minimal automated check. | A restart and one expected failure do not corrupt or duplicate work. |
| **Aug 22–24** | Test with two outsiders; finish the architecture diagram and first complete README. | Both testers can explain what happened and reproduce the happy path. |
| **Aug 25** | Freeze scope and record a rough four-minute demo. | Full story works in under four minutes; only visible or scoring-critical defects remain. |
| **Aug 26–27** | Run the golden path repeatedly and fill the Devpost draft. Use the memory webinar only to close a known gap. | Ten representative runs are reliable; submission text is substantially complete. |
| **Aug 28, noon PT** | Credit deadline and recommended code freeze. | No new features; README, diagram, and demo script are frozen. |
| **Aug 29** | Record the final demo. | A public 3:30–3:45 video shows a real run and Google Cloud proof. |
| **Aug 30** | Audit from a logged-out browser. Check links, permissions, credentials, subtitles, secrets, setup steps, and every requirement. | A fresh reviewer can access everything without help. |
| **Aug 31, noon PT** | Internal submission hard stop. | Submission is sent and receipt captured, leaving five hours for emergencies. |
| **Sep 1–Oct 1** | Judging freeze. | Submitted artifacts and testing access stay unchanged and available. |
| **Through Oct 8** | Check email daily. | Any verification request is answered within two days. |

## Four-minute demo cut

- **0:00–0:25:** the specific problem and cost of the current failure.
- **0:25–0:45:** the user’s goal and one useful clarifying question.
- **0:45–2:15:** an unedited autonomous run with visible state changes.
- **2:15–2:50:** inspect the result and trace it to evidence, actions, and approvals.
- **2:50–3:15:** give feedback and show that it alters the next action.
- **3:15–3:35:** show one safe failure or resume path.
- **3:35–3:55:** show the architecture and visible Google Cloud deployment proof.
- **3:55–4:00:** repeat the value in one sentence.

## Final gates

Do not submit until every answer is “yes”:

1. Does it solve a narrow problem a real person recognizes?
2. Does the agent take meaningful action with limited hand-holding?
3. Is Gemini reasoning necessary rather than decorative?
4. Can a judge see state, memory, failure handling, and scoped tools?
5. Does the live demo prove the outcome in under four minutes?
6. Is Google Cloud deployment visible?
7. Can a stranger reproduce it from the README?
8. Are sensitive inputs redacted and secrets absent?

## Sources

- [Official overview and requirements](https://allthingsagentichackathon.devpost.com/)
- [Official Rules](https://allthingsagentichackathon.devpost.com/rules)
- [Official Schedule](https://allthingsagentichackathon.devpost.com/details/dates)
- [Resources, credits, and webinars](https://allthingsagentichackathon.devpost.com/resources)
- [Frequently Asked Questions](https://allthingsagentichackathon.devpost.com/details/faqs)
- [Google Cloud credit request](https://forms.gle/5PtXmw1dSbDnpYke9)
