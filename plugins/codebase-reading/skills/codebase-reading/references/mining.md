# mining.md — command cookbook, disagreement law, history queries, research ledger

All commands are read-only. Run from the repo root. `--since` windows: 12–18
months default; shrink for very active repos. Every ranked list lands in
map.md as `layer / rank / path / score / note`.

## §layers — the four salience layers + people index

### 1. Backbone (structural centrality)

Preferred when installed — **graphify** (github.com/Graphify-Labs/graphify, a
Claude Code extension; the USER installs it manually after verifying
provenance — never auto-install; note its PyPI name differs from the repo and
it hooks into Claude Code config). Detect "installed" via `command -v
graphify` OR an existing `graphify-out/` directory (GRAPH_REPORT.md and
graph.json live INSIDE it, not at repo root) — check both; venv installs hide
from PATH. CLI subcommands vary by build — `graphify --help` before relying
on any. Then `/graphify .` and read `graphify-out/GRAPH_REPORT.md` — its god
nodes, FILTERED TO CODE NODES (mixed corpora surface doc nodes in the list),
rolled up to file level, are the backbone candidate list. Call + inheritance
edges see more than import-only mining, but Protocol/DI seams still
under-rank on raw edge count — the grep table and one live trace remain the
cross-checks, not formalities. Resuming a map that already has a grep
backbone: keep both — roll god nodes up to files, diff against the grep
table, promote agreements to the core, investigate deltas (expect the seams
to BE the deltas). Edge-tag → provenance mapping: facts on EXTRACTED edges
are `[m]`; INFERRED / AMBIGUOUS edges are `[i]`, candidates until
human-corrected. Graph facts beyond edges: community membership counts and
verbatim auto-labels are `[m]`; aggregation choices and label-trust judgments
are `[i]`. The whole `graphify-out/` directory (megabytes, includes an LLM
cache) is untracked tool droppings — allowed under the read-only rule, never
committed; recommend the repo owner add `graphify-out/` to .gitignore (the
mapper must not edit tracked files to do it themselves).

Not installed → per ecosystem, all ranked by in-degree (PageRank if offered):

```bash
madge --json src | jq -r 'to_entries[] | .value[]' | sort | uniq -c | sort -rn | head -25   # JS/TS
go mod graph | awk '{print $2}' | sort | uniq -c | sort -rn | head -25                       # Go (module level)
jdeps -R -verbose:class build/  # Java — aggregate targets
# Python: pydeps <pkg> --show-deps IF installed; otherwise the fallback below is fine
```

Universal fallback (any language): rank per-module IN-DEGREE — extract the
imported TARGET and count it. Raw import-line counts rank statements
(`import sqlite3` wins), not internal centrality — never skip the extraction.

```bash
# adapt package roots (here app|cli) and extension to the repo
grep -rhE '^(from|import) (app|cli)\.' --include='*.py' . \
  | awk '{print $2}' | cut -d. -f1-2 | sort | uniq -c | sort -rn | head -30
```

Caveats: static graphs miss DI, events, dynamic dispatch — cross-check the
top-10 against one live trace before trusting. Entry points (mains, routes,
consumers, crons) are roots, not ranked nodes; inventory them separately.

### 2. Churn heat

```bash
git log --since='18 months ago' --name-only --format= \
  | grep -v '^$' | sort | uniq -c | sort -rn | head -40
```

Cross with size as the complexity proxy (`wc -l` on the top-40). Optional
refinement: recency-weight by rerunning with `--since='3 months ago'` and
flagging risers. Clamp the window to repo age; skip the recency re-run when
the repo is younger than the window.

### 3. Discussion heat

```bash
# review-comment density per file (repo-wide; paginates — can be slow on huge repos)
gh api 'repos/{owner}/{repo}/pulls/comments?per_page=100' --paginate \
  --jq '.[].path' | sort | uniq -c | sort -rn | head -30

# most-contested merged PRs
gh pr list --state merged --limit 300 --json number,title,comments \
  --jq 'map({n:.number, t:.title, c:(.comments|length)}) | sort_by(-.c) | .[0:15]'

# bug-label tallies per component label
gh issue list --state all --label bug --limit 500 --json labels \
  --jq '[.[].labels[].name] | group_by(.) | map({l:.[0], n:length}) | sort_by(-.n)'
```

Plus the non-minable source: ask the team "which module causes the most
arguments?" — record both the answer and the fact it was common knowledge.

### 4. Incident heat

In descending value-per-hour:

Preflight "incident source: none" refers to EXTERNAL sources (1, 3) — the
in-log greps (2) are free and always run; record zeroes if zero.

1. **Postmortem tally** — read every postmortem from the last ~2 years, count
   root-cause component. One hour, highest-yield artifact in this skill.
2. **Incident-linked commits:**
```bash
git log -i -E --grep='INC-[0-9]+|SEV-?[0-9]|outage|postmortem|rollback' \
  --name-only --format= | grep -v '^$' | sort | uniq -c | sort -rn | head -30
```
3. **Crash tracker** — Sentry/Rollbar top culprit frames = a ready-made
   incident-origin file list; PagerDuty alert counts per service.
4. **SZZ walk** (fix-lineage; approximate): for each incident-fix commit,
   `git blame` the changed lines in the fix's PARENT to find the inducing
   commit; aggregate inducing files. `pyszz` automates at scale.

### 5. Co-change coupling (optional layer)

Files that change in the same commits are coupled regardless of imports.
`code-maat -a coupling` on `git log --all --numstat --date=short
--pretty=format:'--%h--%ad--%aN'` output. Answers: "if I touch X, what else
secretly needs touching?"

### 6. People index

```bash
# HEAD is REQUIRED: without it, non-interactive shells make shortlog read
# empty stdin and silently return nothing ("no contributors" ≠ true)
git shortlog -sn HEAD --since='2 years ago' -- <top-dir>   # per major dir
cat CODEOWNERS 2>/dev/null
git log -1 --format='%an %ad' --date=short -- <hot-file>   # is the owner still active?
```

Flag: hot area + no dominant owner, or dominant owner's last commit >6 months
ago → orphaned knowledge; history-first reading, extra seeds.

## §disagreements — cross-layer diagnosis table

| Pattern | Diagnosis | Prescribed move |
|---|---|---|
| churn high · discussion low | under-reviewed velocity (defect signal) | read defensively; over-review own PRs here |
| discussion high · churn low | contested design / cross-team coordination surface | read the longest PR threads BEFORE the code — they are the missing design doc |
| incidents high · churn low | frozen fragile legacy | postmortems first, then error/retry/timeout paths; verify the "don't touch" folklore via history |
| all high | the true core | DEEP tier: code + tests + threads + postmortems |
| community clusters ≠ directory layout | the folder structure lies (drift / Conway scars) | navigate and tier by community, not folder; record the mismatch in map.md; distrust directory-name assumptions in that zone |

The last row needs a dependency graph (graphify Leiden communities, or
equivalent clustering over a REAL EDGE LIST — clustering degree counts is not
equivalent); without one it simply can't fire — don't eyeball it. Rows whose
required layer is absent are recorded in Diagnoses as cannot-fire, not
silently omitted.

**Flat-column rule:** a layer that ran but returned uniform/zero signal (solo
repo → zero review comments; young repo → flat churn) is recorded as FLAT in
the audit, and its column is EXCLUDED from the table — diagnoses fire only
between layers with real variance. A flat discussion layer may substitute PR
description length as a labeled proxy, marked as such.

## §history — archaeology query cookbook

Never scroll; always query. In rough order of frequency of use:

```bash
git log --first-parent --oneline main -- <area> | head -50   # PR-title chronicle of an area
git log -S'MAGIC_CONSTANT' --oneline                          # when did this appear/vanish (pickaxe)
git log -L :funcName:path/to/file                             # full history of one function
git blame -w -C <file>                                        # who/when, ignoring whitespace + moves
gh pr list --search "<sha>" --state merged                    # commit → PR review thread (the rationale)
git log --reverse --format='%ad %s' --date=short -- <dir> | head -20   # origins = the module's founding theory
git log -i -E --grep='revert|hotfix|rollback|workaround' --oneline -- <area>   # scar tissue
git tag --sort=creatordate                                    # chapter markers
```

Curated history outranks mined history: ADRs, design docs, postmortems first
when they exist.

## §artifacts — templates

**map.md**: frontmatter (slug, repo path+remote, dates, density) → `## L0`
(one annotated line per SUBSYSTEM, ≤1 screen — Leiden communities when a
graph exists, else top-level dirs; when communities outnumber the screen,
aggregate to ≤12 subsystem lines quoting community labels verbatim — the
counts and labels are `[m]`, the aggregation itself `[i]`; membership-check
the auto-label of any low-cohesion (≲0.1) mega-community before trusting it,
labels can name minority members; community↔directory mismatches noted per
the disagreement table) → `## Ground truth`
(stack, entities, topology boxes, entry points) → `## Layers` (four ranked
lists + people index) → `## Core` (backbone∩heat, each with tier + why;
role-focus promotions and companion docs labeled as such) → `## Diagnoses`
(disagreement-table hits) → `## Glossary` → `## Surprises` → `## Audit`
(per layer: mined / skipped / FLAT + why; human-corrected: yes/no+date).
Every L0 line and Glossary ENTRY (one tag per entry, so glossaries are
bulleted) carries a provenance tag — `[m]` mined (command output or verbatim
source evidence) · `[i]` inferred (reader's interpretation) · `[✓]`
human-confirmed (assigned only by the §6 mentor pass). A mixed line takes the
tag of its weakest load-bearing claim. The mentor session triages `[i]`
first.

**roadmap.md**: `## Tiers` (DEEP with per-item reading packet: files, tests,
thread links, postmortems, error-paths-first flag · RECOGNIZE · AS-NEEDED) →
`## Sessions` (numbered; each: prequestions / trace target / debrief notes /
redraw diff / questions-asked log) → `## Next`.

**seeds.md** (only when the Seeds gate is open): YAML list; fields: question,
answer, distractors?, item_type (qa | teachback | refutation | minimal_pair),
topic, source — importable into whatever SRS the user runs.

## §ledger — research behind each rule (finding → source → what it licenses)

| Finding | Source | Licenses |
|---|---|---|
| Experts comprehend as-needed; none read systematically | Koenemann & Robertson, CHI 1991 | AS-NEEDED tier; no guilt about unread code |
| Fluency in a large codebase ≈ up to 3 years; productivity still rising at 3 | Zhou & Mockus, FSE 2010 | pacing expectations; roadmap beats default curve, doesn't skip it |
| Comprehension = program model × situation model, cross-referenced | Pennington, Cognitive Psychology 1987 | live traces tied to domain glossary |
| Pros comprehend by interacting with the running system | Roehm et al., ICSE 2012 | sessions 1–2 are debugger traces |
| Key-class detection ≈ 90% recall, ~50% precision; validated as newcomer starting points | Zaidman & Demeyer, JSME 2008 | backbone layer; mined-lists-are-candidates rule |
| Central nodes in dependency network are defect-prone; network > complexity metrics | Zimmermann & Nagappan, ICSE 2008 | backbone = leverage AND risk |
| Relative churn discriminates fault-prone components (~89%) | Nagappan & Ball, ICSE 2005 | churn layer |
| Change history beats static metrics; recency dominates | Graves et al., TSE 2000 | `--since` windows; recency re-run |
| Co-change reveals coupling invisible in code | Gall, Hajek & Jazayeri, ICSM 1998 | co-change layer |
| Low review participation → post-release defects | McIntosh et al., MSR 2014 | silent-churn diagnosis |
| Review's real outcomes: knowledge transfer + understanding negotiation | Bacchelli & Bird, ICSE 2013 | PR threads as the missing design doc |
| Coordination-requirement gaps → failures; congruence −32% resolution time | Cataldo & Herbsleb, TSE 2013 | discussion heat = structural risk, not noise |
| 92% of catastrophic failures = mishandled non-fatal errors; ⅓ trivial | Yuan et al., OSDI 2014 | error-paths-first rule in incident-hot code |
| Fix-inducing changes traceable from fixes (SZZ) | Śliwerski, Zimmermann & Zeller, MSR 2005 | incident lineage walk |
| Developers mine history to recover rationale; "history does not begin with the latest commit" | Codoban et al., ICSME 2015 | query-never-scroll; origins query |
| Rationale is the scarcest knowledge; docs inadequate; it lives in people | LaToza, Venolia & DeLine, ICSE 2006 · Ko, DeLine & Venolia, ICSE 2007 | mentor session; commit→PR walk |
| Walked-through first tasks + proactive mentors beat wait-for-questions | Dagenais et al., ICSE 2010 | request walkthroughs; don't wait |
| New-hire blockers are social, not technical | Begel & Simon, ICER 2008 | timeboxed asking with hypothesis attached |
| Prequestions guide attention and improve retention | Carpenter & Toftness, JARMAC 2017 | 3 prequestions per session |
| Retrieval practice ≫ re-reading | Roediger & Karpicke, 2006 | memory-redraw + FSRS seeds |
| Expertise = chunked patterns; recall advantage vanishes on scrambled code | Chase & Simon 1973 · McKeithen et al. 1981 | learn the repo's ~5 idioms via exemplar files |
| Self-explanation separates strong learners | Chi et al., 1989 | debrief + teachback seeds |
