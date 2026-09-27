#!/usr/bin/env python3
"""Build the part and fleet registries (BUILD_SPEC.md Sections 4.3, 4.4).

Both files are generated rather than hand-written: parts.json follows
mechanically from the Section 4.2 naming scheme, and fleet.json needs 480
seeded per-motor supplier-lot assignments that must stay reproducible.

These two files are the *observable* fleet facts — the ones fleet
intelligence is allowed to join incidents against when it mines for patterns
(Section 9.2 mines supplier_lot, site and ambient_class). Anything that would
hand over a hidden root cause outright, such as a site's abrasive surface,
belongs in data/synthetic/ground_truth.json instead, not here.

Usage:
    python -m sim.synth.build_registry [--seed 7] [--units 40]
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_DIR = REPO_ROOT / "data" / "registry"

LEGS = ("fl", "fr", "rl", "rr")
LEG_NAMES = {"fl": "Front-left", "fr": "Front-right", "rl": "Rear-left", "rr": "Rear-right"}
# Section 4.1: feet are geoms on the calf bodies, so a foot pad highlights the calf.
LEG_NODES = {"fl": "FL", "fr": "FR", "rl": "RL", "rr": "RR"}

SUPPLIER_LOTS = ("A", "B", "C")

SITES = [
    {"site_id": "austin-refinery", "ambient_class": "hot", "region": "TX"},
    {"site_id": "phoenix-solar", "ambient_class": "hot", "region": "AZ"},
    {"site_id": "houston-port", "ambient_class": "hot", "region": "TX"},
    {"site_id": "pittsburgh-plant", "ambient_class": "temperate", "region": "PA"},
    {"site_id": "denver-dc", "ambient_class": "temperate", "region": "CO"},
    {"site_id": "sf-lab", "ambient_class": "temperate", "region": "CA"},
]
# 40 units over 6 sites; hot sites carry a little more of the fleet.
SITE_UNIT_COUNTS = {
    "phoenix-solar": 8,
    "austin-refinery": 7,
    "houston-port": 7,
    "pittsburgh-plant": 6,
    "denver-dc": 6,
    "sf-lab": 6,
}


def motor_part_ids() -> list[str]:
    return [f"{leg}.{seg}.motor" for leg in LEGS for seg in ("hip", "thigh", "calf")]


def build_parts() -> list[dict]:
    """Every part_id in Section 4.2, with the mesh nodes the viewer highlights."""
    parts: list[dict] = []

    for leg in LEGS:
        node = LEG_NODES[leg]
        leg_name = LEG_NAMES[leg]
        parts.extend(
            [
                {
                    "part_id": f"{leg}.hip.motor",
                    "name": f"{leg_name} hip abduction actuator",
                    "kind": "motor",
                    "parent": f"{leg}.leg",
                    "mesh_nodes": [f"{node}_hip"],
                    "spec": "hip abduction actuator (sim value)",
                    "supplier_lots": list(SUPPLIER_LOTS),
                },
                {
                    "part_id": f"{leg}.thigh.motor",
                    "name": f"{leg_name} thigh actuator",
                    "kind": "motor",
                    "parent": f"{leg}.leg",
                    "mesh_nodes": [f"{node}_thigh"],
                    "spec": "thigh joint actuator (sim value)",
                    "supplier_lots": list(SUPPLIER_LOTS),
                },
                {
                    # The thigh motor sits on the hip body, so its cover highlights (and collides in sim) there.
                    "part_id": f"{leg}.thigh.cover",
                    "name": f"{leg_name} thigh motor cover",
                    "kind": "shell",
                    "parent": f"{leg}.leg",
                    "mesh_nodes": [f"{node}_hip"],
                    "spec": "plastic cover over the thigh actuator, 4x M3 screws (sim value)",
                },
                {
                    "part_id": f"{leg}.calf.motor",
                    "name": f"{leg_name} knee actuator",
                    "kind": "motor",
                    "parent": f"{leg}.leg",
                    "mesh_nodes": [f"{node}_calf"],
                    "spec": "knee joint actuator (sim value)",
                    "supplier_lots": list(SUPPLIER_LOTS),
                },
                {
                    "part_id": f"{leg}.thigh.link",
                    "name": f"{leg_name} thigh link",
                    "kind": "link",
                    "parent": f"{leg}.leg",
                    "mesh_nodes": [f"{node}_thigh"],
                    "spec": "structural thigh link (sim value)",
                },
                {
                    "part_id": f"{leg}.calf.link",
                    "name": f"{leg_name} calf link",
                    "kind": "link",
                    "parent": f"{leg}.leg",
                    "mesh_nodes": [f"{node}_calf"],
                    "spec": "structural calf link (sim value)",
                },
                {
                    "part_id": f"{leg}.foot.pad",
                    "name": f"{leg_name} foot pad",
                    "kind": "wear_part",
                    "parent": f"{leg}.leg",
                    "mesh_nodes": [f"{node}_calf"],
                    "spec": "rubber foot pad (sim value)",
                },
                {
                    "part_id": f"{leg}.hip.mount_bolts",
                    "name": f"{leg_name} hip mount bolts",
                    "kind": "fastener",
                    "parent": f"{leg}.leg",
                    "mesh_nodes": [f"{node}_hip"],
                    "spec": "hip mount bolt set (sim value)",
                },
                {
                    "part_id": f"{leg}.leg.harness",
                    "name": f"{leg_name} leg cable harness",
                    "kind": "harness",
                    "parent": f"{leg}.leg",
                    "mesh_nodes": [f"{node}_hip", f"{node}_thigh", f"{node}_calf"],
                    "spec": "per-leg cable harness (sim value)",
                },
            ]
        )

    parts.extend(
        [
            {
                "part_id": "base.battery",
                "name": "Battery pack",
                "kind": "battery",
                "parent": "base",
                "mesh_nodes": ["base"],
                "spec": "main battery pack (sim value)",
            },
            {
                "part_id": "base.imu",
                "name": "IMU",
                "kind": "sensor",
                "parent": "base",
                "mesh_nodes": ["base"],
                "spec": "body inertial measurement unit (sim value)",
            },
            {
                "part_id": "base.shell",
                "name": "Body shell",
                "kind": "shell",
                "parent": "base",
                "mesh_nodes": ["base"],
                "spec": "body shell (sim value)",
            },
        ]
    )
    return parts


def build_fleet(rng: random.Random, unit_count: int, window_end: date) -> dict:
    site_slots: list[str] = []
    for site_id, count in SITE_UNIT_COUNTS.items():
        site_slots.extend([site_id] * count)
    # Trim or extend if --units differs from the 40 the counts add up to.
    while len(site_slots) < unit_count:
        site_slots.append(SITES[len(site_slots) % len(SITES)]["site_id"])
    site_slots = site_slots[:unit_count]
    rng.shuffle(site_slots)

    ambient_by_site = {site["site_id"]: site["ambient_class"] for site in SITES}
    motors = motor_part_ids()

    units = []
    for index, site_id in enumerate(site_slots, start=1):
        unit_id = f"go2-{index:02d}"
        # Commissioned 4-24 months before the window ends, so units have
        # meaningfully different ages and duty histories.
        commissioned = window_end - timedelta(days=rng.randint(120, 730))
        units.append(
            {
                "unit_id": unit_id,
                "site": site_id,
                "ambient_class": ambient_by_site[site_id],
                "commissioned_at": commissioned.isoformat(),
                # Some robots simply work harder; this is observable fleet
                # metadata, and it is deliberately uncorrelated with the
                # hidden patterns so it acts as honest confounding noise.
                "usage_factor": round(rng.uniform(0.75, 1.35), 3),
                "supplier_lot": {motor: rng.choice(SUPPLIER_LOTS) for motor in motors},
            }
        )

    return {"sites": SITES, "units": units}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--units", type=int, default=40)
    parser.add_argument("--window-end", default=None, help="ISO date the 90-day window ends (default: today)")
    parser.add_argument("--out", type=Path, default=REGISTRY_DIR)
    args = parser.parse_args()

    window_end = date.fromisoformat(args.window_end) if args.window_end else date.today()
    rng = random.Random(args.seed)

    parts = build_parts()
    fleet = build_fleet(rng, args.units, window_end)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "parts.json").write_text(json.dumps(parts, indent=2) + "\n")
    (args.out / "fleet.json").write_text(json.dumps(fleet, indent=2) + "\n")

    print(f"wrote {args.out / 'parts.json'}  ({len(parts)} parts)")
    print(f"wrote {args.out / 'fleet.json'}  ({len(fleet['units'])} units, {len(fleet['sites'])} sites)")


if __name__ == "__main__":
    main()
