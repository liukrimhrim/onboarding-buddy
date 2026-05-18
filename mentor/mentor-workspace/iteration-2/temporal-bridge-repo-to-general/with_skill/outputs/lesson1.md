# Lesson 1 — Workflows vs. Activities, and why the split exists

**Goal:** By the end you can read any `@workflow_decorator`-decorated class in this repo and instantly tell which lines are "durable orchestration code" vs. "real-world side effects," and explain *why* Temporal forces that boundary on you.

---

## (a) The concept map first

A workflow engine like Temporal solves one problem: **you have a multi-step business process that mixes deterministic decision-making with messy real-world I/O, and you need it to survive process crashes, machine reboots, and deploys without losing track of where it was.**

The way Temporal solves it is a two-tier model. There are two kinds of code, and they obey very different rules:

```
                ┌───────────────────────────────────────────────┐
                │            WORKFLOW (the brain)               │
                │   pure, deterministic, replayable function    │
                │   "what should happen next, given history?"   │
                │                                               │
                │   - no DB, no network, no time.now()          │
                │   - no random, no UUIDs, no env vars          │
                │   - just: await activity(...), if/else,       │
                │     loops, asyncio.gather, signals            │
                └────────────────┬──────────────────────────────┘
                                 │  schedules
                                 ▼
                ┌───────────────────────────────────────────────┐
                │           ACTIVITY (the hands)                │
                │   ordinary async Python — does the real work  │
                │                                               │
                │   - HTTP calls, S3 reads/writes, DB writes    │
                │   - LLM inference, OCR, PDF parsing           │
                │   - anything that touches the outside world   │
                │                                               │
                │   Temporal records the *result* in history.   │
                └───────────────────────────────────────────────┘
```

Why this split: Temporal achieves durability by **replaying** the workflow function from scratch every time it needs to resume (worker died, deploy happened, signal arrived). For replay to give the same answer, the workflow code has to be deterministic — same inputs → same sequence of `await activity(...)` calls. Anything non-deterministic has to live inside an activity, because activity *results* are recorded in the workflow's event history. On replay, the workflow doesn't re-run the activity; Temporal just hands back the result it recorded the first time.

So the rule is: **workflow code says *what* and *in what order*. Activity code does *the thing*.**

Hold that frame as we drop into real code. Watch for: which functions are decorated `@workflow_decorator` vs. `@activity_decorator`, what those functions are *allowed* to do, and where the boundary gets crossed.

---

## (b) Ground it: a real workflow in this repo

Open [backend/src/extract/temporal/workflow.py](backend/src/extract/temporal/workflow.py). Look at lines 78–110.

```python
@workflow_decorator(name=EXTRACT_WORKFLOW_NAME, queue=TaskQueueTypeValues.EXTRACT)
class ExtractionWorkflow:
    async def run_extraction(self, parsed_content, extraction_agent, extract_settings):
        extract_meta_response = await get_extract_meta_activity(
            GetExtractMetadataActivityRequest(...)
        )
        resolved_settings = extract_meta_response.extract_settings
        ...
```

Three things to notice — these are the things you'll look for in *every* workflow class going forward:

**1. The body looks like normal Python but isn't.** That `await get_extract_meta_activity(...)` is not a function call in the ordinary sense. It's a *workflow command* — Temporal records "I asked for activity X with input Y" in the event history. Then the SDK suspends the workflow. Later, when the activity result comes back (possibly minutes or hours later, possibly on a different worker pod after a deploy), Temporal records "activity X returned Z" and resumes the workflow with `Z` as the result. The workflow function itself never sat in memory the whole time.

**2. The decorator pins the workflow to a task queue.** `queue=TaskQueueTypeValues.EXTRACT` says "this workflow runs on workers listening to the `extract` queue." That's how we separate parse workers from extract workers — different pods, different scaling, different concurrency limits. We'll go deep on this in lesson 4.

**3. There's a `@workflow.signal` handler up top.** Signals are the *one* way external code can poke a running workflow without going through an activity. We use them here for the semaphore-grant pattern (the workflow waits to be told "OK, you can proceed"). Don't worry about semaphores yet; just note: workflows are message-driven entities, not request/response handlers.

Now contrast with an activity. Open [backend/src/parse/temporal/direct/activity.py](backend/src/parse/temporal/direct/activity.py) and skim lines 1–60. Notice:

- It imports `file_crud`, `S3Client`, calls `activity.logger.info(...)`.
- It's ordinary async Python. It can do anything.
- It raises `UnrecoverableDirectExtractionError` to mark a failure non-retryable (we'll cover that in lesson 3).

If you wrote `await s3_client.get_object(...)` directly inside `ExtractionWorkflow.run_extraction`, your workflow would technically run the first time and then explode on the first replay — the S3 call is non-deterministic (different latencies, different transient errors, maybe the object got deleted), so the second run would diverge from history. Temporal would raise a **Non-Determinism Error (NDE)** — a one-line gloss since you flagged it: an NDE is "the SDK replayed your workflow and it tried to do something different from what history says it did the first time." Hard-fails the workflow. We'll see NDEs in lesson 3.

**Quick exercise (don't skip):** Open [backend/src/extract/temporal/workflow.py](backend/src/extract/temporal/workflow.py) and find one line in the workflow body that, if you didn't know better, you might be tempted to write directly without an activity. (Hint: think about anything involving time, randomness, or external state.) Then check whether it actually is wrapped in an activity. If it isn't, ask yourself: is this OK because it's deterministic, or is it a latent NDE waiting to happen?

---

## (c) Climb to the general concept

Strip the LlamaCloud specifics: what is Temporal actually?

Temporal is an instance of a broader pattern called a **durable workflow engine** (sometimes "workflow-as-code" or "durable execution"). The core idea is **event sourcing applied to control flow**:

- Your business process is a function.
- Every decision point and every external call gets persisted to an append-only log (the event history).
- The function's *state* is not stored. It's *reconstructed* by replaying the log through the function.
- This makes the function "durable": it survives any kind of process death because nothing important lives in process memory.

The two-tier workflow/activity split is the standard way this pattern is realized. The workflow tier is pure-by-construction; the activity tier is impure-by-construction. The engine handles persistence, retries, timeouts, and resumption *across the boundary*.

A useful analogy — and I mean this one literally, not hand-wavily: **a workflow is a generator function that yields side-effect requests.** Replaying it is like fast-forwarding the generator by feeding it the recorded results of past yields until it gets to the next new yield. (This is roughly how the SDK is actually implemented under the hood — `await` points are the yields.)

What this buys you, concretely:

- **Crash safety.** Pod dies mid-workflow? Another pod replays from history, picks up where it left off.
- **No "stuck job" state in your DB.** You don't need a status column with 14 transitions and a cron job to nudge things forward — Temporal *is* that state machine.
- **Long-lived processes are cheap.** A workflow can sleep for 30 days (`asyncio.sleep(timedelta(days=30))`) — it costs you exactly zero memory while sleeping, because it's not in memory.

What it costs you:

- **You have to think about determinism.** The discipline is non-negotiable. Half this lesson is about that boundary.
- **Workflow code is awkward.** You can't just call `datetime.now()` or `uuid.uuid4()` — you need `workflow.now()` and `workflow.uuid4()` (these are deterministic versions that record their values in history). Repo `CLAUDE.md` has the full prohibited list under "Temporal Workflow Determinism."
- **Versioning is real work.** Changing a workflow's structure means using `workflow.patched(...)` so in-flight workflows that started on the old code path can still replay. We'll cover this in lesson 3.

---

## (d) Compare to alternatives (briefly)

| Approach | What plays the workflow role | What plays the activity role | How durability works |
|---|---|---|---|
| **Temporal (this repo)** | `@workflow_decorator` class | `@activity_decorator` function | Replay from event history |
| **RabbitMQ + status column** | Hand-rolled state machine in DB | Job consumer handlers | DB row + manual retries |
| **AWS Step Functions** | JSON state machine (Amazon States Language) | Lambda functions / SDK integrations | Managed; history per execution |
| **Airflow** | DAG of operators (Python) | Operator `execute()` methods | Scheduler + metadata DB; less granular than Temporal |
| **Cadence** | Same model as Temporal (Temporal forked from Cadence) | Same | Same; Temporal is the actively-maintained successor |

The interesting comparison for us is **RabbitMQ + a status column** — because that's what big chunks of this repo *used* to be, and what `backend/jobs/` (the older job-processing path) still partly is. The tradeoff: hand-rolled status machines are dead simple to start but get gnarly fast once you need retries, parent/child relationships, timeouts, signals, query handlers, and replay-safe deploys. By the time you've built those, you've reinvented Temporal poorly. So the team migrated. (You can see the migration partially complete in the repo — `services_v2/parse/` is Temporal-native, while some older services still use the queue-and-status pattern.)

Step Functions is the closest "buy" alternative to Temporal-the-product. The honest answer for why this team went Temporal: control over workflow code in Python alongside the rest of the backend, local development without paying AWS, and the ability to express complex async patterns (signals, child workflows, semaphores) more naturally than JSON.

---

## (e) Comprehension check

Two things, in this order:

**1. Predict before reading.** Open [backend/src/extract/temporal/workflow.py](backend/src/extract/temporal/workflow.py) and find the `run` method (somewhere below `run_extraction`). Before reading it, predict: what are the *categories* of activities this workflow will call? (Hint: think extract lifecycle — what has to happen for an extraction job to complete?) Then read and check yourself. Note any activity whose existence surprises you — that's a lead worth pulling on.

**2. The "spot the bug" exercise.** Imagine someone opens a PR that adds this line directly inside `ExtractionWorkflow.run_extraction`:

```python
request_id = str(uuid.uuid4())  # for logging correlation
```

Reading what you just learned: what specifically goes wrong? When does it go wrong (the first run? a later run?)? What's the one-line fix? If you can answer all three of those without looking it up, lesson 1 has landed.

---

## What we did *not* cover (and where it goes)

- **What the event history actually looks like** → lesson 2.
- **What happens when an activity throws, and how retries work** → lesson 3.
- **NDEs and `workflow.patched(...)` in detail** → lesson 3.
- **Workers, task queues, KEDA, how work gets routed** → lesson 4.
- **Triaging a real failed workflow** → lesson 5.

When you're ready, say "continue" and we'll roll into lesson 2.

---

*Footnote on persistence:* The mentor skill normally writes curriculum state to `~/.claude/mentor-curricula/<slug>.md` so you can resume across sessions. In this sandbox that path is blocked, so the curriculum and this lesson live at `~/.claude/skills/mentor-workspace/iteration-2/temporal-bridge-repo-to-general/with_skill/outputs/` instead. Resumption logic still works — point me at the curriculum file and say "continue."
