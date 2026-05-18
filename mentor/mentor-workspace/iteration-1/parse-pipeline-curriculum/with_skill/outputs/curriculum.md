# Curriculum: parse-pipeline (end-to-end, debug-oriented)

**Created:** 2026-05-18
**Status:** in_progress
**Current lesson:** 2

## Goal

Trace one parse job from HTTP upload through the Node worker and back to the
database. For each stage, the user can say (a) where the state lives, (b) what
can wedge it, and (c) which signal (Loki / Temporal UI / Postgres / S3) tells
you it's wedged. Success = given a stuck `pjb-…` job, the user can locate the
stuck stage and propose a remediation without external help.

## Prerequisites

- Python + async/await fluency
- Comfortable reading SQLAlchemy 2.0 async code
- Surface-level Temporal vocabulary (workflow vs. activity, replay)
- Familiarity with reading Loki logs
- No prior knowledge of this repo's parse internals assumed

## Lessons

- [x] 1. The 30,000-ft path: request -> row -> workflow -> worker -> result
      Anchor in the canonical entry/exit points and build the mental map
      of which process owns which step.
- [ ] 2. The control plane: `ParseJobWorkflow` as a state machine
      What the Temporal workflow itself does (semaphore acquire, status
      updates, cleanup), distinct from the parsing work it dispatches.
      General concept: workflow engines vs. ad-hoc retry loops; why
      determinism matters and what `workflow.patched` is buying us.
- [ ] 3. The data plane: handoff to the Node worker
      How the inner `llamaparseWorkflow` submits work into the Node
      worker's queue, what crosses S3 vs. what crosses Temporal payloads,
      and how results come back to the Python side.
- [ ] 4. Concurrency, rate limiting, and the semaphore
      Per-tenant `parse_concurrency` semaphore, KEDA-driven worker pool,
      the `granted` signal. Why jobs queue and what controls the rate.
      General concept: cooperative vs. preemptive throttling, backpressure.
- [ ] 5. Failure modes: a tour of "stuck"
      Five concrete stuck-shapes:
        a. Cache short-circuit (looks stuck, actually completed)
        b. Semaphore grant timeout
        c. Activity heartbeat lapse / lost worker
        d. Worker OOM mid-parse
        e. S3 read failure on result fetch
      For each: what shows up in Temporal UI, Loki, Postgres; how to
      confirm; how to unstick.

## Notes from sessions

### Lesson 1 (2026-05-18)
- User wanted the worker handoff covered early -- surfaced it as the
  weakest spot during intake. Lesson 3 reserved for that.
- User asked for cache short-circuit as a stuck-shape in lesson 5
  (added). They have seen jobs that "look stuck" but actually returned
  cached results.
- User has never written a Temporal workflow themselves; determinism
  rules feel cargo-cult to them. Make sure lesson 2 grounds patches in
  the actual `_PARALLELIZATION_PATCH` in `workflow.py` rather than
  abstract examples.
- Lesson 1 comprehension check: predict what `_acquire_and_setup` does
  before reading it, then verify. Result: TBD -- user will report.
</content>
</invoke>