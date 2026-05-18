# Curriculum: Temporal — repo + concepts

**Created:** 2026-05-18
**Status:** in_progress
**Current lesson:** 2

## Goal

After 5 lessons you can (a) walk a failing `llamaparseMultiActivityWorkflow` from
the Temporal UI through its event history to a root cause, and (b) explain to a
teammate, in your own words, what durable execution buys you, what an event
history *is*, why workflow code has to be deterministic, and how this team's
queue/worker topology maps onto Temporal primitives. Bias is toward
**debug + concept**, light on greenfield-build.

## Prerequisites

- Comfortable with Python async and reading TypeScript at a moderate level.
- Knows that this repo splits into `backend/` (Python) and `llamaparse/worker/`
  (TypeScript), and that parse jobs flow between them.
- No prior Temporal internals required. Casual UI use is fine.

## Lessons

- [x] 1. **The shape of a parse job in Temporal** — trace one parse job
      end-to-end across the Python `ParseJobWorkflow`, the TS
      `llamaparseWorkflow`, and the single `llamaParseActivity`. Goal: name
      every Temporal primitive (workflow, activity, task queue, worker) in
      the path.
- [ ] 2. **Event history & durable execution** — open a real workflow in
      Temporal UI, read the history end-to-end. Concept: how event sourcing
      makes workflows replayable, and what "durable execution" mechanically
      means.
- [ ] 3. **Determinism, replays, and the NDE landmine** — anchor on
      `backend/CLAUDE.md`'s Temporal section, `workflow.patched()` use in
      this repo, and `tests_v2/unit/temporal/test_replay_pre_semaphore_refactor_histories.py`.
      Concept: why workflow code is special, what the SDK sandbox enforces,
      how to evolve a workflow without breaking running history.
- [ ] 4. **Retries, timeouts, heartbeats, and the rate-limiter loop** —
      anchor on `llamaparseWorkflow.ts`'s rate-limit retry,
      `proxyActivities` options, and the multi-activity workflow's per-stage
      retry. Concept: which timeouts measure what, when to use heartbeats,
      why activities retry and workflows mostly don't.
- [ ] 5. **Queues, workers, and the team's topology** —
      `backend/src/temporal/registry/topology_registrations.py`,
      `backend/src/temporal/worker/dynamic_worker.py`,
      `infra/kubernetes/k8sctl/components/temporal_parse/`. Concept: task
      queues as routing, worker pools, KEDA scaling. Comparison: vs. raw
      RabbitMQ, Step Functions, Celery.

## Notes from sessions

### Lesson 1 (2026-05-18)

- Goal: be able to *name every Temporal primitive in the path of a single
  parse job* — workflow, activity, task queue, worker — and point at the
  concrete file or symbol where each one is defined in this repo.
- Anchors used:
  - `backend/src/parse/temporal/llamaparse/flows/settings.py` —
    `LlamaParseWorkflowInput / Output`,
    `WORKFLOW_NAME = "llamaparseWorkflow"`.
  - `backend/src/parse/temporal/llamaparse/flows/multiActivitySettings.py`
    — `MULTI_ACTIVITY_WORKFLOW_NAME = "llamaparseMultiActivityWorkflow"`.
  - `backend/src/temporal/registry/topology_registrations.py` (lines
    ~167–194) — Python side registers the TS workflow as `is_external=True`.
    This is the seam where the two languages meet.
  - `llamaparse/worker/src/temporal/workflows/llamaparseWorkflow.ts` —
    `proxyActivities`, `startToCloseTimeout: '35 minutes'`,
    `heartbeatTimeout: '2 minutes'`, retry loop on rate-limit errors.
  - `llamaparse/worker/src/temporal/activities/llamaParseActivity.ts` — the
    single big activity invoked by the legacy workflow.
  - Queue names from `backend/src/temporal/RUNBOOK.md`: `parse`,
    `parse-activity-queue`, `LLAMAPARSE_WORKFLOW` for the multi-activity
    variant.
- Mental model after lesson 1: **the Python "parse" worker hosts the parent
  workflow that spawns the TS workflow as a child; that TS workflow runs on
  a separate TS worker on a separate queue; the activity it calls is the
  only thing that actually touches PDFs.** Workflow code is the
  orchestrator, activity code does the I/O.
- Things to revisit: the user's intuition that "workflows = orchestrator,
  activities = side effects" is the right one — comes back in lesson 3
  (determinism) and lesson 4 (retries).
- The user wanted clarification on the difference between the *legacy*
  `llamaparseWorkflow` and the *multi-activity* variant. Captured: same
  input type, same output type, but the multi-activity one explodes the
  single big activity into `extract → agent → output` so each stage retries
  independently and intermediate state lives in S3 instead of in-memory.
- Comprehension exercise the user worked on: predict what happens if the
  Python parse worker is healthy but the TS worker is down. Answer arrived
  at: the parent workflow's child-workflow start hits Temporal's server
  fine (server just records "this child workflow was scheduled"), but no TS
  worker is polling `parse-activity-queue` so the workflow stays queued
  until either a TS worker comes back or a workflow execution timeout
  fires. Right intuition.
