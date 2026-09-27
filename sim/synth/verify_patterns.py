#!/usr/bin/env python3
"""Check that the planted patterns are recoverable from the data alone.

This is the dataset's own test, not the product feature: fleet intelligence
proper lives in server/fleet/intel.py (Section 9). It deliberately reads
only what a miner is allowed to see — incidents.jsonl plus the fleet
registry — and never ground_truth.json, so a pass means the patterns really
are in the incident counts rather than in an answer key.

Verdicts use Section 9.3's flag thresholds: a cell needs a rate ratio above
2.5 and at least 8 incidents behind it.

Usage:
    python -m sim.synth.verify_patterns
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from server.fleet.registry import Registry

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = REPO_ROOT / "data" / "synthetic"

RATIO_THRESHOLD = 2.5
MIN_INCIDENTS = 8
LEGS = ("fl", "fr", "rl", "rr")
KNEE_FAULTS = {"knee_motor_weak", "knee_motor_overheat"}


def load_incidents(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _verdict(ratio: float, incidents: int) -> str:
    ok = ratio > RATIO_THRESHOLD and incidents >= MIN_INCIDENTS
    return f"{'FLAG' if ok else 'no flag'} (ratio {ratio:.2f}x, n={incidents})"


def knee_lot_pattern(incidents: list[dict], registry: Registry) -> str:
    """Knee failures per calf motor at risk, split by supplier lot x ambient."""
    exposure: dict[tuple[str, str], int] = {}
    for unit_id, unit in registry.units.items():
        for leg in LEGS:
            lot = registry.supplier_lot(unit_id, f"{leg}.calf.motor")
            key = (lot or "unknown", unit["ambient_class"])
            exposure[key] = exposure.get(key, 0) + 1

    counts: dict[tuple[str, str], int] = {}
    for incident in incidents:
        if incident["fault_id"] not in KNEE_FAULTS:
            continue
        unit = registry.unit(incident["unit_id"])
        lot = registry.supplier_lot(incident["unit_id"], incident["part_id"]) or "unknown"
        key = (lot, unit["ambient_class"])
        counts[key] = counts.get(key, 0) + 1

    lines = ["Knee actuator failures per motor at risk, by supplier lot x ambient:"]
    for key in sorted(exposure):
        lot, ambient = key
        motors, hits = exposure[key], counts.get(key, 0)
        lines.append(f"    lot {lot} / {ambient:9s}  {hits:4d} incidents / {motors:3d} motors = {hits / motors:.3f}")

    target = ("B", "hot")
    target_rate = counts.get(target, 0) / exposure[target]
    rest_hits = sum(v for k, v in counts.items() if k != target)
    rest_motors = sum(v for k, v in exposure.items() if k != target)
    rest_rate = rest_hits / rest_motors
    ratio = target_rate / rest_rate if rest_rate else float("inf")

    lines.append(f"  lot B at hot sites vs all other knee actuators: {_verdict(ratio, counts.get(target, 0))}")
    return "\n".join(lines)


def footpad_site_pattern(incidents: list[dict], registry: Registry) -> str:
    """Foot pad failures per unit, by site."""
    exposure: dict[str, int] = {}
    for unit in registry.units.values():
        exposure[unit["site"]] = exposure.get(unit["site"], 0) + 1

    counts: dict[str, int] = {}
    for incident in incidents:
        if incident["fault_id"] != "foot_pad_worn":
            continue
        counts[incident["site"]] = counts.get(incident["site"], 0) + 1

    rates = {site: counts.get(site, 0) / units for site, units in exposure.items()}
    worst = max(rates, key=rates.get)
    rest_hits = sum(v for k, v in counts.items() if k != worst)
    rest_units = sum(v for k, v in exposure.items() if k != worst)
    ratio = rates[worst] / (rest_hits / rest_units) if rest_units and rest_hits else float("inf")

    lines = ["Foot pad failures per unit, by site:"]
    for site in sorted(rates, key=rates.get, reverse=True):
        lines.append(f"    {site:18s}  {counts.get(site, 0):4d} incidents / {exposure[site]:2d} units = {rates[site]:.3f}")
    lines.append(f"  worst site ({worst}) vs the rest: {_verdict(ratio, counts.get(worst, 0))}")
    return "\n".join(lines)


def threadlocker_pattern(incidents: list[dict]) -> str:
    """Do hip-bolt fixes that mention threadlocker hold better than those that don't?

    Read from the repair record the extractor produced, the way fleet
    intelligence would — never from the generator's own bookkeeping.
    """
    with_locker = {"total": 0, "failed": 0}
    without = {"total": 0, "failed": 0}

    for incident in incidents:
        if incident["fault_id"] != "hip_bolts_loose":
            continue
        record = incident.get("repair_record", {})
        fix = record.get("fix", {})
        blob = " ".join([*fix.get("steps", []), *fix.get("tools", []), fix.get("tip") or ""]).lower()
        bucket = with_locker if "threadlocker" in blob else without
        bucket["total"] += 1
        bucket["failed"] += 1 if incident["outcome"] == "failure" else 0

    locked_rate = with_locker["failed"] / with_locker["total"] if with_locker["total"] else 0.0
    plain_rate = without["failed"] / without["total"] if without["total"] else 0.0
    ratio = plain_rate / locked_rate if locked_rate else float("inf")

    return "\n".join(
        [
            "Hip bolt fixes, by whether the note mentions threadlocker:",
            f"    with threadlocker    {with_locker['failed']:3d} came back / {with_locker['total']:3d} fixes = {locked_rate:.3f}",
            f"    plain retighten      {without['failed']:3d} came back / {without['total']:3d} fixes = {plain_rate:.3f}",
            f"  plain vs threadlocker recurrence: {_verdict(ratio, without['total'])}",
        ]
    )


def three_strike_flags(incidents: list[dict]) -> str:
    """Section 9.3's other trigger: 3 incidents on one part_id across 3 distinct units in 7 days.

    This is the path a sub-threshold pattern can still surface through — a
    site chewing through one part faster than the rest of the fleet shows up
    as clustered strikes even when its rate ratio never clears 2.5x.
    """
    by_part: dict[str, list[tuple[datetime, str, str]]] = {}
    for incident in incidents:
        by_part.setdefault(incident["part_id"], []).append(
            (datetime.fromisoformat(incident["timestamp"]), incident["unit_id"], incident["site"])
        )

    flags: list[tuple[str, datetime, int, str]] = []
    for part_id, entries in by_part.items():
        entries.sort()
        for index, (start, _, _) in enumerate(entries):
            window = [e for e in entries[index:] if e[0] - start <= timedelta(days=7)]
            if len({unit for _, unit, _ in window}) >= 3:
                sites = {site for _, _, site in window}
                dominant = max(sites, key=lambda s: sum(1 for _, _, site in window if site == s))
                flags.append((part_id, start, len(window), dominant))
                break

    lines = [f"Three-strike flags (same part_id, 3+ distinct units, 7 days): {len(flags)} part(s)"]
    for part_id, start, size, dominant in sorted(flags):
        lines.append(f"    {part_id:22s} first cluster {start.date()}  {size} incidents, mostly {dominant}")
    if not flags:
        lines.append("    none")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--registry", type=Path, default=None)
    args = parser.parse_args()

    registry = Registry.load(args.registry)
    incidents = load_incidents(args.data / "incidents.jsonl")

    print(f"{len(incidents)} incidents, {len(registry.units)} units, {len(registry.sites)} sites")
    print(f"(flag threshold: ratio > {RATIO_THRESHOLD}x with at least {MIN_INCIDENTS} incidents)\n")
    print(knee_lot_pattern(incidents, registry), "\n")
    print(footpad_site_pattern(incidents, registry), "\n")
    print(threadlocker_pattern(incidents), "\n")
    print(three_strike_flags(incidents))


if __name__ == "__main__":
    main()
