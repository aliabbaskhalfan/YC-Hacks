from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.fleet.approve import apply_to_procedure, approve_flag
from server.fleet.fix_signature import canonical_steps, with_canonical_steps
from server.fleet.intel import (
    FlagStore,
    build_flags,
    counters,
    load_rows,
    mine_patterns,
    part_class,
    three_strike_clusters,
)
from server.fleet.registry import Registry
from server.models import RepairFix, RepairRecord

REPO_ROOT = Path(__file__).resolve().parents[1]
INCIDENTS = REPO_ROOT / "data" / "synthetic" / "incidents.jsonl"

pytestmark = pytest.mark.skipif(
    not INCIDENTS.exists(),
    reason="run `python -m sim.synth.generate_incidents --seed 7` first",
)


@pytest.fixture(scope="module")
def registry() -> Registry:
    return Registry.load()


@pytest.fixture(scope="module")
def rows(registry: Registry):
    return load_rows(registry, INCIDENTS)


# ---- fix signatures -------------------------------------------------------


@pytest.mark.parametrize(
    "step, expected",
    [
        ("swapped the front right knee actuator", "replace knee actuator"),
        ("pulled the rear left knee actuator and installed a new one", "replace knee actuator"),
        ("put threadlocker on them", "apply threadlocker"),
        ("verified with a stand cycle", "verify with stand cycle"),
        ("tested it, no errors", "verify with stand cycle"),
        ("retightened the front right hip bolts", "retorque hip bolts"),
        ("bolts had backed right off", None),
    ],
)
def test_canonical_step(step: str, expected: str | None) -> None:
    assert (canonical_steps([step]) or [None])[0] == expected


def test_different_wordings_of_one_repair_collapse() -> None:
    """Without this, every trace is a singleton and nothing is ever 'proven'."""
    a = canonical_steps(["swapped the front right knee actuator", "ran a stand cycle to verify"])
    b = canonical_steps(["pulled the rear left knee actuator and installed a new one", "tested it, no errors"])
    assert a == b == ["replace knee actuator", "verify with stand cycle"]


def test_with_canonical_steps_keeps_record_otherwise_intact() -> None:
    record = RepairRecord(
        incident_id="inc-0001", unit_id="go2-01", part_id="fr.calf.motor",
        what_went_wrong="x",
        fix=RepairFix(steps=["swapped the front right knee actuator"], parts_used=["knee actuator"]),
        confidence=0.9,
    )
    canonical = with_canonical_steps(record)
    assert canonical.fix.steps == ["replace knee actuator"]
    assert canonical.fix.parts_used == ["knee actuator"]
    assert record.fix.steps == ["swapped the front right knee actuator"], "original must not be mutated"


def test_commentary_only_note_keeps_its_original_steps() -> None:
    record = RepairRecord(
        incident_id="inc-0002", unit_id="go2-01", part_id="fr.calf.motor",
        what_went_wrong="x", fix=RepairFix(steps=["bolts had backed right off"]), confidence=0.5,
    )
    assert with_canonical_steps(record).fix.steps == ["bolts had backed right off"]


# ---- counters and mining --------------------------------------------------


def test_part_class() -> None:
    assert part_class("fr.calf.motor") == "calf.motor"
    assert part_class("base.battery") == "base.battery"


def test_counters_cover_every_dimension(rows) -> None:
    result = counters(rows)
    assert set(result) == {"part_id", "part_class", "site", "supplier_lot", "fault_id"}
    knees = result["part_class"]["calf.motor"]
    assert knees.incidents > 50
    assert knees.distinct_units > 10
    assert 0 <= knees.recurrence_rate <= 1
    assert knees.mtbf_days and knees.mtbf_days > 0


def test_hip_bolt_fixes_hold_worse_than_others(rows) -> None:
    """The threadlocker problem should be visible in the counters alone."""
    result = counters(rows)["part_class"]
    assert result["hip.mount_bolts"].success_rate < result["calf.motor"].success_rate


def test_mining_finds_the_planted_knee_pattern(rows, registry: Registry) -> None:
    cells = {(c.part_class, c.dimension, c.key): c for c in mine_patterns(rows, registry)}
    cell = cells.get(("calf.motor", "supplier_lot+ambient_class", "B@hot"))
    assert cell is not None, "the lot-B-at-hot-sites pattern did not surface"
    assert cell.ratio > 2.5 and cell.incidents >= 8
    assert cell.rate > cell.baseline_rate


def test_mining_finds_the_threadlocker_pattern(rows, registry: Registry) -> None:
    cells = {(c.part_class, c.dimension, c.key): c for c in mine_patterns(rows, registry)}
    cell = cells.get(("hip.mount_bolts", "fix_used", "without:apply threadlocker"))
    assert cell is not None, "the threadlocker pattern did not surface"
    assert cell.ratio > 2.5


def test_mining_uses_exposure_not_raw_counts(rows, registry: Registry) -> None:
    """A big site must not flag purely for owning more robots."""
    for cell in mine_patterns(rows, registry):
        assert cell.exposure > 0
        assert cell.rate == pytest.approx(cell.incidents / cell.exposure, rel=1e-3)


def test_mining_reports_nothing_on_an_empty_fleet(registry: Registry) -> None:
    assert mine_patterns([], registry) == []


# ---- flags ----------------------------------------------------------------


def test_pattern_flags_outrank_three_strike(rows, registry: Registry) -> None:
    flags = build_flags(rows, registry)
    kinds = [flag.kind for flag in flags]
    assert kinds[0] == "pattern"
    assert kinds.index("pattern") < kinds.index("three_strike")


def test_overlapping_views_of_one_problem_flag_once(rows, registry: Registry) -> None:
    """lot B, lot B at hot sites, and the hot site itself are one finding."""
    knee_patterns = [
        flag for flag in build_flags(rows, registry)
        if flag.kind == "pattern" and flag.part_class == "calf.motor"
    ]
    assert len(knee_patterns) == 1


def test_flags_carry_an_applicable_procedure_change(rows, registry: Registry) -> None:
    for flag in build_flags(rows, registry):
        if flag.kind != "pattern":
            continue
        assert flag.procedure_id and flag.step_id and flag.step_addition
        assert flag.units and flag.evidence_notes


def test_three_strike_needs_three_distinct_units(rows) -> None:
    clusters = three_strike_clusters(rows)
    assert clusters, "expected at least one cluster in a 90-day fleet history"
    for cluster in clusters:
        units = cluster["units"]
        assert len(set(units)) == len(units) >= 3
        assert len(cluster["incidents"]) >= len(units)


def test_flag_store_preserves_status_across_remining(tmp_path: Path, rows, registry: Registry) -> None:
    store = FlagStore(tmp_path / "flags.json")
    flags = build_flags(rows, registry)
    store.save(flags)
    target = flags[0].flag_id
    store.set_status(target, "dismissed")

    reminted = store.merge(build_flags(rows, registry))
    assert next(flag for flag in reminted if flag.flag_id == target).status == "dismissed"


# ---- approve --------------------------------------------------------------


@pytest.fixture
def procedures(tmp_path: Path) -> Path:
    destination = tmp_path / "procedures"
    shutil.copytree(REPO_ROOT / "server" / "procedures", destination)
    return destination


def test_apply_to_procedure_bumps_version_and_records_evidence(procedures: Path) -> None:
    result = apply_to_procedure(procedures, "replace-knee-motor", 4, "Check the lot label.", 70)
    assert result["changed"] and result["version"] == "1.1"

    saved = json.loads((procedures / "replace-knee-motor.json").read_text())
    step = next(s for s in saved["steps"] if s["step_id"] == 4)
    assert "Check the lot label." in step["text"]
    assert step["tips"][0]["source"] == "70 field reports"
    assert saved["changelog"][0]["evidence_count"] == 70


def test_applying_the_same_change_twice_is_a_no_op(procedures: Path) -> None:
    apply_to_procedure(procedures, "replace-knee-motor", 4, "Check the lot label.", 70)
    second = apply_to_procedure(procedures, "replace-knee-motor", 4, "Check the lot label.", 70)
    assert second["changed"] is False

    saved = json.loads((procedures / "replace-knee-motor.json").read_text())
    step = next(s for s in saved["steps"] if s["step_id"] == 4)
    assert step["text"].count("Check the lot label.") == 1
    assert len(saved["changelog"]) == 1


def test_apply_to_procedure_rejects_unknown_targets(procedures: Path) -> None:
    with pytest.raises(FileNotFoundError):
        apply_to_procedure(procedures, "no-such-procedure", 1, "x", 1)
    with pytest.raises(KeyError):
        apply_to_procedure(procedures, "replace-knee-motor", 99, "x", 1)


def test_approve_emits_a_procedure_updated_event(tmp_path: Path, procedures: Path, rows, registry: Registry) -> None:
    store = FlagStore(tmp_path / "flags.json")
    flags = build_flags(rows, registry)
    store.save(flags)
    knee = next(f for f in flags if f.kind == "pattern" and f.part_class == "calf.motor")

    event = asyncio.run(approve_flag(knee.flag_id, flags=store, procedures_dir=procedures))
    assert event["type"] == "procedure_updated"
    assert event["procedure_id"] == "replace-knee-motor"
    assert event["version"] == "1.1"
    assert event["evidence_count"] > 8
    assert store.get(knee.flag_id)["status"] == "approved"


def test_approve_refuses_a_flag_with_no_change_to_apply(tmp_path: Path, procedures: Path) -> None:
    store = FlagStore(tmp_path / "flags.json")
    store.path.write_text(json.dumps({"flag-x": {"flag_id": "flag-x", "status": "open"}}))
    with pytest.raises(ValueError):
        asyncio.run(approve_flag("flag-x", flags=store, procedures_dir=procedures))


# ---- API ------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    from server.fleet.api import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_flags_endpoint_filters(client: TestClient) -> None:
    everything = client.get("/flags").json()["flags"]
    patterns = client.get("/flags?kind=pattern").json()["flags"]
    assert 0 < len(patterns) < len(everything)
    assert all(flag["kind"] == "pattern" for flag in patterns)


def test_counters_and_patterns_endpoints(client: TestClient) -> None:
    assert "part_class" in client.get("/fleet/counters").json()
    assert client.get("/fleet/patterns").json()["patterns"]


def test_unknown_flag_is_404(client: TestClient) -> None:
    assert client.post("/flags/nope/approve").status_code == 404
    assert client.post("/flags/nope/dismiss").status_code == 404
