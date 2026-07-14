---
name: codebase-reading
description: Turn an unfamiliar repo (new job, new team, adopted codebase) into a quantitative salience map (structural backbone × three heat layers — churn, review-discussion, incidents), a tiered reading roadmap (deep-read the backbone∩hotspot core, recognize the rest, skip the periphery), and history-archaeology answers — so a new joiner masters the ~10% that matters instead of scrolling the tree. Use when the user joins a company/team or adopts an unfamiliar codebase ("get me up to speed on this repo", "onboard me", "build a salience map / reading roadmap"), wants the load-bearing or dangerous parts located, asks why some code is the way it is (git/PR archaeology), or resumes a partially mapped codebase. Optional spaced-repetition seeds are strictly OPT-IN (explicit request only — never emitted by default). Not for reviewing diffs, designing module boundaries, or reading books/papers — this is for learning an existing codebase.
---

# codebase-reading: salience map + tiered roadmap over an unfamiliar repo

One run turns a cloned repo into `~/reading/codebases/<slug>/`: `map.md` (the
product: L0 one-screen map, four salience layers, disagreement diagnoses,
people index, audit block) + `roadmap.md` (tiered reading sessions + log) +
an INDEX row (+ `seeds.md` only on explicit request — see the Seeds gate).
Design principles, all research-backed (ledger in references/mining.md):
**attention ∝ centrality × heat, never uniform** — no expert comprehends a
system by systematic reading; as-needed, task-scoped comprehension is the
validated norm · **mined lists are candidates, not verdicts** — automated
key-class detection hits ~90% recall at ~50% precision, so every layer is
human-corrected before the deep-read tier is final · **history is a database
to query, never a document to scroll** · the subject repo is read-only for
this skill.

`references/mining.md` is the COOKBOOK + RESEARCH LEDGER (per-layer commands
with fallbacks, disagreement table, history queries, artifact templates,
finding→citation table). Read it before Phase 2.

## Pipeline

0. **ALWAYS ASK first — never silently default.** One preflight question
   combining: repo path + slug · the user's role focus and suspected
   money path (weights salience) · incident source if any (postmortem folder /
   Sentry / PagerDuty / issue label / none) · density (lean = map only |
   standard = map + roadmap — suggest standard; seeds are NOT a density level:
   see the Seeds gate below). Check
   `~/reading/codebases/INDEX.md` FIRST: existing row → report state and
   resume (skip phases whose artifacts exist); never silently redo.

1. **Ground truth, ~30 min, no mining yet.** CI config (the only honest
   build/test doc) → reproduce a green build + test run. Dependency manifest →
   tech stack list. DB schema / newest migrations → top ~15 domain entities
   into the glossary. Deployment topology (Dockerfile/compose/k8s/terraform) →
   process boxes and stores. Entry-point inventory (mains, route tables, queue
   consumers, cron jobs) → the roots every later trace starts from.

2. **Mine the four salience layers** (cookbook §layers; each yields a ranked
   list in map.md):
   - **Backbone** — dependency-graph centrality. graphify god-nodes when
     installed (call + inheritance edges see past import-only blindness;
     Leiden communities double as the L0); else madge / pydeps / `go mod
     graph` / jdeps; per-module in-degree grep as universal fallback.
   - **Churn heat** — 12–18-month change frequency, crossed with file size.
   - **Discussion heat** — review-comment density per file, longest merged PR
     threads, bug-label tallies per component.
   - **Incident heat** — postmortem tally by root-cause component (the single
     highest-value hour of onboarding), incident-ticket greps over the log,
     crash-tracker culprit frames, SZZ walk when fix-lineage matters.
   Plus the **people index**: `git shortlog -sn HEAD` per top dir +
   CODEOWNERS; flag hot areas with no dominant owner or a departed owner
   (last-commit dates) — those areas get extra care and history-first reading.
   A layer that can't be mined (no gh, no PRs, no incident source) is SKIPPED
   AND SAID in the audit block; a layer that ran but returned uniform/zero
   signal is recorded as FLAT and excluded from disagreement diagnoses.
   Never fake or silently omit a layer.

3. **Diagnose + tier** (roadmap.md). Core = backbone ∩ any-heat, typically
   5–15 files. Entry-point roots are core-eligible when they carry heat
   (their in-degree is ignored — it's an artifact). Churn-hot non-code files
   inside the role focus join the core as labeled "companion docs" (no
   backbone score required). Role focus may promote items into DEEP — always
   labeled "role-focus promotion" in the Core table, never silently. Run the
   disagreement table (cookbook §disagreements) — where
   the layers disagree is the diagnosis: silent churn = under-reviewed risk;
   discussion-hot + churn-cold = contested design, threads before code;
   incident-hot + churn-cold = frozen fragile, postmortems + error paths
   first; community clusters ≠ directory layout (needs a graph) = the folders
   lie, navigate by community there. Tiers: **DEEP** (core: read with its tests + its 3 longest PR
   threads + linked postmortems; in incident-hot code read the error / retry /
   timeout paths FIRST — ~92% of catastrophic failures live in the handling of
   non-fatal errors, and error paths barely churn, so churn alone buries them)
   · **RECOGNIZE** (remaining hot files: one-line role each, no mastery) ·
   **AS-NEEDED** (everything else: explicit skip license). Sessions 1–2 of
   DEEP are always live traces — debugger through the money path, then the
   async path — never cold reading. When a graph exists, pre-query the static
   path (`/graphify path "A" "B"`) as the hypothesis the live trace verifies —
   the graph plans the trace, it never replaces it. Read the hop labels:
   shortest paths may shortcut through contains/imports edges and skip the
   real orchestrator — prefer the all-`calls` chain as the hypothesis even
   when it's longer. No graph → no pre-query;
   a hand-traced hypothesis is labeled hand-traced, never given graph
   authority.

4. **Session protocol** (every DEEP session): write 3 prequestions BEFORE
   opening files — mine the incident corpus for them ("what happens when X
   times out mid-capture?" beats any invented question); no incident corpus →
   derive them from error-handling surfaces and the longest PR design bodies
   → trace/read →
   debrief: every question the user asked mid-session is a weakness signal;
   log it and weight later study toward it → memory-redraw the architecture,
   diff against map.md; gaps seed the next session's prequestions → mint
   seeds ONLY if the Seeds gate is open (explicit request — never by default).

5. **Archaeology on demand** (whenever code looks insane — cookbook §history):
   first-parent PR-title stream · pickaxe `-S` · `log -L :func:file` ·
   `blame -w -C` → PR thread via gh · `--reverse` origins · scar greps
   (revert/hotfix/rollback). Rationale lives in PR review threads, almost
   never in commit messages — always walk commit → PR.

6. **Correct + close.** 30-min senior/mentor session: present map.md —
   triage its `[i]`-tagged (inferred) lines first, then the rest (`[m]` is
   not exempt); confirmed-or-corrected lines flip to `[✓]` — and ask
   "what's wrong with it?" and "what would you never touch, and why?" —
   folklore answers become refutation seeds whose answers are then VERIFIED
   via history, not inherited. An UNSURE mentor answer is not a confirmation:
   if the claim is history-verifiable (design intent, why-it's-like-this),
   run §5 archaeology and let the evidence flip the tag; if it isn't, the
   line stays `[i]` with a named revisit trigger (e.g. "after session 1").
   Fix the map, upsert INDEX, report counts
   (core size, layers mined/skipped) + audit block.

## Seeds (opt-in gate)

**OPT-IN ONLY: never generate seeds.md or import items into any study system
unless the user EXPLICITLY asks** ("mint seeds", "quiz me on this repo").
Onboarding knowledge lives in the map/roadmap; a personal spaced-repetition
queue holds deliberate curricula, and codebase items would cross-contaminate
them. When seeds ARE requested, scope their topics to a single dedicated
track ("codebases/<slug>/...") and confirm the track with the user before
importing anything.

`seeds.md` is plain YAML, one entry per item: question, answer, distractors?
(for choice-based types), item_type (qa | teachback | refutation |
minimal_pair), topic, source (a map.md anchor). Import into whatever SRS the
user runs (Anki, an FSRS app, a custom loop). Minting rules: every core
module → `teachback` ("walk the money path through X") · every
disagreement-table diagnosis → `qa` · every folklore claim from the mentor
session → `refutation` whose distractor is the folklore and whose answer is
the history-verified fact · confusable module pairs → `minimal_pair`.

## Hard rules

- Never linear or alphabetical reading; never "read the whole tree first."
  If you are reading a file no layer flagged and no task demands, stop.
- No DEEP tier is final until a human marked up the mined map (§6 can move
  earlier, never be skipped).
- Silent churn is a risk marker, not reassurance.
- History: query, never scroll. Paging through `git log` = doing it wrong.
- No refactoring during onboarding; "this is dumb" goes in the surprises log —
  half dissolve once the constraint surfaces via archaeology.
- Missing data source → skip the layer; ran-but-flat → mark FLAT. Both go in
  the audit block. Never fabricate a signal.
- The subject repo is read-only for tracked content: no edits, commits,
  checkouts, or pushes. Build/test caches from the phase-1 green run and
  `git fetch` refs are fine.
