# Tutorial: learning any codebase with `codebase-reading` + `mentor`

This guide explains, from zero, how to install and use the two skills in this
repo, how they work together, and the habits that make them effective. No
prior experience with Claude Code skills is assumed. If you already know what
a skill is, jump to [Install](#2-install).

---

## 1. What are these skills?

**Claude Code** is Anthropic's AI coding assistant that runs in your terminal.
A **skill** is a set of written instructions that teaches Claude Code a
repeatable workflow — like a recipe card it pulls out when you ask for that
kind of task.

This repo contains two skills that solve one problem together: **you've been
handed a big unfamiliar codebase, and you need to actually understand it —
fast, and without reading all of it.**

| Skill | What it does | Analogy |
|---|---|---|
| **codebase-reading** | Analyzes a repo and produces a *salience map*: which files actually matter, which are risky, which you can safely ignore | A city map that marks the main streets, the dangerous intersections, and the neighborhoods you'll never need to visit |
| **mentor** | Runs a multi-session tutoring curriculum over that repo: ordered lessons, each grounded in real files, each ending in a quiz | A personal tutor with a syllabus, who checks you actually learned each lesson before moving on |

Why two skills? Because *mapping* a codebase and *learning* it are different
jobs. The map tells you **where** to spend attention. The tutor makes the
knowledge **stick**. Use them in that order.

### A few terms, defined once

- **repo (repository)** — a project's folder of source code, tracked by git.
- **churn** — how often a file changes. High churn = active, evolving code.
- **dependency graph** — which files use which other files. A file that
  hundreds of others depend on is a "backbone" file.
- **salience** — importance. A *salience map* ranks code by how much your
  attention it deserves, instead of treating all files equally.

---

## 2. Install

You need [Claude Code](https://code.claude.com) installed and working first.

### 2a. codebase-reading (one command)

It's published as a plugin. In your terminal:

```sh
claude plugin marketplace add liukrimhrim/onboarding-buddy
claude plugin install codebase-reading@onboarding-buddy
```

Or from inside a Claude Code session:

```
/plugin marketplace add liukrimhrim/onboarding-buddy
/plugin install codebase-reading@onboarding-buddy
```

Update later with `/plugin marketplace update onboarding-buddy`.

### 2b. mentor (one command)

Also a plugin — and installing it brings the quiz gate (below) along
automatically:

```sh
claude plugin install mentor@onboarding-buddy
```

### 2c. mentor's quiz gate

The mentor skill has a *hard gate*: a small script that refuses to let a
lesson be marked "done" unless its quiz actually happened and was recorded.
Without it, the quiz rule is just prose that an AI can accidentally skip.
With it, skipping is impossible.

**If you installed mentor as a plugin (2b), you already have it** — the
plugin registers the hook itself; nothing to configure.

<details>
<summary>Manual install only (skill copied into <code>~/.claude/skills/</code>)</summary>

Add this to the `"hooks"` section of `~/.claude/settings.json` (create the
`PostToolUse` list if it doesn't exist):

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/skills/mentor/scripts/mentor_curriculum_gate.py",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

</details>

What the gate does: every time Claude Code saves a curriculum file, the script
checks that each completed lesson has a proper record (what was taught, what
was quizzed, what you got right or wrong). If not, the save is rejected with
an error telling Claude exactly what's missing. You never have to think about
it — it just quietly enforces honesty.

### 2d. Not on Claude Code? These skills are just markdown

Nothing in these skills is Claude-Code-specific at the core: a skill is a
`SKILL.md` instruction file, and the quiz gate is a plain stdlib-Python
script. To use them with another coding agent (Codex, Cursor, or anything
that reads instruction files):

1. **Give the agent the skill text.** Copy `plugins/mentor/skills/mentor/`
   into wherever your agent discovers instructions — e.g. the shared
   `~/.agents/skills/` convention, your agent's skills directory, or paste
   `SKILL.md` into its custom-instructions slot.
2. **Run the gate without hooks.** The validator works standalone:

   ```sh
   python3 scripts/mentor_curriculum_gate.py ~/.mentor-curricula/<topic>.md
   ```

   Wire it into whatever your agent offers (a save-hook, a pre-commit hook,
   or just run it before ending a session). Exit code 0 = clean; 2 = a
   lesson was closed without its quiz record, with the reason printed.
3. **Curricula are plain markdown** in `~/.mentor-curricula/` — readable and
   editable by hand, no lock-in.

The same goes for `codebase-reading`: its mining commands are ordinary
`git`/`grep`/`gh` shell invocations any agent can run.

### 2e. Optional booster: graphify

codebase-reading works better if [graphify](https://github.com/Graphify-Labs/graphify)
is installed — it builds a real dependency graph (which files call which),
instead of approximating with text search. Not required; the skill falls back
gracefully.

---

## 3. The workflow

The full journey, start to finish:

```
 new repo
    │
    ▼
 ① /codebase-reading  ──►  map.md + roadmap.md     (an afternoon)
    │                       "what matters, what's risky, what to skip"
    ▼
 ② mentor  ──►  curriculum with 3–7 lessons        (spread over days/weeks)
    │            each lesson: real files → concept → quiz
    ▼
 ③ verified understanding you can act on
```

### Step ① — map the repo

Open Claude Code inside the repo and say:

> build me a salience map of this repo and onboard me

The skill will first ask you a few questions — **answer them carefully,
they steer everything**:

- **Role focus / goal.** Say *what you want the map for*. "I'm learning the
  architecture" produces a very different (and for learning, much better)
  map than "I'm on-call for incidents". If you don't say, it guesses.
- **Incident source.** If your team uses Sentry or keeps postmortems, point
  at them; if not, "none" is fine.
- **Density.** "Standard" gives you the map *and* a reading roadmap. Take it.

You get two files (saved under `~/reading/codebases/<repo>/`):

- **map.md** — the one-screen overview, ranked file lists, who owns what,
  a glossary, and diagnoses like "this area changes a lot but nobody reviews
  it — be careful there."
- **roadmap.md** — the repo split into three tiers:
  - **DEEP**: the ~10 files you must genuinely understand,
  - **RECOGNIZE**: files you should know exist (one line each),
  - **AS-NEEDED**: everything else — *explicitly licensed to skip*.

That skip license is the point. Nobody understands a big repo by reading it
top to bottom; experts read on demand. The map just makes your on-demand
choices smart instead of random.

### Step ② — learn it with mentor

In a Claude Code session, say:

> /mentor — build me a curriculum to learn this repo, seeded from my salience map

Mentor writes a syllabus (3–7 lessons) to `~/.claude/mentor-curricula/` and
shows it to you. Push back if a lesson looks wrong — it's your syllabus.

Then run lessons one at a time ("start lesson 1", later "continue"). Every
lesson follows the same shape:

1. **Mastery points up front** — 3–5 concrete things you'll own by the end.
2. **Real files** — you read actual code, with clickable links, framed by a
   concept map so the files aren't trivia.
3. **The general concept** — the lesson climbs from "how *this repo* does it"
   to "how the industry does it", so the knowledge transfers to other jobs.
4. **A quiz** — one question per mastery point. You answer, it corrects you.
   Anything you miss gets revisited next session.

A lesson is one sitting (30–60 min). The curriculum file remembers where you
stopped, so "continue my curriculum" next week picks up cleanly.

---

## 4. Best practices

Hard-won rules — each one exists because skipping it produced a worse result.

**When mapping:**

1. **State your goal in the preflight.** The #1 lever. A map optimized for
   the wrong goal is technically correct and practically useless.
2. **Treat mined results as candidates, not truth.** Automated analysis is
   right about ~half of what it flags as important. Every claim in map.md is
   tagged: `[m]` = a tool measured this, `[i]` = the AI inferred it, `[✓]` =
   a human confirmed it. Trust `[m]`, double-check `[i]`.
3. **Do the human pass.** Show map.md to someone who knows the repo and ask
   two questions: *"what's wrong with this map?"* and *"what would you never
   touch, and why?"* Thirty minutes; converts guesses into verified facts.
4. **Never read the tree linearly.** If you're reading a file that no layer
   flagged and no task needs — stop. That's the skill telling you it's fine.
5. **Old ≠ skippable.** Deprecated code that still serves production traffic
   must be understood; it's just labeled "sunsetting — don't invest deeply."
   Only genuinely dead code gets skipped.

**When learning:**

6. **Answer the quizzes honestly, out loud.** Reading an answer feels like
   learning but doesn't stick; retrieving it from memory does (this is the
   "testing effect" from learning science). A whiffed question is a gift —
   it's the one thing worth revisiting.
7. **Watch for confusables.** The lessons deliberately slow down on pairs
   that are easy to mix up (authentication vs authorization; a job queue vs
   a workflow engine). If a quiz asks you to tell two things apart, that's
   because most people can't at first.
8. **Ask "why does this exist?" relentlessly.** Every lesson should justify
   complexity by showing what breaks without it (the *subtraction test*).
   If neither the lesson nor the code can name what breaks, you may have
   found over-engineering — which is also worth knowing.
9. **Spread lessons out.** Six lessons over two weeks beats six in one day.
   Spacing is not laziness; it's how memory consolidation works.

**When something looks insane:**

10. **Query history, don't scroll it.** The answer to "why is this code like
    this?" almost always lives in an old pull-request discussion, not in the
    code or the commit message. codebase-reading includes an archaeology
    cookbook (`git log -S`, `git blame -w -C`, commit → PR lookups) for
    exactly this. Half of the "this is dumb" reactions dissolve once the
    original constraint surfaces.

---

## 5. Troubleshooting

**"The map is too incident-heavy / hard to follow."**
You didn't state a learning goal in the preflight. Re-run and say "structure
over incidents" — same data, much friendlier output.

**"The curriculum save was rejected with 'mentor curriculum gate FAILED'."**
Working as intended: a lesson was checked off without a complete record.
Claude will fix the record and re-save; you don't need to do anything. If a
lesson legitimately predates the gate, the record can say
`**Record waived:** <reason>`.

**"graphify isn't installed."**
Fine — codebase-reading falls back to text-based analysis and says so in the
map's audit section. Install graphify later and re-run for the upgrade.

**"I want to re-run the map after the repo changed a lot."**
Just ask again. The skill keeps an index (`~/reading/codebases/INDEX.md`),
detects the existing map, and resumes/updates instead of starting over.

---

## 6. Why trust this method?

Every rule in codebase-reading cites published research — from program-
comprehension studies (experts read as-needed, never linearly), software-
repository mining (churn predicts defects; review-starved code ships more
bugs), and learning science (retrieval practice beats re-reading). The
research ledger with full citations ships inside the skill:
`plugins/codebase-reading/skills/codebase-reading/references/mining.md`.

The short version: **attention ∝ importance × risk, mined lists are
candidates until a human corrects them, and knowledge isn't yours until
you've retrieved it from memory.** Everything else is plumbing.
