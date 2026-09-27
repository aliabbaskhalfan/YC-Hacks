from __future__ import annotations

import json
import random
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from server.fleet.registry import Registry
from sim.synth import telemetry as telemetry_mod
from sim.synth.generate_incidents import FAULT_WEIGHTS, KNEE_FAULTS, draw_events

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGS = ("fl", "fr", "rl", "rr")


@pytest.fixture(scope="module")
def registry() -> Registry:
    return Registry.load()


@pytest.fixture(scope="module")
def dataset(tmp_path_factory) -> list[dict]:
    out = tmp_path_factory.mktemp("synthetic")
    subprocess.run(
        [
            sys.executable, "-m", "sim.synth.generate_incidents",
            "--seed", "7", "--window-end", "2026-09-27", "--out", str(out),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return [json.loads(line) for line in (out / "incidents.jsonl").read_text().splitlines()]


def test_registry_covers_every_part_and_unit(registry: Registry) -> None:
    assert len(registry.units) == 40
    assert len(registry.sites) == 6
    assert len(registry.motor_part_ids) == 12
    # Every motor on every unit has a lot; nothing else does.
    for unit_id in registry.units:
        for motor in registry.motor_part_ids:
            assert registry.supplier_lot(unit_id, motor) in {"A", "B", "C"}
        assert registry.supplier_lot(unit_id, "fr.foot.pad") is None


@pytest.mark.parametrize("fault_id", sorted(telemetry_mod.FAULT_SIGNALS))
def test_every_fault_trips_its_detector(fault_id: str) -> None:
    """An incident that never crosses its threshold would not have been raised."""
    for index in range(40):
        rng = random.Random(index)
        window = telemetry_mod.simulate(fault_id, rng.uniform(0.1, 1.0), rng)
        assert window.t_cross is not None, f"{fault_id} failed to trip at draw {index}"
        assert window.detector_peak > window.threshold


def test_generation_is_reproducible(tmp_path: Path) -> None:
    def run(out: Path) -> str:
        subprocess.run(
            [
                sys.executable, "-m", "sim.synth.generate_incidents",
                "--seed", "7", "--window-end", "2026-09-27", "--out", str(out),
                "--skip-records",
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        )
        return (out / "incidents.jsonl").read_text()

    assert run(tmp_path / "a") == run(tmp_path / "b")


def test_dataset_shape(dataset: list[dict]) -> None:
    assert 420 <= len(dataset) <= 560, f"expected ~500 incidents, got {len(dataset)}"
    assert {row["fault_id"] for row in dataset} == set(FAULT_WEIGHTS)
    assert len({row["unit_id"] for row in dataset}) == 40
    assert len({row["site"] for row in dataset}) == 6
    assert len({row["incident_id"] for row in dataset}) == len(dataset)
    assert all(0 <= row["day_index"] < 90 for row in dataset)
    for row in dataset:
        assert row["synthetic"] is True
        assert row["anomaly"]["part_id"] == row["part_id"]
        assert row["repair_record"]["incident_id"] == row["incident_id"]
        assert row["outcome"] in {"success", "failure"}


def test_lot_is_consistent_with_the_registry(dataset: list[dict], registry: Registry) -> None:
    """A note that names a lot must name the lot actually fitted to that motor."""
    for row in dataset:
        assert row["supplier_lot"] == registry.supplier_lot(row["unit_id"], row["part_id"])
        if row["capture"]["mentioned_lot"]:
            assert row["supplier_lot"] is not None
            assert f"lot {row['supplier_lot']}" in row["capture"]["transcript"]


def test_hidden_knee_pattern_is_discoverable(dataset: list[dict], registry: Registry) -> None:
    """Recoverable from incidents + registry alone, with no access to ground_truth."""
    exposure: dict[tuple[str, str], int] = {}
    for unit_id, unit in registry.units.items():
        for leg in LEGS:
            key = (registry.supplier_lot(unit_id, f"{leg}.calf.motor"), unit["ambient_class"])
            exposure[key] = exposure.get(key, 0) + 1

    counts: dict[tuple[str, str], int] = {}
    for row in dataset:
        if row["fault_id"] not in KNEE_FAULTS:
            continue
        key = (registry.supplier_lot(row["unit_id"], row["part_id"]), row["ambient_class"])
        counts[key] = counts.get(key, 0) + 1

    target = ("B", "hot")
    target_rate = counts[target] / exposure[target]
    rest_hits = sum(v for k, v in counts.items() if k != target)
    rest_rate = rest_hits / sum(v for k, v in exposure.items() if k != target)

    # Section 9.3 flags a cell at ratio > 2.5 with at least 8 incidents.
    assert counts[target] >= 8
    assert target_rate / rest_rate > 2.5


def test_threadlocker_pattern_shows_in_the_extracted_record(dataset: list[dict]) -> None:
    """Pattern 3 has to be visible in what the extractor pulled from the note."""
    buckets = {True: [0, 0], False: [0, 0]}  # mentions threadlocker -> [total, failed]
    for row in dataset:
        if row["fault_id"] != "hip_bolts_loose":
            continue
        fix = row["repair_record"]["fix"]
        blob = " ".join([*fix["steps"], *fix["tools"], fix.get("tip") or ""]).lower()
        bucket = buckets["threadlocker" in blob]
        bucket[0] += 1
        bucket[1] += row["outcome"] == "failure"

    locked_total, locked_failed = buckets[True]
    plain_total, plain_failed = buckets[False]
    assert locked_total >= 8 and plain_total >= 8
    assert (plain_failed / plain_total) > 2.5 * (locked_failed / locked_total)


def test_patterns_are_not_written_into_any_incident(dataset: list[dict]) -> None:
    """The dataset must never hand over the answer — it has to be mined."""
    banned = ("lot_b", "hidden", "ground_truth", "pattern", "multiplier")
    for row in dataset:
        keys = json.dumps(row).lower()
        for term in banned:
            assert term not in keys, f"{row['incident_id']} leaks '{term}'"


def test_recurrences_point_at_a_real_earlier_incident(dataset: list[dict]) -> None:
    by_id = {row["incident_id"]: row for row in dataset}
    seen = 0
    for row in dataset:
        parent_id = row["recurrence_of"]
        if not parent_id:
            continue
        seen += 1
        parent = by_id[parent_id]
        assert parent["unit_id"] == row["unit_id"]
        assert parent["part_id"] == row["part_id"]
        assert parent["day_index"] < row["day_index"]
        assert parent["outcome"] == "failure"
    assert seen > 0, "expected at least some repeat failures"


def test_draw_is_unbiased_across_seeds(registry: Registry) -> None:
    """Lot B must only be elevated where the pattern says: at hot sites."""
    totals = {"B_temperate": 0, "A_temperate": 0}
    reps = 12
    for rep in range(reps):
        events = draw_events(registry, random.Random(500 + rep), 90, 400, date(2026, 6, 30))
        for event in events:
            if event.fault_id not in KNEE_FAULTS or event.parent_uid or not event.leg:
                continue
            unit = registry.unit(event.unit_id)
            if unit["ambient_class"] != "temperate":
                continue
            lot = registry.supplier_lot(event.unit_id, f"{event.leg}.calf.motor")
            if lot in {"A", "B"}:
                totals[f"{lot}_temperate"] += 1

    b_motors = sum(1 for u in registry.units for leg in LEGS
                   if registry.supplier_lot(u, f"{leg}.calf.motor") == "B"
                   and registry.ambient_class(u) == "temperate")
    a_motors = sum(1 for u in registry.units for leg in LEGS
                   if registry.supplier_lot(u, f"{leg}.calf.motor") == "A"
                   and registry.ambient_class(u) == "temperate")
    b_rate = totals["B_temperate"] / (b_motors * reps)
    a_rate = totals["A_temperate"] / (a_motors * reps)
    assert 0.6 < b_rate / a_rate < 1.7, f"lot B is skewed at temperate sites: {b_rate / a_rate:.2f}x"
