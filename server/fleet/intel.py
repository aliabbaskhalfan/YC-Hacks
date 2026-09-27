"""Fleet intelligence: counters, pattern mining, and flags (BUILD_SPEC.md Section 9).

Nothing here knows what the planted patterns are. It counts incidents,
divides by how many parts were actually at risk, and reports cells whose
rate stands out — so a pattern surfaces because it is in the data, not
because it was hard-coded. `data/synthetic/ground_truth.json` exists to
check this afterwards and is never read.

Rates are always per part *at risk*, never raw counts. A site with eight
robots will out-count a site with six on volume alone; only exposure-adjusted
rates say anything. Mining works per part class ("calf.motor" across all four
legs) because that is the unit an engineer reasons about — "knee actuators",
not "the front-right one specifically".

Section 9.2 names supplier_lot, site, ambient_class and "fix used" as
dimensions. The lot x ambient interaction is mined as well: a lot that only
fails in the heat is invisible in either margin alone, and that interaction
is exactly the shape of the failure this fleet has.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from server.fleet.fix_signature import canonical_steps
from server.fleet.registry import Registry

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INCIDENTS = REPO_ROOT / "data" / "synthetic" / "incidents.jsonl"

MIN_RATIO = 2.5  # Section 9.3
MIN_INCIDENTS = 8
STRIKE_WINDOW_DAYS = 7
STRIKE_MIN_UNITS = 3

LEGS = ("fl", "fr", "rl", "rr")


def part_class(part_id: str) -> str:
    """"fr.calf.motor" -> "calf.motor"; base parts keep their own name."""
    head, _, tail = part_id.partition(".")
    return tail if head in LEGS else part_id


# --------------------------------------------------------------------------- #
# Incidents
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class IncidentRow:
    incident_id: str
    unit_id: str
    part_id: str
    part_class: str
    site: str
    ambient_class: str
    supplier_lot: str | None
    fault_id: str | None
    at: datetime
    outcome: str  # success | failure | open
    is_recurrence: bool
    fix_actions: tuple[str, ...]
    source: str


def _row_from_synthetic(raw: dict[str, Any], registry: Registry) -> IncidentRow:
    record = raw.get("repair_record") or {}
    fix = record.get("fix") or {}
    # Steps first so the action order survives, then tools and the tip: the
    # extractor files "threadlocker" under tools, and only one of the ways a
    # tech says it ("applied threadlocker") also lands as a step.
    steps = [*fix.get("steps", []), *fix.get("tools", []), *([fix["tip"]] if fix.get("tip") else [])]
    return IncidentRow(
        incident_id=raw["incident_id"],
        unit_id=raw["unit_id"],
        part_id=raw["part_id"],
        part_class=part_class(raw["part_id"]),
        site=raw["site"],
        ambient_class=raw["ambient_class"],
        supplier_lot=registry.supplier_lot(raw["unit_id"], raw["part_id"]),
        fault_id=raw["fault_id"],
        at=datetime.fromisoformat(raw["timestamp"]),
        outcome=raw["outcome"],
        is_recurrence=bool(raw.get("recurrence_of")),
        fix_actions=tuple(canonical_steps(steps)),
        source="synthetic",
    )


def _rows_from_live(path: Path, registry: Registry) -> list[IncidentRow]:
    """Live incidents raised on stage, which never appear in the synthetic corpus."""
    if not path.exists():
        return []
    try:
        live = json.loads(path.read_text())
    except (OSError, ValueError):
        return []

    rows: list[IncidentRow] = []
    for raw in live.values():
        unit_id = raw.get("unit_id")
        part_id = raw.get("part_id")
        if not unit_id or not part_id or unit_id not in registry.units:
            continue
        unit = registry.unit(unit_id)
        status = raw.get("status", "red")
        rows.append(
            IncidentRow(
                incident_id=raw["incident_id"],
                unit_id=unit_id,
                part_id=part_id,
                part_class=part_class(part_id),
                site=raw.get("site") or unit["site"],
                ambient_class=unit["ambient_class"],
                supplier_lot=registry.supplier_lot(unit_id, part_id),
                # A live anomaly carries a signal, not a fault id — only the
                # sim knows which fault was injected.
                fault_id=None,
                at=datetime.now().astimezone(),
                outcome="success" if status == "fixed" else "open",
                is_recurrence=False,
                fix_actions=(),
                source="live",
            )
        )
    return rows


def load_rows(
    registry: Registry,
    incidents_path: Path = DEFAULT_INCIDENTS,
    live_path: Path | None = None,
) -> list[IncidentRow]:
    rows: list[IncidentRow] = []
    if incidents_path.exists():
        for line in incidents_path.read_text().splitlines():
            if line.strip():
                rows.append(_row_from_synthetic(json.loads(line), registry))
    if live_path:
        rows.extend(_rows_from_live(live_path, registry))
    return sorted(rows, key=lambda row: row.at)


# --------------------------------------------------------------------------- #
# 9.1 Counters
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Metrics:
    incidents: int
    distinct_units: int
    recurrences: int
    recurrence_rate: float
    mtbf_days: float | None
    success_rate: float | None


def _metrics(rows: list[IncidentRow]) -> Metrics:
    resolved = [row for row in rows if row.outcome in {"success", "failure"}]
    gaps: list[float] = []
    by_unit: dict[str, list[datetime]] = defaultdict(list)
    for row in rows:
        by_unit[row.unit_id].append(row.at)
    for times in by_unit.values():
        times.sort()
        gaps.extend((b - a).total_seconds() / 86400 for a, b in zip(times, times[1:]))

    return Metrics(
        incidents=len(rows),
        distinct_units=len({row.unit_id for row in rows}),
        recurrences=sum(1 for row in rows if row.is_recurrence),
        recurrence_rate=round(sum(1 for row in rows if row.is_recurrence) / len(rows), 3) if rows else 0.0,
        mtbf_days=round(statistics.fmean(gaps), 2) if gaps else None,
        success_rate=(
            round(sum(1 for row in resolved if row.outcome == "success") / len(resolved), 3) if resolved else None
        ),
    )


def counters(rows: list[IncidentRow]) -> dict[str, dict[str, Metrics]]:
    """Per part_id, site, supplier lot and fault type (Section 9.1)."""
    dimensions: dict[str, dict[str, list[IncidentRow]]] = {
        "part_id": defaultdict(list),
        "part_class": defaultdict(list),
        "site": defaultdict(list),
        "supplier_lot": defaultdict(list),
        "fault_id": defaultdict(list),
    }
    for row in rows:
        dimensions["part_id"][row.part_id].append(row)
        dimensions["part_class"][row.part_class].append(row)
        dimensions["site"][row.site].append(row)
        if row.supplier_lot:
            dimensions["supplier_lot"][row.supplier_lot].append(row)
        if row.fault_id:
            dimensions["fault_id"][row.fault_id].append(row)

    return {
        name: {key: _metrics(group) for key, group in sorted(buckets.items())}
        for name, buckets in dimensions.items()
    }


# --------------------------------------------------------------------------- #
# 9.2 Pattern mining
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PartInstance:
    unit_id: str
    part_id: str
    supplier_lot: str | None
    site: str
    ambient_class: str


def part_instances(registry: Registry, cls: str) -> list[PartInstance]:
    """Every copy of a part class in the fleet — the denominator for a rate."""
    instances: list[PartInstance] = []
    for unit_id, unit in registry.units.items():
        candidates = [f"{leg}.{cls}" for leg in LEGS] if not cls.startswith("base.") else [cls]
        for part_id in candidates:
            if part_id not in registry.parts:
                continue
            instances.append(
                PartInstance(
                    unit_id=unit_id,
                    part_id=part_id,
                    supplier_lot=registry.supplier_lot(unit_id, part_id),
                    site=unit["site"],
                    ambient_class=unit["ambient_class"],
                )
            )
    return instances


@dataclass(frozen=True)
class PatternCell:
    part_class: str
    dimension: str
    key: str
    incidents: int
    exposure: int
    rate: float
    baseline_rate: float
    ratio: float
    units: tuple[str, ...]
    incident_ids: tuple[str, ...]

    @property
    def flags(self) -> bool:
        return self.ratio > MIN_RATIO and self.incidents >= MIN_INCIDENTS

    def describe(self) -> str:
        return (
            f"{self.part_class} where {self.dimension}={self.key}: "
            f"{self.incidents} incidents across {self.exposure} parts at risk "
            f"({self.rate:.3f} per part) vs {self.baseline_rate:.3f} elsewhere — {self.ratio:.2f}x"
        )


_DIMENSIONS: dict[str, Any] = {
    "supplier_lot": lambda inst: inst.supplier_lot,
    "site": lambda inst: inst.site,
    "ambient_class": lambda inst: inst.ambient_class,
    # The interaction, because a lot that only fails in the heat is invisible
    # in either margin on its own.
    "supplier_lot+ambient_class": lambda inst: (
        f"{inst.supplier_lot}@{inst.ambient_class}" if inst.supplier_lot else None
    ),
}


def mine_patterns(
    rows: Iterable[IncidentRow],
    registry: Registry,
    *,
    min_ratio: float = MIN_RATIO,
    min_incidents: int = MIN_INCIDENTS,
) -> list[PatternCell]:
    rows = list(rows)
    cells: list[PatternCell] = []

    by_class: dict[str, list[IncidentRow]] = defaultdict(list)
    for row in rows:
        by_class[row.part_class].append(row)

    for cls, class_rows in by_class.items():
        instances = part_instances(registry, cls)
        if not instances:
            continue
        instance_lot = {(inst.unit_id, inst.part_id): inst for inst in instances}

        for dimension, keyfn in _DIMENSIONS.items():
            exposure_by_key: dict[str, int] = defaultdict(int)
            for inst in instances:
                key = keyfn(inst)
                if key is not None:
                    exposure_by_key[key] += 1

            hits_by_key: dict[str, list[IncidentRow]] = defaultdict(list)
            for row in class_rows:
                inst = instance_lot.get((row.unit_id, row.part_id))
                key = keyfn(inst) if inst else None
                if key is not None:
                    hits_by_key[key].append(row)

            total_hits = sum(len(group) for group in hits_by_key.values())
            total_exposure = sum(exposure_by_key.values())

            for key, exposure in exposure_by_key.items():
                hits = hits_by_key.get(key, [])
                rest_hits = total_hits - len(hits)
                rest_exposure = total_exposure - exposure
                if not exposure or not rest_exposure or not rest_hits:
                    continue
                rate = len(hits) / exposure
                baseline = rest_hits / rest_exposure
                cells.append(
                    PatternCell(
                        part_class=cls,
                        dimension=dimension,
                        key=key,
                        incidents=len(hits),
                        exposure=exposure,
                        rate=round(rate, 4),
                        baseline_rate=round(baseline, 4),
                        ratio=round(rate / baseline, 3) if baseline else float("inf"),
                        units=tuple(sorted({row.unit_id for row in hits})),
                        incident_ids=tuple(row.incident_id for row in hits),
                    )
                )

        cells.extend(_mine_fix_used(cls, class_rows, min_incidents))

    return sorted(
        [cell for cell in cells if cell.ratio > min_ratio and cell.incidents >= min_incidents],
        key=lambda cell: cell.ratio,
        reverse=True,
    )


def _mine_fix_used(cls: str, class_rows: list[IncidentRow], min_incidents: int) -> list[PatternCell]:
    """Section 9.2's "fix used" dimension: which repairs actually hold.

    Exposure is fixes rather than parts, and the cell counts the ones that
    came back — so the ratio reads "skipping this fails N times as often".
    """
    resolved = [row for row in class_rows if row.outcome in {"success", "failure"}]
    actions = {action for row in resolved for action in row.fix_actions}
    cells: list[PatternCell] = []

    for action in sorted(actions):
        with_action = [row for row in resolved if action in row.fix_actions]
        without = [row for row in resolved if action not in row.fix_actions]
        if len(with_action) < min_incidents or len(without) < min_incidents:
            continue
        failed_with = sum(1 for row in with_action if row.outcome == "failure")
        failed_without = sum(1 for row in without if row.outcome == "failure")
        rate_with = failed_with / len(with_action)
        rate_without = failed_without / len(without)
        if not rate_with or not failed_without:
            continue
        cells.append(
            PatternCell(
                part_class=cls,
                dimension="fix_used",
                key=f"without:{action}",
                incidents=failed_without,
                exposure=len(without),
                rate=round(rate_without, 4),
                baseline_rate=round(rate_with, 4),
                ratio=round(rate_without / rate_with, 3),
                units=tuple(sorted({row.unit_id for row in without if row.outcome == "failure"})),
                incident_ids=tuple(row.incident_id for row in without if row.outcome == "failure"),
            )
        )
    return cells


# --------------------------------------------------------------------------- #
# 9.3 Flags
# --------------------------------------------------------------------------- #

# Which procedure step a finding about a part class should change.
PART_PROCEDURE: dict[str, tuple[str, int]] = {
    "calf.motor": ("replace-knee-motor", 4),
    "calf.link": ("replace-knee-motor", 4),
    "foot.pad": ("replace-foot-pad", 2),
    "hip.mount_bolts": ("retorque-hip-mount", 2),
    "hip.motor": ("retorque-hip-mount", 2),
    "thigh.motor": ("recalibrate-encoders", 1),
    "thigh.link": ("recalibrate-encoders", 1),
    "leg.harness": ("replace-knee-motor", 3),
    "base.battery": ("replace-knee-motor", 1),
    "base.imu": ("recalibrate-encoders", 3),
}

OVERLAP_LIMIT = 0.6  # two cells over the same incidents are one finding


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value.lower()).strip("-").replace("--", "-")


@dataclass
class Flag:
    flag_id: str
    part_id: str
    part_class: str
    kind: str  # "pattern" | "three_strike"
    summary: str
    units: list[str]
    evidence_notes: list[str]
    suggested_change: str
    status: str = "open"
    procedure_id: str | None = None
    step_id: int | None = None
    step_addition: str | None = None
    significance: float = 0.0
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "flag_id": self.flag_id,
            "part_id": self.part_id,
            "part_class": self.part_class,
            "kind": self.kind,
            "summary": self.summary,
            "units": self.units,
            "evidence_notes": self.evidence_notes,
            "suggested_change": self.suggested_change,
            "status": self.status,
            "procedure_id": self.procedure_id,
            "step_id": self.step_id,
            "step_addition": self.step_addition,
            "significance": round(self.significance, 3),
            "detail": self.detail,
        }


def _change_for(cell: PatternCell) -> tuple[str, str]:
    """(suggested_change, step_addition) for a mined cell."""
    procedure_id, _ = PART_PROCEDURE.get(cell.part_class, ("", 0))
    if cell.dimension.startswith("supplier_lot"):
        lot = cell.key.split("@")[0]
        where = " at hot sites" if cell.key.endswith("@hot") else ""
        return (
            f"Add a supplier-lot check to {procedure_id or 'the procedure'}; "
            f"quarantine lot {lot}{where}.",
            f"Check the part's lot label. If it is lot {lot}{where}, fit a different lot.",
        )
    if cell.dimension == "fix_used":
        action = cell.key.split(":", 1)[1]
        return (
            f"Make '{action}' mandatory in {procedure_id or 'the procedure'} — "
            f"fixes that skip it come back {cell.ratio:.1f}x as often.",
            f"Always {action} before closing this step.",
        )
    if cell.dimension == "site":
        return (
            f"Shorten the inspection interval for {cell.part_class} at {cell.key}.",
            f"At {cell.key}, inspect this part every visit — it fails {cell.ratio:.1f}x as often here.",
        )
    return (
        f"Review {cell.part_class} where {cell.dimension} is {cell.key}.",
        f"Note: {cell.part_class} fails {cell.ratio:.1f}x as often when {cell.dimension} is {cell.key}.",
    )


def _summarise(cell: PatternCell) -> str:
    if cell.dimension == "fix_used":
        action = cell.key.split(":", 1)[1]
        return (
            f"{cell.part_class} fixes that skip '{action}' come back {cell.ratio:.1f}x as often "
            f"({cell.incidents} of {cell.exposure} such fixes failed, vs {cell.baseline_rate:.0%} when it is used)."
        )
    where = f"{cell.dimension.replace('+', ' and ')} {cell.key}"
    return (
        f"{cell.part_class} fails {cell.ratio:.1f}x more often where {where}: "
        f"{cell.incidents} incidents across {cell.exposure} parts at risk "
        f"({cell.rate:.2f} per part, vs {cell.baseline_rate:.2f} elsewhere)."
    )


def _dedupe(cells: list[PatternCell]) -> list[PatternCell]:
    """One finding per underlying set of incidents.

    The lot-B interaction, plain lot B, and the hot site that happens to hold
    most lot-B parts are three views of one problem. Keeping the strongest
    ratio stops the Engineering tab reporting it three times.
    """
    kept: list[PatternCell] = []
    for cell in cells:
        ids = set(cell.incident_ids)
        if any(
            other.part_class == cell.part_class
            and len(ids & set(other.incident_ids)) / max(1, min(len(ids), len(other.incident_ids))) > OVERLAP_LIMIT
            for other in kept
        ):
            continue
        kept.append(cell)
    return kept


def three_strike_clusters(
    rows: list[IncidentRow],
    *,
    window_days: int = STRIKE_WINDOW_DAYS,
    min_units: int = STRIKE_MIN_UNITS,
) -> list[dict[str, Any]]:
    """3 incidents on one part_id across 3 distinct units inside a week."""
    by_part: dict[str, list[IncidentRow]] = defaultdict(list)
    for row in rows:
        by_part[row.part_id].append(row)

    clusters: list[dict[str, Any]] = []
    for part_id, entries in by_part.items():
        entries.sort(key=lambda row: row.at)
        span_days = max(1.0, (entries[-1].at - entries[0].at).total_seconds() / 86400)
        expected_per_window = len(entries) * window_days / span_days
        for index, anchor in enumerate(entries):
            window = [
                row for row in entries[index:]
                if (row.at - anchor.at).total_seconds() / 86400 <= window_days
            ]
            units = sorted({row.unit_id for row in window})
            if len(units) < min_units:
                continue
            clusters.append(
                {
                    "part_id": part_id,
                    "part_class": part_class(part_id),
                    "from": anchor.at,
                    "incidents": [row.incident_id for row in window],
                    "units": units,
                    # How unusual the burst is against this part's own rate,
                    # so a genuine spike outranks routine clustering.
                    "significance": round(len(window) / max(1.0, expected_per_window), 3),
                }
            )
            break
    return sorted(clusters, key=lambda cluster: cluster["significance"], reverse=True)


def build_flags(rows: list[IncidentRow], registry: Registry, **kwargs: Any) -> list[Flag]:
    """Pattern flags and three-strike flags, ranked most significant first."""
    flags: list[Flag] = []

    for cell in _dedupe(mine_patterns(rows, registry, **kwargs)):
        suggested, addition = _change_for(cell)
        procedure_id, step_id = PART_PROCEDURE.get(cell.part_class, (None, None))
        representative = max(
            {row.part_id for row in rows if row.incident_id in set(cell.incident_ids)},
            key=lambda pid: sum(1 for row in rows if row.part_id == pid and row.incident_id in set(cell.incident_ids)),
            default=cell.part_class,
        )
        flags.append(
            Flag(
                flag_id=f"flag-{_slug(cell.part_class)}-{_slug(cell.dimension)}-{_slug(cell.key)}",
                part_id=representative,
                part_class=cell.part_class,
                kind="pattern",
                summary=_summarise(cell),
                units=list(cell.units),
                evidence_notes=list(cell.incident_ids[:8]),
                suggested_change=suggested,
                procedure_id=procedure_id,
                step_id=step_id,
                step_addition=addition,
                significance=cell.ratio,
                detail={
                    "dimension": cell.dimension,
                    "key": cell.key,
                    "incidents": cell.incidents,
                    "exposure": cell.exposure,
                    "rate": cell.rate,
                    "baseline_rate": cell.baseline_rate,
                    "ratio": cell.ratio,
                },
            )
        )

    for cluster in three_strike_clusters(rows):
        procedure_id, step_id = PART_PROCEDURE.get(cluster["part_class"], (None, None))
        flags.append(
            Flag(
                flag_id=f"flag-strike-{_slug(cluster['part_id'])}",
                part_id=cluster["part_id"],
                part_class=cluster["part_class"],
                kind="three_strike",
                summary=(
                    f"{len(cluster['incidents'])} {cluster['part_id']} failures across "
                    f"{len(cluster['units'])} units in {STRIKE_WINDOW_DAYS} days "
                    f"from {cluster['from'].date()}."
                ),
                units=cluster["units"],
                evidence_notes=cluster["incidents"][:8],
                suggested_change=f"Inspect {cluster['part_id']} across the affected units.",
                procedure_id=procedure_id,
                step_id=step_id,
                significance=cluster["significance"],
                detail={"window_days": STRIKE_WINDOW_DAYS, "from": cluster["from"].isoformat()},
            )
        )

    # Pattern findings outrank bursts: a burst is a week, a pattern is the fleet.
    return sorted(flags, key=lambda flag: (flag.kind != "pattern", -flag.significance))


class FlagStore:
    """Flag status, kept out of the mining path so re-mining never resets it."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def merge(self, flags: list[Flag]) -> list[Flag]:
        """Re-apply stored status to freshly mined flags."""
        stored = self._read()
        for flag in flags:
            saved = stored.get(flag.flag_id)
            if saved:
                flag.status = saved.get("status", flag.status)
        return flags

    def save(self, flags: list[Flag]) -> None:
        stored = self._read()
        for flag in flags:
            stored[flag.flag_id] = {**flag.to_dict(), "detail": flag.detail}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(stored, indent=2, default=str) + "\n")

    def set_status(self, flag_id: str, status: str) -> dict[str, Any]:
        stored = self._read()
        if flag_id not in stored:
            raise KeyError(flag_id)
        stored[flag_id]["status"] = status
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(stored, indent=2, default=str) + "\n")
        return stored[flag_id]

    def get(self, flag_id: str) -> dict[str, Any]:
        stored = self._read()
        if flag_id not in stored:
            raise KeyError(flag_id)
        return stored[flag_id]

    def all(self) -> list[dict[str, Any]]:
        return list(self._read().values())


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def report(rows: list[IncidentRow], registry: Registry) -> str:
    lines = [f"{len(rows)} incidents ({sum(1 for r in rows if r.source == 'live')} live)", ""]

    counts = counters(rows)
    lines.append("Top part classes:")
    for key, metrics in sorted(counts["part_class"].items(), key=lambda kv: -kv[1].incidents)[:6]:
        mtbf = f"{metrics.mtbf_days:.1f}d" if metrics.mtbf_days else "n/a"
        success = f"{metrics.success_rate:.0%}" if metrics.success_rate is not None else "n/a"
        lines.append(
            f"    {key:18s} {metrics.incidents:4d} incidents  {metrics.distinct_units:3d} units  "
            f"recur {metrics.recurrence_rate:.0%}  MTBF {mtbf:>7s}  fix holds {success}"
        )

    lines += ["", "Mined patterns (rate per part at risk):"]
    patterns = mine_patterns(rows, registry)
    if patterns:
        lines.extend(f"    {cell.describe()}" for cell in patterns)
    else:
        lines.append("    none above threshold")

    flags = build_flags(rows, registry)
    pattern_flags = [flag for flag in flags if flag.kind == "pattern"]
    strike_flags = [flag for flag in flags if flag.kind == "three_strike"]
    lines += ["", f"Flags: {len(pattern_flags)} pattern, {len(strike_flags)} three-strike"]
    for flag in pattern_flags:
        lines += [f"    [{flag.status}] {flag.flag_id}", f"        {flag.summary}", f"        -> {flag.suggested_change}"]
    return "\n".join(lines)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Fleet intelligence report (BUILD_SPEC.md Section 9)")
    parser.add_argument("--incidents", type=Path, default=DEFAULT_INCIDENTS)
    parser.add_argument("--live", type=Path, default=REPO_ROOT / "data" / "runtime" / "incidents.json")
    parser.add_argument("--save-flags", action="store_true", help="persist flags to data/runtime/flags.json")
    parser.add_argument("--json", action="store_true", help="emit flags as JSON")
    args = parser.parse_args()

    registry = Registry.load()
    rows = load_rows(registry, args.incidents, args.live)
    flags = build_flags(rows, registry)

    store = FlagStore(REPO_ROOT / "data" / "runtime" / "flags.json")
    flags = store.merge(flags)
    if args.save_flags:
        store.save(flags)

    if args.json:
        print(json.dumps([flag.to_dict() for flag in flags], indent=2, default=str))
    else:
        print(report(rows, registry))
        if args.save_flags:
            print(f"\nsaved {len(flags)} flags to {store.path}")


if __name__ == "__main__":
    main()
