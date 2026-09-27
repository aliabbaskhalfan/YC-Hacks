#!/usr/bin/env python3
"""Load the synthetic history into GBrain and Memorable (BUILD_SPEC.md Section 8.3).

Every synthetic incident becomes a brain note with `synthetic=true` in its
provenance line and a Memorable trace carrying its real outcome — including
the failures, so Memorable learns which repair paths do *not* hold
(Section 7.5).

Only the synthetic corpus is loaded. Live demo incidents are raised on stage
through `POST /events/anomaly` and never appear in incidents.jsonl, which is
what lets the counters visibly move during the demo.

Idempotent three times over: a ledger skips incidents already loaded, GBrain
notes are keyed by an `<!-- incident:... -->` marker, and trace ids are
deduplicated by the trace store. Fleet counters need no loading step at all
— `server.fleet.intel` derives them from the same files on demand, so they
cannot drift out of sync with what was written.

Pushing ~485 notes to the real GBrain endpoint takes about eight minutes of
round trips. That is the right default — the corpus belongs in GBrain — but
`--local-only` writes just the local mirror for fast iteration, and
`--limit` loads a slice.

Usage:
    python -m server.fleet.load_synthetic
    python -m server.fleet.load_synthetic --local-only --reset   # fast rebuild
    python -m server.fleet.load_synthetic --llm                  # real model hygiene pass
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from server.config import Settings, get_settings
from server.integrations.gbrain import GBrainAdapter, LocalBrain
from server.integrations.llm import ModelGateway
from server.integrations.memorable import LocalTraceStore, MemorableAdapter
from server.fleet.fix_signature import with_canonical_steps
from server.models import IncidentContext, Provenance, RepairRecord
from server.procedures import ProcedureStore

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INCIDENTS = REPO_ROOT / "data" / "synthetic" / "incidents.jsonl"


class LoadLedger:
    """Remembers which incidents were loaded, so a re-run is cheap and safe."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.loaded: set[str] = set()
        if path.exists():
            try:
                self.loaded = set(json.loads(path.read_text()).get("incident_ids", []))
            except (OSError, ValueError):
                # A damaged ledger must not block a reload; the adapters
                # deduplicate anyway, so the worst case is redundant work.
                print(f"warn: ignoring unreadable ledger {path}")

    def add(self, incident_id: str) -> None:
        self.loaded.add(incident_id)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"incident_ids": sorted(self.loaded)}, indent=2) + "\n")


def _context_for(row: dict[str, Any]) -> IncidentContext:
    return IncidentContext(
        incident_id=row["incident_id"],
        unit_id=row["unit_id"],
        part_id=row["part_id"],
        site=row["site"],
        signal=row["anomaly"]["signal"],
        what_went_wrong=row["what_went_wrong"],
        fault_signature=row["anomaly"].get("fault_signature", {}),
        status="fixed",
    )


async def load_one(
    row: dict[str, Any],
    *,
    brain: GBrainAdapter,
    memorable: MemorableAdapter,
    llm: ModelGateway,
    procedures: ProcedureStore,
) -> tuple[str, str]:
    record = RepairRecord.model_validate(row["repair_record"])
    incident = _context_for(row)
    capture = row["capture"]

    # Hygiene is judged here rather than at generation time: it compares the
    # record against the SOP *and* the notes already in the brain, so it only
    # means anything once the notes are actually being written, in order.
    sop_text = procedures.step_text(capture["procedure_id"], capture["step_id"])
    prior_notes = await brain.read_part(record.part_id)
    hygiene = await llm.hygiene(record, sop_text, prior_notes)

    provenance = Provenance(
        incident_id=row["incident_id"],
        unit_id=row["unit_id"],
        site=row["site"],
        tech=capture["tech"],
        procedure_id=capture["procedure_id"],
        step_id=capture["step_id"],
        part_id=row["part_id"],
        transcript=capture["transcript"],
        synthetic=True,
        captured_at=row["timestamp"],
    )
    await brain.append_repair(record, hygiene, provenance)

    # The note keeps the tech's words; the trace carries the canonical action
    # so repeats of the same repair group together and can actually be counted.
    trace = memorable.make_trace(with_canonical_steps(record), incident, hygiene, outcome=row["outcome"])
    trace_id, _ = await memorable.record(trace)
    return hygiene.label, trace_id


async def run(args: argparse.Namespace, settings: Settings) -> None:
    rows = [json.loads(line) for line in args.incidents.read_text().splitlines() if line.strip()]
    if not rows:
        raise SystemExit(f"no incidents in {args.incidents} — run sim.synth.generate_incidents first")
    if "repair_record" not in rows[0]:
        raise SystemExit("incidents have no repair_record — regenerate without --skip-records")

    ledger_path = settings.repo_root / "data" / "runtime" / "loaded_synthetic.json"
    if args.reset and ledger_path.exists():
        ledger_path.unlink()
    ledger = LoadLedger(ledger_path)

    brain = GBrainAdapter(
        local=LocalBrain(settings.brain_dir),
        base_url=None if args.local_only else settings.gbrain_mcp_url,
        api_key=settings.gbrain_mcp_token or settings.gbrain_api_key,
        use_local_fallback=settings.use_local_fallbacks,
    )
    memorable = MemorableAdapter(
        local=LocalTraceStore(settings.traces_path),
        api_url=settings.memorable_api_url,
        api_key=None if args.local_only else settings.memorable_api_key,
        environment_id=settings.memorable_environment_id,
        enabled=settings.memorable_enabled and not args.local_only,
        consent=settings.memorable_consent,
        use_local_fallback=settings.use_local_fallbacks,
    )
    llm = ModelGateway(
        settings.anthropic_api_key if args.llm else None,
        settings.anthropic_model,
        bedrock_api_key=settings.aws_bearer_token_bedrock if args.llm else None,
        bedrock_model_id=settings.bedrock_model_id,
        aws_region=settings.aws_region,
    )
    procedures = ProcedureStore(settings.repo_root / "server" / "procedures")

    pending = [row for row in rows if row["incident_id"] not in ledger.loaded]
    if args.limit:
        pending = pending[: args.limit]
    where = "local mirror only" if args.local_only else f"GBrain {settings.gbrain_mcp_url or '(local)'}"
    print(f"{len(rows)} incidents, {len(pending)} to load ({len(rows) - len(pending)} already in the ledger) -> {where}")

    labels: dict[str, int] = {}
    outcomes: dict[str, int] = {}
    # Sequential on purpose: hygiene compares each note against the notes
    # already written, so the order the brain grows in is part of the result.
    for index, row in enumerate(pending, start=1):
        label, _ = await load_one(row, brain=brain, memorable=memorable, llm=llm, procedures=procedures)
        labels[label] = labels.get(label, 0) + 1
        outcomes[row["outcome"]] = outcomes.get(row["outcome"], 0) + 1
        ledger.add(row["incident_id"])
        if index % 100 == 0 or index == len(pending):
            print(f"  {index}/{len(pending)}")
    ledger.save()

    print(f"\nhygiene: {labels or 'nothing new'}")
    print(f"traces:  {outcomes or 'nothing new'}")
    print(f"brain:   {settings.brain_dir}")
    print(f"traces:  {settings.traces_path}")
    print(f"ledger:  {ledger_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--incidents", type=Path, default=DEFAULT_INCIDENTS)
    parser.add_argument("--reset", action="store_true", help="forget the ledger and load everything again")
    parser.add_argument("--llm", action="store_true", help="run the hygiene pass through the real model")
    parser.add_argument("--local-only", action="store_true", help="skip the remote GBrain/Memorable push")
    parser.add_argument("--limit", type=int, default=0, help="load at most this many incidents")
    args = parser.parse_args()
    asyncio.run(run(args, get_settings(REPO_ROOT)))


if __name__ == "__main__":
    main()
