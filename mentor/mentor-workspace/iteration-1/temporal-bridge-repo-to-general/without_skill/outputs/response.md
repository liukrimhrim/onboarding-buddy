Great topic. Before I write anything I spent a few minutes looking at how this repo actually uses Temporal so the plan is grounded in real code, not a generic tutorial. Quick findings:

- The core Temporal scaffolding lives under `backend/src/temporal/` — client, worker, registry/topology, decorators, semaphore, rate_limiter, purge, interceptors, observability. There's a `RUNBOOK.md` here that already documents every env var, which is a great anchor.
- Each product domain has its own `temporal/` subdir with workflows + activities: `backend/src/parse/temporal/`, `backend/src/extract/temporal/`, `backend/src/classify/temporal/`, `backend/src/batch/temporal/`, `backend/src/split/temporal/`, `backend/src/spreadsheet/temporal/`, `backend/src/jobs_temporal/temporal/`.
- The TypeScript worker side (parse activities) is in `llamaparse/worker/src/temporal/` — so we have a real two-language worker setup talking to one Temporal cluster.
- Infra: `infra/kubernetes/k8sctl/components/temporal_server/`, `temporal_parse/`, `temporal_jobs_service/` — the server is self-hosted in EKS via Helm, with separate worker deployments per task queue.
- Operational tooling: `backend/scripts/temporal_dashboard/`, `backend/scripts/temporal_workflow_report.py`, `backend/load/batch/parse/temporal_operations.py`.
- The project CLAUDE.md has a whole section on **workflow determinism** and `workflow.patched()` — that's a real footgun we've hit, worth a dedicated lesson.

Given that, here's the plan.

---

## Curriculum: Temporal — from this repo outward

**Goal:** by the end you can (a) read any workflow/activity in this repo and predict how it will behave under failure/replay, (b) explain to someone else what Temporal is solving and why it's built the way it is, and (c) make safe changes to our workflows without causing non-determinism errors in production.

Each lesson follows the same shape: **start in our repo → zoom out to the general concept → end with a small exercise so you can prove to yourself you got it.**

### Lesson 1 — What Temporal is, why we picked it, and the mental model
- Anchor file: `backend/src/parse/temporal/parse_workflow.py` + `backend/src/temporal/RUNBOOK.md`.
- Repo lens: one concrete parse job, end-to-end. Client → workflow → activities → worker → history.
- General lens: durable execution, event sourcing, replay, the "function that survives a process crash" framing. Contrast with RabbitMQ (which we also use, for different reasons).
- Exercise: trace one workflow_id through the codebase from API entry to activity completion.

### Lesson 2 — Workflows vs activities, and the determinism contract
- Anchor files: `backend/src/temporal/workflow/`, `backend/src/temporal/decorators/workflow.py` and `activity.py`, plus the "Temporal Workflow Determinism" section in the project CLAUDE.md.
- Repo lens: why we forbid `datetime.now()` / `uuid.uuid4()` / network I/O inside workflow code, what `workflow.patched()` actually does, what an NDE looks like in our logs.
- General lens: the event-sourcing model, how replay works, why "workflow code is a pure function over history," and the universal rule "side effects belong in activities."
- Exercise: read a recent workflow PR diff and decide whether it needs a patch.

### Lesson 3 — Workers, task queues, and topology
- Anchor files: `backend/src/temporal/worker/dynamic_worker.py`, `backend/src/temporal/registry/topology_registry.py`, `infra/kubernetes/k8sctl/components/temporal_parse/` and `temporal_jobs_service/`, the `_QUEUE_*` env vars in RUNBOOK.md.
- Repo lens: why parse, extract, spreadsheet, semaphore each get their own queue; why spreadsheet's concurrency is 1/2; how KEDA scales workers per queue.
- General lens: task queues as the unit of routing and capacity isolation, sticky execution, worker versioning, why polling beats pushing.
- Exercise: given a new CPU-bound workload, decide whether it gets its own queue or joins an existing one — and defend the answer.

### Lesson 4 — Failure, retries, timeouts, and our safety rails
- Anchor files: `backend/src/temporal/timeout_interceptor.py`, `child_timeout_interceptor.py`, `non_retryable.py`, `backend/src/temporal/semaphore/`, `backend/src/temporal/rate_limiter/`, `backend/src/temporal/purge/`.
- Repo lens: the four timeout types we set, how the semaphore workflow gives us a global concurrency limiter, the rate-limiter workflow, and the "purge config" emergency kill switch.
- General lens: at-least-once vs exactly-once semantics, idempotency at the activity boundary, heartbeats, why "retry forever" is sometimes the right answer in a workflow engine but never in a request handler.
- Exercise: pick one activity and identify every way it can fail, then check whether our retry policy + idempotency story actually handles each one.

### Lesson 5 — Operating Temporal in production
- Anchor files: `backend/scripts/temporal_dashboard/`, `backend/scripts/temporal_workflow_report.py`, `infra/kubernetes/k8sctl/components/temporal_server/`, the observability bits under `backend/src/temporal/observability/`, plus the `investigate-temporal` and `triage-parse-workflow-failures` skills.
- Repo lens: how we self-host the server, what metrics we emit, how on-call actually investigates a failing workflow today.
- General lens: history size limits, continue-as-new, archival, schedules vs cron, Temporal Cloud vs self-host trade-offs, what to monitor.
- Exercise: walk through a real failed-workflow triage end-to-end (pick one from the last week) using only Temporal UI + Loki.

That's five sessions, roughly 45–75 min each depending on how deep you want to go on the exercises.

**Reply "go" or "approve" and I'll start lesson 1.** If you want to reorder, swap topics, or stretch this to 6–7 sessions (e.g. split lesson 4 into "retries" and "concurrency control"), say so now.

---

## Lesson 1 — What Temporal is, why we picked it, and the mental model

(Starting this now since you asked me to kick off lesson 1 after the plan — feel free to pause and push back on the plan above, we can always re-scope.)

### 1.1 The five-second pitch

Temporal is a **durable execution engine**. You write what looks like a normal async Python function — it can call other functions, sleep, retry, branch — and Temporal guarantees that function runs to completion even if the process crashes, the machine dies, the deploy rolls, or the activity it called timed out three hours into a four-hour job. When the process comes back, the function picks up exactly where it left off, with all its local variables intact, as if nothing happened.

That's the magic claim. The rest of this lesson is about how it pulls that off and why we believed the claim enough to bet a lot of LlamaCloud on it.

### 1.2 Why we have it (the LlamaCloud-specific motivation)

Open `backend/src/parse/temporal/parse_workflow.py` and `backend/src/parse/temporal/llamaparse/`. A parse job in our system isn't one operation — it's a sequence:

1. Validate the file and write a row in Postgres.
2. Upload to S3 (or read it back).
3. Call the TypeScript llamaparse worker, which itself does layout extraction, OCR, vision-LLM calls, page-by-page processing.
4. Optionally run screenshot generation, classification, extraction, splitting.
5. Stream usage events to the usage service.
6. Update the job row, fire a webhook, possibly trigger downstream extract.

Any one of those steps can take seconds or hours. Any one can fail transiently (S3 503, model rate limit, OCR pod OOM). Any one can require a retry policy with a different shape — OCR retries differ from a Postgres write retry. And the whole thing has to survive a worker pod restart at any moment because we're on Kubernetes with HPA + KEDA scaling pods up and down constantly.

Before Temporal, the analogous flow lived in RabbitMQ-driven `jobs/defs/` consumers — each step a separate message, with state smeared across Postgres rows and DLQs. You can build that, and we did, but every "what's the status of job X?" required reading three tables and reconstructing a state machine in your head. Adding a step meant adding a queue, a consumer, a status enum, a retry policy, and a way for downstream consumers to know the upstream step finished.

Temporal compresses all of that into one piece of Python code where the state machine is just... the control flow of the function. The workflow *is* the state machine. That's the trade we made.

We still use RabbitMQ — see the project CLAUDE.md and `jobs/defs/`. The rule of thumb is: short-lived, fire-and-forget, single-step → RabbitMQ. Multi-step, long-running, must-survive-crashes, needs-observable-state → Temporal.

### 1.3 The mental model: workflow code is a pure function over history

Here's the part that took me embarrassingly long to internalize, and it's what every other Temporal concept hangs off:

> **The workflow code does not run forward. It runs forward, then it dies, then later it is replayed from the beginning against a recorded log of what happened the first time, and it continues from wherever the log runs out.**

Read that twice. Then look at our determinism rules in the project CLAUDE.md — "no `datetime.now()`, no `uuid.uuid4()`, no env var reads inside workflows." Every single one of those rules is a direct consequence of the sentence above. If your workflow calls `datetime.now()`, then on replay it will get a *different* timestamp than it got the first time, and the entire premise — "this is the same execution, just resumed" — falls apart.

Concretely: when a workflow runs, every "interesting" thing it does — calling an activity, starting a timer, getting cancelled, receiving a signal — gets recorded as an **event** in a persistent **event history** in the Temporal server (which is itself backed by a database; we use the bundled Postgres setup, see `infra/kubernetes/k8sctl/components/temporal_server/`). The workflow function itself runs in a **worker** process — that's what `backend/src/temporal/worker/dynamic_worker.py` is. The worker pulls work from a **task queue**, executes a chunk of workflow code until it hits the next "interesting" thing (e.g. `await execute_activity(...)`), records the result, and effectively suspends.

When the worker pod gets killed mid-workflow, no problem. Another worker picks up the workflow, replays the function from line 1, but instead of *actually* calling the activities again it reads their recorded results from history. The function flies through the recorded portion in microseconds, reaches the point where history ends, and from there runs forward for real again.

This is the same trick event-sourcing systems have used for decades, applied to control flow instead of to data. Once you see it, every Temporal API makes sense, and every footgun is obvious in retrospect.

### 1.4 The cast of characters

When you read our code you'll see roughly six concepts. Memorize these now:

- **Workflow.** A Python function decorated with `@workflow.defn` (see `backend/src/temporal/decorators/workflow.py` and `wrappers.py`). The orchestrator. Deterministic. Cannot do I/O.
- **Activity.** A Python function decorated with `@activity.defn`. Where all the dangerous stuff lives — HTTP calls, DB writes, S3, LLM invocations. Can be retried independently. Must be idempotent if at all possible.
- **Worker.** A process that polls a task queue for workflow tasks and activity tasks and executes them. We run many of these as Kubernetes deployments per product domain.
- **Task queue.** A named lane that workers poll. We have separate ones for parse, extract, spreadsheet, semaphore, etc. — see the `_QUEUE_*` table in `backend/src/temporal/RUNBOOK.md`.
- **Temporal server.** The cluster that stores event histories and dispatches tasks. We self-host it in EKS.
- **Client.** What your FastAPI handler uses to start a workflow. See `backend/src/temporal/client.py`.

The hand-wave-y end-to-end: an API request creates a client, calls `start_workflow`, the server persists a "WorkflowExecutionStarted" event, a worker poll picks it up, runs the workflow function until the first `await execute_activity(...)`, the server persists "ActivityTaskScheduled," an activity worker picks it up, runs the activity, returns the result, server persists "ActivityTaskCompleted," the workflow worker resumes from where it suspended, etc. The API handler can either `await` the result or fire-and-forget — your call.

### 1.5 Why we picked Temporal specifically

There are other options in this space — AWS Step Functions, Cadence (Temporal's predecessor at Uber), Airflow, Prefect, Dagster, plain old saga libraries, hand-rolled state machines in Postgres. Roughly, why Temporal:

- **Code, not YAML.** Step Functions and Airflow want you to declare the DAG outside the code. For workflows with conditional branches, dynamic fan-out, and "depends on the LLM output" routing — which describes basically everything we do — that's painful.
- **Polyglot workers on the same workflow.** Our parse workflow has a Python orchestrator but the actual parse activities are TypeScript (`llamaparse/worker/src/temporal/`). Temporal handles that natively.
- **Self-hostable, with a hosted option as escape hatch.** We run our own cluster; we could move to Temporal Cloud without rewriting workflows.
- **Mature primitives for the hard cases.** Signals, queries, child workflows, continue-as-new, schedules, search attributes — we use all of these. Building any one of them on top of RabbitMQ would be a quarter of work.

The cost: workflow determinism is a real constraint, the operational surface is non-trivial (you'll see in lesson 5), and the abstraction leaks in specific places (e.g. the sandbox restrictions on imports inside workflow files).

### 1.6 Exercise

Pick one parse job from staging in the last week. Then:

1. Find the workflow_id in our logs (Loki, label `app=temporal-parse-worker`).
2. Open it in the Temporal UI (`*-temporal-web` in the cluster). Look at the **History** tab.
3. Count: how many `ActivityTaskScheduled` events? How many `WorkflowTaskCompleted` events? What's the ratio?
4. Map at least three of those activity events back to a function in `backend/src/parse/temporal/`.
5. Find a `WorkflowTaskFailed` event somewhere in your sample (look at a *failed* job if your happy path has none). Read the failure reason. Was it a code error, a determinism error, or an activity error bubbling up?

When you've done that, ping me with what you found and any "wait, why?" questions, and we'll move into lesson 2 — where the determinism contract gets a lot more concrete and we look at how `workflow.patched()` actually works in our codebase.

---

A couple of meta notes:

- I'm deliberately writing these to be *readable straight through* rather than as a code-along. We'll do code-along bits in lessons 2–4 where the syntax matters.
- If a section was too basic or too dense, tell me and I'll recalibrate for lesson 2. Better to over-correct early.
- If you want me to save progress between sessions, I can drop notes into the repo or a scratch file — your preference.

Ready when you are.
