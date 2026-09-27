from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from server.fleet.load_synthetic import LoadLedger, load_one
from server.integrations.gbrain import GBrainAdapter, LocalBrain
from server.integrations.llm import ModelGateway
from server.integrations.memorable import LocalTraceStore, MemorableAdapter
from server.procedures import ProcedureStore

REPO_ROOT = Path(__file__).resolve().parents[1]
INCIDENTS = REPO_ROOT / "data" / "synthetic" / "incidents.jsonl"

pytestmark = pytest.mark.skipif(
    not INCIDENTS.exists(),
    reason="run `python -m sim.synth.generate_incidents --seed 7` first",
)


@pytest.fixture(scope="module")
def sample() -> list[dict]:
    rows = [json.loads(line) for line in INCIDENTS.read_text().splitlines() if line.strip()]
    bolts = [row for row in rows if row["fault_id"] == "hip_bolts_loose"][:6]
    knees = [row for row in rows if row["fault_id"] in {"knee_motor_weak", "knee_motor_overheat"}][:6]
    return bolts + knees


@pytest.fixture
def pipeline(tmp_path: Path):
    brain = GBrainAdapter(local=LocalBrain(tmp_path / "brain"), base_url=None, api_key=None, use_local_fallback=True)
    memorable = MemorableAdapter(
        local=LocalTraceStore(tmp_path / "traces.jsonl"),
        api_url="https://example.invalid",
        api_key=None,
        enabled=False,
        use_local_fallback=True,
    )
    return {
        "brain": brain,
        "memorable": memorable,
        # No key: the deterministic offline hygiene path, so tests never
        # depend on a network call or an API budget.
        "llm": ModelGateway(None, "offline"),
        "procedures": ProcedureStore(REPO_ROOT / "server" / "procedures"),
    }


def test_ledger_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    ledger = LoadLedger(path)
    assert ledger.loaded == set()
    ledger.add("inc-0001")
    ledger.save()
    assert LoadLedger(path).loaded == {"inc-0001"}


def test_ledger_survives_a_corrupt_file(tmp_path: Path) -> None:
    """A damaged ledger must not block a reload."""
    path = tmp_path / "ledger.json"
    path.write_text("{not json")
    assert LoadLedger(path).loaded == set()


def test_load_writes_a_note_and_a_trace(tmp_path: Path, sample, pipeline) -> None:
    row = sample[0]
    label, trace_id = asyncio.run(load_one(row, **pipeline))

    assert label in {"addition", "contradiction", "duplicate"}
    assert trace_id == f"repair:{row['incident_id']}"

    note = (tmp_path / "brain" / "fleet" / "go2" / "parts" / f"{row['part_id']}.md").read_text()
    assert row["capture"]["transcript"] in note
    assert "synthetic=true" in note, "synthetic notes must be labelled as such"
    assert row["incident_id"] in note


def test_loading_twice_does_not_duplicate_the_note(tmp_path: Path, sample, pipeline) -> None:
    row = sample[0]
    asyncio.run(load_one(row, **pipeline))
    asyncio.run(load_one(row, **pipeline))

    note = (tmp_path / "brain" / "fleet" / "go2" / "parts" / f"{row['part_id']}.md").read_text()
    assert note.count(f"<!-- incident:{row['incident_id']} -->") == 1
    traces = [line for line in (tmp_path / "traces.jsonl").read_text().splitlines() if line.strip()]
    assert len(traces) == 1


def test_failed_repairs_are_traced_as_failures(tmp_path: Path, sample, pipeline) -> None:
    """Memorable has to learn which fixes did NOT hold (Section 7.5)."""
    for row in sample:
        asyncio.run(load_one(row, **pipeline))

    traces = [json.loads(line) for line in (tmp_path / "traces.jsonl").read_text().splitlines() if line.strip()]
    by_id = {trace["trace_id"]: trace for trace in traces}
    for row in sample:
        assert by_id[f"repair:{row['incident_id']}"]["outcome"] == row["outcome"]


def test_traces_carry_canonical_steps_so_repeats_group(tmp_path: Path, sample, pipeline) -> None:
    for row in sample:
        asyncio.run(load_one(row, **pipeline))
    traces = [json.loads(line) for line in (tmp_path / "traces.jsonl").read_text().splitlines() if line.strip()]

    descriptions = {
        step["args"].get("description")
        for trace in traces
        for step in trace["steps"]
        if step["tool"] != "diagnose"
    }
    assert descriptions, "traces should carry repair steps"
    # Canonical actions are a small closed vocabulary; verbatim notes are not.
    assert len(descriptions) < 12
    assert all(description == description.lower() for description in descriptions)


def test_recall_returns_a_counted_fix(tmp_path: Path, sample, pipeline) -> None:
    for row in sample:
        asyncio.run(load_one(row, **pipeline))

    bolts = next(row for row in sample if row["fault_id"] == "hip_bolts_loose")
    result = asyncio.run(pipeline["memorable"].recall(bolts["part_id"]))
    assert result.steps, "recall should return a repair path"
    assert result.successes + result.failures >= 1
