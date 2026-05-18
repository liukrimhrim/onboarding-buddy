# Curriculum: parse pipeline (end-to-end)

**Status:** in_progress
**Current lesson:** 1

## Goal

By the end of this curriculum you can take a `pjb-…` ID from a pager alert and (a) reason from first principles about *where* in the pipeline it is stuck — API ingress, Temporal queue, extract activity, agent activity, output activity, OCR, layout, or S3 — and (b) read the relevant code well enough to either patch a bug or write a defensible "no fix needed, here's why" note. Triage fluency first, root-cause-and-patch fluency second.

## Prerequisites

- Comfortable with Python / async / Postgres.
- Have used Temporal as a client (signals, queries) but never designed a workflow. We'll cover workflow-vs-activity, task queues, retries, heartbeats, and determinism as they come up.
- Have read the parse worker `CLAUDE.md` at `llamaparse/CLAUDE.md` (skim, don't memorize).

## Lessons

- [ ] 1. The pipeline as a system — what runs where, and why it's split that way — end with a one-page mental model and the triage decision tree
- [ ] 2. Ingress: how a `POST /parsing/upload` turns into a `pjb-…` and a started Temporal workflow — focus on idempotency, validation, and where state lives in Postgres
- [ ] 3. The TS workflow: `llamaparseMultiActivityWorkflow` line-by-line — proxyActivities, per-stage task queues, timeouts, heartbeats, rate-limit backoff, the `patched()` gates
- [ ] 4. Inside the activities: extract → agent → output, the S3 hand-off contract, the cache-hit short circuit, and the chunked agent fan-out
- [ ] 5. The infra layer (light): KEDA scalers for each task queue, role-split deployments, OCR/layout sidecars, and how saturation in one stage shows up as backlog in another. Shortest of the six.
- [ ] 6. Triage playbook: given a `pjb-…`, walk the decision tree (API → DB row → workflow ID → history → activity → S3 artifact → pod logs → upstream model). Practice on 2 synthetic cases — one app-layer failure, one queue-saturation symptom that exercises lesson 5.

<!-- Mentor scratchpad — terse, no dates -->
## Mentor scratchpad
- user wants jargon-direct with one-line inline defs; calibrate after lesson 1
- triage first, patching second — lessons 4–6 should bias toward "what does this look like when broken"
