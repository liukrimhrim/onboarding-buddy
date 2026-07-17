# onboarding-buddy

Agent-neutral onboarding skills — map an unfamiliar repo, then learn it
through a tutored curriculum. The skills are plain markdown + a stdlib
Python validator and work with any coding agent; [Claude Code](https://code.claude.com)
(recommended) gets one-command install via this repo's plugin marketplace,
other agents copy the skill folders (see the
[tutorial](TUTORIAL.md#2d-any-other-agent--these-skills-are-just-markdown)).

**New here? Start with the [step-by-step tutorial](TUTORIAL.md)** — install,
workflow, and best practices, written for beginners.

## Install

```sh
claude plugin marketplace add liukrimhrim/onboarding-buddy
claude plugin install codebase-reading@onboarding-buddy
claude plugin install mentor@onboarding-buddy
```

Or interactively inside Claude Code: `/plugin marketplace add
liukrimhrim/onboarding-buddy`, then `/plugin install
codebase-reading@onboarding-buddy` and `/plugin install
mentor@onboarding-buddy`. Update later with
`/plugin marketplace update onboarding-buddy`.

**Other ways to install** — no marketplace required:

- **Manual copy** (Claude Code, no plugin system): copy a skill folder into
  `~/.claude/skills/` — note the mentor quiz gate then needs a one-time hook
  snippet ([tutorial §2c](TUTORIAL.md#2c-mentors-quiz-gate)).
- **Team install**: commit a skill folder into your repo's `.claude/skills/`
  — everyone who opens the repo gets it, zero individual setup.
- **Local marketplace** (offline / hacking on the skills):
  `claude plugin marketplace add /path/to/clone`.
- **Any other agent**: the skills are plain markdown + a stdlib script —
  copy the folder into your agent's skills/instructions mechanism
  ([tutorial §2d](TUTORIAL.md#2d-any-other-agent--these-skills-are-just-markdown)).

Details for each: [tutorial §2](TUTORIAL.md#2-install).

## Skills

### codebase-reading

Onboard onto an unfamiliar repo the quantitative way. One run mines four
salience layers — dependency-graph **backbone**, **churn**,
**review-discussion heat**, **incident heat** — into a one-screen map, then
tiers the repo into DEEP / RECOGNIZE / AS-NEEDED so you master the ~10% that
matters instead of scrolling the tree. Includes a git/PR archaeology cookbook
("why is this code like this?"), a disagreement table that turns cross-layer
mismatches into diagnoses (silent churn = under-reviewed risk; incident-hot +
churn-cold = frozen fragile — read the error paths first), and a
human-correction pass with per-claim provenance tags. Every rule is backed by
a research ledger (program-comprehension and mining-software-repositories
literature, Naur to SZZ) inside the skill.

Trigger it with things like *"onboard me to this repo"*, *"build a salience
map"*, or *"why is this code like this?"*.

### mentor

Multi-session tutor that turns a repo into a curated curriculum: 3–7 ordered
lessons, each grounded in real files, climbing to the general concept, ending
in a quiz mapped to explicit mastery points. Confusables get disambiguated and
tested; deprecated code is down-weighted but not skipped; a validator hook
hard-enforces that no lesson closes without its quiz recorded. Curricula
persist across sessions. Installing the plugin also registers the validator
hook automatically — see the [tutorial](TUTORIAL.md#2b-mentor-on-claude-code-one-command).

Trigger it with *“tutor me on X”*, *“build me a learning plan”*, or
*“continue my curriculum”*.

## License

MIT
