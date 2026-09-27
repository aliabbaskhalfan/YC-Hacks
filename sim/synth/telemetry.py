"""Parametric telemetry for synthetic incidents (BUILD_SPEC.md Section 8.2).

Section 8.2 allows "a cheap parametric approximation if sim time is too
slow" instead of running the real MuJoCo rollout ~500 times. That is what
this is: each fault gets a signal shape that behaves the way its real
detector would see it, with an onset partway through an 8-second window and
a threshold crossing that has to be *sustained* before it counts — the same
0.4s dwell rule the live detector uses (Section 5.1).

Every window is generated fresh from a per-incident seed rather than cached
per severity bucket; at 240 samples an incident the whole fleet costs well
under a second, and fresh draws keep the CSVs from repeating.

Baselines are anchored to the numbers Section 5.1 reports as verified for
joint tracking error: healthy legs stay under ~0.23 rad, the alert fires at
0.35 rad, and a severe weak-knee fault peaks around 0.54 rad.

"Sustained for 0.4s" is implemented as a trailing 0.4s mean crossing the
threshold, not as a run of consecutive raw samples above it. Half these
signals are intrinsically bursty — oscillation energy, per-stance foot
slip, harness dropout spikes — and dip below threshold between bursts, so a
consecutive-sample rule would simply never fire on them however bad the
fault got. The window is also what makes the detector statistic linear in
the fault amplitude, which lets `simulate` solve for the amplitude that puts
the crossing exactly where the severity says it should be. Raw per-sample
series are still written to the CSV, so a stricter rule can be applied
downstream.
"""

from __future__ import annotations

import csv
import math
import random
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

DURATION_S = 8.0
SAMPLE_RATE_HZ = 30
SUSTAIN_S = 0.4  # Section 5.1: the signal must hold above threshold this long


@dataclass(frozen=True)
class SignalSpec:
    name: str
    unit: str
    threshold: float
    shape: str
    baseline_ratio: float = 0.30  # healthy level, as a fraction of threshold
    noise_ratio: float = 0.10  # noise sd, as a fraction of threshold


# Primary detection signal per fault, plus any corroborating signal the
# fault signature should carry (Section 5.2's detection column).
FAULT_SIGNALS: dict[str, tuple[SignalSpec, ...]] = {
    "knee_motor_weak": (
        SignalSpec("joint_tracking_error", "rad", 0.35, "step_plateau", 0.29, 0.10),
    ),
    "knee_motor_overheat": (
        SignalSpec("motor_temp_index", "index", 0.70, "thermal_ramp", 0.40, 0.05),
        SignalSpec("joint_tracking_error", "rad", 0.35, "thermal_ramp", 0.29, 0.10),
    ),
    "hip_bolts_loose": (
        SignalSpec("hip_oscillation_energy", "index", 0.18, "bursty_growth", 0.28, 0.14),
        SignalSpec("joint_tracking_error", "rad", 0.35, "bursty_growth", 0.30, 0.12),
    ),
    "foot_pad_worn": (
        SignalSpec("foot_slip_velocity", "m/s", 0.12, "stance_spikes", 0.25, 0.12),
    ),
    "encoder_drift": (
        SignalSpec("joint_angle_offset", "rad", 0.09, "linear_drift", 0.18, 0.08),
    ),
    "harness_intermittent": (
        SignalSpec("multi_joint_error_spike", "rad", 0.40, "dropout_spikes", 0.22, 0.09),
    ),
    "battery_sag": (
        SignalSpec("global_tracking_error", "rad", 0.28, "global_ramp", 0.35, 0.09),
    ),
    "imu_bias": (
        SignalSpec("body_roll_offset", "rad", 0.06, "step_offset", 0.25, 0.10),
    ),
}


@dataclass
class TelemetryWindow:
    fault_id: str
    signal: str
    unit: str
    threshold: float
    times: list[float]
    series: dict[str, list[float]] = field(default_factory=dict)
    detector: dict[str, list[float]] = field(default_factory=dict)
    t_cross: float | None = None
    peak: float = 0.0
    detector_peak: float = 0.0
    fault_onset_s: float = 0.0

    @property
    def fault_signature(self) -> dict[str, float]:
        """Top signals at their worst, for the anomaly event (Section 5.2)."""
        return {name: round(max(values), 4) for name, values in self.series.items()}

    def summary(self) -> dict[str, object]:
        return {
            "signal": self.signal,
            "unit": self.unit,
            "threshold": round(self.threshold, 4),
            "peak": round(self.peak, 4),
            "detector_peak": round(self.detector_peak, 4),
            "t_cross_s": round(self.t_cross, 3) if self.t_cross is not None else None,
            "fault_onset_s": round(self.fault_onset_s, 3),
            "duration_s": DURATION_S,
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "fault_signature": self.fault_signature,
        }


def _detector_target(threshold: float, severity: float) -> float:
    """Severity 0->just over threshold, 1->~1.9x it (0.54 rad for a knee, as in 5.1)."""
    return threshold * (1.08 + 0.85 * severity)


def _rolling_mean(values: list[float], window: int) -> list[float]:
    """Trailing mean, the way an online detector would actually compute it."""
    out: list[float] = []
    total = 0.0
    queue: deque[float] = deque()
    for value in values:
        queue.append(value)
        total += value
        if len(queue) > window:
            total -= queue.popleft()
        out.append(total / len(queue))
    return out


def _shape_value(shape: str, progress: float, rng: random.Random) -> float:
    """Fault contribution in 0..1 as a function of time since onset."""
    if shape == "step_plateau":
        return min(1.0, progress / 0.12) if progress < 0.12 else 1.0
    if shape == "thermal_ramp":
        # slow sigmoid: heat builds, it does not step
        return 1.0 / (1.0 + math.exp(-9.0 * (progress - 0.45)))
    if shape == "linear_drift":
        return min(1.0, progress * 1.15)
    if shape == "global_ramp":
        return min(1.0, progress * 1.05) ** 1.4
    if shape == "step_offset":
        return min(1.0, progress / 0.06) if progress < 0.06 else 1.0
    if shape == "bursty_growth":
        envelope = min(1.0, progress * 1.3)
        burst = 0.55 + 0.45 * math.sin(progress * 34.0)
        return envelope * burst
    if shape == "stance_spikes":
        envelope = min(1.0, 0.45 + progress * 0.8)
        # slip shows up during stance, so it spikes at the gait cadence
        phase = math.sin(progress * 26.0)
        spike = 1.0 if phase > 0.72 else 0.18 + 0.25 * max(0.0, phase)
        return envelope * spike
    if shape == "dropout_spikes":
        # random 50-200ms windows of lost torque -> simultaneous spikes
        return 1.0 if rng.random() < 0.16 else 0.12 + 0.2 * rng.random()
    raise ValueError(f"unknown telemetry shape: {shape}")


def simulate(fault_id: str, severity: float, rng: random.Random) -> TelemetryWindow:
    specs = FAULT_SIGNALS[fault_id]
    primary = specs[0]

    n_samples = int(DURATION_S * SAMPLE_RATE_HZ)
    times = [round(i / SAMPLE_RATE_HZ, 4) for i in range(n_samples)]
    window_samples = max(1, int(round(SUSTAIN_S * SAMPLE_RATE_HZ)))
    onset = rng.uniform(1.8, 3.6)

    window = TelemetryWindow(
        fault_id=fault_id,
        signal=primary.name,
        unit=primary.unit,
        threshold=primary.threshold,
        times=times,
        fault_onset_s=onset,
    )

    for spec in specs:
        baseline = spec.threshold * spec.baseline_ratio
        noise_sd = spec.threshold * spec.noise_ratio

        healthy = [max(0.0, baseline + rng.gauss(0.0, noise_sd)) for _ in times]
        shape = [
            _shape_value(spec.shape, (t - onset) / max(0.4, DURATION_S - onset), rng) if t >= onset else 0.0
            for t in times
        ]

        # The detector is a trailing mean, so it is linear in the fault
        # amplitude: solve once for the amplitude that lands the detector
        # peak on target instead of guessing and hoping it trips.
        smoothed_healthy = _rolling_mean(healthy, window_samples)
        smoothed_shape = _rolling_mean(shape, window_samples)
        peak_index = max(range(n_samples), key=lambda i: smoothed_shape[i])

        target = _detector_target(spec.threshold, severity)
        if spec is not primary:
            # Corroborating signals track the fault, but less definitively.
            target = spec.threshold * (0.92 + 0.62 * severity)
        headroom = smoothed_shape[peak_index]
        reach = max(0.0, (target - smoothed_healthy[peak_index]) / headroom) if headroom > 1e-9 else 0.0

        values = [round(max(0.0, healthy[i] + reach * shape[i]), 5) for i in range(n_samples)]
        window.series[spec.name] = values
        window.detector[spec.name] = [round(v, 5) for v in _rolling_mean(values, window_samples)]

    primary_values = window.series[primary.name]
    primary_detector = window.detector[primary.name]
    window.peak = max(primary_values)
    window.detector_peak = max(primary_detector)
    window.t_cross = next(
        (times[i] for i, value in enumerate(primary_detector) if value > primary.threshold),
        None,
    )
    return window


def write_csv(window: TelemetryWindow, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(window.series)
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["t_s", *columns])
        for index, t in enumerate(window.times):
            writer.writerow([t, *(window.series[name][index] for name in columns)])
