# my-claude-skills

[Claude Code](https://code.claude.com) plugin marketplace for my skills.

## Install

```sh
claude plugin marketplace add liukrimhrim/my-claude-skills
claude plugin install codebase-reading@my-claude-skills
```

Or interactively inside Claude Code: `/plugin marketplace add
liukrimhrim/my-claude-skills`, then `/plugin install
codebase-reading@my-claude-skills`. Update later with
`/plugin marketplace update my-claude-skills`.

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

## License

MIT
