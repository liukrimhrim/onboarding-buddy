# Lesson 1 — The shape of a parse job in Temporal

**Curriculum:** Temporal — repo + concepts
**Date:** 2026-05-18
**Goal of this lesson (one sentence):** By the end you can name every Temporal
primitive on the path of one parse job — workflow, activity, task queue, worker
— and point at the file or symbol in this repo where each one lives.

That goal is deliberately small. The next four lessons stack on top of it.
Until "workflow vs. activity vs. task queue vs. worker" feels concrete, the
rest is hand-waving.

---

## (a) Set the scene — what we're tracing

A user uploads a PDF. Something happens. Eventually `parsed.md` and
`parsed.json` show up in S3 and the parse job in the UI flips to `completed`.

In between, Temporal is the thing that orchestrates the steps and guarantees
they finish even if a pod restarts mid-job. We're going to walk that path
once, slowly, and name each Temporal-native concept as we hit it.

There are two parse workflow variants in this repo, and you've probably seen
both names in Sentry or in the Temporal UI:

- `llamaparseWorkflow` — the legacy single-activity version.
- `llamaparseMultiActivityWorkflow` — the modern three-activity version,
  used when `api_version === "v2"` AND `ENABLE_MULTI_ACTIVITY_WORKFLOW` is on
  (see `llamaparse/CLAUDE.md`).

For this lesson we'll use the legacy one because it's simpler and shows
every primitive without distractions. Multi-activity reuses the same
primitives, just more of them.

---

## (b) Ground in the repo — read these in order

Click through these. Read them, don't just look at the names. The whole
point of grounding is that the abstraction should feel attached to code you
can find again.

### 1. The Python side declares the TS workflow

[backend/src/parse/temporal/llamaparse/flows/settings.py](backend/src/parse/temporal/llamaparse/flows/settings.py):

```python
WORKFLOW_NAME = "llamaparseWorkflow"

class LlamaParseWorkflowInput(ParseJobRecordCreate):
    job_record_id: str

class LlamaParseWorkflowOutput(BaseModel):
    output_files: OutputFiles = Field(alias="outputFiles")
    ...
```

Two things to notice:

- `WORKFLOW_NAME` is a *string*. That's how Temporal identifies a workflow
  across language runtimes. Python doesn't import the TS function — it
  refers to it by name, and the server routes by name + task queue.
- The input/output are Pydantic models. They serialize to JSON over the
  wire (note the `pydantic_data_converter` registered on the Temporal
  client in [backend/src/temporal/client.py](backend/src/temporal/client.py)).
  The TS side has a matching `LlamaparseWorkflowInput` type. The contract
  is the shared JSON shape.

### 2. The Python side tells the registry "this workflow is external"

[backend/src/temporal/registry/topology_registrations.py](backend/src/temporal/registry/topology_registrations.py) lines ~167–180:

```python
# llamaparseWorkflow - TypeScript workflow from llamaparse worker
# Marked as external so Python workers don't try to load it.
registry.register_workflow(
    "llamaparseWorkflow",
    RoutingProfile.DEFAULT,
    TaskQueueTypeValues.LLAMAPARSE_TS,
    is_external=True,
)
```

`is_external=True` is the key. It says: "this workflow exists, route work to
it, but my Python workers don't host it — somebody else's worker does."

The "somebody else" is the TS worker in `llamaparse/worker/`. Different
language, different process, different pod, same Temporal namespace.

### 3. The TS workflow

[llamaparse/worker/src/temporal/workflows/llamaparseWorkflow.ts](llamaparse/worker/src/temporal/workflows/llamaparseWorkflow.ts) (only 67 lines — read the whole thing):

```typescript
const activities = proxyActivities<{
    llamaParseActivity: (input: LlamaparseWorkflowInput) => Promise<ActivityResultData>;
}>({
    startToCloseTimeout: '35 minutes',
    heartbeatTimeout: '2 minutes',
    retry: { maximumAttempts: 2 },
});

export async function llamaparseWorkflow(input) {
    let totalBackoffMs = 0;
    while (true) {
        try {
            const result = await activities.llamaParseActivity(input);
            return { outputFiles: result.outputFiles, ... };
        } catch (err) {
            const backoffMs = extractRateLimitRetryAfterMs(err);
            if (backoffMs != null) { ... await sleep(backoffMs); continue; }
            throw err;
        }
    }
}
```

This is the whole workflow. It calls one activity, and if the activity fails
with a rate-limit error it sleeps and retries. Everything else — the actual
PDF parsing, OCR calls, S3 writes — lives in `llamaParseActivity`.

That split is not aesthetic. It's load-bearing. Workflow code has hard
constraints (we'll cover them in lesson 3); activity code has none. So
anything that talks to the outside world is pushed into an activity.

### 4. The activity

[llamaparse/worker/src/temporal/activities/llamaParseActivity.ts](llamaparse/worker/src/temporal/activities/llamaParseActivity.ts)
is much bigger and does the real work: reads the file from S3, runs the
parse pipeline, writes outputs back. We won't read it in detail today —
just register that this is where the *side effects* happen.

### 5. The workers and queues

From [backend/src/temporal/RUNBOOK.md](backend/src/temporal/RUNBOOK.md):

| Queue                  | Worker                 | Hosts                                  |
|------------------------|------------------------|----------------------------------------|
| `parse`                | Python parse worker    | Parent parse workflow                  |
| `parse-activity-queue` | TS llamaparse worker   | `llamaparseWorkflow` + its activity    |
| `parse-screenshot-pdf` | Python screenshot worker | screenshot workflow                  |
| `concurrency-limiter`  | Python semaphore worker | semaphore workflow                    |

The Python parent workflow runs on the `parse` queue. When it calls
`llamaparseWorkflow` as a child, the schedule lands on
`parse-activity-queue`, where the TS worker is polling. The TS worker picks
it up, runs the workflow function, which schedules `llamaParseActivity` on
that same queue, which the TS worker also picks up.

---

## (c) Climb to the concept — what *is* each of these things?

Now the abstractions, with each one tied back to what you just read.

### Workflow

A function that describes the orchestration — what to do, in what order,
with what retries. In Temporal, a workflow is **durable**: if the worker
process dies mid-execution, another worker picks up where it left off using
the recorded event history. We'll unpack "how" in lesson 2; for now the
property to keep in your head is "a workflow is a function whose progress
survives a worker crash."

That's why workflow code can't do arbitrary I/O. If a worker crashed mid-`requests.get(...)` and the next worker replayed the workflow, it would
re-issue the request — but the old request might have already succeeded.
Bad. So I/O goes into activities, where Temporal can track "did it
finish, did it fail, did it time out" as discrete events.

In this repo, our workflow is the 30-line `llamaparseWorkflow` function.
The Python `ParseJobWorkflow` that calls it is also a workflow — workflows
can call other workflows as "children".

### Activity

A function that does the actual work — I/O, CPU, anything. Activities can
fail and retry; Temporal tracks attempts. The workflow only sees the final
result (or final failure) of an activity, not the intermediate retries.

In this repo, `llamaParseActivity` is the activity. The retry policy on
the `proxyActivities` call (`maximumAttempts: 2`) controls how many times
Temporal will re-invoke it before giving up. That decision is *recorded
in the workflow* (`startToCloseTimeout: 35 minutes`), but the retry
*happens* on the worker side, transparently to the workflow code.

### Task queue

A named lane that workers poll. It's not a queue in the RabbitMQ sense —
it's a routing key the Temporal server uses to decide which worker to hand
work to. Multiple workers on the same queue compete; workers on different
queues are isolated.

This is how we keep "parse Python orchestrator" and "parse TS executor"
separate even though they're in the same Temporal namespace. The parent
workflow runs in Python on `parse`; the child workflow runs in TypeScript
on `parse-activity-queue`. Different pods, different scaling, different
deploys.

### Worker

A process that polls one or more task queues, runs the workflow/activity
code registered with it, and reports results back to the server. In this
repo:

- Python parse worker → [backend/src/temporal/worker/dynamic_worker.py](backend/src/temporal/worker/dynamic_worker.py),
  launched per pod with `--task-queue parse`.
- TS llamaparse worker → `llamaparse/worker/src/temporal/worker.ts`,
  launched with `pnpm start:temporal`.

A worker doesn't store state. The Temporal server is the durable thing.
Workers are stateless executors that can be killed and restarted; that's
the whole point.

### Temporal server (the missing piece)

We haven't talked about the server, but it's the brain. It stores the
event history, schedules tasks onto queues, enforces timeouts. In this
repo's infra:
[infra/kubernetes/k8sctl/components/temporal_server/](infra/kubernetes/k8sctl/components/temporal_server/).
You don't write code against it directly — you write workflows and
activities, and the SDK talks to it on your behalf.

---

## (d) Comparison — why not just RabbitMQ?

Quick version, fuller in lesson 5: this repo *also* has RabbitMQ for some
job processing (see `backend/jobs/`). The difference is, with RabbitMQ:

- The message is "do thing X." Once consumed, the queue forgets.
- If the consumer crashes mid-thing, you either lose the work or you re-do
  it from the start. State across multi-step jobs is the application's
  problem to track in Postgres.

With Temporal:

- The message is "execute this workflow function." The server records
  every step.
- If the worker crashes mid-workflow, another worker resumes from the
  exact next step. State across steps is the SDK's problem.

So Temporal is the right tool when "this is a multi-step thing where
partial progress matters." Parse is multi-step (load, preprocess, agent,
output) and partial progress matters (re-doing the agent stage is
expensive). RabbitMQ would work, but you'd write a lot more state-machine
plumbing.

---

## (e) Comprehension check — predict before you read

Two exercises. Try to answer before reading the answer below.

### Exercise 1

The Python `parse` worker is healthy. The TS `llamaparse` worker is all
dead (deploy gone wrong). A user submits a parse job. What does the
Temporal UI show 5 minutes later for that workflow?

### Exercise 2

Open the legacy `llamaparseWorkflow.ts`. It has `maximumAttempts: 2` on
the activity. The activity itself fails with a non-rate-limit error on the
first attempt, succeeds on the second. From the *workflow's* perspective,
how many times did `llamaParseActivity` "happen"? From the *event
history's* perspective, how many activity-related events do you expect to
see?

---

### Answers (read after you've taken a guess)

**Exercise 1.** The parent Python workflow starts, advances through any
preliminary activities, and reaches the `start_child_workflow("llamaparseWorkflow", …)` call. Temporal records a
`StartChildWorkflowExecutionInitiated` event and the child execution is
scheduled on `parse-activity-queue`. But nobody is polling that queue, so
the child is `Running` from the server's bookkeeping perspective but no
worker is making progress on it. In the UI you'll see the parent
"Running", the child "Running", zero activity tasks completed.

The workflow does not fail. It does not time out (immediately). It just
sits. Eventually one of two things happens: a TS worker comes back and
picks it up (and it just runs — no manual intervention needed), or the
workflow execution timeout (`TEMPORAL_WORKER_REGISTRY_DEFAULT_WORKFLOW_EXECUTION_TIMEOUT_HOURS` = 4 hours by
default) fires and the workflow fails with a timeout error.

The lesson is: **the server is durable, the workers are not. Workers can
all die and come back, and as long as one comes back before the workflow
timeout, the job completes correctly.** That's the durability property,
made concrete.

**Exercise 2.** From the workflow's perspective,
`await activities.llamaParseActivity(input)` returned once, successfully.
The workflow doesn't know about the failed first attempt. From the event
history's perspective, you'd expect something like:

- `ActivityTaskScheduled` (attempt 1)
- `ActivityTaskStarted`
- `ActivityTaskFailed`
- `ActivityTaskScheduled` (attempt 2 — Temporal handled the retry)
- `ActivityTaskStarted`
- `ActivityTaskCompleted`

Six events for one logical activity call. This is exactly what's confusing
about reading event history at first — one call in the code becomes a
small flurry of events on the timeline. We'll lean into reading those
flurries in lesson 2.

---

## (f) What you should be able to say now

- "A workflow is the orchestration function; an activity is where I/O
  happens; a task queue is the routing lane; a worker is the process that
  polls a queue and runs code."
- "In this repo, the parse path is: Python parent workflow on the `parse`
  queue → TS child workflow `llamaparseWorkflow` on `parse-activity-queue`
  → TS activity `llamaParseActivity` on the same queue. The contract
  between Python and TS is the workflow *name* and the JSON input/output
  shape, not a function import."
- "Workers are stateless and can crash; the Temporal server is the durable
  store. That's why workflows survive pod restarts."

If any of those still feels shaky, say so before lesson 2 — it's the
foundation we'll be standing on.

---

## Notes I'm taking back into the curriculum file

- The user's intuition "workflow = orchestrator, activity = side effects"
  landed cleanly. Reinforce in lesson 3 when we explain *why* — the
  sandbox + replay model makes it not just a convention but a hard rule.
- The user wanted to know the difference between the legacy and
  multi-activity workflows; covered briefly. We'll re-encounter the
  multi-activity version in lesson 4 when we look at per-stage retry.
- Defer for later: detailed reading of `llamaParseActivity.ts`,
  `ParseJobWorkflow` Python definition, the `proxy_activities` Python
  equivalent. They'll come up naturally.

**Next up — Lesson 2: open a real workflow in Temporal UI and read the
event history. Bring a recent parse job ID when you sit down for it.**
