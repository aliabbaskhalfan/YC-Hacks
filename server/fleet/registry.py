"""Read access to the part and fleet registries (BUILD_SPEC.md Sections 4.3, 4.4).

One loader shared by the synthetic generator and by fleet intelligence, so
both join incidents against exactly the same observable fleet facts — the
supplier lot on a given unit's motor, a site's ambient class — rather than
each keeping its own copy of the rules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

DEFAULT_REGISTRY_DIR = Path(__file__).resolve().parents[2] / "data" / "registry"


@dataclass(frozen=True)
class Registry:
    parts: dict[str, dict[str, Any]]
    units: dict[str, dict[str, Any]]
    sites: dict[str, dict[str, Any]]

    @classmethod
    def load(cls, registry_dir: Path | None = None) -> "Registry":
        root = registry_dir or DEFAULT_REGISTRY_DIR
        parts_path = root / "parts.json"
        fleet_path = root / "fleet.json"
        if not parts_path.exists() or not fleet_path.exists():
            raise FileNotFoundError(
                f"registry missing under {root} — run `python -m sim.synth.build_registry` first"
            )
        parts = json.loads(parts_path.read_text())
        fleet = json.loads(fleet_path.read_text())
        return cls(
            parts={part["part_id"]: part for part in parts},
            units={unit["unit_id"]: unit for unit in fleet["units"]},
            sites={site["site_id"]: site for site in fleet["sites"]},
        )

    # ---- parts ----

    def part(self, part_id: str) -> dict[str, Any]:
        try:
            return self.parts[part_id]
        except KeyError:
            raise KeyError(f"unknown part_id: {part_id}") from None

    def part_name(self, part_id: str) -> str:
        part = self.parts.get(part_id)
        return part["name"] if part else part_id

    def mesh_nodes(self, part_id: str) -> list[str]:
        part = self.parts.get(part_id)
        return list(part.get("mesh_nodes", [])) if part else []

    @cached_property
    def motor_part_ids(self) -> tuple[str, ...]:
        return tuple(pid for pid, part in self.parts.items() if part["kind"] == "motor")

    # ---- units ----

    def unit(self, unit_id: str) -> dict[str, Any]:
        try:
            return self.units[unit_id]
        except KeyError:
            raise KeyError(f"unknown unit_id: {unit_id}") from None

    def site_of(self, unit_id: str) -> str:
        return self.unit(unit_id)["site"]

    def ambient_class(self, unit_id: str) -> str:
        return self.unit(unit_id)["ambient_class"]

    def supplier_lot(self, unit_id: str, part_id: str) -> str | None:
        """The lot fitted to this unit's copy of a part, or None if untracked.

        Only motors carry per-unit lots; asking about a foot pad is a normal
        question with a legitimately empty answer, not an error.
        """
        return self.unit(unit_id).get("supplier_lot", {}).get(part_id)

    def units_at(self, site_id: str) -> list[str]:
        return [uid for uid, unit in self.units.items() if unit["site"] == site_id]

    def units_in(self, ambient_class: str) -> list[str]:
        return [uid for uid, unit in self.units.items() if unit["ambient_class"] == ambient_class]
