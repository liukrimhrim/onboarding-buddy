#!/usr/bin/env python3
"""Hard gate for mentor curriculum files.

Rejects a curriculum save when any checked-off lesson lacks a well-formed
`## Lesson N record` section (Mastery / Confusables / Currency / Quiz with
per-question results). This makes the mentor skill's close-out step (f)
machine-enforced instead of prose-advisory.

Two invocation modes:
  - Claude Code PostToolUse hook: reads the tool-call JSON on stdin, extracts
    file_path; exits 0 silently for files outside mentor-curricula/.
  - Standalone: `python3 mentor_curriculum_gate.py <file.md>` for manual runs.

Exit codes: 0 = pass/not-applicable, 2 = violation (blocking; reason on stderr).
"""
import json
import re
import sys
from pathlib import Path

REQUIRED_FIELDS = ("**Mastery:**", "**Confusables:**", "**Currency:**", "**Quiz:**")
QUIZ_RESULT_RE = re.compile(r"→\s*(pass|whiff)", re.IGNORECASE)
CHECKED_LESSON_RE = re.compile(r"^- \[x\]\s*(\d+)\.", re.IGNORECASE | re.MULTILINE)
WAIVER_RE = re.compile(r"\*\*Record waived:\*\*\s*\S")


def find_record(text: str, n: int) -> str | None:
    """Return the body of `## Lesson N record`, or None."""
    m = re.search(rf"^## Lesson {n} record\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return m.group(1) if m else None


def validate(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    for n_str in CHECKED_LESSON_RE.findall(text):
        n = int(n_str)
        record = find_record(text, n)
        if record is None:
            errors.append(f"lesson {n} is checked [x] but has no '## Lesson {n} record' section")
            continue
        if WAIVER_RE.search(record):
            continue  # explicitly waived (pre-gate lesson)
        missing = [f for f in REQUIRED_FIELDS if f not in record]
        if missing:
            errors.append(f"lesson {n} record is missing field(s): {', '.join(missing)}")
        if "**Quiz:**" in record and not QUIZ_RESULT_RE.search(record):
            errors.append(
                f"lesson {n} record has a Quiz section but no per-question results "
                "(each question needs '→ pass' or '→ whiff (revisit: ...)')"
            )
    return errors


def resolve_target() -> Path | None:
    """File from argv (standalone) or hook stdin JSON. None = not applicable."""
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    if "mentor-curricula/" in file_path and file_path.endswith(".md"):
        return Path(file_path)
    return None


def main() -> int:
    target = resolve_target()
    if target is None or not target.exists():
        return 0
    errors = validate(target)
    if errors:
        print(
            "mentor curriculum gate FAILED for "
            f"{target.name}:\n  - " + "\n  - ".join(errors) +
            "\nAppend a well-formed '## Lesson N record' (Mastery/Confusables/Currency/Quiz "
            "with → pass|whiff results) before checking the lesson off.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
