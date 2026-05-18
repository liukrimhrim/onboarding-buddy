# Lesson 1 transcript — The pipeline as a system

> Curriculum: `parse-pipeline`
> Lesson: 1 of 6

---

## Intake (recap)

**Goal sharpness.** "Both — triage first, then enough to patch. I don't want to be the person who can only say 'looks like Temporal is sad.'"

**Starting point + jargon tolerance.** Comfortable with Python/async/Postgres. Casual Temporal user — has used signals/queries but never designed a workflow. Wants terms used directly with brief inline definitions the first time something obscure shows up.

**Scope.** ~5–6 lessons, one per week.

## Curriculum agreed

1. The pipeline as a system — mental model + triage decision tree.
2. Ingress — `POST /parsing/upload` → `pjb-…` → started workflow; idempotency & DB state.
3. The TS workflow — `llamaparseMultiActivityWorkflow` line-by-line; queues, timeouts, heartbeats, rate-limit backoff, `patched()`.
4. Inside the activities — extract → agent → output, S3 hand-off, cache hits, chunked fan-out.
5. The infra layer (light) — KEDA scalers per queue, role-split deployments, OCR/layout sidecars, cross-stage backpressure.
6. Triage playbook — walk a `pjb-…` end-to-end on 2 synthetic cases (one app-layer, one queue-saturation).

User pushback: lesson 5 felt orphaned. Resolution: marked as the lightest, and lesson 6's second synthetic case exercises the KEDA/queue material.

---

## Lesson 1

### Goal

By the end of this lesson, when someone says "parse is broken," you can draw the box-and-arrow diagram from memory, name the *five* places a job can wedge, and explain *why* the team split the work this way (not just *how*).

### Concept map

A parse job is a small distributed system with **three logical actors** that pass work through **two reliability layers**.

The three actors: **the API** (Python/FastAPI, decides whether to accept the job and records the intent), **the workflow orchestrator** (Temporal, written in TypeScript, decides *what* should happen and in what order, but does no real work itself), and **the activity workers** (also TypeScript, the things that actually read PDFs, call OCR/LLMs, write S3). The two reliability layers: **Postgres** (the durable source of truth for "does this job exist and what did the user ask for") and **Temporal history** (the durable source of truth for "what has the workflow done so far"). One-line summary: *the API owns intent, Temporal owns progress, activities own work, S3 is the conveyor belt between activities.*

### Diagram

```
   client
     │  POST /api/v1/parsing/upload   (multipart, options)
     ▼
┌───────────────────────────────────────────────────────────────────┐
│  Python API  (FastAPI, port 8000)                                 │
│  endpoints/parsing_v2.py  →  services_v2/parse/v2/service.py      │
│   • validate file + tier/version                                  │
│   • idempotency check                                             │
│   • create ParseJobRecord row in Postgres   (pjb-…)               │
│   • start Temporal workflow on task queue "parse-workflow-queue"  │
└───────────────────────────────────────────────────────────────────┘
                            │ start_workflow(...)
                            ▼
┌───────────────────────────────────────────────────────────────────┐
│  Temporal server   (the brain — orchestrates, does no PDF work)   │
│   • durable event history per workflow                            │
│   • routes activity tasks to the right task queue                 │
└───────────────────────────────────────────────────────────────────┘
            │                  │                  │
   parse-extract-queue   parse-agent-queue   parse-output-queue
            │                  │                  │
            ▼                  ▼                  ▼
┌──────────────────┐  ┌────────────────────┐  ┌────────────────────┐
│ EXTRACT pods     │  │ AGENT pods         │  │ OUTPUT pods        │
│ extractDocument  │  │ agentProcessing /  │  │ outputHandling /   │
│ Activity         │  │ agentChunkProc.    │  │ chunkedOutput      │
│ • cache check    │  │ • LLM enrichment   │  │ • V1 markdown      │
│ • pdfium parse   │  │ • forks child proc │  │ • V2 JSON          │
│ • screenshots    │  │                    │  │                    │
└────────┬─────────┘  └────────┬───────────┘  └────────┬───────────┘
         │ writes              │ reads/writes          │ reads
         ▼                     ▼                       ▼
       ┌─────────────────── S3 (job-scoped prefix) ──────────────────┐
       │  extractionDataS3Key  →  agentOutputS3Key  →  final outputs │
       └─────────────────────────────────────────────────────────────┘

   side services called by activities:
     llamaparse-ocr        (OCR) — separate deployment, HPA/KEDA scaled
     llamaparse-layout-detection-api  (layout v3) — separate deployment
     LLM providers (Anthropic / OpenAI / Gemini / Bifrost gateway)
```

### Five wedge-points

1. **API layer** — never created the `ParseJobRecord` row, never called `start_workflow`. Client got a 5xx; no `pjb-…` exists in Postgres.
2. **Temporal scheduling** — workflow started but its activities can't get scheduled (no live worker on the target task queue: deployment crashlooping, KEDA scaled to zero, queue name typo after a rename).
3. **An activity** — picked up but failing or stuck (extract times out on a giant PDF, agent keeps hitting LLM rate limits, output OOMs serializing pages).
4. **A downstream service** — OCR unhealthy, layout endpoint 5xx-ing, LLM provider throttling. Surfaces as a stuck/retrying activity.
5. **S3 hand-off** — extract wrote pages, agent can't read them (cross-region issue, lifecycle deletion, presigned URL expiry on long backoff).

### Grounding in the repo

- **API entry.** `backend/src/app/api/endpoints/parsing_v2.py` (751 lines) — FastAPI router for `/upload`; delegates to the service.
- **Service.** `backend/src/app/services_v2/parse/v2/service.py` (1,559 lines) — converts user options into `ParseJobRecordCreate`, runs idempotency, starts the workflow.
- **Workflow.** `llamaparse/worker/src/temporal/workflows/llamaparseMultiActivityWorkflow.ts` (467 lines). Lines 46–110: five `proxyActivities` declarations, each pinned to a different task queue with its own timeout and retry policy. Module-top placement is required: workflow code must be deterministic on replay.
- **Legacy workflow.** `llamaparse/worker/src/temporal/workflows/llamaparseWorkflow.ts` (67 lines) — the one-activity version still used for non-v2 jobs.

Inline definitions used: *task queue* (a named lane Temporal uses to route activity tasks to workers that subscribe to it), *non-determinism error / NDE* (workflow crash when replayed code produces a different command sequence than recorded history), *proxyActivities* (Temporal SDK helper that turns activity references into callable stubs with per-call timeout/retry config).

### Concept

The split is an instance of **stage-and-queue pipelining** — separate the orchestrator from the executor, and separate executors along the axis of what resource they bottleneck on:

- `extractDocumentActivity` — CPU-bound (pdfium, screenshots).
- `agentProcessingActivity` — wait-bound on LLM (high concurrency per pod is fine).
- `outputHandlingActivity` — bursty I/O + short CPU.

One queue for all three means one CPU-heavy job starves LLM-wait jobs that could have run. Three queues means each scales independently. Older literature calls the pattern SEDA (Staged Event-Driven Architecture, Welsh 2001); workflow engines (Temporal, Step Functions, Cadence, Argo) are the orchestrator side of the same idea, with *durable execution* — replay against recorded history rather than retry-from-scratch — as the key value over plain queues.

### Comparison

- **Vs. plain RabbitMQ queues:** cross-stage dependencies become hand-rolled state in Postgres; Temporal makes the workflow code itself the state.
- **Vs. one giant function:** no partial-progress checkpointing; every failure restarts the whole thing.
- **Vs. Step Functions / Argo:** Temporal lets workflows be ordinary code, at the cost of having to respect determinism — covered in lesson 3.

### Comprehension check (sent to user)

1. Workflow open, last event `ActivityTaskScheduled` for `agentProcessingActivity`, no `ActivityTaskStarted` for 10 minutes. Which wedge-point, which queue do you check first?
2. Same workflow, last event `ActivityTaskStarted` 10 minutes ago, activity still heartbeating. Different wedge-point — which, what do you check next?
3. From the resource-axis framing, *why* is `extractDocumentActivity` 15-min timeout vs `agentProcessingActivity` 30-min? Predict the symptom if they were swapped.

---

## Bookkeeping

- Advance current-lesson pointer to 2 after the user sends comprehension-check answers (do not auto-advance).
- Persistence note: writes to canonical `~/.claude/mentor-curricula/parse-pipeline.md` were denied by the sandbox in this session. Workspace copy at `iteration-2/parse-pipeline-curriculum/with_skill/outputs/curriculum.md` is the operative artifact; user should copy it into `~/.claude/mentor-curricula/` for resume to work.
