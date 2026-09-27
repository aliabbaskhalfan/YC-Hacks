#!/usr/bin/env python3
"""Check the planted patterns survive into what fleet intelligence reports.

This is the dataset's own test, and it deliberately runs the *real* miner
(`server.fleet.intel`) rather than a private copy of the same arithmetic —
a dataset whose patterns only a bespoke checker can find would prove
nothing. It reads incidents and the registry, never
data/synthetic/ground_truth.json, so a pass means the patterns are genuinely
in the incident counts.

Usage:
    python -m sim.synth.verify_patterns
"""

from __future__ import annotations

import argparse
from pathlib import Path

from server.fleet.intel import (
    MIN_INCIDENTS,
    MIN_RATIO,
    build_flags,
    load_rows,
    mine_patterns,
    three_strike_clusters,
)
from server.fleet.registry import Registry

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INCIDENTS = REPO_ROOT / "data" / "synthetic" / "incidents.jsonl"

# What the generator planted, and the shape each should surface as. Written
# out here so a pattern that quietly stops being discoverable fails loudly.
EXPECTED = (
    ("knee actuators, lot B at hot sites", "calf.motor", "supplier_lot+ambient_class", "B@hot"),
    ("hip bolts fixed without threadlocker", "hip.mount_bolts", "fix_used", "without:apply threadlocker"),
    ("foot pads at phoenix-solar", "foot.pad", "site", "phoenix-solar"),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--incidents", type=Path, default=DEFAULT_INCIDENTS)
    args = parser.parse_args()

    registry = Registry.load()
    rows = load_rows(registry, args.incidents)
    print(f"{len(rows)} incidents, {len(registry.units)} units, {len(registry.sites)} sites")
    print(f"(flag threshold: ratio > {MIN_RATIO}x with at least {MIN_INCIDENTS} incidents)\n")

    # Mine with the bar dropped, so a pattern that exists but sits under the
    # flag threshold is reported as such rather than silently missing.
    found = {
        (cell.part_class, cell.dimension, cell.key): cell
        for cell in mine_patterns(rows, registry, min_ratio=1.0, min_incidents=1)
    }

    print("Planted patterns:")
    missing = 0
    for label, cls, dimension, key in EXPECTED:
        cell = found.get((cls, dimension, key))
        if cell is None:
            print(f"    MISSING  {label}")
            missing += 1
            continue
        verdict = "FLAG" if cell.flags else f"below the {MIN_RATIO}x bar"
        print(f"    {verdict:18s} {label}: {cell.ratio:.2f}x on {cell.incidents} incidents")

    print("\nEverything the miner flags on its own:")
    for cell in mine_patterns(rows, registry):
        print(f"    {cell.describe()}")

    flags = build_flags(rows, registry)
    patterns = [flag for flag in flags if flag.kind == "pattern"]
    strikes = three_strike_clusters(rows)
    print(f"\nFlags raised: {len(patterns)} pattern, {len(strikes)} three-strike")
    for flag in patterns:
        print(f"    {flag.flag_id}\n        {flag.summary}")

    if missing:
        raise SystemExit(f"{missing} planted pattern(s) no longer present in the data")


if __name__ == "__main__":
    main()
