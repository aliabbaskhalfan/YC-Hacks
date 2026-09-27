"""Approving a flag changes the procedure everyone follows (BUILD_SPEC.md Section 9.4).

This is the point of the whole loop: a pattern nobody could see from one
repair becomes a step every tech reads on their next job. Approving a flag
appends the change to the procedure step, bumps the version with the number
of field reports behind it, writes the changelog to GBrain, and returns a
`procedure_updated` event for the server to broadcast so open tech viewers
re-render the step.

Writing the procedure JSON lives here rather than in ProcedureStore because
that store is the read path the API and the agent share; the write path is
only ever reached through an approval.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server.fleet.intel import FlagStore


def _bump(version: str) -> str:
    try:
        major, minor = version.split(".", 1)
        return f"{major}.{int(minor) + 1}"
    except ValueError:
        return "1.1"


def apply_to_procedure(
    procedures_dir: Path,
    procedure_id: str,
    step_id: int,
    addition: str,
    evidence_count: int,
) -> dict[str, Any]:
    """Append the approved change to a step and bump the procedure's version."""
    path = procedures_dir / f"{procedure_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"no procedure at {path}")

    procedure = json.loads(path.read_text())
    step = next((s for s in procedure.get("steps", []) if s.get("step_id") == step_id), None)
    if step is None:
        raise KeyError(f"{procedure_id} has no step {step_id}")

    if addition in step.get("text", ""):
        # Approving twice must not append the sentence twice.
        return {"procedure": procedure, "changed": False, "version": procedure.get("version", "1.0")}

    version = _bump(str(procedure.get("version", "1.0")))
    step["text"] = f"{step.get('text', '').rstrip()} {addition}".strip()
    step["version"] = version
    tips = step.setdefault("tips", [])
    tips.append({"text": addition, "source": f"{evidence_count} field reports"})

    procedure["version"] = version
    changelog = procedure.setdefault("changelog", [])
    changelog.append(
        {
            "version": version,
            "step_id": step_id,
            "change": addition,
            "evidence_count": evidence_count,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    )
    path.write_text(json.dumps(procedure, indent=2) + "\n")
    return {"procedure": procedure, "changed": True, "version": version}


async def approve_flag(
    flag_id: str,
    *,
    flags: FlagStore,
    procedures_dir: Path,
    brain: Any | None = None,
) -> dict[str, Any]:
    """Apply a flag's suggested change, record it, and return the WS event."""
    flag = flags.get(flag_id)
    procedure_id = flag.get("procedure_id")
    step_id = flag.get("step_id")
    addition = flag.get("step_addition")
    if not (procedure_id and step_id and addition):
        raise ValueError(f"{flag_id} has no procedure change to apply")

    evidence_count = int(flag.get("detail", {}).get("incidents") or len(flag.get("evidence_notes", [])))
    result = apply_to_procedure(procedures_dir, procedure_id, step_id, addition, evidence_count)
    flags.set_status(flag_id, "approved")

    if brain is not None:
        await _write_changelog(brain, flag, result["version"], evidence_count)

    return {
        "type": "procedure_updated",
        "procedure_id": procedure_id,
        "step_id": step_id,
        "version": result["version"],
        "change": addition,
        "evidence_count": evidence_count,
        "flag_id": flag_id,
        "part_id": flag.get("part_id"),
        "changed": result["changed"],
    }


async def _write_changelog(brain: Any, flag: dict[str, Any], version: str, evidence_count: int) -> None:
    """Record the approved change in GBrain next to the evidence that drove it."""
    note = (
        f"\n<!-- flag:{flag['flag_id']} -->\n"
        f"## {datetime.now(timezone.utc).isoformat(timespec='minutes')} · procedure updated to v{version}\n"
        f"- flag: {flag['flag_id']} ({flag.get('kind')})\n"
        f"- finding: {flag.get('summary')}\n"
        f"- change: {flag.get('step_addition')}\n"
        f"- applied to: {flag.get('procedure_id')} step {flag.get('step_id')}\n"
        f"- evidence: {evidence_count} field reports, e.g. {', '.join(flag.get('evidence_notes', [])[:5])}\n"
        f"- units: {', '.join(flag.get('units', [])[:8])}\n"
    )
    root = Path(brain.local.root) if hasattr(brain, "local") else Path(brain.root)
    for relative in (
        Path("fleet") / "go2" / "procedures" / f"{flag.get('procedure_id')}.md",
        Path("fleet") / "go2" / "patterns" / f"{flag['flag_id']}.md",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        current = path.read_text() if path.exists() else f"# {path.stem}\n"
        if f"<!-- flag:{flag['flag_id']} -->" not in current:
            path.write_text(current.rstrip() + "\n" + note)
