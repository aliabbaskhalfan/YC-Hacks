#!/usr/bin/env python3
"""Generate the synthetic Go2 fleet incident history (BUILD_SPEC.md Section 8).

~500 incidents over 90 days across 40 units and 6 sites, carrying three
hidden root-cause patterns that fleet intelligence is supposed to *discover*
rather than be told. The patterns are therefore never written into an
incident field: they live only in the hazard rates below, so they have to be
mined back out of incident counts joined against the fleet registry. The
answer key is written to ground_truth.json purely so the discovery can be
checked; nothing in the pipeline reads it.

Incidents are drawn day by day as independent Bernoulli trials per
(unit, fault, target), not sampled to a quota, so the patterns show up as
genuine rate differences with honest sampling noise on top.

Usage:
    python -m sim.synth.generate_incidents --seed 7
    python -m sim.synth.generate_incidents --seed 7 --llm   # Claude-written notes
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from server.fleet.registry import Registry
from sim.synth import telemetry as telemetry_mod
from sim.synth.transcripts import PERSONAS, TECHS, build_note

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "data" / "synthetic"

LEGS = ("fl", "fr", "rl", "rr")

# Expected first-occurrence incidents fleet-wide over the whole window.
# Each fault's rates are normalised to hit its weight (see
# `build_daily_rates`), so a hazard multiplier decides *which units* get hit
# rather than inflating that fault's share of the fleet's workload. The
# pattern is a ratio between cells, and normalising preserves it exactly
# while keeping the fault mix controllable.
FAULT_WEIGHTS = {
    "knee_motor_weak": 50,
    "knee_motor_overheat": 46,
    "foot_pad_worn": 82,
    "hip_bolts_loose": 65,
    "encoder_drift": 55,
    "harness_intermittent": 46,
    "battery_sag": 33,
    "imu_bias": 23,
}

# part_id template per fault; "{leg}" marks a per-leg fault (Section 5.2).
FAULT_PARTS = {
    "knee_motor_weak": "{leg}.calf.motor",
    "knee_motor_overheat": "{leg}.calf.motor",
    "hip_bolts_loose": "{leg}.hip.mount_bolts",
    "foot_pad_worn": "{leg}.foot.pad",
    "encoder_drift": "{leg}.thigh.motor",
    "harness_intermittent": "{leg}.leg.harness",
    "battery_sag": "base.battery",
    "imu_bias": "base.imu",
}

# Only four procedures exist (Section 7.1), so three faults map to the
# closest step that actually touches the part: the harness to the
# disconnect-harness step, the battery to the power-down/isolate step.
FAULT_PROCEDURE = {
    "knee_motor_weak": ("replace-knee-motor", 4),
    "knee_motor_overheat": ("replace-knee-motor", 4),
    "foot_pad_worn": ("replace-foot-pad", 2),
    "hip_bolts_loose": ("retorque-hip-mount", 2),
    "encoder_drift": ("recalibrate-encoders", 1),
    "imu_bias": ("recalibrate-encoders", 3),
    "harness_intermittent": ("replace-knee-motor", 3),
    "battery_sag": ("replace-knee-motor", 1),
}

WHAT_WENT_WRONG = {
    "knee_motor_weak": "{part} is losing torque under load and cannot hold the stand pose",
    "knee_motor_overheat": "{part} is overheating under load and derating, tracking error is climbing",
    "hip_bolts_loose": "{part} is showing high-frequency oscillation consistent with a loose mount",
    "foot_pad_worn": "{part} is slipping during stance and has lost grip",
    "encoder_drift": "{part} is reporting a steady angle offset at rest",
    "harness_intermittent": "{part} is dropping torque intermittently across the whole leg",
    "battery_sag": "{part} is sagging under load and every motor's tracking error is rising together",
    "imu_bias": "{part} is reporting a body roll offset the other signals do not agree with",
}

# ---- hidden patterns (ground truth; never written into an incident) --------

KNEE_FAULTS = ("knee_motor_weak", "knee_motor_overheat")
LOT_B_HOT_MULTIPLIER = 4.0
PHOENIX_FOOTPAD_MULTIPLIER = 2.0
PHOENIX = "phoenix-solar"
# Mild, non-secret realism so "hot" is not a clean proxy for the lot-B
# interaction — heat alone lifts thermal faults a little for everyone.
HOT_THERMAL_MULTIPLIER = 1.15
HOT_THERMAL_FAULTS = ("knee_motor_overheat", "battery_sag")

# Threadlocker adoption climbs across the window; without it the bolts back
# off again and the same fault returns within a few weeks.
THREADLOCKER_START = 0.12
THREADLOCKER_END = 0.62
RECURRENCE_DAYS_BOLTS = (5, 20)
RECURRENCE_DAYS_OTHER = (7, 25)
BASE_FAILURE_RATE = 0.12
# Strong but not an oracle: a plain retighten usually backs off again and
# threadlocker usually holds, with enough exceptions that the pattern has to
# be counted out of the data rather than read off a single incident.
PLAIN_RETIGHTEN_FAILURE_RATE = 0.85
THREADLOCKER_FAILURE_RATE = 0.08
LOT_MENTION_RATE = 0.33
WRONG_GUESS_RATE = 0.18


@dataclass
class RawEvent:
    uid: int
    day_index: int
    at: datetime
    unit_id: str
    fault_id: str
    leg: str | None
    part_id: str
    forced: bool = False
    parent_uid: int | None = None
    incident_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


def hazard_multiplier(registry: Registry, unit_id: str, fault_id: str, leg: str | None) -> float:
    unit = registry.unit(unit_id)
    multiplier = float(unit["usage_factor"])

    if fault_id in HOT_THERMAL_FAULTS and unit["ambient_class"] == "hot":
        multiplier *= HOT_THERMAL_MULTIPLIER

    # Pattern 1: lot-B knee actuators cook at hot sites.
    if fault_id in KNEE_FAULTS and leg and unit["ambient_class"] == "hot":
        if registry.supplier_lot(unit_id, f"{leg}.calf.motor") == "B":
            multiplier *= LOT_B_HOT_MULTIPLIER

    # Pattern 2: phoenix-solar chews through foot pads.
    if fault_id == "foot_pad_worn" and unit["site"] == PHOENIX:
        multiplier *= PHOENIX_FOOTPAD_MULTIPLIER

    return multiplier


def build_daily_rates(registry: Registry, days: int, target: int) -> dict[tuple[str, str, str | None], float]:
    """Per-(unit, fault, leg) daily probability, scaled so the fleet total lands on target."""
    scale = target / sum(FAULT_WEIGHTS.values())
    rates: dict[tuple[str, str, str | None], float] = {}

    for fault_id, weight in FAULT_WEIGHTS.items():
        legs: tuple[str | None, ...] = LEGS if "{leg}" in FAULT_PARTS[fault_id] else (None,)
        multipliers = {
            (unit_id, fault_id, leg): hazard_multiplier(registry, unit_id, fault_id, leg)
            for unit_id in registry.units
            for leg in legs
        }
        # Normalise within the fault: the multipliers set the relative hazard
        # between units, and the fault still lands on its weight fleet-wide.
        total = sum(multipliers.values())
        for key, multiplier in multipliers.items():
            rates[key] = (weight * scale * multiplier) / (total * days)

    return rates


def sample_time(rng: random.Random, day: date) -> datetime:
    """Field work clusters in daylight shifts, not uniformly around the clock."""
    hour = rng.choices(
        population=list(range(6, 21)),
        weights=[2, 5, 8, 9, 9, 7, 6, 8, 9, 8, 6, 4, 3, 2, 1],
        k=1,
    )[0]
    return datetime.combine(day, time(hour, rng.randrange(0, 60)), tzinfo=timezone.utc)


def draw_events(registry: Registry, rng: random.Random, days: int, target: int, start: date) -> list[RawEvent]:
    rates = build_daily_rates(registry, days, target)
    events: list[RawEvent] = []
    forced: dict[int, list[tuple[str, str, str | None, int]]] = {}
    uid = 0

    for day_index in range(days):
        day = start + timedelta(days=day_index)

        scheduled = forced.pop(day_index, [])
        for unit_id, fault_id, leg, parent_uid in scheduled:
            uid += 1
            events.append(
                RawEvent(
                    uid=uid,
                    day_index=day_index,
                    at=sample_time(rng, day),
                    unit_id=unit_id,
                    fault_id=fault_id,
                    leg=leg,
                    part_id=FAULT_PARTS[fault_id].format(leg=leg),
                    forced=True,
                    parent_uid=parent_uid,
                )
            )

        for (unit_id, fault_id, leg), rate in rates.items():
            if rng.random() >= rate:
                continue
            uid += 1
            event = RawEvent(
                uid=uid,
                day_index=day_index,
                at=sample_time(rng, day),
                unit_id=unit_id,
                fault_id=fault_id,
                leg=leg,
                part_id=FAULT_PARTS[fault_id].format(leg=leg),
            )
            events.append(event)

        # Decide outcomes for everything raised today, because a failed fix
        # is what schedules the next occurrence.
        for event in [e for e in events if e.day_index == day_index and not e.payload]:
            _resolve_outcome(event, rng, days, forced)

    events.sort(key=lambda e: (e.at, e.uid))
    for index, event in enumerate(events, start=1):
        event.incident_id = f"inc-{index:04d}"
    return events


def _resolve_outcome(
    event: RawEvent,
    rng: random.Random,
    days: int,
    forced: dict[int, list[tuple[str, str, str | None, int]]],
) -> None:
    used_threadlocker: bool | None = None

    if event.fault_id == "hip_bolts_loose":
        # Pattern 3: the fix itself decides whether this comes back.
        progress = event.day_index / max(1, days - 1)
        p_threadlocker = THREADLOCKER_START + (THREADLOCKER_END - THREADLOCKER_START) * progress
        used_threadlocker = rng.random() < p_threadlocker
        failure_rate = THREADLOCKER_FAILURE_RATE if used_threadlocker else PLAIN_RETIGHTEN_FAILURE_RATE
        failed = rng.random() < failure_rate
        gap = rng.randint(*RECURRENCE_DAYS_BOLTS)
    else:
        failed = rng.random() < BASE_FAILURE_RATE
        gap = rng.randint(*RECURRENCE_DAYS_OTHER)

    recurred_after = None
    if failed:
        next_day = event.day_index + gap
        if next_day < days:
            recurred_after = gap
            forced.setdefault(next_day, []).append(
                (event.unit_id, event.fault_id, event.leg, event.uid)
            )
        else:
            # It would have come back after the window closed; the fix still
            # did not hold, so the outcome stays a failure.
            recurred_after = None

    event.payload = {
        "outcome": "failure" if failed else "success",
        "recurred_after_days": recurred_after,
        "used_threadlocker": used_threadlocker,
    }


def build_incident(
    registry: Registry,
    rng: random.Random,
    event: RawEvent,
    parent_incident_id: str | None,
    telemetry_dir: Path,
) -> dict[str, Any]:
    unit = registry.unit(event.unit_id)
    part_name = registry.part_name(event.part_id)
    # Only motors carry a per-unit lot; a foot pad legitimately has none.
    supplier_lot = registry.supplier_lot(event.unit_id, event.part_id)
    knee_lot = registry.supplier_lot(event.unit_id, f"{event.leg}.calf.motor") if event.leg else None

    severity = round(min(0.98, rng.uniform(0.15, 0.92) + (0.12 if event.forced else 0.0)), 3)
    window = telemetry_mod.simulate(event.fault_id, severity, rng)
    telemetry_mod.write_csv(window, telemetry_dir / f"{event.incident_id}.csv")

    summary = window.summary()
    reading = f"{window.signal} {window.peak:.3f} {window.unit}, threshold {window.threshold:.3f}"
    what_went_wrong = WHAT_WENT_WRONG[event.fault_id].format(part=part_name) + f" ({reading})."

    anomaly: dict[str, Any] = {
        "type": "anomaly",
        "unit_id": event.unit_id,
        "part_id": event.part_id,
        "signal": window.signal,
        "value": round(window.peak, 4),
        "threshold": round(window.threshold, 4),
        "t_sim": summary["t_cross_s"],
        "context": "stand/crouch cycle",
        "fault_signature": window.fault_signature,
    }
    if window.unit == "rad":
        # Section 5.1's event shape names the radian fields explicitly.
        anomaly["value_rad"] = anomaly["value"]
        anomaly["threshold_rad"] = anomaly["threshold"]

    tech = rng.choice(TECHS)
    persona = rng.choice(PERSONAS)
    mention_lot = supplier_lot is not None and rng.random() < LOT_MENTION_RATE
    wrong_guess = rng.random() < WRONG_GUESS_RATE
    transcript = build_note(
        rng,
        fault_id=event.fault_id,
        leg=event.leg,
        persona=persona,
        supplier_lot=supplier_lot,
        mention_lot=mention_lot,
        used_threadlocker=bool(event.payload.get("used_threadlocker")),
        wrong_guess=wrong_guess,
    )

    procedure_id, step_id = FAULT_PROCEDURE[event.fault_id]

    return {
        "incident_id": event.incident_id,
        "unit_id": event.unit_id,
        "site": unit["site"],
        "ambient_class": unit["ambient_class"],
        "timestamp": event.at.isoformat(),
        "day_index": event.day_index,
        "fault_id": event.fault_id,
        "part_id": event.part_id,
        "part_name": part_name,
        "leg": event.leg,
        "severity": severity,
        # The lot fitted to the failed part, copied from the registry so
        # mining can join on it. For a knee fault these are the same value.
        "supplier_lot": supplier_lot,
        "knee_supplier_lot": knee_lot,
        "synthetic": True,
        "what_went_wrong": what_went_wrong,
        "anomaly": anomaly,
        "telemetry": {**summary, "csv": f"telemetry/{event.incident_id}.csv"},
        "capture": {
            "tech": tech,
            "persona": persona,
            "procedure_id": procedure_id,
            "step_id": step_id,
            "transcript": transcript,
            "mentioned_lot": mention_lot,
            "wrong_guess": wrong_guess,
            "used_threadlocker": event.payload.get("used_threadlocker"),
        },
        "outcome": event.payload["outcome"],
        "recurred_after_days": event.payload["recurred_after_days"],
        "recurrence_of": parent_incident_id,
    }


async def attach_repair_records(incidents: list[dict[str, Any]], llm, concurrency: int) -> None:
    """Run each note through the real extractor, so the dataset exercises the pipeline."""
    from server.models import IncidentContext

    semaphore = asyncio.Semaphore(concurrency)

    async def one(incident: dict[str, Any]) -> None:
        context = IncidentContext(
            incident_id=incident["incident_id"],
            unit_id=incident["unit_id"],
            part_id=incident["part_id"],
            site=incident["site"],
            signal=incident["anomaly"]["signal"],
            what_went_wrong=incident["what_went_wrong"],
            fault_signature=incident["anomaly"]["fault_signature"],
        )
        async with semaphore:
            record = await llm.extract(context, incident["capture"]["transcript"])
        incident["repair_record"] = record.model_dump(mode="json")

    await asyncio.gather(*(one(incident) for incident in incidents))


def build_ground_truth(incidents: list[dict[str, Any]], registry: Registry, args, start: date, end: date) -> dict[str, Any]:
    """The answer key: what was planted, and what actually came out."""
    knee = [i for i in incidents if i["fault_id"] in KNEE_FAULTS]
    knee_lot_b_hot = [i for i in knee if i["ambient_class"] == "hot" and i["knee_supplier_lot"] == "B"]
    footpads = [i for i in incidents if i["fault_id"] == "foot_pad_worn"]
    bolts = [i for i in incidents if i["fault_id"] == "hip_bolts_loose"]
    bolts_locked = [i for i in bolts if i["capture"]["used_threadlocker"]]

    def rate_per_unit(subset: list[dict[str, Any]], unit_ids: set[str]) -> float:
        return round(len(subset) / max(1, len(unit_ids)), 4)

    hot_units = set(registry.units_in("hot"))
    temperate_units = set(registry.units_in("temperate"))
    phoenix_units = set(registry.units_at(PHOENIX))
    other_units = set(registry.units) - phoenix_units

    return {
        "seed": args.seed,
        "days": args.days,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "units": len(registry.units),
        "sites": len(registry.sites),
        "total_incidents": len(incidents),
        "note": "Answer key for verifying pattern discovery. Nothing in the pipeline reads this file.",
        "patterns": [
            {
                "id": "knee-lot-b-hot",
                "description": "Knee actuators from supplier lot B fail far more often at hot sites.",
                "planted_multiplier": LOT_B_HOT_MULTIPLIER,
                "applies_to": {"faults": list(KNEE_FAULTS), "supplier_lot": "B", "ambient_class": "hot"},
                "realized": {
                    "knee_incidents_total": len(knee),
                    "knee_incidents_lot_b_hot": len(knee_lot_b_hot),
                    "share_of_knee_incidents": round(len(knee_lot_b_hot) / max(1, len(knee)), 3),
                },
            },
            {
                "id": "footpad-phoenix",
                "description": "Abrasive ground at phoenix-solar wears foot pads roughly twice as fast.",
                "planted_multiplier": PHOENIX_FOOTPAD_MULTIPLIER,
                "applies_to": {"faults": ["foot_pad_worn"], "site": PHOENIX},
                "realized": {
                    "footpad_incidents_total": len(footpads),
                    "phoenix_per_unit": rate_per_unit([i for i in footpads if i["site"] == PHOENIX], phoenix_units),
                    "elsewhere_per_unit": rate_per_unit([i for i in footpads if i["site"] != PHOENIX], other_units),
                },
            },
            {
                "id": "hipbolts-threadlocker",
                "description": "Hip bolts retightened without threadlocker back off and the fault returns; with threadlocker it holds.",
                "applies_to": {"faults": ["hip_bolts_loose"]},
                "realized": {
                    "bolt_incidents_total": len(bolts),
                    "fixed_with_threadlocker": len(bolts_locked),
                    "threadlocker_failure_rate": round(
                        sum(1 for i in bolts_locked if i["outcome"] == "failure") / max(1, len(bolts_locked)), 3
                    ),
                    "plain_retighten_failure_rate": round(
                        sum(1 for i in bolts if not i["capture"]["used_threadlocker"] and i["outcome"] == "failure")
                        / max(1, len(bolts) - len(bolts_locked)),
                        3,
                    ),
                    "recurrences": sum(1 for i in incidents if i["recurrence_of"]),
                },
            },
        ],
        "confounders": {
            "hot_thermal_multiplier": HOT_THERMAL_MULTIPLIER,
            "hot_thermal_faults": list(HOT_THERMAL_FAULTS),
            "per_unit_usage_factor": "uncorrelated with the planted patterns",
            "hot_units": len(hot_units),
            "temperate_units": len(temperate_units),
        },
        "fault_weights": FAULT_WEIGHTS,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument(
        "--target",
        type=int,
        default=sum(FAULT_WEIGHTS.values()),
        help="expected first-occurrence incidents; recurrences land on top of this",
    )
    parser.add_argument("--window-end", default=None, help="ISO date the window ends (default: today)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument("--llm", action="store_true", help="write notes/records with Claude instead of the offline path")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument(
        "--skip-records",
        action="store_true",
        help="skip the extraction pass (no repair_record field) when the backend is unavailable",
    )
    args = parser.parse_args()

    registry = Registry.load(args.registry)
    rng = random.Random(args.seed)

    end = date.fromisoformat(args.window_end) if args.window_end else date.today()
    start = end - timedelta(days=args.days - 1)

    events = draw_events(registry, rng, args.days, args.target, start)
    by_uid = {event.uid: event for event in events}

    telemetry_dir = args.out / "telemetry"
    incidents = [
        build_incident(
            registry,
            rng,
            event,
            by_uid[event.parent_uid].incident_id if event.parent_uid else None,
            telemetry_dir,
        )
        for event in events
    ]

    if not args.skip_records:
        try:
            from server.integrations.llm import ClaudeGateway
        except ImportError as exc:  # the backend track's extractor is not on this branch yet
            raise SystemExit(
                f"cannot import the extractor ({exc}). Pass --skip-records to generate "
                "incidents without repair records, or merge the backend track first."
            ) from exc

        api_key = None
        model = "claude-sonnet-4-5"
        if args.llm:
            from server.config import get_settings

            settings = get_settings(REPO_ROOT)
            api_key, model = settings.anthropic_api_key, settings.anthropic_model
            if not api_key:
                raise SystemExit("--llm needs ANTHROPIC_API_KEY in .env")
        asyncio.run(attach_repair_records(incidents, ClaudeGateway(api_key, model), args.concurrency))

    args.out.mkdir(parents=True, exist_ok=True)
    incidents_path = args.out / "incidents.jsonl"
    with incidents_path.open("w") as stream:
        for incident in incidents:
            stream.write(json.dumps(incident) + "\n")

    ground_truth = build_ground_truth(incidents, registry, args, start, end)
    (args.out / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2) + "\n")

    print(f"wrote {incidents_path}  ({len(incidents)} incidents, {start} .. {end})")
    print(f"wrote {telemetry_dir}/  ({len(incidents)} CSVs)")
    print(f"wrote {args.out / 'ground_truth.json'}")


if __name__ == "__main__":
    main()
