# `graphene ui` attached live to a scripted-local mission

Captured by `scripts/capture_ui_live_frames.py`. The viewer ran as a separate
process through `ReadOnlyMissionStore` (SQLite `mode=ro`, `query_only=ON`) while
`graphene mission approve-plan` ran the fixture workers. Mission `mission_start_90826373827b3f2244e6150f`;
approve-plan exit 0; viewer exit 0; 20 distinct frames.

Credential-free scripted fixture: real scheduler, fixture workers, no model, no cloud.
What this proves: node states change on screen while the mission runs, read-only.
What it does not prove: a person watching a live model-driven mission.

## Transitions observed

- frame-0001.txt: redact_notes — → queued
- frame-0001.txt: render_json — → queued
- frame-0001.txt: render_markdown — → queued
- frame-0001.txt: wire_cli — → queued
- frame-0001.txt: assemble_candidate — → queued
- frame-0001.txt: verify_candidate — → queued
- frame-0003.txt: redact_notes queued → running
- frame-0003.txt: render_json queued → running
- frame-0003.txt: render_markdown queued → ready
- frame-0004.txt: redact_notes running → done
- frame-0004.txt: render_json running → done
- frame-0005.txt: render_markdown ready → running
- frame-0006.txt: render_markdown running → retrying
- frame-0007.txt: render_markdown retrying → ready
- frame-0008.txt: render_markdown ready → running
- frame-0009.txt: render_markdown running → done
- frame-0010.txt: wire_cli queued → ready
- frame-0011.txt: wire_cli ready → running
- frame-0012.txt: wire_cli running → done
- frame-0013.txt: assemble_candidate queued → ready
- frame-0014.txt: assemble_candidate ready → running
- frame-0015.txt: assemble_candidate running → done
- frame-0016.txt: verify_candidate queued → ready
- frame-0017.txt: verify_candidate ready → verifying
- frame-0018.txt: verify_candidate verifying → done

## Viewer stdout

```
wrote 20 frame(s) to /Users/alexlopez/Desktop/AllThingsAgenticHackathon/evidence/ui/2026-08-26/frames
```
