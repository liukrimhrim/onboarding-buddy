# Curriculum: Temporal — how we use it, and how it works

**Status:** in_progress
**Current lesson:** 1

## Goal

After these five sessions you can open a failed `llamaparseWorkflow` (or any other workflow in this repo) in the Temporal UI, read the event history, and form a grounded hypothesis about *why* it failed and where to fix it — not just file the error in Slack. Alongside that, you have a working mental model of what a workflow engine actually *is*, so the official Temporal docs read like prose instead of incantations.

Bias is **debug + concept understanding**, not "design a brand-new workflow." Temporal Schedules are explicitly out of scope.

## Prerequisites

- Comfortable with Python async (`await`, tasks, cancellation).
- You've at least seen the Temporal UI — clicked into a workflow, looked at the event history tab, even if it was opaque.
- Working knowledge of this repo's service split (backend / parse service / activities). Not deep — just "I know where `backend/src/parse/temporal/` lives."

No prior Temporal-internals reading required. Jargon is used directly; first occurrence of each new term gets a one-line gloss.

## Lessons

- [ ] 1. **Workflows vs. activities, and why the split exists** — by the end, you can read any workflow function in this repo and immediately tell which lines are "durable orchestration" vs. "real side effects," and explain to a new hire why the boundary is where it is.
- [ ] 2. **Event history is the source of truth** — read a real `llamaparseWorkflow` history end-to-end (or a sanitized one). Map every UI row to either a workflow command or an external event. Understand replay: what gets re-executed vs. what is restored from history.
- [ ] 3. **Failure modes: timeouts, retries, NDE, and the difference between them** — `ActivityTaskFailed` vs. `WorkflowTaskFailed` vs. `Non-Deterministic Error`. When the framework retries for you, when it doesn't, and why `workflow.patched(...)` exists. Anchor: `backend/src/temporal/workflow/error_handling.py`, `non_retryable.py`, and the team's NDE notes in `backend/CLAUDE.md`.
- [ ] 4. **Task queues, workers, and how work actually gets picked up** — why this repo has `parse`, `parse-activity-queue`, `extract`, `concurrency-limiter`, etc. as separate queues; how `DynamicWorker` registers everything but listens on one queue; how KEDA scales workers based on queue backlog. (`KEDA scaler` gloss: a Kubernetes autoscaler that watches an external signal — here, Temporal queue depth — and adjusts pod count.) Anchor: `backend/src/temporal/worker/dynamic_worker.py`, `backend/src/temporal/registry/`, RUNBOOK env vars.
- [ ] 5. **Putting it together: triage a real failure** — pick one failed workflow (from the triage-parse-workflow-failures skill or a recent prod incident), and walk the full path: UI symptom → event history → which activity → which retry policy → which code change would fix it. This lesson is mostly *you* driving; I'm there to challenge the reasoning, not to lecture.

Each lesson also closes with the "general concept" climb: what's the abstract problem space, and how do alternatives (Airflow, Step Functions, raw RabbitMQ + a state table, Cadence) solve it differently.

<!-- Mentor scratchpad — terse calibration bullets, not session journaling. -->
## Mentor scratchpad

- User wants jargon direct but first-occurrence gloss. Don't over-define on second use.
- Debug/concept bias confirmed — deprioritize "how to design a new workflow."
- Schedules explicitly skipped.
