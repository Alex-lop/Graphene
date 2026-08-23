# Next steps — answers from the last session

Plain-language answers to the three things you asked about, plus what the last session found and fixed.

## 1. What we found, and why you don't see the commits on GitHub

### What we found

Running the live two-worker Gemini mission for the first time (never done before this session) surfaced a real bug that no fake-model test could have caught: the real Gemini Developer API rejects any `response_schema` that contains `anyOf` — which is exactly what every optional field in our `PlanIntent`/`WorkerIntent` models produces — with an undetailed `400 INVALID_ARGUMENT`. The SDK's own documented alternative (`response_json_schema`) failed the same way in live testing.

**The fix:** stop asking the API to enforce a schema at all. Instead, the schema is embedded as a plain-text instruction in the prompt, and Graphene keeps doing what it already did — strictly validating the model's JSON response against the real schema afterward, failing closed if it doesn't match. This is proven by the full fake-model test suite passing, and by one confirmed live pass of the two-worker mission test.

**What that live pass proved:** two distinct real Gemini worker sessions, evidence-bound receipts, measured overlap between the workers, exact verification, and the source repository left completely untouched — the actual core of "Graphene coordinates two real Gemini coding workers."

**What's still not proven:** a second attempt to capture durable evidence (so the proof labels in `contracts/product_proof.json` could officially flip) hit a real limit — `gemini-3.5-flash`'s free tier caps at **20 requests per project per day**. That's a daily cap, not a short rate limit, so it can't be waited out in minutes. All the details, including the exact error and the fix, are recorded in [`docs/NORTH_STAR_RUNBOOK.md`](docs/NORTH_STAR_RUNBOOK.md) (section "0.1a") and [`docs/AGENT_RUNTIME.md`](docs/AGENT_RUNTIME.md).

Full session commit history (all on your local `main` branch): schema/redaction/store for a new "Shadow Agent" feature, worker-provider-receipt evidence binding, a macOS check executor that doesn't need Docker, a deterministic failure-lab test, `graphene why --json`, mission capsule export/verification, the North Star demo target repo, and finally this live-Gemini schema fix.

### Why you don't see the commits on GitHub

Good news: **most of them are already there.** I checked `origin/main` (your GitHub repo) directly, and 16 of the session's commits are already pushed — someone or something pushed them while I was working (not me; I never run `git push` on my own, per your standing instructions). Only the **last 2 commits** (the schema fix and the evidence-capture script) are sitting locally, unpushed.

Two things to check on your end:
- Make sure you're looking at the **`main` branch** on GitHub, not a stale cache or a different branch (there's also `agent/fix-clean-checkout-docs`, which is a different, older branch).
- Try a hard refresh of the GitHub page.

I have **not** pushed the last 2 commits myself — pushing to GitHub is something I only do with your explicit go-ahead, since it's visible to anyone with repo access. Tell me to push and I will (`git push origin main`), or push them yourself with a plain `git push` from the repo.

## 2. Where to put your new Gemini API key

First: **go rotate the one you pasted in this chat** — treat it as compromised. Get a fresh one from [Google AI Studio](https://aistudio.google.com/app/apikey).

Then, the key goes in your terminal's environment, **never in a file that gets committed, and never pasted into a chat with me.** Two ways to do it, in order of preference:

**Option A — type it directly, every session (safest):**
```bash
export GEMINI_API_KEY='your-new-key-here'
```
Run this in your terminal before running any `graphene` command that needs live Gemini. It only lives in that terminal's memory; nothing touches disk. Downside: you retype it every time you open a new terminal.

**Option B — a local `.env` file (convenient, still safe):**
This repo already has `.env` in `.gitignore` (I double-checked — a file literally named `.env` at the repo root will never be committed). Create it:
```bash
cp .env.example .env
```
Then edit `.env` and fill in just the `GEMINI_API_KEY=` line with your real key. Since nothing in the code auto-loads `.env` files, load it into your shell before running commands:
```bash
set -a; source .env; set +a
```
Run that once per terminal session, then your `graphene` commands will see the key.

Either way: never put the key in `.env.example` (that file **is** committed — it's a template with the names of the variables, not real values) and never paste a real key into a Claude Code chat message again — anything you type to me becomes part of this session's saved transcript.

## 3. Switching to Vertex AI (uses your $150 GCP credit, no daily cap)

The `gemini-3.5-flash` free tier's 20-requests-per-day cap only applies to the AI Studio API key path. Vertex AI bills through your Google Cloud project instead — which is exactly what your $150 hackathon credit is for — and has no such daily cap.

### On the Google Cloud Console website

1. Go to **[console.cloud.google.com](https://console.cloud.google.com)** and make sure the project selector (top left) shows the project where you redeemed the `CNHR-7NY8-HNEG-PHYY` credit. If you haven't redeemed it yet, do that first at **[console.cloud.google.com/billing/redeem](https://console.cloud.google.com/billing/redeem)**.
2. Confirm billing is linked: **Billing** in the left sidebar should show that project with an active billing account (the credit shows up there once redeemed).
3. Enable the Vertex AI API: go to **[console.cloud.google.com/apis/library/aiplatform.googleapis.com](https://console.cloud.google.com/apis/library/aiplatform.googleapis.com)**, make sure the right project is selected, and click **Enable**.
4. Note your **Project ID** (shown on the Cloud Console home page / project selector — it's the short slug, not the display name) and pick a region that supports Gemini, e.g. `us-central1`.

### On your Mac

`gcloud` isn't installed yet on this machine. Install it:
```bash
brew install --cask google-cloud-sdk
```
(or follow [cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install) if you don't use Homebrew.)

Then authenticate and set your default project:
```bash
gcloud init
gcloud auth application-default login
```
The second command opens a browser window — sign in with the Google account that owns the project. This is what lets Graphene's code talk to Vertex AI without any API key at all.

### Set the environment variables (this is your reminder)

**Yes — you need `GOOGLE_GENAI_USE_VERTEXAI=true`.** Set all three together, every session, instead of `GEMINI_API_KEY`:
```bash
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT='your-project-id'
export GOOGLE_CLOUD_LOCATION='us-central1'
```
Leave `GEMINI_API_KEY`/`GOOGLE_API_KEY` unset when using this mode — the code checks and fails closed if both a key and Vertex mode are set.

Check it worked:
```bash
uv run --frozen graphene doctor
```
Look for `"gemini_preflight": {"configuration_ready": true, ...}` with no error about credentials. Then you can rerun the North Star runbook or the evidence-capture script without worrying about the daily quota.
