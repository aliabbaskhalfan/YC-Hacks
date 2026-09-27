"""Reduce a tech's wording to the repair action underneath it.

Memorable groups traces by their step path to count how often a given repair
actually held (Section 7.5's "proven fix, N successes"). Verbatim transcripts
never group: "swapped the front right knee actuator" and "pulled the knee
actuator and installed a new one" are the same repair and would otherwise be
two paths of one, leaving every fix a singleton with nothing proven.

So traces carry the canonical action and brain notes keep the tech's own
words — the note is the evidence a human reads, the trace is the thing the
graph counts.

Patterns are ordered most specific first: the two markers the fleet patterns
turn on (threadlocker, supplier-lot checks) must win over the generic verb
that also matches the same clause.
"""

from __future__ import annotations

import re

from server.models import RepairRecord

_RULES: tuple[tuple[str, str], ...] = (
    (r"threadlock", "apply threadlocker"),
    (r"\b(lot|label)\b.*\b(check|inspect)|\bcheck(ed)?\b.*\blot\b", "check supplier lot"),
    (r"continuity", "check continuity"),
    (r"(knee|calf)\b.*\b(actuator|motor)|actuator|knee motor", "replace knee actuator"),
    (r"foot pad|\bpad\b", "replace foot pad"),
    (r"harness", "reseat leg harness"),
    (r"battery", "replace battery pack"),
    (r"\bimu\b", "recalibrate imu"),
    (r"retighten|retorque|tighten|torqu", "retorque hip bolts"),
    (r"recalibr|calibrat|encoder", "recalibrate encoders"),
    (r"\bclean", "clean mount face"),
    (r"power(ed)? down|isolat", "power down"),
    # Prefix matches on purpose: "verified"/"tested" must match too, and a
    # trailing \b after "verif" would never fire mid-word.
    (r"\b(ran|run|verif|test|holding|no error)", "verify with stand cycle"),
)

# A replacement is only a replacement if something says so; otherwise a
# clause naming a part is just the tech mentioning the part.
_REPLACE_VERBS = re.compile(r"\b(swap|replac|install|pull|put|new|fit)", re.I)
_REPLACEMENTS = {"replace knee actuator", "replace foot pad", "replace battery pack", "reseat leg harness"}


def canonical_step(step: str) -> str | None:
    """The repair action a clause describes, or None if it is commentary."""
    text = step.lower()
    for pattern, action in _RULES:
        if not re.search(pattern, text):
            continue
        if action in _REPLACEMENTS and not _REPLACE_VERBS.search(text):
            continue
        return action
    return None


def canonical_steps(steps: list[str]) -> list[str]:
    """Ordered, de-duplicated repair actions behind a note's steps."""
    actions: list[str] = []
    for step in steps:
        action = canonical_step(step)
        if action and action not in actions:
            actions.append(action)
    return actions


def with_canonical_steps(record: RepairRecord) -> RepairRecord:
    """A copy of the record whose steps are canonical, for trace grouping.

    Falls back to the original wording when nothing canonicalises, so a note
    the rules do not cover still produces a trace rather than an empty one.
    """
    actions = canonical_steps(record.fix.steps)
    if not actions:
        return record
    return record.model_copy(update={"fix": record.fix.model_copy(update={"steps": actions})})
