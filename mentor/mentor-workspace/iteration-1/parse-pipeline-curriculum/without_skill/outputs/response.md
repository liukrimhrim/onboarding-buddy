# Parse Pipeline Tutoring — Plan + Lesson 1

Before drafting the plan, two short intake questions (answer if either guess is wrong; otherwise I'll proceed):

**Q1 — Goal shape.** "Debug a stuck job in prod" can mean a few different things. Which is closest?
- (a) A specific job ID is stuck and I want to know *where* to look (Temporal UI vs. Loki vs. S3 vs. Postgres vs. RabbitMQ).
- (b) I want to understand control flow well enough to form *hypotheses* about *why* jobs stall (retry storms, activity deadlock, worker starvation, KEDA scaling lag, etc.).
- (c) Both — control flow first, ending in a triage playbook.

**Q2 — Starting point.** Have you worked on llamaparse / the parse Temporal workflows? Specifically: do you already know the Temporal *workflow vs activity* distinction, and have you read `backend/src/parse/temporal/llamaparse/flows/` or `llamaparse/worker/`?

**My default while you answer:** Q1 = (c), Q2 = mostly unfamiliar with the Temporal layer. Push back and I'll re-pace.

---

## Curriculum: Parse Pipeline (end-to-end)

I'd normally save this to `~/.claude/mentor-curricula/parse-pipeline.md` so we can resume across sessions. Writing there is currently blocked by sandbox permissions in this session — see note at the very bottom. The plan itself is below; treat it as a working document.

**Goal.** Build enough mental model of the LlamaCloud parse pipeline that, given a `pjb-…` job ID and a symptom like "stuck in RUNNING for 30min, no progress," you can list 4–6 ranked hypotheses and name the exact UI / log query / DB query that confirms each. Not just "I'd look in Temporal."

**Prerequisites.** Python async, FastAPI, Postgres, Docker (assumed). Light familiarity with job-queue patterns; we'll cover Temporal-specific concepts (workflow vs activity, determinism, task queues, heartbeats) as we go. Reading-level TypeScript is enough — you don't need to write TS, just read the worker.

**Lessons:**

1. **The shape of a parse job.** What's a `ParseJob` as a data record? Trace one API request, see the row that gets written, see what fields drive everything downstream. Anchor: `services_v2/parse/`, `managed_service.py`.
2. **Submission to Temporal: the handoff.** How `start_workflow` works, what task queues are, why `workflow_id == parse_job.id`, what happens if Temporal is down at submission time. Anchor: `managed_service.py:387`, `src/temporal/client.py`, the topology registry.
3. **The Python workflow side: `llamaparseWorkflow` vs `llamaparseMultiActivityWorkflow`.** The workflow-vs-activity distinction, why workflow code must be deterministic, why there are two flavors, when each is used (and why some configs force single-activity). Anchor: `backend/src/parse/temporal/llamaparse/flows/` + the two TS workflows under `llamaparse/worker/src/temporal/workflows/`.
4. **Inside the worker: activities, rate limiting, layout/OCR/LLM.** What an activity actually *does* — the long-running unit that holds a slot, talks to OCR and layout services, calls LLMs. Heartbeats, timeouts. Anchor: `llamaparse/worker/src/temporal/activities/`, `pipeline/`, the rate-limit activity.
5. **Failure modes and idempotency.** Retry policy at workflow vs activity level, what's idempotent (DB writes, S3 puts) vs not (LLM calls — they're idempotent only in effect, not in cost). S3 artifact lifecycle and the cleanup path. Anchor: `services_v2/parse/v2/cleanup/`, `idempotency.py` files.
6. **Scaling and the queue layer.** KEDA scaling, worker roles, `generated-queues.ts`, priority queues, why a job can sit `PENDING` even with idle workers. Anchor: `worker/src/temporal/worker.ts`, `workerRole.ts`, `generated-queues.ts`, `infra/` KEDA configs.
7. **Triage playbook.** Synthesize the above into a concrete decision tree for a stuck job: given symptom S, hypothesis ranking and exact verification steps. Outcome: a checklist you can paste into Slack.

Two things worth flagging before we start:
- **Lessons 3 and 4 are the meat.** If you only have time for three lessons, do 1, 3, 4 — that's where most of the actual debugging payoff lives. Tell me if you want to compress.
- **Lesson 7 ties to the existing `triaging-parse-jobs` and `investigate-temporal` skills.** We'll lean on those rather than rebuild them from scratch — the goal of L7 is *understanding* the playbook, not memorizing it.

Push back on lesson count, order, or scope before we run lesson 1.

---

## Lesson 1 — The Shape of a Parse Job

**Goal.** By the end of this lesson, you can answer: "What columns of a parse job row exist, which one tells me where it is in the pipeline, and what's the relationship between this row and the Temporal workflow that processes it?" That's the foundation everything else builds on — every later lesson references back to this row.

### (a) Ground in this repo

The parse service lives at `backend/src/app/services_v2/parse/`. Two layers matter for this lesson:

- **`v1/service.py`** — the pure CRUD-shaped service. Used by Temporal activities that need to *read* or *update* job state without re-running orchestration logic.
- **`v2/managed_service.py`** — the orchestration layer. Used by the API endpoint. It creates the row, picks a priority, picks single-vs-multi-activity, submits to Temporal.

Open `backend/src/app/services_v2/parse/v2/managed_service.py` and find `_create_job_with_workflow` (around line 288). Read it slowly. The sequence is dead simple and worth memorizing:

```
1. INSERT into parse_jobs with status = PENDING.
2. (Optionally) fire a `parse.pending` webhook.
3. Compute task_queue from the workflow name + topology registry.
4. await temporal_client.start_workflow(
       PARSE_WORKFLOW_NAME,
       DirectWorkflowInput(job_id=workflow_id, ...),
       id=workflow_id,        # CRITICAL: workflow_id == parse_job.id
       task_queue=task_queue,
       priority=Priority(priority_key=priority),
   )
5. If start_workflow raises → mark job FAILED with error_message.
```

That's the entire handoff. Everything else (parsing the PDF, OCR, LLM calls, etc.) happens *inside* Temporal, in activities running in the TS worker.

Three concrete things to internalize before we move on:

**1. The job ID *is* the workflow ID.** Look at line 353: `workflow_id = parse_job.id`. This is the most important debugging fact in the whole system. When triage tools say "look up the job in Temporal," they mean: paste the `pjb-...` ID directly into Temporal UI's workflow ID field. No translation table.

**2. The row goes in *before* the workflow is submitted.** That means there is a brief but real window where you can have a `PENDING` row in Postgres and *no* corresponding workflow in Temporal — if `start_workflow` itself fails. The code catches that and updates status to `FAILED`. But what if the *catch block* fails (e.g., DB connection drops between submit and update)? You'd get a `PENDING` row with no workflow. That's a real failure mode — note it for the triage playbook lesson.

**3. `parameters` is a JSON blob, not normalized columns.** The job's full configuration (file ID, output format, target pages, language, webhook configs, auto-mode flags, etc.) is stuffed into one JSONB column. That's why every workflow input includes a `record_create: ParseJobRecordCreate` field — the workflow needs the full blob to know what to do. If you're hunting "why did this job parse as English when it should have been French," that JSON is where the answer lives.

### (b) Generalize

What's the underlying pattern? It's a **command/state separation**.

- The Postgres row is the **state**: who owns this, what's its status, what's its result, when did it transition.
- The Temporal workflow is the **command**: the running computation that drives state transitions.

Plenty of systems use this split. Stripe's payment intents work this way: the `payment_intent` row is durable state, the actual charge attempt is an orchestrated flow that updates the row. AWS Step Functions, Cadence, Airflow — same shape.

Two properties matter:

- **The state record outlives the command.** If the worker dies mid-parse, the row is still there. When a new worker picks up the workflow, it reads the row and continues. This is why DB rows must be authoritative — the workflow can be replayed from history, but the row is the durable truth seen by the API.
- **The command must reconcile to the state.** Activities inside the workflow update the row. If they fail to, you get **drift**: workflow says completed, row says running. Drift is one of the top causes of "stuck" jobs that aren't actually stuck.

Hold onto that word — **drift**. It'll come back in lessons 5 and 7.

### (c) Compare (optional)

Why this split instead of putting state *only* in Temporal? Temporal does have its own state (workflow history, query handlers). Two reasons you keep a Postgres row alongside:

- **Querying.** "List the last 100 parse jobs for project X" is a one-liner in SQL and miserable in Temporal's visibility API (which uses search attributes — limited, indexed separately, eventually consistent). The row makes the API endpoint trivial.
- **Cross-system joins.** Billing, RBAC, webhooks — they all want to join on `parse_job_id`. Temporal isn't a database you join against.

Why not put state *only* in Postgres and use RabbitMQ to dispatch? You could — and the codebase does for some legacy jobs (`backend/jobs/defs/` and the job consumer). The reason parse moved to Temporal:

- **Durable execution.** A workflow that's mid-parse when its pod dies resumes exactly where it was, automatic retry policies, automatic timeouts. Hand-rolling that on RabbitMQ is a year of bugs.
- **Long-running activities.** Parsing a 200-page PDF with LLM calls can take many minutes. Temporal heartbeats keep the activity alive without holding a connection.

So the design heuristic is: short, fast, fire-and-forget → RabbitMQ. Long, stateful, multi-step with retries → Temporal. Parse is the latter.

### (d) Comprehension check

Don't skip this — it's where the lesson lands.

Open `backend/src/app/services_v2/parse/v2/managed_service.py` and answer these *before* reading further. I want predictions, not lookups:

1. After line 318 runs (`create_parse_job`), but before line 387 runs (`start_workflow`), the API returns to the caller. **True or false?** Why does the answer matter for a user who polls `GET /parse/{job_id}` immediately after creating one?
2. Suppose the Postgres `INSERT` on line 318 succeeds, but `start_workflow` on line 387 throws a network error and the `except` block also throws (DB down). The user polls one minute later. What status do they see, and what do they need to wait for to find out the truth?
3. The `id=workflow_id` argument on line 390 is what makes the job ID == workflow ID. Why is that valuable? Hint: think about what happens if a user accidentally retries the same `create_parse_job` request.

I'll wait for your answers, then we'll close out the lesson and either run lesson 2 or — if you find anything above too dense or too thin — adjust the pacing.

### (e) What I'd like you to do next

- Respond to the intake questions at the top (Q1, Q2), or tell me to roll with my defaults.
- Take a swing at the three comprehension questions in (d).
- Tell me if the lesson length felt right. The next lesson on the Temporal handoff is a similar size; lesson 4 (worker internals) is meaningfully bigger and I'll probably want to split it.

---

## Housekeeping note

I tried to save this curriculum to `~/.claude/mentor-curricula/parse-pipeline.md` (the canonical resume location for the mentor flow) but writing there is blocked by sandbox permissions in this session. Two options:

- Grant write access to `~/.claude/mentor-curricula/` and I'll persist it so we can resume next session by name.
- Or leave it here in the workspace output and we re-bootstrap from this file next time.

Either is fine — flag your preference.
