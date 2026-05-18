# Lesson 1: The 30,000-ft path — request, row, workflow, worker, result

Part of the **parse-pipeline** curriculum
(see `outputs/curriculum.md` / `~/.claude/mentor-curricula/parse-pipeline.md`).
Mirror of what the mentor showed the user in the live session.

---

## (a) Goal of this lesson

By the end of this lesson, you can draw the lifecycle of a parse job on a
whiteboard and name, for each stage, the process that owns it and the artifact
that proves it ran. This is the scaffolding all subsequent lessons hang on.
We're not going deep — we're making sure the mental map has the right number
of rooms before we start renovating individual ones.

---

## (b) Ground in this repo

The parse pipeline has **five stages**, each in a different file (and
sometimes a different language). Each anchor below is a verified path in
this worktree.

### Stage 1 — The HTTP request enters

The user POSTs a file (or URL) to the upload endpoint.

- [backend/src/app/api/endpoints/parsing.py:458](backend/src/app/api/endpoints/parsing.py:458)
  — `@router.post("/upload")` decorating `upload_file`.

This is the only stage that runs synchronously inside the user's HTTP
request. It validates auth, resolves the parse configuration / preset,
stages the file into S3, creates a `pjb-...` row in Postgres, and *kicks
off* a Temporal workflow. It does **not** wait for parsing. The HTTP
response is `{job_id: "pjb-...", status: "pending"}` and the user is
expected to poll.

### Stage 2 — The orchestrating workflow starts

Temporal picks up the workflow you just started. This is the *outer*
workflow.

- [backend/src/jobs_temporal/temporal/flows/parse/workflow.py:152](backend/src/jobs_temporal/temporal/flows/parse/workflow.py:152)
  — `@workflow_decorator(name=WORKFLOW_NAME, ...)` on `class ParseJobWorkflow`.
- The `@workflow.run` entry point lives at
  [workflow.py:510](backend/src/jobs_temporal/temporal/flows/parse/workflow.py:510).

This runs in the Python backend's job-service Temporal worker.
**Critically: it does no parsing itself.** It owns the job's lifecycle:
acquire a concurrency slot, write status transitions to Postgres,
dispatch the actual parse work as a child workflow, finalize the row when
results come back. Think of it as the project manager who never touches
the wrench.

### Stage 3 — The inner workflow does the parsing

The outer workflow launches a *child workflow* on a **different task
queue** that's serviced by a **different process in a different language**
(TypeScript / Node).

- [llamaparse/worker/src/temporal/workflows/llamaparseWorkflow.ts](llamaparse/worker/src/temporal/workflows/llamaparseWorkflow.ts)
  — the original monolithic worker workflow.
- [llamaparse/worker/src/temporal/workflows/llamaparseMultiActivityWorkflow.ts](llamaparse/worker/src/temporal/workflows/llamaparseMultiActivityWorkflow.ts)
  — the newer multi-activity variant (split into more, smaller activities
  so Temporal can retry granularly).

This is where pages get rendered, layout is detected, OCR runs, and LLMs
produce the markdown / JSON output. The Node side reads the input file
from S3 (path passed in the workflow input) and writes outputs back to S3.

### Stage 4 — Results flow back to Postgres

Once the child workflow returns, the outer Python workflow's
`_save_parse_results` and finalize-status activities run.

- [backend/src/jobs_temporal/temporal/activities/parse/save_job_results.py](backend/src/jobs_temporal/temporal/activities/parse/save_job_results.py)
- [backend/src/jobs_temporal/temporal/activities/parse/finalize_job_status.py](backend/src/jobs_temporal/temporal/activities/parse/finalize_job_status.py)

These write the S3 result keys into the `parse_job_result` table and flip
the job row to `completed` or `failed`.

### Stage 5 — The user polls for results

Separate HTTP endpoints serve job status and the result artifacts. The
result blobs themselves live in S3; the DB just stores keys.

- [backend/src/app/api/endpoints/parsing.py:1173](backend/src/app/api/endpoints/parsing.py:1173)
  — `GET /job/{job_id}`
- [backend/src/app/api/endpoints/parsing.py:1443](backend/src/app/api/endpoints/parsing.py:1443)
  — `GET /job/{job_id}/result/markdown` (one of several result formats).

---

## (c) Generalize — the underlying concept

What you just walked through is a **classic asynchronous job pattern**
with one important wrinkle: it uses a **workflow engine** (Temporal)
instead of a plain job queue (Celery, Sidekiq, RabbitMQ + worker).

The asynchronous job pattern in general:

1. **Sync request, async work.** The HTTP layer enqueues a unit of work
   and returns an ID. Long work never blocks an HTTP worker.
2. **The job ID is the contract.** Everything else — status polling,
   result fetching, cancellation — happens against that ID.
3. **State lives in two places.** A small *control record* in the primary
   DB (status, timestamps, ownership). Large *artifacts* in blob storage
   (S3 here). The DB stores keys, not blobs. This is what lets the
   parsing process and the API process scale independently.

The wrinkle — **why a workflow engine and not just a queue**:

A queue gives you "run this function once, retry it if it fails." That's
fine for a job that's one function call. A parse job isn't one function
call — it's *create row -> throttle -> run worker -> save result ->
finalize status -> release slot*, with cleanup logic that has to run on
cancel and on partial failure. With a plain queue you'd build that
orchestration by hand, scattered across multiple "next-step" messages,
and you'd reinvent retries-with-state, timeouts, and "did this side
effect already happen on a previous attempt?" each time.

A workflow engine lets you write that orchestration as one straight-line
async function that *appears* to take an hour to run but is actually
replayed from durable event history every time the worker process dies.
The price is determinism rules — which is exactly what lesson 2 is about.

**Mental anchor:** the outer Python workflow is the orchestration. The
inner Node workflow is the work. Two processes, two task queues, one
logical job. When you debug a stuck job, the first split you make is
"is it stuck in the orchestrator, or stuck in the worker?" — because the
diagnostic tools are different.

---

## (d) Compare (optional) — why Temporal, not Celery / Step Functions / Cadence?

Brief, since lesson 4 covers concurrency choices in more depth.

- **Celery / RQ / Sidekiq / direct RabbitMQ consumers:** Great for
  one-shot tasks. Painful for multi-step workflows with cleanup. You end
  up writing a state machine on top of the queue, in your own code, and
  getting partial failures wrong.
- **AWS Step Functions:** Same workflow-engine niche as Temporal, but
  state machine defined in JSON/YAML and runs in AWS. Cheap to set up,
  terrible to debug a custom retry policy in, and you can't run it
  locally next to the rest of your services.
- **Cadence:** Temporal's predecessor — Temporal is a fork. Same model.
- **Temporal:** Workflow as code (Python / TS / Go), runs anywhere,
  durable history, great UI for debugging running workflows. Costs more
  operational overhead (you run your own server) and forces you to learn
  determinism rules. The team here chose it because parse jobs *are*
  multi-step orchestrations with non-trivial cleanup, and being able to
  write them as straight-line async code is worth the determinism tax.

You'll see why the determinism tax matters in lesson 2 when we look at
`workflow.patched(_PARALLELIZATION_PATCH)` in
[workflow.py:81](backend/src/jobs_temporal/temporal/flows/parse/workflow.py:81).
That single string is patching a change that, in any other system, would
be a deploy outage.

---

## (e) Comprehension check

Two parts. Don't read past the divider until you've done part one.

### Part 1 — Predict before you read

Open
[backend/src/jobs_temporal/temporal/flows/parse/workflow.py:446](backend/src/jobs_temporal/temporal/flows/parse/workflow.py:446)
and look at the *signature* of `_acquire_and_setup`. Without reading the
body, predict:

1. What two things does it do, given the name and what we covered above?
2. What does the return type `_SetupResult` need to contain to support
   the rest of the workflow?
3. Why might these two things be done concurrently rather than serially?

Write down your guesses, *then* read the body (lines 446–476). Tell me
where you were right and where you were surprised. The surprises are
where lesson 2 will start.

---

### Part 2 — A live debug scenario

A teammate pings you in Slack: "`pjb-abc123` has been sitting at status
`pending` for 20 minutes. Is it stuck?"

Based only on what we covered in this lesson, what are the *two distinct
possibilities* of where it could be stuck, and what's the *first* file or
signal you'd check for each? (Don't try to give a full triage plan — we
do that in lesson 5. I just want to see whether the outer-vs-inner split
has landed.)

---

## Mentor notes (post-session)

- All file anchors verified against the repo at HEAD before being cited:
  `parsing.py` line numbers from `grep -n '@router.'`, workflow
  decorator confirmed at `workflow.py:152`, `@workflow.run` at line 510,
  `_acquire_and_setup` at line 446, `_PARALLELIZATION_PATCH` at line 81.
- The two-process split (Python orchestrator + Node worker) was the
  user's stated weakest spot during intake — surfaced it explicitly here
  as the load-bearing "mental anchor" so it has somewhere to sit while
  lesson 2 dives into the orchestrator and lesson 3 into the worker.
- Determinism / `workflow.patched` is deliberately *foreshadowed* here,
  not taught. The user said the rules feel cargo-cult; landing them in
  lesson 2 against an actual patch ID in this workflow is the plan.
- Comprehension check Part 1 is a read-and-verify prediction (the skill
  prefers active checks over recall). Part 2 is a mini-debug scenario
  that *only* tests the outer-vs-inner split — the smallest unit of
  understanding this lesson is meant to produce.
- Curriculum file path: this environment's sandbox blocks writes under
  `~/.claude/mentor-curricula/`. The canonical-path copy is preserved at
  `outputs/curriculum.md`; in a normal session the same content would
  live at `~/.claude/mentor-curricula/parse-pipeline.md`.
</content>
</invoke>